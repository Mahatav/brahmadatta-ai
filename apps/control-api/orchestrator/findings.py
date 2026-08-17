"""Recording findings discovered during `STRESS_TEST` (#168, T2).

## The gap this closes

D-061 §5 (`.project/decisions.md`) named it directly: *"No `Finding`-recording
function exists anywhere — fuzzing crashes never become `Finding` rows today."*
`missions.models.Finding` is a real, migrated model, already read by
`orchestrator.evidence_repository.list_findings`/`get_finding_detail` (the read side
of #32, already exercised by the evidence router) and already referenced by
`orchestrator/tests/conftest.py`'s own `finding` fixture — but until this module,
nothing on the *write* side ever produced one outside a test creating the row by
hand. A crash a live libFuzzer campaign captures has never durably become the kind
of row `CORRELATE`/`VERIFY`/`EXPORT` can bind a patch or an evidence bundle to.

## The pattern this mirrors

`orchestrator.candidates.record_patch_candidate` / `record_verification`: lock the
mission row, validate against the frozen `contracts.schemas.evidence.FindingSummary`
schema before writing anything, create the row, emit the matching `MissionEvent`
inside the same transaction (`orchestrator.events.emit` requires exactly that — see
its own docstring — which is why this function takes the mission lock even though,
unlike those two, it writes no `Mission` lifecycle field and enforces no D-046-shaped
freeze).

## Idempotency

Deduplicates by `(mission, fingerprint)` under the mission row lock, not by any
caller-supplied id. This is the FUZZ-shaped instance of D-061 §3 rule 2's "check for
your stage's own terminal artifact before doing real work": a worker that crashed
after this function committed but before its `Job` row reached a terminal state must
not produce a second `Finding` row for the same underlying crash on retry, and a
`FUZZ` job's own `MAX_ATTEMPTS_BY_KIND` of 2 means a second attempt genuinely can
rediscover the same defect. Unlike `BaselineReport`'s `OneToOneField` or
`VerificationRecord.patch`'s `OneToOneField`, `Finding` carries no unique database
constraint on `(mission, fingerprint)` — only a non-unique index
(`finding_fp_idx`, `missions/models.py`). The mission row lock is what makes the
existence-check-then-create sequence race-free here instead of a database
constraint backing it up the way `BaselineReport`'s `IntegrityError` fallback does
for `workers.baseline.dispatch._persist_report`; flagged for database-engineer as a
schema hardening worth considering, not applied here (schema is not this role's to
change — see this repo's own division of authority).
"""

from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from contracts.enums import (
    AnalyzerTool,
    DiscoveryMethod,
    EventType,
    FindingCategory,
    Severity,
)
from contracts.schemas.evidence import FindingSummary, SourceLocation
from missions.models import Finding, Mission
from orchestrator import events

__all__ = ["record_finding"]


def record_finding(
    mission_id: UUID,
    *,
    category: FindingCategory,
    severity: Severity,
    tool: AnalyzerTool,
    discovery_method: DiscoveryMethod,
    file_path: str,
    fingerprint: str,
    title: str,
    detected_at: Any,
    line: int | None = None,
    function: str | None = None,
    replay_source: str | None = None,
    reproducible: bool = False,
    sanitizer_report: str = "",
    code_slice: str = "",
    trace_id: str,
    now: Any = None,
) -> Finding:
    """Persist one finding, or return the existing row for the same
    `(mission, fingerprint)` pair.

    `code_slice`/`sanitizer_report` are truncated to `Finding`'s own field limits
    (20000 chars, `missions/models.py`) rather than raising — a caller quoting more
    sanitizer output than fits is a formatting mismatch, not a reason to lose the
    finding. Never raw repository content, never a secret — same rule as
    `Job.payload`/`Job.result` (`orchestrator/executors.py`'s own docstring); callers
    are responsible for redaction before this boundary, this function does not scan
    for one.
    """
    now = now or timezone.now()

    with transaction.atomic():
        mission = Mission.objects.select_for_update().get(pk=mission_id)

        existing = Finding.objects.filter(mission=mission, fingerprint=fingerprint).first()
        if existing is not None:
            return existing

        schema = FindingSummary(
            id=uuid.uuid4(),
            mission_id=mission.id,
            category=category,
            severity=severity,
            tool=tool,
            discovery_method=discovery_method,
            replay_source=replay_source,
            location=SourceLocation(file_path=file_path, line=line, function=function),
            fingerprint=fingerprint,
            reproducible=reproducible,
            detected_at=detected_at,
            title=title,
        )

        row = Finding.objects.create(
            id=schema.id,
            mission=mission,
            category=str(schema.category),
            severity=str(schema.severity),
            tool=str(schema.tool),
            discovery_method=str(schema.discovery_method),
            replay_source=schema.replay_source,
            file_path=schema.location.file_path,
            line=schema.location.line,
            function=schema.location.function,
            fingerprint=schema.fingerprint,
            reproducible=schema.reproducible,
            title=schema.title,
            sanitizer_report=sanitizer_report[:20000],
            code_slice=code_slice[:20000],
            detected_at=schema.detected_at,
        )

        events.emit(
            mission,
            EventType.FINDING_RECORDED,
            f"Finding recorded: {schema.title}.",
            {"kind": "finding", "finding": schema.model_dump(mode="json")},
            trace_id=trace_id,
            severity=severity,
            timestamp=now,
        )

    return row
