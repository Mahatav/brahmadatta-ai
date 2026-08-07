"""The mission state machine, and the authorization gate that fronts it.

Two things are enforced here, and the orchestrator (issue #12) is expected to call
them rather than reimplement them:

1. **Legal transitions only.** `TRANSITIONS` is exhaustive over `MissionState`; a
   move that is not in the table raises.
2. **No stage runs without authorization.** `assert_stage_can_run` and
   `assert_transition` both require an active `AuthorizationRecord` for every stage
   except `AUTHORIZE` itself. The record has to exist, be unrevoked, be unexpired,
   and cover the snapshot being worked on. There is no argument that bypasses it and
   no default that stands in for it — the parameter is required and `None` is a
   refusal, not a skip.
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from contracts.authorization import AuthorizationRecord, covers_snapshot, is_active
from contracts.enums import MissionStage, MissionState, TERMINAL_STATES, Verdict
from contracts.errors import (
    AuthorizationRequiredError,
    InvalidStateTransitionError,
    VerificationRequiredError,
)
from contracts.schemas.evidence import VerificationRecord
from contracts.verdict import derive_mission_verdict

#: Ordered happy path, for the Command Center stage timeline.
STATE_SEQUENCE: tuple[MissionState, ...] = (
    MissionState.CREATED,
    MissionState.AUTHORIZED,
    MissionState.SNAPSHOTTED,
    MissionState.VALIDATING,
    MissionState.BASELINE,
    MissionState.TRIAGE,
    MissionState.STRESS_TEST,
    MissionState.CORRELATE,
    MissionState.PATCH,
    MissionState.VERIFY,
    MissionState.EXPORTING,
)

#: States a paused mission may resume into.
_RESUMABLE: frozenset[MissionState] = frozenset(
    {
        MissionState.BASELINE,
        MissionState.TRIAGE,
        MissionState.STRESS_TEST,
        MissionState.CORRELATE,
        MissionState.PATCH,
        MissionState.VERIFY,
        MissionState.EXPORTING,
    }
)

#: Escapes available from any non-terminal state.
_ABORTS: frozenset[MissionState] = frozenset(
    {MissionState.CANCELLING, MissionState.FAILED}
)

TRANSITIONS: dict[MissionState, frozenset[MissionState]] = {
    MissionState.CREATED: frozenset({MissionState.AUTHORIZED}) | _ABORTS,
    MissionState.AUTHORIZED: frozenset({MissionState.SNAPSHOTTED}) | _ABORTS,
    MissionState.SNAPSHOTTED: frozenset({MissionState.VALIDATING}) | _ABORTS,
    MissionState.VALIDATING: frozenset({MissionState.BASELINE}) | _ABORTS,
    MissionState.BASELINE: frozenset({MissionState.TRIAGE, MissionState.PAUSED})
    | _ABORTS,
    MissionState.TRIAGE: frozenset({MissionState.STRESS_TEST, MissionState.PAUSED})
    | _ABORTS,
    MissionState.STRESS_TEST: frozenset({MissionState.CORRELATE, MissionState.PAUSED})
    | _ABORTS,
    MissionState.CORRELATE: frozenset(
        {MissionState.PATCH, MissionState.PAUSED, MissionState.HUMAN_REVIEW}
    )
    | _ABORTS,
    MissionState.PATCH: frozenset(
        {MissionState.VERIFY, MissionState.PAUSED, MissionState.HUMAN_REVIEW}
    )
    | _ABORTS,
    MissionState.VERIFY: frozenset(
        {MissionState.EXPORTING, MissionState.PAUSED, MissionState.HUMAN_REVIEW}
    )
    | _ABORTS,
    # A verdict becomes the mission's terminal state only once the evidence bundle
    # that justifies it has been written (P0-12).
    MissionState.EXPORTING: frozenset(
        {MissionState.VERIFIED, MissionState.REJECTED, MissionState.HUMAN_REVIEW}
    )
    | _ABORTS,
    MissionState.PAUSED: _RESUMABLE | _ABORTS,
    MissionState.CANCELLING: frozenset({MissionState.CANCELLED, MissionState.FAILED}),
    MissionState.VERIFIED: frozenset(),
    MissionState.REJECTED: frozenset(),
    MissionState.HUMAN_REVIEW: frozenset(),
    MissionState.FAILED: frozenset(),
    MissionState.CANCELLED: frozenset(),
}

#: Which workflow stage is executing while the mission sits in a given state.
STAGE_FOR_STATE: dict[MissionState, MissionStage | None] = {
    MissionState.CREATED: None,
    MissionState.AUTHORIZED: MissionStage.AUTHORIZE,
    MissionState.SNAPSHOTTED: MissionStage.INGEST,
    MissionState.VALIDATING: MissionStage.INGEST,
    MissionState.BASELINE: MissionStage.BASELINE,
    MissionState.TRIAGE: MissionStage.ANALYZE,
    MissionState.STRESS_TEST: MissionStage.STRESS_TEST,
    MissionState.CORRELATE: MissionStage.CORRELATE,
    MissionState.PATCH: MissionStage.PATCH,
    MissionState.VERIFY: MissionStage.VERIFY,
    MissionState.EXPORTING: MissionStage.EXPORT_EVIDENCE,
    MissionState.PAUSED: None,
    MissionState.CANCELLING: None,
    MissionState.VERIFIED: None,
    MissionState.REJECTED: None,
    MissionState.HUMAN_REVIEW: None,
    MissionState.FAILED: None,
    MissionState.CANCELLED: None,
}

#: Every stage except recording the authorization itself needs an active record.
STAGES_REQUIRING_AUTHORIZATION: frozenset[MissionStage] = frozenset(
    stage for stage in MissionStage if stage is not MissionStage.AUTHORIZE
)

#: Transitions that are always permitted without an authorization record: recording
#: one, and getting out safely. Cancellation and failure must never be blocked by the
#: absence of the thing that makes them necessary.
_AUTHORIZATION_EXEMPT_TARGETS: frozenset[MissionState] = frozenset(
    {
        MissionState.AUTHORIZED,
        MissionState.CANCELLING,
        MissionState.CANCELLED,
        MissionState.FAILED,
        MissionState.PAUSED,
    }
)


#: The verdict states, and the verdict each one requires evidence of. These are the
#: states a judge reads off the Core, and they are reachable only from `EXPORTING`.
VERDICT_FOR_STATE: dict[MissionState, Verdict] = {
    MissionState.VERIFIED: Verdict.VERIFIED,
    MissionState.REJECTED: Verdict.REJECTED,
    MissionState.HUMAN_REVIEW: Verdict.HUMAN_REVIEW_REQUIRED,
}


def allowed_transitions(state: MissionState) -> frozenset[MissionState]:
    return TRANSITIONS[MissionState(state)]


def is_terminal(state: MissionState) -> bool:
    return MissionState(state) in TERMINAL_STATES


def assert_stage_can_run(
    stage: MissionStage,
    authorization: AuthorizationRecord | None,
    now: datetime,
    snapshot_sha256: str | None = None,
) -> None:
    """Raise unless this stage is permitted to execute right now.

    `authorization` is a required positional argument. There is no default, so a
    caller cannot forget it — the code will not import, let alone run.
    """
    stage = MissionStage(stage)
    if stage not in STAGES_REQUIRING_AUTHORIZATION:
        return

    if not is_active(authorization, now):
        raise AuthorizationRequiredError(
            f"Stage {stage} cannot run: no active authorization record.",
            details={"stage": str(stage)},
        )

    assert authorization is not None  # narrowed by is_active
    if not covers_snapshot(authorization, snapshot_sha256):
        raise AuthorizationRequiredError(
            f"Stage {stage} cannot run: the authorization record is bound to a "
            f"different snapshot.",
            details={"stage": str(stage)},
        )


def assert_verdict_is_evidenced(
    current: MissionState,
    target: MissionState,
    verifications: Sequence[VerificationRecord],
) -> None:
    """Raise unless a verdict state is backed by the mission's verification runs.

    Takes the **set** of records, not one. A mission runs N candidates through the
    identical pipeline — the demo runs two, one that holds and one that does not — so
    the terminal state is derived from all of their verdicts through
    `derive_mission_verdict`, never from whichever finished last.

    Only transitions *out of* `EXPORTING` are gated. `HUMAN_REVIEW` reached earlier,
    from `CORRELATE`/`PATCH`/`VERIFY` when policy needs a person before anything has
    been verified, is a legitimate pause and is not covered.

    Each record already guarantees its own verdict was derived from its gate matrix
    (`VerificationRecord` re-derives it in a validator), so requiring the records here
    is enough: there is no path to `VERIFIED` that skips the gates.
    """
    if MissionState(current) is not MissionState.EXPORTING:
        return

    expected = VERDICT_FOR_STATE.get(MissionState(target))
    if expected is None:
        return

    records = list(verifications)
    if not records:
        raise VerificationRequiredError(
            f"Cannot enter {target}: no verification records. A verdict state must be "
            f"justified by at least one gate matrix.",
            details={"requested_state": str(target)},
        )

    derived = derive_mission_verdict([record.verdict for record in records])
    if derived is not expected:
        raise VerificationRequiredError(
            f"Cannot enter {target}: the mission's {len(records)} verification "
            f"run(s) derive {derived}, which does not justify that state.",
            details={
                "requested_state": str(target),
                "derived_verdict": str(derived),
                "required_verdict": str(expected),
                "candidate_verdicts": [str(record.verdict) for record in records],
            },
        )


def assert_transition(
    current: MissionState,
    target: MissionState,
    authorization: AuthorizationRecord | None,
    now: datetime,
    snapshot_sha256: str | None = None,
    verifications: Sequence[VerificationRecord] = (),
) -> None:
    """Raise unless the mission may move from `current` to `target` right now.

    Three independent conditions, all of which must hold: the transition is in the
    table, an active authorization covers the work, and — for the verdict states — a
    verification record justifies the claim.
    """
    current = MissionState(current)
    target = MissionState(target)

    if target not in TRANSITIONS[current]:
        raise InvalidStateTransitionError(
            f"{current} -> {target} is not a legal transition.",
            details={
                "current_state": str(current),
                "requested_state": str(target),
                "allowed": sorted(str(s) for s in TRANSITIONS[current]),
            },
        )

    assert_verdict_is_evidenced(current, target, verifications)

    if target in _AUTHORIZATION_EXEMPT_TARGETS:
        return

    stage = STAGE_FOR_STATE[target]
    if stage is None:
        # Terminal verdict states inherit the authorization requirement of the work
        # that produced them.
        if not is_active(authorization, now):
            raise AuthorizationRequiredError(
                f"Cannot enter {target}: no active authorization record.",
                details={"requested_state": str(target)},
            )
        return

    assert_stage_can_run(stage, authorization, now, snapshot_sha256)
