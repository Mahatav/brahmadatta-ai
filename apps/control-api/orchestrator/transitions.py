"""The only writer of `Mission.state`.

Every transition is one transaction: take `SELECT … FOR UPDATE` on the mission row,
load the evidence, run the guards, write the new state, append the event. One
transaction per transition rather than per tick, so a crash mid-tick leaves the mission
exactly where the database says it is and never half-moved.

## Why the guards are called from *here* and not from the API layer

`contracts.state_machine.assert_verdict_is_evidenced` is a pure function over the
records it is handed. It checks that each record is a real `VerificationRecord`, belongs
to this mission, and derives the verdict being claimed. It cannot check that it was
shown **all** of them — withholding a record before the call is invisible from inside a
function given only what it was given (D-045, BUG-004(c)).

**Which record matters, corrected.** D-045 and this module's first draft both said "a
dropped `REJECTED` record". That is wrong, and the round-2 security review §13.1 showed
why by execution: `derive_mission_verdict` is any-VERIFIED-wins, so
`[VERIFIED, REJECTED]` and `[VERIFIED]` both derive `VERIFIED` and dropping a rejection
changes nothing. The record whose removal reaches `VERIFIED` is a
**`HUMAN_REVIEW_REQUIRED`** one, because that outranks everything.

No validation in `contracts/` closes it either way. The completeness guarantee lives at
the database boundary because that is the only place it can live — and, since the review
defeated the convention that used to protect the write itself, `Mission`'s lifecycle
fields now refuse a write from outside this function (`missions/lifecycle.py`, SEC-16).
See the call site below.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from authorization.errors import MissionNotFoundError
from contracts.enums import (
    EventStatus,
    EventType,
    MissionStage,
    MissionState,
    Severity,
    posture_for,
)
from contracts.errors import InvalidStateTransitionError
from contracts.state_machine import (
    PAUSABLE_STATES,
    STAGE_FOR_STATE,
    VERDICT_FOR_STATE,
    assert_transition,
    is_terminal,
)
from missions.lifecycle import lifecycle_write
from missions.models import Mission
from orchestrator import events, repository

logger = logging.getLogger("orchestrator.transitions")

#: The two targets that must remain reachable when the mission's own bookkeeping is
#: unreadable. Mirrors `contracts.state_machine._ABORTS`; imported rather than retyped
#: would be neater, but that name is private and this list is the *policy*, which is
#: this module's to state.
_ABORT_TARGETS: frozenset[MissionState] = frozenset(
    {MissionState.CANCELLING, MissionState.FAILED}
)


def _tolerate_if_aborting(aborting: bool, fallback, loader, *args):
    """Run `loader`, substituting `fallback` if it raises *and* we are aborting.

    Deliberately narrow, and deliberately not a `try` around the whole transition. The
    tolerance applies to **reading the mission's own bookkeeping**, only when the
    destination is `CANCELLING` or `FAILED`, and only for values an abort does not
    consult. Anything else — the guards, the state write, the event append — still
    raises, because an abort that silently half-succeeded would be worse than one that
    failed loudly.

    It is a helper rather than three inline `try` blocks so that "which reads are
    tolerant" is one list in one place, visible to the next person who adds a fourth.
    """
    try:
        return loader(*args)
    except Exception:
        if not aborting:
            raise
        return fallback


@dataclass(frozen=True)
class TransitionResult:
    mission_id: UUID
    from_state: MissionState
    to_state: MissionState
    sequence: int


def transition(
    mission_id: UUID,
    target: MissionState,
    *,
    trace_id: str,
    reason: str = "",
    now=None,
) -> TransitionResult:
    """Move a mission to `target`, or raise. The mission row is locked throughout.

    Raises `InvalidStateTransitionError`, `AuthorizationRequiredError` or
    `VerificationRequiredError` — all `ContractError`s, so `api.errors` renders them
    into the standard envelope with the right status without a translation table.
    """
    target = MissionState(target)
    now = now or timezone.now()

    with transaction.atomic(), lifecycle_write():
        # The lock. Everything below reads and writes under it, which is what makes
        # the sequence allocation gap-free and the evidence load complete.
        #
        # `lifecycle_write()` is what permits the write at the end. It is entered here
        # and nowhere else, so `Mission.state` cannot be moved by code that did not go
        # through this function — the convention that used to protect that was defeated
        # in four lines by a security review (SEC-16). See `missions/lifecycle.py`.
        #
        # `Mission.DoesNotExist` is translated here, mirroring
        # `authorization.service._lock_mission`. Every caller up to and including #154
        # pre-locked the row through its own guard before ever reaching this line, so a
        # bad `mission_id` never actually hit this `.get()` — `preflight`/`start`/
        # `pause`/`cancel` are the first callers to hit `transition()` directly, and an
        # uncaught `DoesNotExist` here would have been their first caller's first 500
        # instead of a 404. There is no pre-check in those handlers to compensate: this
        # is the one and only place `mission_id` is resolved, under the lock, which is
        # the whole point of the lock-first pattern SEC-15 established.
        try:
            mission = Mission.objects.select_for_update().get(pk=mission_id)
        except Mission.DoesNotExist as exc:
            raise MissionNotFoundError(
                "No mission with that id.", details={"mission_id": str(mission_id)}
            ) from exc
        current = mission.state_enum
        aborting = target in _ABORT_TARGETS

        # BUG-020 / SEC-20. On the abort path, *every* read of the mission's own
        # bookkeeping is tolerant of a row it cannot parse. An abort is authorization-
        # exempt by the transition table already (`_AUTHORIZATION_EXEMPT_TARGETS`), so a
        # malformed `Authorization` row is not merely survivable here, it is irrelevant
        # — and letting it raise would wedge the mission for a value nothing downstream
        # was going to read.
        #
        # The failure this prevents is specific and it happens in front of judges: a
        # mission stuck on the Command Center on D6 with no way to clear it, because
        # the thing blocking the exit is the data the exit exists to escape.
        authorization = _tolerate_if_aborting(
            aborting, None, repository.load_active_authorization, mission, now
        )
        snapshot_sha256 = _tolerate_if_aborting(
            aborting, None, repository.latest_snapshot_sha256, mission
        )

        # ---------------------------------------------------------------------
        # D-045, the load-bearing part. `verifications` is loaded HERE, by mission
        # id, inside the transaction that holds the row lock — it is never a
        # parameter this function accepts and never something a caller assembles.
        #
        # `assert_verdict_is_evidenced` can prove every record it is shown is real,
        # belongs to this mission and derives the claimed verdict. It CANNOT prove it
        # was shown all of them: a caller that withholds one reaches a verdict the
        # full set would not support, and nothing inside a pure function can tell.
        # (The record whose removal reaches VERIFIED is a HUMAN_REVIEW_REQUIRED one,
        # not a REJECTED one — `derive_mission_verdict` is any-VERIFIED-wins, so
        # dropping a REJECTED record is a no-op. The original D-045 framing had this
        # backwards; corrected by the round-2 security review §13.1.)
        #
        # If a future refactor moves this load out of the transaction, or lets a
        # caller pass the records in, invariant B ("no verdict against the evidence")
        # silently becomes "no verdict without *some* evidence" — which is a
        # different and much weaker claim, with no test failure to announce it.
        # `orchestrator/tests/test_verdict_completeness.py` is the test that fails.
        #
        # It is loaded UNCONDITIONALLY and must stay that way. Making the load
        # conditional on the target state would reopen exactly this hole. The abort
        # path below therefore tolerates an *unreadable* set rather than skipping the
        # load — a distinction that matters, because the first is about a corrupted
        # row and the second would be about trusting the caller's destination.
        # ---------------------------------------------------------------------
        #
        # Aborts do not consult evidence: `assert_verdict_is_evidenced` returns
        # immediately for any target that is not a verdict state, so an empty list on
        # the abort path changes no decision it would otherwise make. For every other
        # target the failure propagates, because a verdict must never be derived from a
        # set we could not read.
        verifications = _tolerate_if_aborting(
            aborting, [], repository.load_verifications, mission.id
        )

        assert_transition(
            current,
            target,
            authorization,
            now,
            snapshot_sha256,
            verifications,
            mission_id=mission.id,
            paused_from=mission.paused_from_enum,
        )

        _apply(mission, current, target, verifications, now)

        event = events.emit(
            mission,
            _event_type_for(current, target),
            reason or f"{current} -> {target}",
            {
                "kind": "state_changed",
                "from_state": str(current),
                "to_state": str(target),
                "posture": str(posture_for(target)),
                "reason": reason,
            },
            trace_id=trace_id,
            stage=STAGE_FOR_STATE[target],
            state=target,
            status=EventStatus.SUCCEEDED,
            severity=Severity.INFO,
            timestamp=now,
        )
        if _requires_teardown(target):
            transaction.on_commit(
                lambda: _run_teardown_after_commit(
                    mission_id, trace_id=trace_id, reason=reason, now=now
                )
            )
        if target is MissionState.PATCH:
            transaction.on_commit(
                lambda: _start_model_host_after_commit(
                    mission_id, trace_id=trace_id, now=now
                )
            )

    return TransitionResult(
        mission_id=mission.id,
        from_state=current,
        to_state=target,
        sequence=event.sequence,
    )


def _requires_teardown(target: MissionState) -> bool:
    return target is MissionState.CANCELLING or is_terminal(target)


def _run_teardown_after_commit(
    mission_id: UUID, *, trace_id: str, reason: str, now
) -> None:
    """Run synchronously, from `transaction.on_commit` — after the state write this
    function's caller made has already committed, with no transaction left to roll
    back and no caller left on the stack to hand an exception to (Django's own
    `on_commit` contract: a callback that raises does not undo the commit and can
    break any commit hooks queued after it). `teardown.TeardownFailedError` is
    therefore caught and logged here, never left to propagate: `teardown_started_
    compute`'s own docstring guarantees every outcome — including the failed one this
    exception carries — is already durably persisted as a `TEARDOWN_CONFIRMED` event
    before it raises, so catching it here loses no operator-visible information.

    D-069 (`.project/decisions.md`): found while adding the async `TEARDOWN` job path
    for `CANCELLING` (`orchestrator/queue.py`'s `JOB_BACKED_STATES`). Before that
    change this call site was reachable only from `cancel_mission`/`pause_mission`-
    adjacent direct callers of `transition()`; a `TeardownFailedError` raised here
    propagated out of `transition()` itself with no caller expecting it (a `RuntimeError`,
    not the `ContractError` every caller up the stack is written to catch). Once
    `dispatch_terminal_jobs` started driving `CANCELLING -> FAILED` for a mission whose
    real teardown genuinely failed, this same call fires again for the *second* time —
    now for `MissionState.FAILED`, itself teardown-triggering — and an uncaught
    exception there would crash `dispatch_terminal_jobs`'s per-mission loop for every
    other mission in that tick, not just this one. That blast radius is strictly worse
    than the single-mission stall this fix exists to close, so it is fixed here rather
    than left as a newly-reachable, previously-latent bug.
    """
    from orchestrator import teardown

    try:
        teardown.teardown_started_compute(
            mission_id,
            trace_id=trace_id,
            reason=reason or "mission entered teardown state",
            now=now,
        )
    except teardown.TeardownFailedError:
        logger.exception(
            "Synchronous teardown failed for mission %s; already recorded as "
            "TEARDOWN_CONFIRMED event(s) with released=False. Not re-raised: this "
            "runs after commit, with nothing left to roll back and no caller able to "
            "act on it. The async JobKind.TEARDOWN job (if this state is job-backed) "
            "or the next teardown-triggering transition is what still gets the honest "
            "receipt to a policy that can act on it.",
            mission_id,
        )


def _start_model_host_after_commit(mission_id: UUID, *, trace_id: str, now) -> None:
    from orchestrator import model_host

    model_host.start_model_host_lease(mission_id, trace_id=trace_id, now=now)


def _apply(
    mission: Mission,
    current: MissionState,
    target: MissionState,
    verifications: list,
    now,
) -> None:
    """Write the new state and the fields that travel with it."""
    mission.state = str(target)

    if target is MissionState.PAUSED:
        # D-047. Recorded on the way in, because on the way out there is nothing left
        # to read it from. A pause with no origin can only abort.
        if current not in PAUSABLE_STATES:
            raise InvalidStateTransitionError(
                f"{current} is not a state a mission can pause from.",
                details={"current_state": str(current)},
            )
        mission.paused_from = str(current)
    elif current is MissionState.PAUSED:
        mission.paused_from = None

    verdict = VERDICT_FOR_STATE.get(target)
    if verdict is not None:
        mission.verdict = str(verdict)

    fields = ["state", "paused_from", "verdict", "updated_at"]
    if is_terminal(target):
        # A terminal mission never accepts another candidate either. Belt and braces
        # with D-046: the freeze is already on from the first verification, this just
        # means a mission that reached HUMAN_REVIEW before VERIFY ran is closed too.
        if mission.verification_started_at is None:
            mission.verification_started_at = now
        fields.append("verification_started_at")

    mission.save(update_fields=fields)


#: A transition emits exactly one event, and its payload is always `state_changed`.
#: The types below are the ones with a dedicated member in `EventType` whose meaning is
#: *a state change* — so the event rail can label them without a second lookup.
#:
#: `MISSION_VERDICT_RECORDED` is deliberately absent. It carries a
#: `MissionVerdictSummary`, which is the per-candidate breakdown, and the export stage
#: emits it with the real summary attached. Emitting it here with a `state_changed`
#: payload would put the verdict on the wire without the candidates it was derived
#: from, which is the exact reduction `MissionVerdictSummary` exists to prevent.
_EVENT_TYPE_BY_STATE: dict[MissionState, EventType] = {
    MissionState.AUTHORIZED: EventType.MISSION_AUTHORIZED,
    MissionState.SNAPSHOTTED: EventType.SNAPSHOT_RECORDED,
    MissionState.VALIDATING: EventType.PREFLIGHT_COMPLETED,
    MissionState.PAUSED: EventType.MISSION_PAUSED,
    MissionState.CANCELLING: EventType.MISSION_CANCELLED,
    MissionState.CANCELLED: EventType.MISSION_CANCELLED,
    MissionState.FAILED: EventType.MISSION_FAILED,
}


def _event_type_for(current: MissionState, target: MissionState) -> EventType:
    if current is MissionState.PAUSED and target not in {
        MissionState.CANCELLING,
        MissionState.FAILED,
    }:
        return EventType.MISSION_RESUMED
    return _EVENT_TYPE_BY_STATE.get(target, EventType.STATE_CHANGED)


def stage_for(state: MissionState) -> MissionStage | None:
    return STAGE_FOR_STATE[MissionState(state)]
