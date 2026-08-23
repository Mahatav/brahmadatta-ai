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

#: D-123 (.project/decisions.md): this used to be the ONLY place this number lived —
#: `infrastructure/compose/nginx/model-host-auth/templates/model-host-auth.conf.template`
#: hardcoded its own, separately-maintained `300s`, and the two only matched by
#: coincidence (the template's own comment said exactly that). Confirmed live: raising
#: the client timeout alone did nothing, because the proxy independently re-capped
#: every call at its own 300s and returned a 504 instead. `gateway.settings.
#: GatewaySettings.model_host_timeout_seconds` (read from the `MODEL_HOST_TIMEOUT_
#: SECONDS` env var) is now the one source of truth for a caller that goes through
#: `_build_live_backend`/settings; this constant remains the dataclass field's own
#: default for a caller that constructs this class directly (tests, `model_prep.py`'s
#: CLI, a bare `ollama serve` with no settings object at all) so behavior is
#: unchanged for those callers too. The VALUE itself (300s) is deliberately not
#: changed here — D-123 found real evidence the real ceiling needs re-measuring after
#: a separate memory-capacity question is resolved (Mahatav's call, not this one).
DEFAULT_OLLAMA_TIMEOUT_SECONDS = 300.0

#: D-123: a cold model load costs ~60s (`load_duration` in Ollama's own response); a
#: warm repeat costs ~0.01s. Ollama's own default `keep_alive` (unset here before this
#: fix) is 5 minutes, and D-123 observed the model getting evicted between attempts in
#: real testing — so a mission's PATCH_GENERATE attempts (there can be several per
#: mission, `MissionPolicy.patch_generation_attempts`) could each separately re-pay
#: the cold-load cost. Set as a per-request field (not `OLLAMA_KEEP_ALIVE` on the
#: `model-host` container) — see this repo's `.project/decisions.md` D-124 for the
#: decision record on why. "30m" is generous relative to the gap between attempts in
#: one mission (each attempt itself is capped at `timeout_sec`, comfortably under this)
#: while still letting Ollama reclaim the model between missions rather than pinning it
#: in memory forever, which would work against — not sidestep — D-123's separate,
#: not-yet-resolved memory-pressure finding.
DEFAULT_OLLAMA_KEEP_ALIVE = "30m"


@dataclass(frozen=True)
class OllamaCodeLlamaBackend:
    """Live backend for a local Ollama CodeLlama server.

    `bearer_token` is D-075 / SEC-50: when the compose `model-host` profile is in use,
    Ollama itself is bound to loopback only inside its own container, and a bearer-
    token-checking nginx sidecar (`model-host-auth`, `network_mode:
    "service:model-host"`) is the only thing that can still reach it — so requests
    through `backend` (the compose network, e.g. `endpoint="http://model-host:11434"`)
    now need this header or the sidecar returns 401 before Ollama ever sees the
    request. Blank by default: a bare `ollama serve` on loopback (this class's own
    default `endpoint`) has no auth of any kind to send, and sending no header rather
    than an empty one is what `gateway.client._auth_headers` does with it.

    `keep_alive` is D-123/D-124: sent as Ollama's own per-request `keep_alive` field
    on every `/api/chat` call, so the model stays resident for this long after the
    LAST call rather than Ollama's own 5-minute default. Empty string/`None` means
    "do not send the field at all" (Ollama's own default applies) — kept overridable
    per-instance for tests and the `model_prep.py` CLI, which measure cold-load
    behavior on purpose and would get a wrong answer if this were unconditionally on.
    """

    endpoint: str = DEFAULT_OLLAMA_ENDPOINT
    model_name: str = DEFAULT_CODELLAMA_MODEL
    model_revision: str = CODELLAMA_REVISION
    model_artifact_sha256: str = ""
    timeout_sec: float = DEFAULT_OLLAMA_TIMEOUT_SECONDS
    bearer_token: str = ""
    keep_alive: str = DEFAULT_OLLAMA_KEEP_ALIVE

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
        if self.keep_alive:
            payload["keep_alive"] = self.keep_alive

        response = post_json(
            _endpoint_url(self.endpoint, "chat"),
            payload,
            self.timeout_sec,
            bearer_token=self.bearer_token,
        )
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
