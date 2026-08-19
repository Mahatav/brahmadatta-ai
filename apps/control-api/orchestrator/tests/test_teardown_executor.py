"""`JobKind.TEARDOWN` executor + transition policy (#168, T7).

Three behaviours this file exists to prove, named in the T7 task brief:

1. A clean teardown reports `SUCCEEDED` with a full, itemised receipt.
2. A partial failure is reported honestly — `outcome=FAILED`, but `result` names
   exactly which resource(s) released and which did not, never an all-or-nothing bit
   that could hide a real leak.
3. Re-running teardown against a mission that has nothing left to release is a safe
   no-op, not an error — same guarantee `orchestrator/tests/test_teardown.py` already
   proves for the underlying mechanism, exercised here through the executor itself.

Plus the transition-policy half: R3 (`CANCELLING -> CANCELLED` only with a receipt,
else `-> FAILED`), and that every other teardown-triggering target is left alone
(`None`) because it is already terminal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest

from contracts.enums import ErrorCode, EventType, MissionState
from missions.models import Job, JobKind, JobState, Mission, MissionEvent
from orchestrator import executors, teardown, transitions
from orchestrator.executors import ExecutorContext, JobOutcome
from orchestrator.teardown_executor import teardown_executor, teardown_transition_policy
from orchestrator.tests.conftest import NOW, TRACE, walk_to

pytestmark = pytest.mark.django_db(transaction=True)


@dataclass
class FakeReaper:
    outcomes: tuple[teardown.TeardownOutcome, ...] = ()
    fail: Exception | None = None
    resource_kind: str = "sandbox"

    def teardown_mission(self, mission_id: UUID):
        if self.fail is not None:
            raise self.fail
        return self.outcomes


def _job(mission: Mission, *, state: str = JobState.RUNNING, result: dict | None = None) -> Job:
    return Job.objects.create(
        mission=mission,
        kind=JobKind.TEARDOWN,
        state=state,
        payload={},
        result=result or {},
        attempt=1,
        max_attempts=3,
        run_after=NOW,
        deadline_at=NOW + timedelta(minutes=5),
    )


def _ctx(job: Job, mission: Mission) -> ExecutorContext:
    # TEARDOWN never touches the snapshot; these two paths are never read.
    return ExecutorContext(
        job=job,
        mission=mission,
        source_dir=Path("/tmp/unused-source"),
        workspace_root=Path("/tmp/unused-workspace"),
        trace_id=TRACE,
        cancel_requested=lambda: False,
    )


def _outcome(resource_id: str, *, kind: str = "sandbox", released: bool = True) -> teardown.TeardownOutcome:
    return teardown.TeardownOutcome(
        resource_kind=kind, resource_id=resource_id, released=released, detail="mock"
    )


# --------------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------------


def test_teardown_is_registered_against_the_shared_contract():
    assert executors.executor_for(JobKind.TEARDOWN) is teardown_executor
    assert executors.transition_policy_for(JobKind.TEARDOWN) is teardown_transition_policy


# --------------------------------------------------------------------------------
# Executor: success, partial failure, idempotent re-run
# --------------------------------------------------------------------------------


def test_executor_reports_full_success(monkeypatch, mission):
    reaper = FakeReaper((_outcome("sandbox-1"), _outcome("model-host-1", kind="model-host")))
    monkeypatch.setattr(teardown, "default_reapers", lambda: (reaper,))

    job = _job(mission)
    result = teardown_executor(_ctx(job, mission))

    assert result.outcome is JobOutcome.SUCCEEDED
    assert result.error_code is None
    assert result.result["released_count"] == 2
    assert result.result["failed_count"] == 0
    assert result.result["total"] == 2
    assert {o["resource_id"] for o in result.result["outcomes"]} == {
        "sandbox-1",
        "model-host-1",
    }
    assert "zero leaked" in result.detail


def test_executor_reports_partial_failure_honestly(monkeypatch, mission):
    reaper = FakeReaper(
        (
            _outcome("sandbox-1", released=True),
            _outcome("sandbox-2", released=False),
            _outcome("model-host-1", kind="model-host", released=True),
        )
    )
    monkeypatch.setattr(teardown, "default_reapers", lambda: (reaper,))

    job = _job(mission)
    result = teardown_executor(_ctx(job, mission))

    # Not an all-or-nothing bit: outcome is FAILED, but the honest fraction survives
    # in `result`, not collapsed away.
    assert result.outcome is JobOutcome.FAILED
    assert result.error_code is ErrorCode.INTERNAL_ERROR
    assert result.result["released_count"] == 2
    assert result.result["failed_count"] == 1
    assert result.result["total"] == 3
    failed_ids = {o["resource_id"] for o in result.result["outcomes"] if not o["released"]}
    assert failed_ids == {"sandbox-2"}
    released_ids = {o["resource_id"] for o in result.result["outcomes"] if o["released"]}
    assert released_ids == {"sandbox-1", "model-host-1"}
    assert "2 of 3" in result.detail and "1 failed" in result.detail
    # Nothing here is swallowed: the event stream also carries the failed resource.
    assert MissionEvent.objects.filter(
        mission=mission,
        type=EventType.TEARDOWN_CONFIRMED,
        payload__resource_id="sandbox-2",
        payload__released=False,
    ).exists()


def test_executor_reports_infra_fault_as_retryable_failure(monkeypatch, mission):
    def _boom(*args, **kwargs):
        raise RuntimeError("database unreachable")

    monkeypatch.setattr(teardown, "teardown_started_compute", _boom)

    job = _job(mission, result={})
    result = teardown_executor(_ctx(job, mission))

    assert result.outcome is JobOutcome.FAILED
    assert result.result["infra_failure"] is True
    assert result.retry is True  # attempt(1) < max_attempts(3)


def test_second_teardown_run_is_a_safe_no_op(monkeypatch, mission):
    """Idempotency (D-061 §3's TEARDOWN-shaped obligation): re-running teardown on a
    mission with nothing left to release must not raise or report a fake failure.

    SEC-42 (#176) / D-086: `job_mission_kind_unique` makes a second literal `Job` row
    for `(mission, TEARDOWN)` impossible, matching production reality — a re-run
    reuses the *same* row, it never gets a new one. Both calls below run against one
    `job` instead of the pre-fix version's two separately created rows.
    """
    reaper = FakeReaper(())  # nothing found to release, same as a real empty reaper
    monkeypatch.setattr(teardown, "default_reapers", lambda: (reaper,))

    job = _job(mission)
    first = teardown_executor(_ctx(job, mission))
    second = teardown_executor(_ctx(job, mission))

    for result in (first, second):
        assert result.outcome is JobOutcome.SUCCEEDED
        assert result.result["failed_count"] == 0
        assert result.result["total"] == 1
        assert result.result["outcomes"][0]["resource_id"] == "no-started-compute"


# --------------------------------------------------------------------------------
# Transition policy: R3
# --------------------------------------------------------------------------------


def test_policy_routes_cancelling_to_cancelled_with_a_full_receipt(mission):
    walk_to(mission, MissionState.STRESS_TEST)
    transitions.transition(
        mission.id, MissionState.CANCELLING, trace_id=TRACE, reason="operator cancel", now=NOW
    )
    mission.refresh_from_db()

    job = _job(
        mission,
        state=JobState.SUCCEEDED,
        result={"total": 1, "released_count": 1, "failed_count": 0, "outcomes": []},
    )

    assert teardown_transition_policy(job, mission) is MissionState.CANCELLED


def test_policy_routes_cancelling_to_failed_without_a_receipt(mission):
    walk_to(mission, MissionState.STRESS_TEST)
    transitions.transition(
        mission.id, MissionState.CANCELLING, trace_id=TRACE, reason="operator cancel", now=NOW
    )
    mission.refresh_from_db()

    job = _job(
        mission,
        state=JobState.SUCCEEDED,
        result={"total": 2, "released_count": 1, "failed_count": 1, "outcomes": []},
    )

    assert teardown_transition_policy(job, mission) is MissionState.FAILED


def test_policy_treats_a_non_succeeded_job_as_no_receipt_even_with_a_clean_result(mission):
    """A TIMED_OUT/CANCELLED job never gets the benefit of the doubt, even if `result`
    happens to look complete (e.g. it was written just before the deadline fired)."""
    walk_to(mission, MissionState.STRESS_TEST)
    transitions.transition(
        mission.id, MissionState.CANCELLING, trace_id=TRACE, reason="operator cancel", now=NOW
    )
    mission.refresh_from_db()

    job = _job(
        mission,
        state=JobState.TIMED_OUT,
        result={"total": 1, "released_count": 1, "failed_count": 0, "outcomes": []},
    )

    assert teardown_transition_policy(job, mission) is MissionState.FAILED


def test_policy_treats_a_missing_result_as_no_receipt(mission):
    walk_to(mission, MissionState.STRESS_TEST)
    transitions.transition(
        mission.id, MissionState.CANCELLING, trace_id=TRACE, reason="operator cancel", now=NOW
    )
    mission.refresh_from_db()

    job = _job(mission, state=JobState.SUCCEEDED, result={})

    assert teardown_transition_policy(job, mission) is MissionState.FAILED


def test_policy_returns_none_for_an_already_terminal_mission(mission):
    """VERIFIED/REJECTED/HUMAN_REVIEW/FAILED/CANCELLED all have no outgoing edge —
    nothing further for a terminal TEARDOWN job to route to."""
    walk_to(mission, MissionState.BASELINE)
    transitions.transition(
        mission.id, MissionState.FAILED, trace_id=TRACE, reason="stage failed", now=NOW
    )
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.FAILED

    job = _job(
        mission,
        state=JobState.SUCCEEDED,
        result={"total": 1, "released_count": 1, "failed_count": 0, "outcomes": []},
    )

    assert teardown_transition_policy(job, mission) is None
