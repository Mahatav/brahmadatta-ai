"""The mission state machine, and the authorization gate that fronts it.

Four things are enforced here, and the orchestrator (issue #12) is expected to call
them rather than reimplement them:

1. **Legal transitions only.** `TRANSITIONS` is exhaustive over `MissionState`; a
   move that is not in the table raises.
2. **No stage runs without authorization.** `assert_stage_can_run` and
   `assert_transition` both require an active `AuthorizationRecord` for every stage
   except `AUTHORIZE` itself. The record has to exist, be unrevoked, be unexpired,
   and cover the snapshot being worked on. There is no argument that bypasses it and
   no default that stands in for it — the parameter is required and `None` is a
   refusal, not a skip.
3. **A verdict state is backed by this mission's own verification records** —
   `isinstance`-checked, mission-bound and de-duplicated (D-045).
4. **A paused mission resumes only into the state it paused from** (D-047).

## What this module cannot do, and where the rest lives

`assert_verdict_is_evidenced` is a pure function over the records it is handed. It
can check that each record is real, belongs to this mission, and derives the verdict
being claimed. It **cannot** check that it was shown *all* of them: dropping a
`REJECTED` record before the call is invisible from inside. No amount of validation
in `contracts/` closes that, and a guard that looks total while missing it is worse
than one that is honestly partial (D-045).

The completeness half therefore lives at the database boundary, in
`orchestrator.transitions.transition`, which loads the records itself by mission id
inside the transaction that holds `SELECT … FOR UPDATE` on the mission row. The same
applies to `assert_candidate_set_open`, whose real enforcement is
`Mission.verification_started_at` (D-046).

`contracts/` stays free of a persistence dependency on purpose — it is imported by
the OpenAPI export, which must run without a database.
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence
from uuid import UUID

from contracts.authorization import AuthorizationRecord, covers_snapshot, is_active
from contracts.enums import MissionStage, MissionState, TERMINAL_STATES, Verdict
from contracts.errors import (
    AuthorizationRequiredError,
    CandidateSetFrozenError,
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

#: States a mission may be paused *from*, and therefore the only states it may resume
#: into. This is a static superset used to keep `TRANSITIONS` exhaustive and to answer
#: "could a pause here ever be resumed". It is NOT the set of legal resume targets for
#: a given mission — see `assert_resume` and `allowed_transitions(..., paused_from=)`.
#:
#: D-047: with a fixed resumable set, pause was a forward skip *and* a backward one. A
#: mission paused in VERIFY could resume into BASELINE, re-run the baseline, and write a
#: second `BaselineReport` for the same snapshot — and `BaselineReport` is the
#: denominator for "regression preserved" (P0-5), so two of them make the central
#: verification claim ambiguous to anyone auditing the bundle. `paused_from` closes
#: both directions with one lookup.
PAUSABLE_STATES: frozenset[MissionState] = frozenset(
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
    MissionState.PAUSED: PAUSABLE_STATES | _ABORTS,
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


def allowed_transitions(
    state: MissionState, paused_from: MissionState | None = None
) -> frozenset[MissionState]:
    """What this mission may legally do next.

    For `PAUSED` the answer depends on the mission, not only on the state: it may
    resume into `paused_from` and nowhere else, plus the aborts. A pause with no
    recorded origin can only be aborted — fail closed, because the alternative is
    letting an unknown origin stand in for any origin.

    `MissionDetail.allowed_transitions` is rendered from this, so the UI's buttons and
    the guard below cannot disagree.
    """
    state = MissionState(state)
    if state is not MissionState.PAUSED:
        return TRANSITIONS[state]
    if paused_from is None:
        return _ABORTS
    return frozenset({MissionState(paused_from)}) | _ABORTS


def assert_resume(
    current: MissionState,
    target: MissionState,
    paused_from: MissionState | None,
) -> None:
    """Raise unless a paused mission is resuming into exactly the state it paused from.

    D-047. `TRANSITIONS[PAUSED]` lists every pausable state so the table stays
    exhaustive; this narrows it to the one that is true for *this* mission. Both
    directions are closed by the same check — a mission paused in `BASELINE` cannot
    skip forward to `EXPORTING`, and one paused in `VERIFY` cannot fall back to
    `BASELINE` and write a second `BaselineReport` for the same snapshot.
    """
    if MissionState(current) is not MissionState.PAUSED:
        return

    target = MissionState(target)
    if target in _ABORTS:
        # Getting out safely is never blocked by the bookkeeping.
        return

    if paused_from is None:
        raise InvalidStateTransitionError(
            f"Cannot resume into {target}: this mission has no recorded paused_from, "
            f"so there is no state it is known to have paused in.",
            details={
                "current_state": str(current),
                "requested_state": str(target),
                "allowed": sorted(str(s) for s in _ABORTS),
            },
        )

    paused_from = MissionState(paused_from)
    if target is not paused_from:
        raise InvalidStateTransitionError(
            f"A paused mission resumes only into the state it paused from. This one "
            f"paused in {paused_from} and tried to resume into {target}.",
            details={
                "current_state": str(current),
                "requested_state": str(target),
                "paused_from": str(paused_from),
                "allowed": sorted(str(s) for s in (frozenset({paused_from}) | _ABORTS)),
            },
        )


#: The inverse of `VERDICT_FOR_STATE`. One entry per verdict, so a new `Verdict`
#: member cannot reach the Core as an unmapped state.
STATE_FOR_VERDICT: dict[Verdict, MissionState] = {
    verdict: state for state, verdict in VERDICT_FOR_STATE.items()
}


def is_terminal(state: MissionState) -> bool:
    return MissionState(state) in TERMINAL_STATES


def derive_mission_outcome(verdicts: Sequence[Verdict]) -> MissionState:
    """The terminal state the recorded verdicts produce (architecture spec §2.3).

    The mission's terminal state is a function of the whole candidate set, not of
    whichever verification finished last — that is what makes the fan-out in #80 a
    fan-out rather than a loop. `derive_mission_verdict` owns the reduction rule; this
    only names the state it lands in, so there is exactly one place that decides.
    """
    return STATE_FOR_VERDICT[derive_mission_verdict(verdicts)]


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


def assert_candidate_set_open(
    verifications: Sequence[VerificationRecord],
) -> None:
    """Raise if any verification exists — the candidate set closes when VERIFY starts.

    D-046. This is the **statement** of the rule, not its enforcement: a caller that
    never calls it is not stopped by it, and a caller handed an empty list learns
    nothing. The enforcement is `Mission.verification_started_at`, checked under the
    mission row lock in `orchestrator.candidates.record_patch_candidate` — "has
    verification started" is state, and state lives in the store.

    It lives here anyway because this is the file a developer reads before writing the
    insert, and because the rule needs to be visible next to the fan-out it bounds.
    Without it the next reader sees `PATCH → VERIFY` producing N candidates with no
    stated bound and reasonably concludes there isn't one.

    The failure it exists to prevent: *"add one more candidate and re-verify"* is
    generate-until-pass, and it needs no transition-table change, so it is the one
    failure mode here that leaves no diff for a reviewer to object to.
    """
    if verifications:
        raise CandidateSetFrozenError(
            f"Verification has already produced {len(verifications)} record(s) for "
            f"this mission; the candidate set is closed.",
            details={"verification_count": len(verifications)},
        )


def assert_verdict_is_evidenced(
    current: MissionState,
    target: MissionState,
    verifications: Sequence[VerificationRecord],
    *,
    mission_id: UUID,
) -> None:
    """Raise unless a verdict state is backed by *this mission's* verification runs.

    Takes the **set** of records, not one. A mission runs N candidates through the
    identical pipeline — the demo runs two, one that holds and one that does not — so
    the terminal state is derived from all of their verdicts through
    `derive_mission_verdict`, never from whichever finished last.

    Only transitions *out of* `EXPORTING` are gated. `HUMAN_REVIEW` reached earlier,
    from `CORRELATE`/`PATCH`/`VERIFY` when policy needs a person before anything has
    been verified, is a legitimate pause and is not covered.

    Three checks on the records themselves, each closing a case QA reproduced against
    the D1 guard (BUG-003, BUG-004; ruled on in D-045):

    * **`isinstance`.** The previous guard read `record.verdict` off whatever it was
      handed, so any object with a `.verdict` attribute — a `CandidateVerdict`, or a
      one-line stand-in with no gate matrix anywhere — satisfied it. A type annotation
      is documentation; this is the enforcement.
    * **Mission binding.** Every record's `mission_id` must equal the mission being
      transitioned, so another mission's `VERIFIED` cannot justify this one's verdict.
      `AuthorizationRecord.covers_snapshot` is the same idea applied to authority.
    * **De-duplication by `record.id`.** The same record supplied twice must not
      outvote a record supplied once.

    Each record already guarantees its own verdict was derived from its gate matrix
    (`VerificationRecord` re-derives it in a validator), so a record that survives all
    three carries a real gate matrix for this mission.

    **What is still not checked here, and cannot be.** That the caller passed *every*
    record. Dropping a `REJECTED` one is invisible from inside this function. Call it
    only from a transaction-scoped path that loaded the records itself — see the module
    docstring and `orchestrator.transitions.transition`.
    """
    if MissionState(current) is not MissionState.EXPORTING:
        return

    expected = VERDICT_FOR_STATE.get(MissionState(target))
    if expected is None:
        return

    records = _checked_records(verifications, target, mission_id)
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


def _checked_records(
    verifications: Sequence[VerificationRecord],
    target: MissionState,
    mission_id: UUID,
) -> list[VerificationRecord]:
    """Type-check, mission-bind and de-duplicate the supplied records."""
    mission_id = UUID(str(mission_id))
    seen: dict[UUID, VerificationRecord] = {}

    for index, record in enumerate(verifications):
        if not isinstance(record, VerificationRecord):
            raise VerificationRequiredError(
                f"Cannot enter {target}: element {index} of the verification set is a "
                f"{type(record).__name__}, not a VerificationRecord. Only a record "
                f"carrying a gate matrix can justify a verdict.",
                details={
                    "requested_state": str(target),
                    "offending_index": index,
                    "offending_type": type(record).__name__,
                },
            )
        if record.mission_id != mission_id:
            raise VerificationRequiredError(
                f"Cannot enter {target}: verification {record.id} belongs to mission "
                f"{record.mission_id}, not {mission_id}. Another mission's evidence "
                f"does not justify this mission's verdict.",
                details={
                    "requested_state": str(target),
                    "mission_id": str(mission_id),
                    "offending_verification_id": str(record.id),
                    "offending_mission_id": str(record.mission_id),
                },
            )
        seen[record.id] = record

    return list(seen.values())


def assert_transition(
    current: MissionState,
    target: MissionState,
    authorization: AuthorizationRecord | None,
    now: datetime,
    snapshot_sha256: str | None = None,
    verifications: Sequence[VerificationRecord] = (),
    *,
    mission_id: UUID,
    paused_from: MissionState | None = None,
) -> None:
    """Raise unless the mission may move from `current` to `target` right now.

    Four independent conditions, all of which must hold: the transition is in the
    table; a paused mission is resuming into the state it paused from; an active
    authorization covers the work; and — for the verdict states — this mission's own
    verification records justify the claim.

    `mission_id` is keyword-only and required. It has no default, so the verdict guard
    cannot be run "without a mission" by a caller who did not think about it.
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

    assert_resume(current, target, paused_from)
    assert_verdict_is_evidenced(current, target, verifications, mission_id=mission_id)

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
