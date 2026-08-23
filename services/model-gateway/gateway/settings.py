"""Gateway configuration, read from the environment, validated on construction.

Two things here are unusual and both are deliberate.

**`MODEL_GATEWAY_MODE` has no default.** An unset mode is a configuration error, not
"live". The mode decides whether the system will later say "model-generated" or "recorded
and replayed" about its own output, and D-049 rules that the system never makes a
provenance claim on the operator's behalf by staying silent. Requiring the variable costs
one line in a compose file and removes the failure where a forgotten export produces the
stronger claim.

**`MODEL_SERVICE_NAMES` defaults to empty.** The endpoint policy then permits only
loopback, RFC 1918, IPv6 unique-local and `localhost`. Anything else — including the
compose service name of the model host — is an explicit declaration.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from gateway.endpoint_policy import (
    assert_local_inference_endpoint,
    normalise_service_names,
)
from gateway.errors import GatewayConfigurationError

DEFAULT_TRANSCRIPT_ROOT = Path(__file__).resolve().parents[1] / "transcripts"

#: D-123. Matches `gateway.ollama.DEFAULT_OLLAMA_TIMEOUT_SECONDS` and the
#: `${MODEL_HOST_TIMEOUT_SECONDS:-300}` fallback in `infrastructure/compose/
#: docker-compose*.yml`'s `model-host-auth` service — three defaults that all exist
#: because three different runtimes (this dataclass, the nginx template's envsubst,
#: and a bare-metal caller with no `.env` at all) each need a fallback for "the
#: variable was never set", not because the number is chosen three separate times:
#: change `MODEL_HOST_TIMEOUT_SECONDS` in one place and every one of these reads it.
DEFAULT_MODEL_HOST_TIMEOUT_SECONDS = 300.0


class GatewayMode(StrEnum):
    """Where a response comes from. Chosen by the operator, never by the gateway."""

    LIVE = "live"
    REPLAY = "replay"


@dataclass(frozen=True)
class GatewaySettings:
    mode: GatewayMode
    #: Empty is legal in REPLAY mode — replay opens no socket, so there is nothing to
    #: validate. In LIVE mode an empty endpoint is a configuration error.
    endpoint: str = ""
    service_names: frozenset[str] = frozenset()
    transcript_root: Path = DEFAULT_TRANSCRIPT_ROOT
    #: Serving a transcript that was written by hand rather than captured from a model run
    #: is a different claim again, and off unless asked for. See
    #: `gateway/transcripts.py::CaptureKind`.
    allow_synthetic_transcripts: bool = False
    #: Resolve the endpoint's name and check every answer before the first request.
    #: On in LIVE mode; meaningless in REPLAY mode.
    resolve_endpoint: bool = True

    prompt_version: str = ""
    response_schema_version: str = ""

    #: D-075 / SEC-50. Sent as `Authorization: Bearer <token>` by the caller that
    #: constructs a live backend (e.g. `gateway.ollama.OllamaCodeLlamaBackend`) with
    #: it — `GatewaySettings` itself does not call the backend, it only carries the
    #: value the same way it carries `endpoint`. Blank is legal: only the compose
    #: `model-host-auth` sidecar demands this header today, and a bare `ollama serve`
    #: on loopback (this module's other supported shape) has no auth to send at all.
    model_host_bearer_token: str = ""

    #: D-123 (.project/decisions.md). Read from `MODEL_HOST_TIMEOUT_SECONDS` — the
    #: ONE source of truth for both this client's own request timeout (passed to
    #: `gateway.ollama.OllamaCodeLlamaBackend(timeout_sec=...)` by the caller that
    #: builds the live backend) AND `model-host-auth`'s nginx `proxy_read_timeout`/
    #: `proxy_send_timeout` (`infrastructure/compose/nginx/model-host-auth/templates/
    #: model-host-auth.conf.template`, rendered from the SAME env var name via the
    #: image's own envsubst entrypoint). Before this fix the two were two
    #: independently hardcoded `300s` literals that only matched by coincidence —
    #: raising the client's alone did nothing, because the proxy silently re-capped
    #: every call at its own value and returned a 504 instead. Defaults to 300.0,
    #: unchanged from before this fix; the actual number is deliberately not
    #: revisited here (D-123 — needs re-measuring after a separate, pending
    #: memory-capacity decision).
    model_host_timeout_seconds: float = DEFAULT_MODEL_HOST_TIMEOUT_SECONDS

    #: Populated by `validate()` so callers do not re-derive it.
    _validated: bool = field(default=False, compare=False)

    def validate(self) -> GatewaySettings:
        if self.mode is GatewayMode.LIVE:
            if not self.endpoint:
                raise GatewayConfigurationError(
                    "MODEL_GATEWAY_MODE=live but MODEL_ENDPOINT is empty. Live mode needs "
                    "a locally-served model to call."
                )
            assert_local_inference_endpoint(
                "MODEL_ENDPOINT", self.endpoint, service_names=self.service_names
            )
        elif self.endpoint:
            # Validated even though replay opens no socket: a bad value that only fails
            # when someone switches to live mode fails on the worst possible day.
            assert_local_inference_endpoint(
                "MODEL_ENDPOINT", self.endpoint, service_names=self.service_names
            )
        return self


def _bool(raw: str | None, *, default: bool) -> bool:
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def from_environment(env: Mapping[str, str] | None = None) -> GatewaySettings:
    """Build settings from environment variables and validate them.

    Raises `GatewayConfigurationError` if `MODEL_GATEWAY_MODE` is unset or unrecognised,
    and `ExternalInferenceBlockedError` if the endpoint is outside the boundary.
    """
    source: Mapping[str, str] = os.environ if env is None else env

    raw_mode = (source.get("MODEL_GATEWAY_MODE") or "").strip().lower()
    if not raw_mode:
        raise GatewayConfigurationError(
            "MODEL_GATEWAY_MODE is not set. It has no default: 'live' and 'replay' make "
            "different claims about where the output came from, and the gateway does not "
            "pick between them on your behalf. Set it to 'live' or 'replay'."
        )
    try:
        mode = GatewayMode(raw_mode)
    except ValueError as exc:
        raise GatewayConfigurationError(
            f"MODEL_GATEWAY_MODE={raw_mode!r} is not a mode. Use 'live' or 'replay'."
        ) from exc

    service_names = normalise_service_names(
        (source.get("MODEL_SERVICE_NAMES") or "").replace(";", ",").split(",")
    )

    root = source.get("MODEL_TRANSCRIPT_ROOT")
    settings = GatewaySettings(
        mode=mode,
        endpoint=(source.get("MODEL_ENDPOINT") or "").strip(),
        service_names=service_names,
        transcript_root=Path(root) if root else DEFAULT_TRANSCRIPT_ROOT,
        allow_synthetic_transcripts=_bool(
            source.get("MODEL_ALLOW_SYNTHETIC_TRANSCRIPTS"), default=False
        ),
        resolve_endpoint=_bool(source.get("MODEL_RESOLVE_ENDPOINT"), default=True),
        prompt_version=(source.get("MODEL_PROMPT_VERSION") or "").strip(),
        response_schema_version=(source.get("MODEL_RESPONSE_SCHEMA_VERSION") or "").strip(),
        model_host_bearer_token=(source.get("MODEL_HOST_BEARER_TOKEN") or "").strip(),
        model_host_timeout_seconds=_model_host_timeout_seconds(source),
    )
    return settings.validate()


def _model_host_timeout_seconds(source: Mapping[str, str]) -> float:
    """D-123: the one env var both the gateway client and the nginx proxy read.

    Unset/blank -> the same 300.0 default `DEFAULT_MODEL_HOST_TIMEOUT_SECONDS` names,
    so behavior is unchanged until an operator deliberately sets this. A value that
    parses but is not a positive number of seconds is a configuration error rather
    than a silent fallback — the same posture `MODEL_GATEWAY_MODE` takes above, since
    an operator who set this to something nonsensical almost certainly meant to
    change the real per-call ceiling, not to leave it at the default.
    """
    raw = (source.get("MODEL_HOST_TIMEOUT_SECONDS") or "").strip()
    if not raw:
        return DEFAULT_MODEL_HOST_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError as exc:
        raise GatewayConfigurationError(
            f"MODEL_HOST_TIMEOUT_SECONDS={raw!r} is not a number of seconds."
        ) from exc
    if value <= 0:
        raise GatewayConfigurationError(
            f"MODEL_HOST_TIMEOUT_SECONDS={raw!r} must be greater than zero."
        )
    return value
