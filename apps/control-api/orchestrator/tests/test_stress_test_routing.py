"""The D-061 §2 trap: a terminal `FUZZ` job must never try to move a mission straight
from `STRESS_TEST` to `HUMAN_REVIEW` — that edge does not exist.

Two layers, deliberately both present:

1. A pure contract-table assertion (`test_the_frozen_table_has_no_stress_test_to_
   human_review_edge`) — the fact the trap exists at all, independent of any of T0's
   own code.
2. A real, end-to-end exercise of `orchestrator.queue.dispatch_terminal_jobs` against
   a real terminal `Job` row and the real `transitions.transition()` call it drives —
   proving T0's dispatcher, using the reference `FUZZ` policy registered in
   `orchestrator/executors.py`, actually takes the legal path (`STRESS_TEST ->
   CORRELATE`) rather than the illegal one, for every terminal shape a `FUZZ` job can
   take (crashes found, clean timeout, stalled-and-exhausted) — and separately, that
   an infra-fault `FUZZ` job routes to `FAILED` instead.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from contracts.enums import MissionState
from contracts.state_machine import TRANSITIONS
from missions.models import Job, JobKind, JobState, Mission
from orchestrator import queue
from orchestrator.executors import transition_policy_for
from orchestrator.tests.conftest import NOW, TRACE, walk_to

pytestmark = pytest.mark.django_db(transaction=True)


def test_the_frozen_table_has_no_stress_test_to_human_review_edge():
    """The trap, named directly. If this ever fails, either the transition table
    changed (a CTO/software-architect call, per architecture spec §1.4 — not something
    a downstream engineer should route around) or something upstream is relying on an
    edge that was never actually added."""
    assert MissionState.HUMAN_REVIEW not in TRANSITIONS[MissionState.STRESS_TEST]
    assert MissionState.CORRELATE in TRANSITIONS[MissionState.STRESS_TEST]


@pytest.mark.parametrize(
    "job_state,result",
    [
        (JobState.SUCCEEDED, {"crashes_found": 3}),
        (JobState.TIMED_OUT, {"crashes_found": 0}),  # §6.3(a), zero crashes at budget
        (JobState.FAILED, {"crashes_found": 0}),  # §6.3(b), stalled twice, exhausted
    ],
)
def test_fuzz_reference_policy_always_targets_correlate_never_human_review(job_state, result):
    """Direct unit test of the registered policy function, independent of the
    dispatcher — every terminal shape a normal (non-infra-fault) FUZZ job can end in
    routes to CORRELATE, never HUMAN_REVIEW."""
    policy = transition_policy_for(JobKind.FUZZ)
    job = Job(kind=JobKind.FUZZ, state=job_state, result=result)
    assert policy(job, Mission()) is MissionState.CORRELATE


def test_fuzz_reference_policy_targets_failed_on_an_infra_fault():
    policy = transition_policy_for(JobKind.FUZZ)
    job = Job(kind=JobKind.FUZZ, state=JobState.FAILED, result={"infra_failure": True})
    assert policy(job, Mission()) is MissionState.FAILED


def test_dispatch_terminal_jobs_actually_moves_a_zero_crash_mission_through_correlate(mission):
    """End to end, through the real dispatcher and the real `transition()` call: a
    mission sitting in `STRESS_TEST` with a terminal, zero-crash `FUZZ` job reaches
    `CORRELATE` — not a 409, not a stall. This is the scenario D-061 §2 warns an
    implementation that "reads the prose literally" gets wrong."""
    walk_to(mission, MissionState.STRESS_TEST)
    Job.objects.create(
        mission=mission,
        kind=JobKind.FUZZ,
        state=JobState.TIMED_OUT,
        result={"crashes_found": 0},
        run_after=NOW,
        deadline_at=NOW + timedelta(hours=1),
        finished_at=NOW,
    )

    advanced = queue.dispatch_terminal_jobs(trace_id=TRACE, now=NOW)

    assert advanced == [mission.id]
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.CORRELATE


def test_dispatch_terminal_jobs_moves_an_infra_faulted_fuzz_job_to_failed(mission):
    walk_to(mission, MissionState.STRESS_TEST)
    Job.objects.create(
        mission=mission,
        kind=JobKind.FUZZ,
        state=JobState.FAILED,
        result={"infra_failure": True},
        run_after=NOW,
        deadline_at=NOW + timedelta(hours=1),
        finished_at=NOW,
    )

    advanced = queue.dispatch_terminal_jobs(trace_id=TRACE, now=NOW)

    assert advanced == [mission.id]
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.FAILED


def test_dispatch_terminal_jobs_never_wedges_on_an_unregistered_kind(mission):
    """`BASELINE`'s transition policy is still the D-062 stub (`NotImplementedError`)
    as of T0 — dispatch must log and skip it, not raise into the caller and stop
    every other mission's tick from running."""
    walk_to(mission, MissionState.BASELINE)
    Job.objects.create(
        mission=mission,
        kind=JobKind.BASELINE,
        state=JobState.SUCCEEDED,
        result={"passed": True},
        run_after=NOW,
        deadline_at=NOW + timedelta(hours=1),
        finished_at=NOW,
    )

    advanced = queue.dispatch_terminal_jobs(trace_id=TRACE, now=NOW)

    assert advanced == []
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.BASELINE
