"""Event emission, and the gap-free sequence counter.

`MissionEvent.sequence` is the SSE `id:` field and the input to the Command Center's
gap detection: a client that sees a jump replays from its last known value. That only
works if the counter never gaps, which rules out a Postgres sequence (they gap on
rollback) and rules out `max(sequence) + 1` computed outside a lock (two writers get
the same answer).

So allocation happens here, and only here, and only while the caller already holds
`SELECT … FOR UPDATE` on the mission row. `unique_together(mission, sequence)` is the
backstop that turns a mistake into an `IntegrityError` rather than a silently reused
ordinal.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from contracts.enums import EventStatus, EventType, MissionStage, MissionState, Severity
from missions.models import Mission, MissionEvent


def next_sequence(mission: Mission) -> int:
    """The next gap-free ordinal for this mission.

    Caller must already hold the mission row lock. `select_for_update` is not repeated
    here because re-locking a row inside the same transaction would read as though the
    lock were this function's job — it is the transaction's.
    """
    current = MissionEvent.objects.filter(mission=mission).aggregate(
        high=Max("sequence")
    )["high"]
    return (current or 0) + 1


def emit(
    mission: Mission,
    event_type: EventType,
    message: str,
    payload: dict[str, Any],
    *,
    trace_id: str,
    stage: MissionStage | None = None,
    state: MissionState | None = None,
    status: EventStatus = EventStatus.SUCCEEDED,
    severity: Severity = Severity.INFO,
    evidence_refs: list[str] | None = None,
    metrics: dict[str, float] | None = None,
    timestamp=None,
) -> MissionEvent:
    """Append one event. Must run inside the transaction holding the mission lock."""
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError(
            "emit() allocates a gap-free sequence and must run inside the transaction "
            "that holds SELECT ... FOR UPDATE on the mission row."
        )

    return MissionEvent.objects.create(
        mission=mission,
        sequence=next_sequence(mission),
        timestamp=timestamp or timezone.now(),
        type=str(event_type),
        stage=str(stage) if stage else None,
        state=str(state or mission.state),
        status=str(status),
        severity=str(severity),
        message=message[:1000],
        payload=payload,
        evidence_refs=evidence_refs or [],
        metrics=metrics or {},
        trace_id=trace_id,
    )
