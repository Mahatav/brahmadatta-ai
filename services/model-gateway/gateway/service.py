"""`ModelGateway` — one code path, two sources, one place the mode is chosen.

## The shape, and why it is this shape

```
    generate(request)
      |
      +-- 1. validate the request                (same for both)
      +-- 2. source.produce(request)             <-- the ONLY difference
      +-- 3. re-validate the candidate           (same for both)
      +-- 4. check the response schema version   (same for both)
      +-- 5. attach provenance                   (same for both)
      +-- 6. label it via gateway.provenance     (same for both)
```

Steps 1 and 3 to 6 are written once. That is issue #82's "through the same code path and
schema as live generation" made structural: there is no branch on `self.mode` after the
source is chosen, so the replay path cannot drift into accepting a response the live path
would reject, and no renderer downstream can be given a replayed response that is missing
the fields a live one would have carried.

## Two rules with tests behind them

**Replay is never a silent fallback.** In `LIVE` mode a timeout, an OOM or an unreachable
backend raises. The transcript store is not consulted — not "consulted and found empty",
not consulted. `gateway/tests/test_no_silent_fallback.py` asserts this with a store that is
fully populated and a spy that fails the test if it is read.

**The mode is an operator choice.** `MODEL_GATEWAY_MODE` has no default and
`GatewaySettings.validate()` refuses to start without it. Switching modes is a
configuration change and an audit line, not a runtime decision.

## Degrading

Rule 5 for this seat is "degrade, don't die": GPU unreachable, OOM, timeout — the mission
falls back to the deterministic tier and reports a degraded state. That fallback belongs to
the orchestrator, not here. The gateway's contribution is to raise a typed error promptly
so the orchestrator can make that call; it must not make it itself, because the only
fallback available *inside* the gateway is the one that changes what the system claims
about its own output.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from gateway.endpoint_policy import assert_resolves_inside_boundary
from gateway.errors import GatewayConfigurationError, LiveGenerationError
from gateway.provenance import describe, render_for_ui
from gateway.schemas import GatewayResponse, GenerationRequest, PatchCandidate
from gateway.settings import GatewayMode, GatewaySettings
from gateway.transcripts import TranscriptStore

from gateway.backends import (  # isort: skip  (grouped: the seam this module drives)
    GenerationSource,
    LiveSource,
    RecordingSource,
    ReplaySource,
    UnavailableLiveBackend,
)

__all__ = ["ModelGateway", "build_gateway"]

logger = logging.getLogger("brahmadatta.gateway")


class ModelGateway:
    def __init__(
        self,
        settings: GatewaySettings,
        source: GenerationSource,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.settings = settings
        self.source = source
        self.clock = clock

    # -- the one path -------------------------------------------------------------------

    def generate(self, request: GenerationRequest) -> GatewayResponse:
        if not isinstance(request, GenerationRequest):  # pragma: no cover - type guard
            raise GatewayConfigurationError("generate() takes a GenerationRequest")

        started = self.clock()
        if self.settings.mode is GatewayMode.LIVE:
            self._check_endpoint()

        result = self.source.produce(request)

        # Re-validated rather than trusted. A backend returns a `PatchCandidate` by type
        # annotation; this is the assertion that it actually did, and it runs on the
        # replay path too, where the object was reconstructed from a file on disk.
        candidate = PatchCandidate.model_validate(
            result.candidate
            if isinstance(result.candidate, dict)
            else result.candidate.model_dump()
        )

        if result.provenance.response_schema_version != request.response_schema_version:
            raise LiveGenerationError(
                "the response was produced under schema "
                f"{result.provenance.response_schema_version!r} but the request asked for "
                f"{request.response_schema_version!r}",
                details={"source": self.source.name},
            )

        response = GatewayResponse(
            candidate=candidate,
            provenance=result.provenance,
            wall_time_ms=result.wall_time_ms,
            output_tokens=result.output_tokens,
        )

        # Rule 3 for this seat: everything is pinned and logged, so a run is explainable
        # afterwards. The provenance label is in the log line for the same reason it is on
        # the screen — a log that says "patch candidate produced" without saying whether a
        # model ran is the same overclaim in a different medium.
        logger.info(
            "patch candidate produced",
            extra={
                "mission_id": request.mission_id,
                "source": self.source.name,
                "mode": self.settings.mode.value,
                "provenance": describe(response.provenance),
                "prompt_version": request.prompt_version,
                "prompt_sha256": request.prompt_sha256,
                "response_schema_version": request.response_schema_version,
                "model_artifact_sha256": response.provenance.model_artifact_sha256,
                "transcript_sha256": response.provenance.transcript_sha256,
                "wall_time_ms": response.wall_time_ms,
                "gateway_wall_time_ms": int((self.clock() - started).total_seconds() * 1000),
            },
        )
        return response

    def ui_payload(self, response: GatewayResponse) -> dict[str, object]:
        """What a Command Center panel renders. Wording comes from one place."""
        return render_for_ui(response.provenance)

    # -- endpoint check -----------------------------------------------------------------

    def _check_endpoint(self) -> None:
        """Resolve the endpoint and check every answer before each live call.

        Syntactic validation happened at settings construction. This is the DNS half — the
        case where a name inside the boundary answers with an address outside it. D5's
        gateway review requires this assertion on every call because DNS answers can
        change between requests.
        """
        if not self.settings.resolve_endpoint:
            return
        assert_resolves_inside_boundary(
            "MODEL_ENDPOINT",
            self.settings.endpoint,
            service_names=self.settings.service_names,
        )


def build_gateway(
    settings: GatewaySettings,
    *,
    live_backend: object | None = None,
    capture_note: str = "",
) -> ModelGateway:
    """Assemble a gateway from settings. The only place the mode selects a source.

    Note what is absent: there is no `try live, except: replay`. The mode is read once,
    a source is built, and the gateway never reconsiders.
    """
    store = TranscriptStore(
        settings.transcript_root, allow_synthetic=settings.allow_synthetic_transcripts
    )

    if settings.mode is GatewayMode.REPLAY:
        return ModelGateway(settings, ReplaySource(store))

    backend = live_backend if live_backend is not None else UnavailableLiveBackend()
    live = LiveSource(backend)  # type: ignore[arg-type]
    recording = RecordingSource(
        live,
        store,
        note=capture_note,
        on_capture_error=lambda exc: logger.error(
            "live response was produced but could not be recorded: %s", exc
        ),
    )
    return ModelGateway(settings, recording)
