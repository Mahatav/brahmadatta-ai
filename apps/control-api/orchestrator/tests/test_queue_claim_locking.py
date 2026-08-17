"""`orchestrator.queue.claim_job`'s `SELECT ... FOR UPDATE SKIP LOCKED` discipline,
proved under real concurrent Postgres transactions — not asserted, exercised.

Mirrors `api/tests/test_mission_lifecycle.py`'s `_run_concurrently` pattern (#161):
fire two real claim attempts on separate threads and separate DB connections, forced
to overlap at the row lock by blocking the first caller mid-transaction. Same
`_requires_real_row_locking` skip for the same reason — SQLite compiles `SELECT ...
FOR UPDATE [SKIP LOCKED]` to a no-op, so this property is unproven (not "passing for
the wrong reason") on a local `pytest` run with no `DATABASE_URL` override, and CI
already runs the full suite against Postgres for exactly this reason.
"""

from __future__ import annotations

import threading
from datetime import timedelta
from unittest import mock

import pytest
from django.db import connection, connections

from contracts.enums import MissionState
from missions.models import Job, JobKind, JobState
from orchestrator import queue
from orchestrator.tests.conftest import NOW, walk_to

pytestmark = pytest.mark.django_db(transaction=True)

_requires_real_row_locking = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Real row-level locking is required to prove this race; SQLite is a no-op "
    "for SELECT ... FOR UPDATE [SKIP LOCKED]. Run with DATABASE_URL pointed at "
    "Postgres, as CI does.",
)


def _enqueue(mission, kind: JobKind, *, created_at_offset=timedelta(0)) -> Job:
    job = Job.objects.create(
        mission=mission,
        kind=kind,
        state=JobState.QUEUED,
        run_after=NOW,
        deadline_at=NOW + timedelta(hours=1),
    )
    # `claim_job` orders by `created_at`. `created_at` is `auto_now_add`, i.e. real
    # wall-clock time — unrelated to the fixture `NOW` (2026-08-07) this test's other
    # timestamps use. Pin it explicitly so ordering between two jobs created a few
    # microseconds apart in the same test is deterministic rather than incidental.
    Job.objects.filter(pk=job.pk).update(created_at=NOW + created_at_offset)
    job.refresh_from_db()
    return job


@_requires_real_row_locking
def test_two_concurrent_claimers_on_two_queued_jobs_never_claim_the_same_one(mission):
    """Two workers, two queued jobs, forced to overlap: the second worker's claim
    must not block on the first job's lock, and must not receive it — `SKIP LOCKED`
    means it moves on to the next queued row instead.
    """
    walk_to(mission, MissionState.BASELINE)
    job_a = _enqueue(mission, JobKind.BASELINE)
    job_b = _enqueue(mission, JobKind.FUZZ, created_at_offset=timedelta(seconds=1))

    first_holds_lock = threading.Event()
    release_first = threading.Event()
    original_save = Job.save

    def _slow_save(self, *args, **kwargs):
        # Only the row `claim_job` is actively claiming reaches `save()` while the
        # transaction (and therefore the row lock) is open — the second thread's
        # attempt on a locked row returns from `claim_job` via `SKIP LOCKED` without
        # ever calling `save()` at all, so this only fires once per contended pair.
        if self.pk == job_a.pk:
            first_holds_lock.set()
            release_first.wait(timeout=5)
        return original_save(self, *args, **kwargs)

    results: dict[str, Job | None] = {}

    def _claim(name: str, worker_id: str) -> None:
        try:
            results[name] = queue.claim_job(worker_id, now=NOW)
        finally:
            connections.close_all()

    with mock.patch.object(Job, "save", _slow_save):
        t1 = threading.Thread(target=_claim, args=("first", "worker-1"))
        t1.start()
        assert first_holds_lock.wait(timeout=5), "first claimer never reached the lock"

        t2 = threading.Thread(target=_claim, args=("second", "worker-2"))
        t2.start()
        # `SKIP LOCKED` never blocks — the second claimer should finish almost
        # immediately even while the first is still holding job_a's row lock open.
        t2.join(timeout=5)
        assert not t2.is_alive(), "SKIP LOCKED claim blocked instead of skipping"

        release_first.set()
        t1.join(timeout=5)

    first_job = results["first"]
    second_job = results["second"]
    assert first_job is not None and second_job is not None
    assert first_job.id == job_a.id
    assert second_job.id == job_b.id
    assert first_job.id != second_job.id

    job_a.refresh_from_db()
    job_b.refresh_from_db()
    assert job_a.state == JobState.LEASED and job_a.lease_owner == "worker-1"
    assert job_b.state == JobState.LEASED and job_b.lease_owner == "worker-2"


@_requires_real_row_locking
def test_many_concurrent_claimers_on_one_job_exactly_one_wins(mission):
    """No artificial blocking here — `SKIP LOCKED` never blocks, so N real concurrent
    claim attempts against a single queued job all return promptly, and Postgres
    itself (not application logic) guarantees exactly one of them locks and claims
    the row."""
    walk_to(mission, MissionState.BASELINE)
    job = _enqueue(mission, JobKind.BASELINE)

    n = 8
    results: list[Job | None] = [None] * n
    barrier = threading.Barrier(n)

    def _claim(i: int) -> None:
        try:
            barrier.wait(timeout=5)
            results[i] = queue.claim_job(f"worker-{i}", now=NOW)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=_claim, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
        assert not t.is_alive()

    winners = [r for r in results if r is not None]
    assert len(winners) == 1, f"expected exactly one winner, got {len(winners)}"
    assert winners[0].id == job.id

    job.refresh_from_db()
    assert job.state == JobState.LEASED
    assert job.lease_owner in {f"worker-{i}" for i in range(n)}


def test_claim_job_returns_none_when_nothing_is_queued(mission, db):
    assert queue.claim_job("worker-1", now=NOW) is None


def test_claim_job_skips_a_job_whose_run_after_is_in_the_future(mission):
    walk_to(mission, MissionState.BASELINE)
    Job.objects.create(
        mission=mission,
        kind=JobKind.BASELINE,
        state=JobState.QUEUED,
        run_after=NOW + timedelta(minutes=5),
        deadline_at=NOW + timedelta(hours=1),
    )
    assert queue.claim_job("worker-1", now=NOW) is None


def test_mark_running_and_heartbeat_and_complete_round_trip(mission):
    walk_to(mission, MissionState.BASELINE)
    job = _enqueue(mission, JobKind.BASELINE)

    claimed = queue.claim_job("worker-1", now=NOW)
    assert claimed is not None and claimed.id == job.id

    assert queue.mark_running(job.id, "worker-1", now=NOW) is True
    job.refresh_from_db()
    assert job.state == JobState.RUNNING
    assert job.started_at is not None

    later = NOW + timedelta(seconds=30)
    assert queue.heartbeat(job.id, "worker-1", now=later) is True
    job.refresh_from_db()
    assert job.heartbeat_at == later
    assert job.lease_expires_at == later + timedelta(seconds=queue.DEFAULT_LEASE_SECONDS)

    assert queue.complete_job(
        job.id, "worker-1", JobState.SUCCEEDED, result={"passed": True}, now=later
    ) is True
    job.refresh_from_db()
    assert job.state == JobState.SUCCEEDED
    assert job.result == {"passed": True}
    assert job.finished_at == later


def test_heartbeat_and_complete_are_fenced_off_once_the_lease_owner_changes(mission):
    """A worker whose lease has already been reassigned (e.g. by the reaper) must not
    be able to heartbeat or complete the job out from under the new owner."""
    walk_to(mission, MissionState.BASELINE)
    job = _enqueue(mission, JobKind.BASELINE)
    queue.claim_job("worker-1", now=NOW)

    # Simulate the reaper reassigning the lease to a second worker.
    Job.objects.filter(pk=job.pk).update(lease_owner="worker-2")

    assert queue.heartbeat(job.id, "worker-1", now=NOW) is False
    assert queue.complete_job(job.id, "worker-1", JobState.SUCCEEDED, now=NOW) is False

    job.refresh_from_db()
    assert job.state == JobState.LEASED
    assert job.lease_owner == "worker-2"
