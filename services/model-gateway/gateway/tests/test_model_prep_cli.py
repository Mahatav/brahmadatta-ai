from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

from gateway.tools import model_prep


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_hash_artifact_records_size_and_sha256(tmp_path: Path) -> None:
    artifact = tmp_path / "tiny-model.gguf"
    artifact.write_bytes(b"not a real model; enough for a deterministic hash\n")
    output = tmp_path / "artifact.json"

    assert (
        model_prep.main(
            [
                "hash-artifact",
                "--artifact",
                str(artifact),
                "--model-name",
                "tiny-local-code-model",
                "--revision",
                "rev-1",
                "--quantization",
                "q4_K_M",
                "--output",
                str(output),
            ]
        )
        == model_prep.EXIT_OK
    )

    payload = _load(output)
    assert payload["kind"] == "model-artifact-manifest"
    assert payload["schema_version"] == model_prep.EVIDENCE_SCHEMA_VERSION
    assert payload["model"] == {
        "name": "tiny-local-code-model",
        "revision": "rev-1",
        "quantization": "q4_K_M",
    }
    artifact_record = payload["artifact"]
    assert artifact_record["bytes"] == artifact.stat().st_size
    assert artifact_record["sha256"] == model_prep._sha256_file(artifact)


def test_check_serving_blocks_hosted_provider(tmp_path: Path, capsys: Any) -> None:
    output = tmp_path / "serving.json"

    assert (
        model_prep.main(
            [
                "check-serving",
                "--endpoint",
                "https://api.openai.com/v1",
                "--output",
                str(output),
            ]
        )
        == model_prep.EXIT_BLOCKED
    )

    captured = capsys.readouterr()
    assert "blocked:" in captured.err
    assert not output.exists()


def test_check_serving_records_local_policy_rule(tmp_path: Path) -> None:
    output = tmp_path / "serving.json"

    assert (
        model_prep.main(
            [
                "check-serving",
                "--endpoint",
                "http://127.0.0.1:8080/v1",
                "--output",
                str(output),
            ]
        )
        == model_prep.EXIT_OK
    )

    serving = _load(output)["serving"]
    assert serving["local_only"] is True
    assert serving["policy_rule"] == "allowed-network"


def test_doctor_reports_missing_codellama_as_degraded(
    tmp_path: Path, monkeypatch: Any
) -> None:
    output = tmp_path / "doctor.json"

    monkeypatch.setattr(
        model_prep,
        "get_json",
        lambda url, timeout, **kwargs: {"models": [{"name": "llama3.2:latest"}]},
    )

    assert (
        model_prep.main(
            [
                "doctor",
                "--endpoint",
                "http://127.0.0.1:11434/api",
                "--output",
                str(output),
            ]
        )
        == model_prep.EXIT_BLOCKED
    )

    payload = _load(output)
    assert payload["kind"] == "ollama-codellama-doctor"
    assert payload["status"] == "model-missing"
    assert payload["checks"]["endpoint_reachable"] is True
    assert payload["checks"]["model_present"] is False
    assert payload["degraded_state"]["active"] is True
    assert "codellama:7b-instruct" in payload["message"]


def test_doctor_reports_codellama_ready(tmp_path: Path, monkeypatch: Any) -> None:
    output = tmp_path / "doctor.json"

    monkeypatch.setattr(
        model_prep,
        "get_json",
        lambda url, timeout, **kwargs: {"models": [{"model": "codellama:7b-instruct"}]},
    )

    assert (
        model_prep.main(
            [
                "doctor",
                "--endpoint",
                "http://127.0.0.1:11434/api",
                "--output",
                str(output),
            ]
        )
        == model_prep.EXIT_OK
    )

    payload = _load(output)
    assert payload["status"] == "ready"
    assert payload["checks"]["endpoint_reachable"] is True
    assert payload["checks"]["model_present"] is True
    assert payload["degraded_state"]["active"] is False


def test_doctor_sends_bearer_token_when_configured(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """D-075 / SEC-50. `--bearer-token` (or MODEL_HOST_BEARER_TOKEN in the
    environment) must reach `get_json` as the keyword the client turns into
    `Authorization: Bearer <token>` — the header the compose `model-host-auth`
    sidecar requires before it will proxy to Ollama at all.
    """
    output = tmp_path / "doctor.json"
    seen: dict[str, Any] = {}

    def fake_get_json(url: str, timeout: float, **kwargs: Any) -> dict[str, Any]:
        seen["bearer_token"] = kwargs.get("bearer_token")
        return {"models": [{"model": "codellama:7b-instruct"}]}

    monkeypatch.setattr(model_prep, "get_json", fake_get_json)

    assert (
        model_prep.main(
            [
                "doctor",
                "--endpoint",
                "http://model-host:11434/api",
                "--service-name",
                "model-host",
                "--bearer-token",
                "s3cr3t-token",
                "--output",
                str(output),
            ]
        )
        == model_prep.EXIT_OK
    )
    assert seen["bearer_token"] == "s3cr3t-token"


def test_doctor_falls_back_to_bearer_token_env_var(
    tmp_path: Path, monkeypatch: Any
) -> None:
    output = tmp_path / "doctor.json"
    seen: dict[str, Any] = {}

    def fake_get_json(url: str, timeout: float, **kwargs: Any) -> dict[str, Any]:
        seen["bearer_token"] = kwargs.get("bearer_token")
        return {"models": [{"model": "codellama:7b-instruct"}]}

    monkeypatch.setattr(model_prep, "get_json", fake_get_json)
    monkeypatch.setenv("MODEL_HOST_BEARER_TOKEN", "from-the-environment")

    assert (
        model_prep.main(
            [
                "doctor",
                "--endpoint",
                "http://model-host:11434/api",
                "--service-name",
                "model-host",
                "--output",
                str(output),
            ]
        )
        == model_prep.EXIT_OK
    )
    assert seen["bearer_token"] == "from-the-environment"


class _FakeChatResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> _FakeChatResponse:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _fake_ollama_chat_success(request: Any, timeout: float) -> _FakeChatResponse:
    body = json.dumps(
        {
            "message": {
                "content": json.dumps(
                    {
                        "diff": "--- a/x.c\n+++ b/x.c\n",
                        "rationale": "ok",
                        "touched_files": [],
                        "confidence": 0.5,
                    }
                )
            },
            "eval_count": 1,
        }
    ).encode("utf-8")
    return _FakeChatResponse(body)


def _fake_ollama_insufficient_memory(request: Any, timeout: float) -> None:
    body = json.dumps(
        {"error": "model requires more system memory (8.4 GiB) than is available (7.7 GiB)"}
    ).encode("utf-8")
    raise HTTPError(request.full_url, 500, "Internal Server Error", None, io.BytesIO(body))


def test_doctor_check_memory_passes_when_generation_succeeds(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """#298: `--check-memory` is opt-in real proof the model actually loads and
    generates inside the memory this container was given, not just that Ollama's
    HTTP endpoint answers and the model name is present."""
    output = tmp_path / "doctor.json"
    monkeypatch.setattr(
        model_prep,
        "get_json",
        lambda url, timeout, **kwargs: {"models": [{"model": "codellama:7b-instruct"}]},
    )
    monkeypatch.setattr("gateway.client.urlopen", _fake_ollama_chat_success)

    assert (
        model_prep.main(
            [
                "doctor",
                "--endpoint",
                "http://127.0.0.1:11434/api",
                "--check-memory",
                "--output",
                str(output),
            ]
        )
        == model_prep.EXIT_OK
    )

    payload = _load(output)
    assert payload["status"] == "ready"
    assert payload["checks"]["model_fits_memory"] is True


def test_doctor_check_memory_reports_insufficient_memory_clearly(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """#298's actual regression guard at the CLI/operator layer: the exact live
    failure (a real HTTP 500, Ollama's own "requires more system memory" wording)
    must come out of `doctor --check-memory` as a clear, actionable
    'insufficient-memory' status — caught here, before a mission ever runs — not
    surface for the first time as an opaque failure mid-PATCH_GENERATE."""
    output = tmp_path / "doctor.json"
    monkeypatch.setattr(
        model_prep,
        "get_json",
        lambda url, timeout, **kwargs: {"models": [{"model": "codellama:7b-instruct"}]},
    )
    monkeypatch.setattr("gateway.client.urlopen", _fake_ollama_insufficient_memory)

    assert (
        model_prep.main(
            [
                "doctor",
                "--endpoint",
                "http://127.0.0.1:11434/api",
                "--check-memory",
                "--output",
                str(output),
            ]
        )
        == model_prep.EXIT_BLOCKED
    )

    payload = _load(output)
    assert payload["status"] == "insufficient-memory"
    assert payload["checks"]["model_fits_memory"] is False
    assert "8.4 GiB" in payload["message"]
    assert "7.7 GiB" in payload["message"]
    assert "MODEL_HOST_MEM_LIMIT" in payload["message"]
    assert payload["degraded_state"]["active"] is True
    assert "MODEL_HOST_MEM_LIMIT" in payload["degraded_state"]["reason"]


def test_doctor_without_check_memory_flag_leaves_model_fits_memory_unchecked(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """The default, fast doctor run (no `--check-memory`) must not make any
    generation call at all -- `model_fits_memory` stays explicitly `None`
    ("not checked"), not `True` (which would be a false all-clear) or `False`."""
    output = tmp_path / "doctor.json"
    monkeypatch.setattr(
        model_prep,
        "get_json",
        lambda url, timeout, **kwargs: {"models": [{"model": "codellama:7b-instruct"}]},
    )

    assert (
        model_prep.main(
            [
                "doctor",
                "--endpoint",
                "http://127.0.0.1:11434/api",
                "--output",
                str(output),
            ]
        )
        == model_prep.EXIT_OK
    )

    payload = _load(output)
    assert payload["status"] == "ready"
    assert payload["checks"]["model_fits_memory"] is None


def test_fake_measure_goes_through_gateway_and_emits_evidence(tmp_path: Path) -> None:
    output = tmp_path / "measurement.json"

    assert (
        model_prep.main(
            [
                "measure",
                "--backend",
                "fake",
                "--endpoint",
                "http://127.0.0.1:8080/v1",
                "--fake-cold-start-ms",
                "11",
                "--fake-first-token-ms",
                "222",
                "--fake-wall-time-ms",
                "4000",
                "--fake-output-tokens",
                "100",
                "--output",
                str(output),
            ]
        )
        == model_prep.EXIT_OK
    )

    payload = _load(output)
    assert payload["kind"] == "model-measurement"
    assert payload["backend"] == "fake"
    measurement = payload["measurement"]
    assert measurement["cold_start_ms"] == 11
    assert measurement["first_token_ms"] == 222
    assert measurement["wall_time_ms"] == 4000
    assert measurement["output_tokens"] == 100
    assert measurement["throughput_tokens_per_sec"] == 25.0
    assert "no model was loaded" in str(measurement["mode"])
    assert payload["model"]["artifact_sha256"] == "b" * 64
    assert payload["prompt"]["response_schema_version"] == "patch-candidate/1"


def test_attempts_records_threshold_and_candidate_hashes(tmp_path: Path) -> None:
    output = tmp_path / "attempts.json"

    assert (
        model_prep.main(
            [
                "attempts",
                "--backend",
                "fake",
                "--attempts",
                "3",
                "--success-threshold",
                "2",
                "--endpoint",
                "http://127.0.0.1:8080/v1",
                "--seed",
                "90",
                "--output",
                str(output),
            ]
        )
        == model_prep.EXIT_OK
    )

    payload = _load(output)
    assert payload["kind"] == "model-generation-attempts"
    assert payload["gate"] == {
        "required_attempts": 3,
        "success_threshold": 2,
        "schema_valid_successes": 3,
        "passed": True,
        "status": "3 of 3 attempts returned schema-valid patch candidates",
    }
    assert [attempt["seed"] for attempt in payload["attempts"]] == [90, 91, 92]
    assert all(attempt["candidate_sha256"] for attempt in payload["attempts"])
    assert all(attempt["compile_status"] == "NOT_RUN" for attempt in payload["attempts"])


def test_ollama_measure_records_codellama_stream_evidence(
    tmp_path: Path, monkeypatch: Any
) -> None:
    output = tmp_path / "measurement.json"
    seen: dict[str, Any] = {}

    def fake_iter_response_lines(url: str, payload: dict[str, Any], timeout: float, **kwargs: Any):
        seen["url"] = url
        seen["payload"] = payload
        yield json.dumps(
            {
                "message": {
                    "content": (
                        '{"diff":"--- a/src/parse.c\\n+++ b/src/parse.c\\n@@\\n-a\\n+b\\n",'
                    )
                },
                "done": False,
            }
        )
        yield json.dumps(
            {
                "message": {
                    "content": (
                        '"rationale":"Bounds check.","touched_files":["src/parse.c"],'
                        '"confidence":0.52}'
                    )
                },
                "done": False,
            }
        )
        yield json.dumps({"done": True, "eval_count": 64, "eval_duration": 2_000_000_000})

    monkeypatch.setattr(model_prep, "iter_response_lines", fake_iter_response_lines)

    assert (
        model_prep.main(
            [
                "measure",
                "--backend",
                "ollama",
                "--endpoint",
                "http://127.0.0.1:11434/api",
                "--output",
                str(output),
            ]
        )
        == model_prep.EXIT_OK
    )

    assert seen["url"] == "http://127.0.0.1:11434/api/chat"
    assert seen["payload"]["model"] == "codellama:7b-instruct"
    assert seen["payload"]["stream"] is True
    payload = _load(output)
    assert payload["backend"] == "ollama-codellama-stream"
    assert payload["serving"]["local_only"] is True
    assert payload["model"]["name"] == "codellama:7b-instruct"
    measurement = payload["measurement"]
    assert measurement["output_stream_chunks"] == 2
    assert measurement["observed_output_chars"] > 0
    assert measurement["ollama_eval_count"] == 64
    assert measurement["parsed_patch_candidate"] is True
    assert measurement["parse_error"] == ""


def test_plan_prints_exact_operator_command_shape(capsys: Any) -> None:
    assert model_prep.main(["plan", "--evidence-dir", "evidence/d4-model"]) == 0

    captured = capsys.readouterr()
    assert "ollama pull codellama:7b-instruct" in captured.out
    assert "http://127.0.0.1:11434/api" in captured.out
    assert "hash-artifact" in captured.out
    assert "model-doctor.json" in captured.out
    assert "check-serving" in captured.out
    assert "measure --backend ollama" in captured.out
    assert "evidence/d4-model/model-measurement.json" in captured.out
