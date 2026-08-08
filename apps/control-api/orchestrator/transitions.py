"""The only writer of `Mission.state`.

Every transition is one transaction: take `SELECT … FOR UPDATE` on the mission row,
load the evidence, run the guards, write the new state, append the event. One
transaction per transition rather than per tick, so a crash mid-tick leaves the mission
exactly where the database says it is and never half-moved.

## Why the guards are called from *here* and not from the API layer

`contracts.state_machine.assert_verdict_is_evidenced` is a pure function over the
records it is handed. It checks that each record is a real `VerificationRecord`, belongs
to this mission, and derives the verdict being claimed. It cannot check that it was
shown **all** of them — dropping a `REJECTED` record before the call is invisible from
inside a function given only what it was given (D-045, and BUG-004(c) which QA
reproduced by execution).

No validation in `contracts/` closes that. The completeness guarantee lives at the
database boundary because that is the only place it can live. See the call site below.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.db import transaction
from django.utils import timezone

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
from missions.models import Mission
from orchestrator import events, repository


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

    with transaction.atomic():
        # The lock. Everything below reads and writes under it, which is what makes
        # the sequence allocation gap-free and the evidence load complete.
        mission = Mission.objects.select_for_update().get(pk=mission_id)
        current = mission.state_enum

        authorization = repository.load_active_authorization(mission, now)
        snapshot_sha256 = repository.latest_snapshot_sha256(mission)

        # ---------------------------------------------------------------------
        # D-045, the load-bearing part. `verifications` is loaded HERE, by mission
        # id, inside the transaction that holds the row lock — it is never a
        # parameter this function accepts and never something a caller assembles.
        #
        # `assert_verdict_is_evidenced` can prove every record it is shown is real,
        # belongs to this mission and derives the claimed verdict. It CANNOT prove it
        # was shown all of them: a caller that quietly drops the REJECTED record
        # reaches VERIFIED and nothing inside a pure function can tell. That is why
        # the load lives at the database boundary and not in `contracts/`.
        #
        # If a future refactor moves this load out of the transaction, or lets a
        # caller pass the records in, invariant B ("no verdict against the evidence")
        # silently becomes "no verdict without *some* evidence" — which is a
        # different and much weaker claim, with no test failure to announce it.
        # `orchestrator/tests/test_verdict_completeness.py` is the test that fails.
        # ---------------------------------------------------------------------
        verifications = repository.load_verifications(mission.id)

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

    return TransitionResult(
        mission_id=mission.id,
        from_state=current,
        to_state=target,
        sequence=event.sequence,
    )


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
