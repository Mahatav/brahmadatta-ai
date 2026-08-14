"""Ollama-backed local inference for D5.

This module is deliberately small and boring: it speaks to Ollama's local HTTP API,
requires the same gateway endpoint policy as every other live backend, and returns the
same `PatchCandidate` shape the replay path uses. It does not pull models. The operator
does that explicitly with `ollama pull codellama:7b-instruct`.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

from pydantic import ValidationError

from gateway.client import post_json
from gateway.errors import LiveGenerationError
from gateway.schemas import GenerationRequest, PatchCandidate

DEFAULT_OLLAMA_ENDPOINT = "http://127.0.0.1:11434/api"
DEFAULT_CODELLAMA_MODEL = "codellama:7b-instruct"
CODELLAMA_REVISION = "ollama-library/codellama"


@dataclass(frozen=True)
class OllamaCodeLlamaBackend:
    """Live backend for a local Ollama CodeLlama server."""

    endpoint: str = DEFAULT_OLLAMA_ENDPOINT
    model_name: str = DEFAULT_CODELLAMA_MODEL
    model_revision: str = CODELLAMA_REVISION
    model_artifact_sha256: str = ""
    timeout_sec: float = 300.0

    @property
    def served_from(self) -> str:
        return self.endpoint

    def generate(self, request: GenerationRequest) -> tuple[PatchCandidate, int, int | None]:
        started = time.perf_counter_ns()
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Brahmadatta's local patch generator. Return only JSON "
                        "with keys diff, rationale, touched_files, confidence. diff must "
                        "be a unified diff."
                    ),
                },
                {"role": "user", "content": request.prompt},
            ],
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_output_tokens,
            },
        }
        if request.seed is not None:
            payload["options"]["seed"] = request.seed

        response = post_json(_endpoint_url(self.endpoint, "chat"), payload, self.timeout_sec)
        wall_time_ms = int((time.perf_counter_ns() - started) / 1_000_000)
        content = _ollama_message_content(response)
        output_tokens = response.get("eval_count")
        return (
            patch_candidate_from_model_text(content),
            wall_time_ms,
            output_tokens if isinstance(output_tokens, int) else None,
        )


def patch_candidate_from_model_text(text: str) -> PatchCandidate:
    """Parse the constrained JSON object expected from CodeLlama."""

    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise LiveGenerationError(
                "Ollama CodeLlama response did not contain a JSON patch candidate.",
                details={"response_preview": text[:500]},
            ) from None
        try:
            raw = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LiveGenerationError(
                "Ollama CodeLlama response contained malformed JSON.",
                details={"response_preview": text[start : end + 1][:500]},
            ) from exc

    try:
        return PatchCandidate.model_validate(raw)
    except ValidationError as exc:
        raise LiveGenerationError(
            "Ollama CodeLlama response did not match PatchCandidate.",
            details={"errors": exc.errors()},
        ) from exc


def _endpoint_url(endpoint: str, route: str) -> str:
    return urljoin(endpoint.rstrip("/") + "/", route.lstrip("/"))


def _ollama_message_content(response: dict[str, Any]) -> str:
    message = response.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"]
    if isinstance(response.get("response"), str):
        return response["response"]
    raise LiveGenerationError(
        "Ollama response did not include message.content.",
        details={"response_keys": sorted(str(key) for key in response)},
    )
