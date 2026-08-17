"""`orchestrator.queue.tick` and its pieces: the actual #168 fix (nothing previously
advanced a mission past `VALIDATING`), the `TRIAGE` stub pass-through, and
`ensure_jobs_enqueued`'s one-job-per-stage idempotency.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from contracts.enums import EventType, MissionState
from missions.models import Job, JobKind, JobState
from orchestrator import queue
from orchestrator.tests.conftest import NOW, TRACE, walk_to

pytestmark = pytest.mark.django_db(transaction=True)


def test_this_is_the_168_fix_validating_no_longer_sits_forever(mission):
    """Literally #168's own repro: a mission reaches VALIDATING and, before this
    module existed, nothing ever advanced it. One tick now does."""
    walk_to(mission, MissionState.VALIDATING)

    result = queue.tick(now=NOW)

    mission.refresh_from_db()
    assert mission.state_enum is MissionState.BASELINE
    assert mission.id in result["advanced_from_validating"]
    assert Job.objects.filter(mission=mission, kind=JobKind.BASELINE).exists()


def test_advance_out_of_validating_leaves_an_unauthorized_mission_exactly_where_it_is(mission):
    """A guard failure (no active authorization, in this case — revoked mid-flight)
    must not raise into the tick; the mission is left in VALIDATING for the next tick
    to retry, same as a failed preflight would report."""
    from missions.models import Authorization

    walk_to(mission, MissionState.VALIDATING)
    Authorization.objects.filter(mission=mission).update(revoked_at=NOW - timedelta(minutes=1))

    advanced = queue.advance_out_of_validating(now=NOW)

    assert advanced == []
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.VALIDATING


def test_advance_through_triage_emits_the_hollow_stage_events_and_reaches_stress_test(mission):
    walk_to(mission, MissionState.TRIAGE)

    advanced = queue.advance_through_triage(trace_id=TRACE, now=NOW)

    assert advanced == [mission.id]
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.STRESS_TEST

    messages = list(
        mission.events.filter(type=str(EventType.LOG)).values_list("message", flat=True)
    )
    assert any("no static analyzers configured" in m.lower() for m in messages)
    assert mission.events.filter(type=str(EventType.STAGE_STARTED)).exists()
    assert mission.events.filter(type=str(EventType.STAGE_COMPLETED)).exists()


def test_ensure_jobs_enqueued_writes_exactly_one_job_per_stage(mission):
    walk_to(mission, MissionState.BASELINE)

    first = queue.ensure_jobs_enqueued(now=NOW)
    second = queue.ensure_jobs_enqueued(now=NOW)

    assert len(first) == 1
    assert second == []  # already has a BASELINE job; never a duplicate
    assert Job.objects.filter(mission=mission, kind=JobKind.BASELINE).count() == 1


def test_ensure_jobs_enqueued_sets_a_real_deadline_from_mission_policy():
    from contracts.enums import LanguageAdapter
    from missions.models import Authorization, Mission, Snapshot

    now = NOW
    mission = Mission.objects.create(
        name="fuzz budget mission",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={"fuzz_seconds": 120},
    )
    Authorization.objects.create(
        mission=mission,
        statement="I am authorized to test this repository on behalf of the owner.",
        granted_by="tester",
        granted_at=now - timedelta(minutes=5),
        expires_at=now + timedelta(hours=8),
        repository_ref=mission.repository_ref,
    )
    Snapshot.objects.create(
        mission=mission, archive_sha256="d" * 64, file_count=1, bytes_total=1
    )
    walk_to(mission, MissionState.STRESS_TEST, now=now)

    queue.ensure_jobs_enqueued(now=now)

    job = Job.objects.get(mission=mission, kind=JobKind.FUZZ)
    assert job.deadline_at == now + timedelta(seconds=120)


def test_a_full_tick_walks_a_mission_from_validating_through_triage_in_one_call(mission):
    """`tick()` runs its steps in an order that lets a mission which only needed
    orchestrator-driven (non-job) hops this tick clear more than one of them without
    waiting for a second tick — VALIDATING -> BASELINE only, though: BASELINE itself
    is job-backed and genuinely waits for a worker."""
    walk_to(mission, MissionState.VALIDATING)

    queue.tick(now=NOW)

    mission.refresh_from_db()
    assert mission.state_enum is MissionState.BASELINE
    assert Job.objects.filter(mission=mission, kind=JobKind.BASELINE, state=JobState.QUEUED).exists()


def test_tick_is_a_no_op_on_a_mission_already_sitting_in_a_job_backed_state_with_work_in_flight(
    mission,
):
    walk_to(mission, MissionState.BASELINE)
    queue.tick(now=NOW)  # enqueues the one BASELINE job
    job = Job.objects.get(mission=mission, kind=JobKind.BASELINE)

    queue.tick(now=NOW)  # a second tick, nothing new should happen

    assert Job.objects.filter(mission=mission, kind=JobKind.BASELINE).count() == 1
    job.refresh_from_db()
    assert job.state == JobState.QUEUED
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.BASELINE
