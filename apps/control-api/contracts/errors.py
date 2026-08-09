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


class CandidateSetFrozenError(ContractError):
    """A patch candidate was offered after verification had already begun (D-046).

    Without this, *"add one more candidate and re-verify"* reaches generate-until-pass
    with no transition-table change for a reviewer to object to — the one failure mode
    in this system that leaves no diff to catch it.

    It reuses `ErrorCode.CONFLICT` deliberately. A dedicated member would be the more
    descriptive code, and `ErrorCode` is a `StrEnum` consumed by generated TypeScript:
    D-030 froze it and said no further additions. The specifics travel in `details`
    instead of in the vocabulary.
    """

    code = ErrorCode.CONFLICT
    http_status = 409
    default_message = (
        "The candidate set is frozen: verification has already started for this "
        "mission. A candidate added now could only be an attempt to generate until "
        "something passes."
    )


class CrossMissionEvidenceError(ContractError):
    """Evidence from one mission was offered as evidence for another (SEC-15).

    D-046 freezes a mission's *candidate set*. On its own it does not freeze the set of
    candidates that can be verified *into* that mission — so a frozen mission whose only
    candidate was `REJECTED` could reach terminal `VERIFIED` by verifying a second
    mission's candidate into it, through the sanctioned writer, with no forged record
    and no direct database write.

    The mission-binding check in `contracts.state_machine` cannot catch this: it reads
    `VerificationRecord.mission_id`, and the row genuinely carries the right mission id
    because the writer set it. The check has to happen at the moment that column is
    written, which is `orchestrator.candidates.record_verification`.

    Reuses `ErrorCode.CONFLICT` for the reason given on `CandidateSetFrozenError`.
    """

    code = ErrorCode.CONFLICT
    http_status = 409
    default_message = (
        "That patch candidate belongs to a different mission. Evidence is only "
        "evidence for the mission whose candidate set it came from."
    )


class MissionStateWriteError(ContractError):
    """`Mission` was written outside the orchestrator's transition path (SEC-16).

    `orchestrator.transitions.transition` is the only sanctioned writer of
    `Mission.state`, because it is the only place that loads the mission's *complete*
    verification set under the row lock before deciding. A write from anywhere else
    reaches a terminal verdict past guards that were never run — which a reviewer
    reproduced in four lines through a public function, with no test failing.

    Raised by `Mission.save()` and by the mission queryset's `update()`.
    """

    code = ErrorCode.INTERNAL_ERROR
    http_status = 500
    default_message = (
        "Mission lifecycle fields are written only by "
        "orchestrator.transitions.transition, which holds the row lock and has loaded "
        "the mission's complete evidence set."
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


class TooManyConcurrentStreamsError(ContractError):
    """A mission's SSE view already has `SSE_MAX_STREAMS_PER_MISSION` open readers.

    Reuses `ErrorCode.CONFLICT` for the reason given on `CandidateSetFrozenError` —
    D-030 froze the vocabulary and a dedicated member is not on the list. `http_status`
    is 429, not `CONFLICT`'s usual 409: the caller's remedy is "close another viewer
    and reconnect," not "the request itself is wrong."
    """

    code = ErrorCode.CONFLICT
    http_status = 429
    default_message = (
        "Too many concurrent event-stream connections for this mission. Close "
        "another viewer and reconnect."
    )


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
