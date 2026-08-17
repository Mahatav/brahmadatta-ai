"""`JobKind.CORRELATE`'s transition policy (#168, T3) — the D-061 §2 "nothing to bind"
edge this stage owns, exercised the same way `orchestrator/tests/
test_stress_test_routing.py` exercises T0's own `FUZZ` reference policy: a direct unit
test of the registered policy function, then the same scenario end to end through the
real `orchestrator.queue.dispatch_terminal_jobs` and the real `transitions.transition()`
call it drives.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from contracts.enums import MissionState
from contracts.state_machine import TRANSITIONS
from missions.models import Job, JobKind, JobState, Mission
from orchestrator import queue
from orchestrator.executors import ExecutorContext, executor_for, transition_policy_for
from orchestrator.tests.conftest import NOW, TRACE, walk_to

pytestmark = pytest.mark.django_db(transaction=True)


def test_the_frozen_table_has_both_edges_this_policy_needs():
    """Named directly, mirroring `test_the_frozen_table_has_no_stress_test_to_
    human_review_edge`: both targets this policy can return are legal from
    `CORRELATE`. If this ever fails, the transition table changed — a CTO/
    software-architect call, not something to route around here."""
    assert MissionState.PATCH in TRANSITIONS[MissionState.CORRELATE]
    assert MissionState.HUMAN_REVIEW in TRANSITIONS[MissionState.CORRELATE]


@pytest.mark.parametrize(
    "result",
    [
        {"correlated": True, "source": "finding_rows", "finding_count": 1},
        {"correlated": True, "source": "fuzz_result_crashes_found", "crashes_found": 5},
    ],
)
def test_correlate_policy_routes_something_to_bind_to_patch(result):
    policy = transition_policy_for(JobKind.CORRELATE)
    job = Job(kind=JobKind.CORRELATE, state=JobState.SUCCEEDED, result=result)
    assert policy(job, Mission()) is MissionState.PATCH


@pytest.mark.parametrize(
    "result",
    [
        {"correlated": False, "source": "no_signal"},
        {},  # a job whose result never carries "correlated" at all
    ],
)
def test_correlate_policy_routes_nothing_to_bind_to_human_review(result):
    policy = transition_policy_for(JobKind.CORRELATE)
    job = Job(kind=JobKind.CORRELATE, state=JobState.SUCCEEDED, result=result)
    assert policy(job, Mission()) is MissionState.HUMAN_REVIEW


def test_correlate_policy_defers_on_a_cancelled_job():
    policy = transition_policy_for(JobKind.CORRELATE)
    job = Job(kind=JobKind.CORRELATE, state=JobState.CANCELLED, result={})
    assert policy(job, Mission()) is None


@pytest.mark.parametrize("job_state", [JobState.FAILED, JobState.TIMED_OUT])
def test_correlate_policy_routes_a_job_that_never_completed_to_failed(job_state):
    """`MAX_ATTEMPTS_BY_KIND[CORRELATE]` is 1 — neither of these is retried. A
    CORRELATE job that reached FAILED/TIMED_OUT means the (read-only, single-query)
    decision itself never completed, not a legitimate 'we looked and found nothing'
    outcome (that always reports SUCCEEDED) — see `_correlate_transition_policy`'s own
    docstring."""
    policy = transition_policy_for(JobKind.CORRELATE)
    job = Job(kind=JobKind.CORRELATE, state=job_state, result={})
    assert policy(job, Mission()) is MissionState.FAILED


def test_dispatch_terminal_jobs_moves_a_correlated_mission_to_patch(mission):
    walk_to(mission, MissionState.CORRELATE)
    Job.objects.create(
        mission=mission,
        kind=JobKind.CORRELATE,
        state=JobState.SUCCEEDED,
        result={"correlated": True, "source": "finding_rows", "finding_count": 1},
        run_after=NOW,
        deadline_at=NOW + timedelta(hours=1),
        finished_at=NOW,
    )

    advanced = queue.dispatch_terminal_jobs(trace_id=TRACE, now=NOW)

    assert advanced == [mission.id]
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.PATCH


def test_dispatch_terminal_jobs_moves_a_mission_with_nothing_to_correlate_to_human_review(mission):
    """The scenario D-061 §2 names by example: a mission whose FUZZ campaign found
    nothing reaches HUMAN_REVIEW via CORRELATE, not via a direct (illegal) edge out of
    STRESS_TEST."""
    walk_to(mission, MissionState.CORRELATE)
    Job.objects.create(
        mission=mission,
        kind=JobKind.CORRELATE,
        state=JobState.SUCCEEDED,
        result={"correlated": False, "source": "no_signal"},
        run_after=NOW,
        deadline_at=NOW + timedelta(hours=1),
        finished_at=NOW,
    )

    advanced = queue.dispatch_terminal_jobs(trace_id=TRACE, now=NOW)

    assert advanced == [mission.id]
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.HUMAN_REVIEW


def test_full_pipeline_a_real_finding_carries_a_mission_through_correlate_to_patch(
    mission, finding
):
    """End to end through the *real* executor's output, not a fabricated `Job.result`
    — proves the executor and the policy actually agree with each other, not just that
    each independently accepts a hand-written dict."""
    walk_to(mission, MissionState.CORRELATE)
    ctx = ExecutorContext(
        job=Job(mission=mission, kind=JobKind.CORRELATE, state=JobState.RUNNING),
        mission=mission,
        source_dir=Path("."),
        workspace_root=Path("."),
        trace_id=TRACE,
        cancel_requested=lambda: False,
    )
    exec_result = executor_for(JobKind.CORRELATE)(ctx)
    Job.objects.create(
        mission=mission,
        kind=JobKind.CORRELATE,
        state=JobState.SUCCEEDED,
        result=exec_result.result,
        run_after=NOW,
        deadline_at=NOW + timedelta(hours=1),
        finished_at=NOW,
    )

    advanced = queue.dispatch_terminal_jobs(trace_id=TRACE, now=NOW)

    assert advanced == [mission.id]
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.PATCH


def test_full_pipeline_a_clean_mission_reaches_human_review_through_correlate(mission):
    """The mirror case, with no Finding and no FUZZ job at all — the real executor's
    own 'nothing to correlate' output, fed through the real dispatcher, lands on
    HUMAN_REVIEW rather than stalling or hitting a 409."""
    walk_to(mission, MissionState.CORRELATE)
    ctx = ExecutorContext(
        job=Job(mission=mission, kind=JobKind.CORRELATE, state=JobState.RUNNING),
        mission=mission,
        source_dir=Path("."),
        workspace_root=Path("."),
        trace_id=TRACE,
        cancel_requested=lambda: False,
    )
    exec_result = executor_for(JobKind.CORRELATE)(ctx)
    Job.objects.create(
        mission=mission,
        kind=JobKind.CORRELATE,
        state=JobState.SUCCEEDED,
        result=exec_result.result,
        run_after=NOW,
        deadline_at=NOW + timedelta(hours=1),
        finished_at=NOW,
    )

    advanced = queue.dispatch_terminal_jobs(trace_id=TRACE, now=NOW)

    assert advanced == [mission.id]
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.HUMAN_REVIEW


def test_dispatch_terminal_jobs_never_wedges_when_correlate_result_never_ran(mission):
    """Belt-and-suspenders on the transition policy itself: a terminal CORRELATE job
    whose result is missing the 'correlated' key entirely (e.g. a crashed executor
    reported by run_worker's own outer handler, which writes only a 'detail' key) still
    routes somewhere legal rather than raising past dispatch_terminal_jobs."""
    walk_to(mission, MissionState.CORRELATE)
    Job.objects.create(
        mission=mission,
        kind=JobKind.CORRELATE,
        state=JobState.FAILED,
        result={"detail": "Unhandled error in CORRELATE executor: boom"},
        run_after=NOW,
        deadline_at=NOW + timedelta(hours=1),
        finished_at=NOW,
    )

    advanced = queue.dispatch_terminal_jobs(trace_id=TRACE, now=NOW)

    assert advanced == [mission.id]
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.FAILED
