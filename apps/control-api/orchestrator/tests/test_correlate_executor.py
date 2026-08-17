"""`JobKind.CORRELATE` executor (#168, T3) — the two signals it reads, and the
priority between them. See `orchestrator/correlate_executor.py`'s own module
docstring for the full reasoning; this file proves it.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from contracts.enums import FindingCategory
from missions.models import Finding, Job, JobKind, JobState, Mission
from orchestrator.executors import ExecutorContext, JobOutcome, executor_for
from orchestrator.tests.conftest import NOW, TRACE

pytestmark = pytest.mark.django_db(transaction=True)


def _ctx(mission: Mission) -> ExecutorContext:
    return ExecutorContext(
        job=Job(mission=mission, kind=JobKind.CORRELATE, state=JobState.RUNNING),
        mission=mission,
        source_dir=Path("."),
        workspace_root=Path("."),
        trace_id=TRACE,
        cancel_requested=lambda: False,
    )


def _terminal_fuzz_job(mission: Mission, *, crashes_found: int, state=JobState.SUCCEEDED) -> Job:
    return Job.objects.create(
        mission=mission,
        kind=JobKind.FUZZ,
        state=state,
        result={"crashes_found": crashes_found},
        run_after=NOW,
        deadline_at=NOW + timedelta(hours=1),
        finished_at=NOW,
    )


def test_reports_nothing_to_correlate_when_no_finding_and_no_fuzz_job(mission):
    """The common no-signal case: nothing recorded, and no FUZZ job to fall back to
    (e.g. a mission driven straight into CORRELATE by a test's own `walk_to`)."""
    result = executor_for(JobKind.CORRELATE)(_ctx(mission))
    assert result.outcome is JobOutcome.SUCCEEDED
    assert result.result["correlated"] is False
    assert result.result["source"] == "no_signal"
    assert result.result["finding_count"] == 0


def test_reports_nothing_to_correlate_when_fuzz_job_reports_zero_crashes(mission):
    _terminal_fuzz_job(mission, crashes_found=0)
    result = executor_for(JobKind.CORRELATE)(_ctx(mission))
    assert result.outcome is JobOutcome.SUCCEEDED
    assert result.result["correlated"] is False
    assert result.result["source"] == "no_signal"
    assert result.result["crashes_found"] == 0


def test_falls_back_to_raw_fuzz_crashes_found_when_no_finding_rows_exist(mission):
    """T2 has not landed `record_finding` yet — see this module's docstring. The
    fallback signal is the same `crashes_found` key `_fuzz_transition_policy` already
    treats as the provisional FUZZ/CORRELATE contract."""
    _terminal_fuzz_job(mission, crashes_found=3)
    result = executor_for(JobKind.CORRELATE)(_ctx(mission))
    assert result.outcome is JobOutcome.SUCCEEDED
    assert result.result["correlated"] is True
    assert result.result["source"] == "fuzz_result_crashes_found"
    assert result.result["crashes_found"] == 3
    assert result.result["finding_ids"] == []


def test_uses_finding_rows_when_present(mission, finding: Finding):
    result = executor_for(JobKind.CORRELATE)(_ctx(mission))
    assert result.outcome is JobOutcome.SUCCEEDED
    assert result.result["correlated"] is True
    assert result.result["source"] == "finding_rows"
    assert result.result["finding_count"] == 1
    assert result.result["finding_ids"] == [str(finding.id)]


def test_finding_rows_take_priority_over_a_conflicting_raw_crash_count(mission, finding: Finding):
    """A `Finding` row is the authoritative signal (it's what `PATCH_GENERATE` actually
    needs a `finding_id` for) — present even alongside a zero-crash FUZZ result, it
    still wins."""
    _terminal_fuzz_job(mission, crashes_found=0)
    result = executor_for(JobKind.CORRELATE)(_ctx(mission))
    assert result.result["correlated"] is True
    assert result.result["source"] == "finding_rows"


def test_does_not_leak_another_missions_finding_rows(mission):
    """SEC-15's own discipline, applied here: a `Finding` belonging to a different
    mission must never make this mission's CORRELATE decision for it."""
    other = Mission.objects.create(
        name="another mission",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter="C_CMAKE_CTEST",
        policy={},
    )
    Finding.objects.create(
        mission=other,
        category=FindingCategory.HEAP_BUFFER_OVERFLOW.value,
        severity="HIGH",
        tool="ADDRESS_SANITIZER",
        discovery_method="FUZZING_CAMPAIGN",
        file_path="src/decode.c",
        line=74,
        fingerprint="other-missions-finding",
        reproducible=True,
        title="a different mission's finding entirely",
        detected_at=NOW,
    )

    result = executor_for(JobKind.CORRELATE)(_ctx(mission))

    assert result.result["correlated"] is False
    assert result.result["source"] == "no_signal"
    assert result.result["finding_count"] == 0
