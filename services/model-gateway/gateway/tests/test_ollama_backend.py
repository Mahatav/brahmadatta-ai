from __future__ import annotations

import io
import json
from typing import Any
from urllib.error import HTTPError

import pytest

from gateway.errors import LiveGenerationError
from gateway.ollama import (
    DEFAULT_CODELLAMA_MODEL,
    DEFAULT_OLLAMA_ENDPOINT,
    DEFAULT_OLLAMA_KEEP_ALIVE,
    DEFAULT_OLLAMA_TIMEOUT_SECONDS,
    OllamaCodeLlamaBackend,
    patch_candidate_from_model_text,
)
from gateway.schemas import GenerationRequest


def _ollama_http_error(status: int, body: dict[str, Any], *, reason: str = "Internal Server Error") -> HTTPError:
    payload = json.dumps(body).encode("utf-8")
    return HTTPError("http://127.0.0.1:11434/api/chat", status, reason, None, io.BytesIO(payload))


class FakeHTTPResponse:
    def __init__(self, body: dict[str, Any]) -> None:
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self) -> FakeHTTPResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def _make_fake_urlopen(seen: dict[str, Any]) -> Any:
    def fake_urlopen(request: Any, timeout: float) -> FakeHTTPResponse:
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        seen["authorization"] = request.get_header("Authorization")
        return FakeHTTPResponse(
            {
                "message": {
                    "content": json.dumps(
                        {
                            "diff": "--- a/src/parse.c\n+++ b/src/parse.c\n@@\n-a\n+b\n",
                            "rationale": "Bounds check.",
                            "touched_files": ["src/parse.c"],
                            "confidence": 0.57,
                        }
                    )
                },
                "eval_count": 42,
            }
        )

    return fake_urlopen


def test_ollama_backend_posts_to_local_chat_and_parses_patch(
    monkeypatch: pytest.MonkeyPatch,
    request_: GenerationRequest,
) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr("gateway.client.urlopen", _make_fake_urlopen(seen))

    candidate, wall_time_ms, output_tokens = OllamaCodeLlamaBackend().generate(request_)

    assert seen["url"] == f"{DEFAULT_OLLAMA_ENDPOINT}/chat"
    assert seen["payload"]["model"] == DEFAULT_CODELLAMA_MODEL
    assert seen["payload"]["stream"] is False
    assert seen["payload"]["options"]["temperature"] == request_.temperature
    assert "Return only JSON" in seen["payload"]["messages"][0]["content"]
    assert candidate.touched_files == ("src/parse.c",)
    assert candidate.confidence == 0.57
    assert wall_time_ms >= 0
    assert output_tokens == 42


def test_ollama_backend_sends_no_authorization_header_when_no_token_configured(
    monkeypatch: pytest.MonkeyPatch,
    request_: GenerationRequest,
) -> None:
    """The default shape: a bare `ollama serve` on loopback has no auth of any kind
    to send. Sending `Authorization: Bearer ` (empty) rather than omitting the header
    entirely would be a different, wrong claim.
    """
    seen: dict[str, Any] = {}
    monkeypatch.setattr("gateway.client.urlopen", _make_fake_urlopen(seen))

    OllamaCodeLlamaBackend().generate(request_)

    assert seen["authorization"] is None


def test_ollama_backend_sends_bearer_token_when_configured(
    monkeypatch: pytest.MonkeyPatch,
    request_: GenerationRequest,
) -> None:
    """D-075 / SEC-50: the compose `model-host-auth` sidecar rejects every request
    without exactly this header — this is the assertion that the Ollama backend
    actually sends it when a token is configured, not merely that the field exists.
    """
    seen: dict[str, Any] = {}
    monkeypatch.setattr("gateway.client.urlopen", _make_fake_urlopen(seen))

    OllamaCodeLlamaBackend(bearer_token="s3cr3t-token").generate(request_)

    assert seen["authorization"] == "Bearer s3cr3t-token"


def test_ollama_backend_sends_keep_alive_by_default(
    monkeypatch: pytest.MonkeyPatch,
    request_: GenerationRequest,
) -> None:
    """D-123/D-125: the confirmed-live cold-load cost (~60s -> ~0.01s warm) is only
    avoidable between calls if the model is told to stay resident. Before this fix
    nothing set `keep_alive` at all, so Ollama's own 5-minute default applied and the
    model was observed getting evicted between PATCH_GENERATE attempts."""
    seen: dict[str, Any] = {}
    monkeypatch.setattr("gateway.client.urlopen", _make_fake_urlopen(seen))

    OllamaCodeLlamaBackend().generate(request_)

    assert seen["payload"]["keep_alive"] == DEFAULT_OLLAMA_KEEP_ALIVE


def test_ollama_backend_keep_alive_is_overridable_and_omittable(
    monkeypatch: pytest.MonkeyPatch,
    request_: GenerationRequest,
) -> None:
    """A caller that wants to measure cold-load behavior on purpose (tests,
    `model_prep.py`) must be able to turn this back off rather than being forced onto
    the generous default."""
    seen: dict[str, Any] = {}
    monkeypatch.setattr("gateway.client.urlopen", _make_fake_urlopen(seen))

    OllamaCodeLlamaBackend(keep_alive="10m").generate(request_)
    assert seen["payload"]["keep_alive"] == "10m"

    seen.clear()
    OllamaCodeLlamaBackend(keep_alive="").generate(request_)
    assert "keep_alive" not in seen["payload"]


def test_ollama_backend_default_timeout_matches_the_named_constant() -> None:
    """D-123: `gateway.settings.GatewaySettings.model_host_timeout_seconds` and this
    dataclass field must agree on what "unset" means, or the single-source-of-truth
    fix is only true for callers that go through settings."""
    assert OllamaCodeLlamaBackend().timeout_sec == DEFAULT_OLLAMA_TIMEOUT_SECONDS
    assert DEFAULT_OLLAMA_TIMEOUT_SECONDS == 300.0


def test_ollama_backend_surfaces_actionable_error_on_memory_capacity_failure(
    monkeypatch: pytest.MonkeyPatch,
    request_: GenerationRequest,
) -> None:
    """#298, live-observed: Ollama refuses to load `codellama:7b-instruct` with a real
    HTTP 500 because the model-host container's actual memory is smaller than the
    model needs. Before this fix, this reached `PATCH_GENERATE` as an opaque
    "did not respond" transport error deep inside a live generation call — this test
    is the regression guard that the failure is now a clear, actionable
    `LiveGenerationError` instead: it names the model, the required and available
    amounts, states plainly that a retry will not help, and points at the one compose
    knob (`MODEL_HOST_MEM_LIMIT`) an operator would actually check.
    """

    def fake_urlopen(request: Any, timeout: float) -> Any:
        raise _ollama_http_error(
            500,
            {"error": "model requires more system memory (8.4 GiB) than is available (7.7 GiB)"},
        )

    monkeypatch.setattr("gateway.client.urlopen", fake_urlopen)

    with pytest.raises(LiveGenerationError) as excinfo:
        OllamaCodeLlamaBackend().generate(request_)

    message = str(excinfo.value)
    assert "8.4 GiB" in message
    assert "7.7 GiB" in message
    assert "MODEL_HOST_MEM_LIMIT" in message
    assert DEFAULT_CODELLAMA_MODEL in message
    assert "retrying will not help" in message

    assert excinfo.value.details["capacity_error"] is True
    assert excinfo.value.details["model_required"] == "8.4 GiB"
    assert excinfo.value.details["model_available"] == "7.7 GiB"
    assert excinfo.value.details["model_name"] == DEFAULT_CODELLAMA_MODEL
    # The original, now-surfaced Ollama detail (#298's `gateway.client` fix) is still
    # present underneath the friendlier message, not thrown away a second time.
    assert excinfo.value.details["http_status"] == 500


def test_ollama_backend_does_not_rewrite_unrelated_server_errors(
    monkeypatch: pytest.MonkeyPatch,
    request_: GenerationRequest,
) -> None:
    """The capacity-specific rewrap must only fire for the one specific, recognised
    Ollama wording — every other server error still reaches the caller as the
    (#298-fixed, now body-surfacing) generic `LiveGenerationError`, unrewritten."""

    def fake_urlopen(request: Any, timeout: float) -> Any:
        raise _ollama_http_error(500, {"error": "an unrelated ollama failure"})

    monkeypatch.setattr("gateway.client.urlopen", fake_urlopen)

    with pytest.raises(LiveGenerationError, match="an unrelated ollama failure") as excinfo:
        OllamaCodeLlamaBackend().generate(request_)

    assert "capacity_error" not in excinfo.value.details


def test_ollama_candidate_parser_accepts_json_inside_text() -> None:
    candidate = patch_candidate_from_model_text(
        "Here is the patch:\n"
        '{"diff":"--- a/x.c\\n+++ b/x.c\\n@@\\n-a\\n+b\\n","rationale":"small",'
        '"touched_files":["x.c"],"confidence":0.4}'
    )

    assert candidate.touched_files == ("x.c",)
    assert candidate.rationale == "small"


def test_ollama_candidate_parser_rejects_unstructured_text() -> None:
    with pytest.raises(LiveGenerationError, match="JSON patch candidate"):
        patch_candidate_from_model_text("I would probably edit parse.c.")


def test_ollama_candidate_parser_schema_mismatch_details_never_carry_raw_secrets() -> None:
    """#258: `PatchCandidate.model_validate` failing on a model response used to store
    `exc.errors()` unfiltered in `LiveGenerationError.details` — including each failing
    field's actual value (`errors()["input"]`) and, for a forbidden-extra-field
    rejection, the extra field's own key name verbatim in `loc`. `details` is not
    logged anywhere today, but the same #229 discipline `api/sse.py::safe_to_schema`
    applies should hold here too, latent or not.

    A secret-shaped model response is exactly the realistic trigger: CodeLlama
    hallucinating or echoing something that looks like a credential into a field this
    schema forbids.
    """
    secret_value = "sk-live-SUPER-SECRET-should-never-reach-details-abc123"
    secret_key = "sk-live-SOME-SECRET-999"

    with pytest.raises(LiveGenerationError) as excinfo:
        patch_candidate_from_model_text(
            json.dumps(
                {
                    "diff": "--- a/x.c\n+++ b/x.c\n",
                    "rationale": "ok",
                    "touched_files": [],
                    # wrong type -> a real ValidationError entry whose "input" is the
                    # secret-shaped value itself.
                    "confidence": secret_value,
                    # forbidden extra field whose *key name* is secret-shaped.
                    secret_key: "y",
                }
            )
        )

    details_text = repr(excinfo.value.details)
    assert secret_value not in details_text
    assert secret_key not in details_text

    # still diagnostically useful: which field, which kind of mismatch.
    errors = excinfo.value.details["errors"]
    assert any(e["loc"] == ("confidence",) for e in errors)
    assert any("<redacted secret-shaped segment>" in e["loc"] for e in errors)
