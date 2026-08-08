"""Errors the gateway raises. All of them are refusals, none of them are fallbacks.

Every error here means "the gateway declined to do the thing" and none of them is
recoverable *inside* the gateway. That is deliberate: the two ways this component can
break the product's central claims are to reach a host it should not have reached, and to
substitute a recorded response for a live one without saying so. Both are prevented by
raising rather than by degrading.

Degradation is the orchestrator's job (`degrade, don't die` — the mission drops to the
deterministic tier and reports a degraded state). It is not the gateway's, because the
gateway cannot tell the difference between "the operator wants a fallback" and "the
operator wants the truth".
"""

from __future__ import annotations


class GatewayError(Exception):
    """Base class for everything this package raises."""

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.details: dict[str, object] = details or {}


class ExternalInferenceBlockedError(GatewayError):
    """A configured or requested endpoint is outside the trust boundary.

    Deliberately the same name as `contracts.errors.ExternalInferenceBlockedError` in the
    control API. They are separate classes in separate processes — the ASGI process must
    not import this package (see `tests/architecture/test_import_direction.py`) — but they
    mean the same thing and a reader should not have to learn two names.
    """


class TranscriptError(GatewayError):
    """A transcript is missing, malformed, or does not hash to its own name."""


class TranscriptNotFoundError(TranscriptError):
    """No recorded transcript matches this request.

    In replay mode this is fatal. It is never answered by generating live, for the same
    reason a live timeout is never answered by replaying: the operator chose a mode and
    the gateway does not silently choose a different one.
    """


class LiveGenerationError(GatewayError):
    """Live generation failed — timeout, OOM, unreachable backend, bad output.

    Raised, never swallowed. `ModelGateway` in `LIVE` mode does not consult the transcript
    store on this path; see `gateway/tests/test_no_silent_fallback.py`.
    """


class LiveBackendUnavailableError(LiveGenerationError):
    """No live backend is wired up in this build.

    Distinct from `LiveGenerationError` so that "we never implemented it" cannot be
    mistaken in a log for "the model tried and failed". Issues #35/#36 replace this.
    """


class OperatorCandidateError(GatewayError):
    """Rung 3 of the fallback ladder cannot be served — the diff file is missing or empty."""


class GatewayConfigurationError(GatewayError):
    """The gateway was asked to start in a state it refuses to start in.

    Chiefly: no mode selected. `MODEL_GATEWAY_MODE` has no default on purpose — an
    unattended process must not pick between "live" and "replayed" on the operator's
    behalf, because that choice is a claim (D-049).
    """
