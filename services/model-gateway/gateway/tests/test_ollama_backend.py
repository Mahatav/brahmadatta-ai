from __future__ import annotations

import json
from typing import Any

import pytest

from gateway.errors import LiveGenerationError
from gateway.ollama import (
    DEFAULT_CODELLAMA_MODEL,
    DEFAULT_OLLAMA_ENDPOINT,
    OllamaCodeLlamaBackend,
    patch_candidate_from_model_text,
)
from gateway.schemas import GenerationRequest


class FakeHTTPResponse:
    def __init__(self, body: dict[str, Any]) -> None:
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self) -> FakeHTTPResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def test_ollama_backend_posts_to_local_chat_and_parses_patch(
    monkeypatch: pytest.MonkeyPatch,
    request_: GenerationRequest,
) -> None:
    seen: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float) -> FakeHTTPResponse:
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        seen["payload"] = json.loads(request.data.decode("utf-8"))
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

    monkeypatch.setattr("gateway.client.urlopen", fake_urlopen)

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
