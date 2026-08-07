"""Contract-level exceptions.

Every one carries an `ErrorCode` from the frozen vocabulary and an HTTP status, so
`api.errors` can render them into one error envelope without a translation table that
drifts.
"""

from __future__ import annotations

from typing import Any

from contracts.enums import ErrorCode


class ContractError(Exception):
    """Base class. Never raised directly."""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    http_status: int = 500
    default_message: str = "Request failed."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.details = details or {}
        super().__init__(self.message)


class AuthorizationRequiredError(ContractError):
    """No active authorization record covers the requested stage.

    This is the hard safety boundary: an unauthorized repository must not be built,
    fuzzed, patched or even snapshotted. Raised by `contracts.state_machine`.
    """

    code = ErrorCode.INVALID_AUTHORIZATION
    http_status = 403
    default_message = (
        "No active authorization record for this mission. "
        "Record an authorization before any stage runs."
    )


class InvalidStateTransitionError(ContractError):
    code = ErrorCode.INVALID_STATE_TRANSITION
    http_status = 409
    default_message = "That transition is not legal from the mission's current state."


class VerificationRequiredError(ContractError):
    """A mission tried to enter a verdict state with nothing to justify it.

    `VERIFIED`, `REJECTED` and `HUMAN_REVIEW` reached from `EXPORTING` are the states
    a judge reads off the Core. Reaching one without a `VerificationRecord` — and
    therefore without a gate matrix — is the product's core claim failing open, so it
    is refused here rather than trusted to the orchestrator's discipline.
    """

    code = ErrorCode.VERIFICATION_REQUIRED
    http_status = 409
    default_message = (
        "A verdict state cannot be entered without a verification record whose "
        "verdict was derived from the deterministic gate matrix."
    )


class ExternalInferenceBlockedError(ContractError):
    """An inference endpoint pointed outside the trust boundary.

    Repository content never reaches a hosted third-party inference API. Raised by
    `contracts.model_policy` and surfaced at startup by a Django system check, so a
    misconfigured endpoint fails the process rather than leaking source at runtime.
    """

    code = ErrorCode.SANDBOX_POLICY_VIOLATION
    http_status = 403
    default_message = "Inference endpoint is outside the permitted trust boundary."


class NotImplementedYetError(ContractError):
    """A frozen-contract stub that has no implementation behind it yet.

    Returns 501 with the real response schema still documented in OpenAPI, so the
    Command Center can be typed against an endpoint before the pipeline lands.
    """

    code = ErrorCode.NOT_IMPLEMENTED
    http_status = 501
    default_message = "Endpoint is contract-frozen but not implemented yet."

    def __init__(self, owner_issue: str, message: str | None = None) -> None:
        super().__init__(
            message or f"Not implemented yet; tracked by {owner_issue}.",
            details={"tracked_by": owner_issue},
        )
