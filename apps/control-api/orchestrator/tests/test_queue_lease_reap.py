"""A crashed worker's lease must eventually be reclaimed (architecture spec §3.3.2,
§3.4) — `orchestrator.queue.reap_expired_leases`.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from contracts.enums import EventType, MissionState
from missions.models import Job, JobKind, JobState, MissionEvent
from orchestrator import queue
from orchestrator.tests.conftest import NOW, walk_to

pytestmark = pytest.mark.django_db(transaction=True)


def _leased_job(mission, *, attempt=1, max_attempts=1, lease_expires_at) -> Job:
    job = Job.objects.create(
        mission=mission,
        kind=JobKind.BASELINE,
        state=JobState.LEASED,
        attempt=attempt,
        max_attempts=max_attempts,
        run_after=NOW,
        deadline_at=NOW + timedelta(hours=1),
        lease_owner="dead-worker-1",
        lease_expires_at=lease_expires_at,
        heartbeat_at=NOW - timedelta(seconds=90),
    )
    return job


def test_a_job_whose_lease_is_still_valid_is_left_alone(mission):
    walk_to(mission, MissionState.BASELINE)
    job = _leased_job(mission, lease_expires_at=NOW + timedelta(seconds=30))

    reaped = queue.reap_expired_leases(now=NOW)

    assert reaped == []
    job.refresh_from_db()
    assert job.state == JobState.LEASED
    assert job.lease_owner == "dead-worker-1"


def test_a_dead_workers_leased_job_with_attempts_remaining_is_requeued(mission):
    """Architecture spec §3.4: `LEASED`/`RUNNING` past its lease -> `QUEUED` if
    `attempt < max_attempts`, with the attempt counter incremented and the lease
    cleared so a live worker can claim it fresh."""
    walk_to(mission, MissionState.BASELINE)
    job = _leased_job(
        mission, attempt=1, max_attempts=2, lease_expires_at=NOW - timedelta(seconds=1)
    )

    reaped = queue.reap_expired_leases(now=NOW)

    assert [j.id for j in reaped] == [job.id]
    job.refresh_from_db()
    assert job.state == JobState.QUEUED
    assert job.attempt == 2
    assert job.lease_owner == ""
    assert job.lease_expires_at is None
    assert job.started_at is None

    # Immediately claimable by a live worker — the whole point of requeuing it.
    claimed = queue.claim_job("worker-alive", now=NOW)
    assert claimed is not None and claimed.id == job.id


def test_a_dead_workers_leased_job_with_no_attempts_left_is_failed(mission):
    walk_to(mission, MissionState.BASELINE)
    job = _leased_job(
        mission, attempt=1, max_attempts=1, lease_expires_at=NOW - timedelta(seconds=1)
    )

    reaped = queue.reap_expired_leases(now=NOW)

    assert [j.id for j in reaped] == [job.id]
    job.refresh_from_db()
    assert job.state == JobState.FAILED
    assert job.finished_at == NOW
    assert job.lease_owner == ""


def test_reaping_a_dead_lease_emits_a_log_event_on_the_mission(mission):
    walk_to(mission, MissionState.BASELINE)
    _leased_job(mission, lease_expires_at=NOW - timedelta(seconds=1))

    queue.reap_expired_leases(now=NOW)

    log_events = MissionEvent.objects.filter(mission=mission, type=str(EventType.LOG))
    assert log_events.count() == 1
    assert "lease expired" in log_events.first().message.lower()


def test_a_job_still_running_but_within_its_lease_is_not_reaped_by_the_deadline_watchdog(mission):
    walk_to(mission, MissionState.BASELINE)
    job = Job.objects.create(
        mission=mission,
        kind=JobKind.BASELINE,
        state=JobState.RUNNING,
        run_after=NOW,
        deadline_at=NOW + timedelta(minutes=10),
        lease_owner="worker-1",
        lease_expires_at=NOW + timedelta(seconds=30),
    )
    assert queue.reap_missed_deadlines(now=NOW) == []
    job.refresh_from_db()
    assert job.state == JobState.RUNNING


def test_a_job_past_its_deadline_is_marked_timed_out_even_if_its_lease_has_not_expired(mission):
    """Belt-and-suspenders: the worker is expected to self-timeout at its own
    deadline, but if it wedges without crashing (lease still fresh, heartbeats still
    landing) the deadline watchdog still catches it."""
    walk_to(mission, MissionState.BASELINE)
    job = Job.objects.create(
        mission=mission,
        kind=JobKind.BASELINE,
        state=JobState.RUNNING,
        run_after=NOW,
        deadline_at=NOW - timedelta(seconds=1),
        lease_owner="worker-1",
        lease_expires_at=NOW + timedelta(seconds=30),
    )
    timed_out = queue.reap_missed_deadlines(now=NOW)
    assert [j.id for j in timed_out] == [job.id]
    job.refresh_from_db()
    assert job.state == JobState.TIMED_OUT
    assert job.finished_at == NOW
