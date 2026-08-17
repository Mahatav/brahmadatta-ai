"""The wiring D-069 adds: `MissionState.CANCELLING` is now a row in
`orchestrator.queue.JOB_BACKED_STATES`, closing the gap PR #173's engineering-manager
review found — `teardown_transition_policy` (D-068) was correct and fully tested but
unreachable, because nothing ever enqueued a `TEARDOWN` job for a mission sitting in
`CANCELLING`, so `dispatch_terminal_jobs` never had a terminal job to route. This is the
literal mechanism behind `.project/evidence/d7-gate-50-live-run-2026-08-17.md`'s repro: a
mission cancelled and stuck in `CANCELLING` forever.

Mirrors `test_stress_test_routing.py`'s own shape (D-061 §2's `FUZZ` end-to-end test) per
the engineering-manager review's explicit ask: "Once finding 1's wiring lands, I'd want a
`dispatch_terminal_jobs`-level test added alongside it" — the existing
`test_teardown_executor.py` routing tests call `teardown_transition_policy(job, mission)`
directly because, before this fix, there was no real path to exercise end to end. Now
there is; this file exercises it through the real dispatcher.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest import mock
from uuid import UUID

import pytest

from contracts.enums import EventType, MissionState
from missions.models import Job, JobKind, JobState, MissionEvent
from orchestrator import executors, queue, teardown, transitions
from orchestrator.executors import ExecutorContext, JobOutcome
from orchestrator.tests.conftest import NOW, TRACE, walk_to

pytestmark = pytest.mark.django_db(transaction=True)


@dataclass
class FakeReaper:
    outcomes: tuple[teardown.TeardownOutcome, ...] = ()
    resource_kind: str = "sandbox"
    calls: list[UUID] | None = None

    def teardown_mission(self, mission_id: UUID):
        if self.calls is not None:
            self.calls.append(mission_id)
        return self.outcomes


def _outcome(resource_id: str, *, released: bool = True) -> teardown.TeardownOutcome:
    return teardown.TeardownOutcome(
        resource_kind="sandbox", resource_id=resource_id, released=released, detail="mock"
    )


def _run_real_teardown_job(job: Job, mission) -> Job:
    """Claim, run through the real `TEARDOWN` executor, and complete a job — the same
    sequence `manage.py run_worker` performs, not a stand-in for it."""
    claimed = queue.claim_job("test-worker-1", now=NOW)
    assert claimed is not None and claimed.id == job.id
    assert queue.mark_running(claimed.id, "test-worker-1", now=NOW)

    executor = executors.executor_for(JobKind.TEARDOWN)
    ctx = ExecutorContext(
        job=claimed,
        mission=mission,
        source_dir=Path("/tmp/unused-source"),
        workspace_root=Path("/tmp/unused-workspace"),
        trace_id=TRACE,
        cancel_requested=lambda: False,
    )
    result = executor(ctx)

    job_state = JobState.SUCCEEDED if result.outcome is JobOutcome.SUCCEEDED else JobState.FAILED
    assert queue.complete_job(
        claimed.id, "test-worker-1", job_state, result=result.result, now=NOW
    )
    claimed.refresh_from_db()
    return claimed


# ------------------------------------------------------------------------------------
# Enqueue: the first half of the wiring
# ------------------------------------------------------------------------------------


def test_cancelling_is_now_a_job_backed_state():
    assert queue.JOB_BACKED_STATES[MissionState.CANCELLING] is JobKind.TEARDOWN


def test_a_mission_entering_cancelling_gets_a_teardown_job_enqueued(monkeypatch, mission):
    monkeypatch.setattr(teardown, "default_reapers", lambda: (FakeReaper(),))
    walk_to(mission, MissionState.STRESS_TEST)

    transitions.transition(
        mission.id, MissionState.CANCELLING, trace_id=TRACE, reason="operator cancel", now=NOW
    )
    assert not Job.objects.filter(mission=mission, kind=JobKind.TEARDOWN).exists()

    enqueued = queue.ensure_jobs_enqueued(now=NOW)

    assert [job.mission_id for job in enqueued] == [mission.id]
    job = Job.objects.get(mission=mission, kind=JobKind.TEARDOWN)
    assert job.state == JobState.QUEUED
    assert job.max_attempts == 3  # MAX_ATTEMPTS_BY_KIND[JobKind.TEARDOWN]


def test_ensure_jobs_enqueued_never_double_enqueues_teardown(monkeypatch, mission):
    monkeypatch.setattr(teardown, "default_reapers", lambda: (FakeReaper(),))
    walk_to(mission, MissionState.STRESS_TEST)
    transitions.transition(
        mission.id, MissionState.CANCELLING, trace_id=TRACE, reason="operator cancel", now=NOW
    )

    queue.ensure_jobs_enqueued(now=NOW)
    second = queue.ensure_jobs_enqueued(now=NOW)

    assert second == []
    assert Job.objects.filter(mission=mission, kind=JobKind.TEARDOWN).count() == 1


# ------------------------------------------------------------------------------------
# End to end: cancel -> enqueue -> real worker -> real dispatch -> CANCELLED/FAILED
# ------------------------------------------------------------------------------------


def test_cancelling_walks_all_the_way_to_cancelled_through_the_real_worker_path_with_both_teardown_paths_running(
    monkeypatch, mission
):
    """The actual #50 repro, closed for real. Not the policy called directly — the real
    `queue.tick()`-shaped path: `transition()` (which fires the synchronous
    `_run_teardown_after_commit` hook, D-069 decision 2's kept-alongside path),
    `ensure_jobs_enqueued`, a real `claim_job`/`mark_running`/`complete_job` cycle
    against the actual `TEARDOWN` executor, then `dispatch_terminal_jobs` calling the
    real `transitions.transition()` off its terminal result.

    Also proves D-069 decision 2's safety claim directly, not just in prose: the fake
    reaper's `teardown_mission` is called exactly twice — once by the synchronous hook
    at the moment `CANCELLING` commits, once by the real executor run through the job
    queue — and the mission still reaches `CANCELLED` cleanly.
    """
    calls: list[UUID] = []
    reaper = FakeReaper((_outcome("cancel-sandbox-1"),), calls=calls)
    monkeypatch.setattr(teardown, "default_reapers", lambda: (reaper,))

    walk_to(mission, MissionState.STRESS_TEST)

    transitions.transition(
        mission.id, MissionState.CANCELLING, trace_id=TRACE, reason="operator cancel", now=NOW
    )
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.CANCELLING
    assert calls == [mission.id]  # the synchronous hook already ran, for real

    enqueued = queue.ensure_jobs_enqueued(now=NOW)
    assert len(enqueued) == 1
    job = Job.objects.get(mission=mission, kind=JobKind.TEARDOWN)

    completed = _run_real_teardown_job(job, mission)
    assert completed.state == JobState.SUCCEEDED
    # The synchronous hook already released everything for real; the async run finds
    # nothing left and reports the synthetic no-started-compute receipt — still a real
    # receipt, per teardown_transition_policy's own has_receipt check.
    assert completed.result["total"] == 1
    assert completed.result["failed_count"] == 0
    assert calls == [mission.id, mission.id]  # called again, by the real worker path

    advanced = queue.dispatch_terminal_jobs(trace_id=TRACE, now=NOW)

    assert advanced == [mission.id]
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.CANCELLED


def test_cancelling_routes_to_failed_when_the_teardown_job_itself_reports_a_leak(
    monkeypatch, mission
):
    """R3's other branch, end to end: a `TEARDOWN` job that genuinely fails to release a
    resource must route `CANCELLING -> FAILED`, never leave the mission stuck and never
    silently claim `CANCELLED`.

    Nothing was running yet at cancel time (no sandbox/model-host lease started), so the
    synchronous hook's own run is a clean, resource-free no-op — realistic (a mission can
    be cancelled before `PATCH` ever starts a model-host lease, say) and avoids a separate,
    pre-existing gap this test run surfaced: `_run_teardown_after_commit` does not catch
    `teardown.TeardownFailedError`, so a reaper that fails *synchronously*, at the moment
    `CANCELLING` commits, raises out of `transitions.transition()` itself rather than being
    reported as an event and swallowed — flagged in this fix's handoff as a pre-existing
    issue in code this task does not own, not fixed here. The failure this test exercises
    is the one that matters for R3: the resource fails to release when the real worker
    later runs the `TEARDOWN` job.
    """
    monkeypatch.setattr(teardown, "default_reapers", lambda: (FakeReaper(),))
    walk_to(mission, MissionState.STRESS_TEST)
    transitions.transition(
        mission.id, MissionState.CANCELLING, trace_id=TRACE, reason="operator cancel", now=NOW
    )
    queue.ensure_jobs_enqueued(now=NOW)
    job = Job.objects.get(mission=mission, kind=JobKind.TEARDOWN)

    failing_reaper = FakeReaper((_outcome("stuck-sandbox", released=False),))
    monkeypatch.setattr(teardown, "default_reapers", lambda: (failing_reaper,))

    completed = _run_real_teardown_job(job, mission)
    assert completed.state == JobState.FAILED
    assert completed.result["failed_count"] == 1

    advanced = queue.dispatch_terminal_jobs(trace_id=TRACE, now=NOW)

    assert advanced == [mission.id]
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.FAILED


def test_a_full_tick_drives_cancelling_to_a_queued_teardown_job(monkeypatch, mission):
    """`queue.tick()` itself — the function `manage.py run_orchestrator` actually calls
    in a loop — enqueues the `TEARDOWN` job for a `CANCELLING` mission in the same pass,
    mirroring `test_queue_tick.py`'s own coverage for every other job-backed state."""
    monkeypatch.setattr(teardown, "default_reapers", lambda: (FakeReaper(),))
    walk_to(mission, MissionState.STRESS_TEST)
    transitions.transition(
        mission.id, MissionState.CANCELLING, trace_id=TRACE, reason="operator cancel", now=NOW
    )

    result = queue.tick(now=NOW)

    assert mission.id in [job.mission_id for job in result["enqueued"]]
    job = Job.objects.get(mission=mission, kind=JobKind.TEARDOWN)
    assert job.state == JobState.QUEUED
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.CANCELLING  # still waiting on the worker


# ------------------------------------------------------------------------------------
# Regression: a synchronously-failing teardown must not crash transition() itself
# ------------------------------------------------------------------------------------


def test_a_synchronously_failing_teardown_does_not_crash_the_cancelling_transition(mission):
    """D-069's second finding, fixed alongside the wiring: `_run_teardown_after_commit`
    used to let `teardown.TeardownFailedError` propagate out of `transaction.on_commit`
    — meaning a genuine resource-release failure at the moment `CANCELLING` (or any
    teardown-triggering target) commits crashed the caller of `transition()` outright.
    That was always latent; this fix makes `dispatch_terminal_jobs` reach a *second*
    teardown-triggering transition (`CANCELLING -> FAILED`) for the first time, which
    would have crashed the whole tick's dispatch loop for every mission, not just this
    one, had it not been fixed. Proves both halves: `transition()` itself does not
    raise, and the failure is still honestly recorded as a `TEARDOWN_CONFIRMED` event
    with `released=False` — nothing is silently swallowed, only the uncaught exception
    is."""

    class AlwaysFailsReaper:
        resource_kind = "sandbox"

        def teardown_mission(self, mission_id):
            return (teardown.TeardownOutcome(
                resource_kind="sandbox",
                resource_id="wedged-container",
                released=False,
                detail="daemon refused rm",
            ),)

    with mock.patch.object(teardown, "default_reapers", lambda: (AlwaysFailsReaper(),)):
        walk_to(mission, MissionState.STRESS_TEST)
        result = transitions.transition(  # must not raise
            mission.id,
            MissionState.CANCELLING,
            trace_id=TRACE,
            reason="operator cancel",
            now=NOW,
        )

    assert result.to_state is MissionState.CANCELLING
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.CANCELLING
    assert MissionEvent.objects.filter(
        mission=mission,
        type=EventType.TEARDOWN_CONFIRMED,
        payload__resource_id="wedged-container",
        payload__released=False,
    ).exists()
