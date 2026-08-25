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
rediscover the same defect.

## Cluster counts (#30)

A rediscovery of an existing `(mission, fingerprint)` pair is not a pure no-op: it is
real evidence that the same root cause crashed again, so `Finding.crash_count`
increments by one every time this function is called for a fingerprint that already
has a row -- whether the pre-check below finds it, or the `IntegrityError` race
fallback does. This is the "so a hundred crashes on one root cause read as one
finding" half of #30's acceptance criteria: `fingerprint` (see `workers.fuzzing.
dispatch._fingerprint`, derived from the sanitizer's stack signature) is the
dedup key that decides *whether* two crashes cluster, and `crash_count` is the number
that says *how many* raw crashes clustered into this row. No new `MissionEvent` is
emitted on a rediscovery -- `FINDING_RECORDED` still fires exactly once per
fingerprint (existing callers, e.g. `orchestrator/tests/test_findings.py::
test_record_finding_dedupes_by_mission_and_fingerprint`, assert exactly that), and
nothing downstream currently consumes a per-crash event stream; the count is
readable through the normal read path (`FindingSummary.crash_count`,
`evidence_repository._finding_summary`) instead of a new event type. Revisit if a UI
panel needs to animate a cluster growing live rather than reading it on refresh.

SEC-42 (#176) / D-083 §4 / D-086: `Finding` now carries a real database constraint on
`(mission, fingerprint)` (`finding_mission_fingerprint_unique`, `missions/models.py`,
replacing the old non-unique `finding_fp_idx`), matching `BaselineReport`'s
`OneToOneField`/`VerificationRecord.patch`'s `OneToOneField` shape. The mission row
lock still makes the existence-check-then-create sequence race-free for every caller
that goes through this function alone; the constraint is the second line of defence
D-083 §4 flagged as missing, for the same reason `BaselineReport`'s `IntegrityError`
fallback exists for `workers.baseline.dispatch._persist_report` — "not supposed to be
possible" (two callers both passing the pre-flight check) is not the same guarantee as
"structurally prevented here." The `create()` call below is wrapped accordingly.

## `record_reproducer` (D-106)

Closes the gap D-098/D-105 both hit live, twice: no code path anywhere in this
pipeline ever wrote a `Reproducer` row for a `FUZZING_CAMPAIGN`-discovered `Finding`,
so `VERIFY`'s `REPRODUCER_ELIMINATED` gate (`orchestrator/verify_dispatch.py::
_resolve_reproducer_path` -> `orchestrator/verification.py::_run_reproducer`) always
resolved to a sentinel path that does not exist on disk and came back `NOT_RUN`,
capping every verdict at `HUMAN_REVIEW_REQUIRED` regardless of patch correctness.

Mirrors `record_finding` exactly: mission row lock (required by `events.emit`, same
reason `record_finding` takes it even though it writes no `Mission` lifecycle field),
validate against the frozen `contracts.schemas.evidence.ReproducerRecord` schema
before writing, `EventType.REPRODUCER_RECORDED` in the same transaction. Deduplicates
by `(finding, artifact.sha256)` — read in Python off the JSON field, the same way
`_resolve_reproducer_path` itself reads `reproducer.artifact.get("sha256")`, rather
than a JSONField key lookup (portable across the Postgres this project deploys to and
the `sqlite:///:memory:` this project's own test suite runs against) — so a retried
`FUZZ` job that re-enters `workers.fuzzing.dispatch._persist_outcome` (a crash
between recording the `Finding` and recording the `FuzzingReport` re-runs the whole
campaign; see that module's own "Idempotency" docstring) never creates a second
`Reproducer` row for bytes it has already durably recorded once.

`minimized=False` always — this function does not minimize anything, and D-106's own
ruling is explicit that an unminimized-but-real reproducer is honest and sufficient
for `VERIFY`'s gate, which only checks whether the bytes still fault, never whether
they are the smallest input that does.
"""

from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from contracts.enums import (
    AnalyzerTool,
    DiscoveryMethod,
    EventType,
    FindingCategory,
    Severity,
)
from contracts.schemas.common import ArtifactRef
from contracts.schemas.evidence import FindingSummary, ReproducerRecord, SourceLocation
from missions.models import Finding, Mission, Reproducer
from orchestrator import events

__all__ = ["record_finding", "record_reproducer"]


def _bump_crash_count(finding: Finding) -> Finding:
    """Record one more raw crash occurrence clustered into `finding` (#30).

    Called under the mission row lock `record_finding` already holds (both call
    sites), so a plain `F("crash_count") + 1` update is race-free for the normal
    case; it is still used (rather than a Python `+= 1`) because it also protects the
    `IntegrityError` fallback, which reads `finding` from a fresh query rather than
    from a row this transaction already holds a lock on.
    """
    Finding.objects.filter(pk=finding.pk).update(crash_count=F("crash_count") + 1)
    finding.refresh_from_db(fields=["crash_count"])
    return finding


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
            return _bump_crash_count(existing)

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

        try:
            with transaction.atomic():
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
        except IntegrityError:
            # Someone else's write won the race for (mission, fingerprint) — the
            # mission row lock above should make this unreachable for any caller that
            # goes through `record_finding` alone, but "not supposed to be possible"
            # is not the same guarantee as "structurally prevented here" (see this
            # module's docstring, "Idempotency"). Report *their* row, not ours, and
            # emit no event — the winning call already emitted one. The savepoint
            # above has already been rolled back by the time we get here, so this
            # query runs against a clean transaction state. This call is itself real
            # evidence of a rediscovered crash, so it still counts toward the cluster
            # (#30) even though it lost the race to create the row.
            winner = Finding.objects.get(mission=mission, fingerprint=fingerprint)
            return _bump_crash_count(winner)

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


def record_reproducer(
    finding_id: UUID,
    *,
    sha256: str,
    size_bytes: int,
    uri: str,
    test_command: str,
    trace_id: str,
    kind: str = "reproducer_input",
    replay_attempts: int = 0,
    replay_successes: int = 0,
    minimized: bool = False,
    now: Any = None,
) -> Reproducer:
    """Persist one real reproducer for an existing `Finding`, or return the existing
    row for the same `(finding, sha256)` pair. See this module's docstring, "D-106".

    `replay_attempts`/`replay_successes` default to `0` — honest, since this function
    does not itself run a confirming replay (D-106's own ruling names that as
    optional, not required: `VERIFY`'s `_run_reproducer` gate does its own live
    replay against these bytes and does not read either field). A caller that *did*
    run a confirming replay before calling this may pass real counts.
    """
    now = now or timezone.now()

    with transaction.atomic():
        finding = Finding.objects.select_related("mission").get(pk=finding_id)
        mission = Mission.objects.select_for_update().get(pk=finding.mission_id)

        for existing in finding.reproducers.all():
            if (existing.artifact or {}).get("sha256") == sha256:
                return existing

        schema = ReproducerRecord(
            id=uuid.uuid4(),
            finding_id=finding.id,
            minimized=minimized,
            replay_attempts=replay_attempts,
            replay_successes=replay_successes,
            test_command=test_command,
            artifact=ArtifactRef(uri=uri, kind=kind, sha256=sha256, size_bytes=size_bytes),
            created_at=now,
        )

        try:
            with transaction.atomic():
                row = Reproducer.objects.create(
                    id=schema.id,
                    finding=finding,
                    minimized=schema.minimized,
                    replay_attempts=schema.replay_attempts,
                    replay_successes=schema.replay_successes,
                    test_command=schema.test_command,
                    artifact=schema.artifact.model_dump(mode="json"),
                    created_at=schema.created_at,
                )
        except IntegrityError:
            # Same discipline as `record_finding`'s own fallback: not supposed to be
            # reachable under the mission row lock above, but report the winning
            # write rather than propagate a race neither caller could have avoided.
            for existing in finding.reproducers.all():
                if (existing.artifact or {}).get("sha256") == sha256:
                    return existing
            raise

        events.emit(
            mission,
            EventType.REPRODUCER_RECORDED,
            f"Reproducer recorded for finding {finding.id}.",
            {"kind": "reproducer", "reproducer": schema.model_dump(mode="json")},
            trace_id=trace_id,
            severity=Severity.INFO,
            timestamp=now,
        )

    return row
