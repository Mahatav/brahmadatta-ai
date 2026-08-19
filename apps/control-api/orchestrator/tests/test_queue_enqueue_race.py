"""SEC-42 (#176) / D-086: `Job(mission, kind)` no longer relies on application-level
checking alone. Two things proved here, both against real concurrent Postgres
transactions — not asserted, exercised — mirroring `test_queue_claim_locking.py`'s own
pattern (`_requires_real_row_locking`, `threading.Barrier`/blocking-`Event` pairs, one
real DB connection per thread):

1. `test_job_mission_kind_unique_constraint_rejects_a_concurrent_duplicate_write` —
   the schema constraint itself (`job_mission_kind_unique`), not any caller's
   discipline, is what refuses a second `Job` row for the same `(mission, kind)` pair.
   Bypasses `orchestrator.queue` entirely and writes `Job.objects.create()` directly
   from two real threads forced to overlap with a `threading.Barrier` — the same
   "prove the schema alone holds" shape SEC-42's own review used to reproduce the bug
   in the first place (a plain, unlocked existence check followed by an unguarded
   insert).

2. `test_ensure_jobs_enqueued_survives_a_real_concurrent_race` — the actual
   production entry point (`orchestrator.queue.ensure_jobs_enqueued`, driven by
   `manage.py run_orchestrator`'s tick loop) degrades gracefully under the exact race
   the issue describes: two overlapping calls for the same mission, forced to
   contend for `enqueue_job`'s own mission row lock. Before this fix, both calls
   reached `Job.objects.create` and both succeeded, producing two duplicate,
   independently claimable `Job` rows (issue #176's own repro, "live, every run").
   After this fix, the second caller's `Job.objects.create` raises `IntegrityError`
   against `job_mission_kind_unique`, `enqueue_job` catches it and returns the first
   caller's row instead of propagating the error, and exactly one `Job` row exists
   once both threads finish.

SQLite compiles `SELECT ... FOR UPDATE` to a no-op and does not reliably support two
real concurrent writer connections at all (single-writer, often surfacing as
"database is locked" rather than blocking), so neither test here can be proven
against it — both are Postgres-only, same caveat this module's sibling already
documents. A local `pytest` run with no `DATABASE_URL` override (i.e. SQLite) skips
both; CI runs the full suite against Postgres for exactly this reason.
"""

from __future__ import annotations

import threading
import time
from unittest import mock

import pytest
from django.db import IntegrityError, connection, connections

from contracts.enums import MissionState
from missions.models import Job, JobKind, JobState
from orchestrator import queue
from orchestrator.tests.conftest import NOW, walk_to

pytestmark = pytest.mark.django_db(transaction=True)

_requires_real_row_locking = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Real row-level locking (and real concurrent writer connections) is "
    "required to prove this race; SQLite is a no-op for SELECT ... FOR UPDATE and "
    "does not support genuine concurrent writers the same way. Run with "
    "DATABASE_URL pointed at Postgres, as CI does.",
)


@_requires_real_row_locking
def test_job_mission_kind_unique_constraint_rejects_a_concurrent_duplicate_write(mission):
    """Direct proof the database constraint itself — not `ensure_jobs_enqueued`'s own
    existence check, not `enqueue_job`'s `IntegrityError` catch — is what makes a
    second `(mission, kind)` row impossible. Two real threads, two real connections,
    a `threading.Barrier` forcing them to fire their `INSERT` at the same instant, no
    application-level coordination at all: exactly one must succeed."""
    walk_to(mission, MissionState.BASELINE)
    assert not Job.objects.filter(mission=mission, kind=JobKind.BASELINE).exists()

    n = 2
    barrier = threading.Barrier(n)
    created: list[Job | None] = [None, None]
    errors: list[Exception | None] = [None, None]

    def _create(i: int) -> None:
        try:
            barrier.wait(timeout=5)
            created[i] = Job.objects.create(
                mission=mission,
                kind=JobKind.BASELINE,
                state=JobState.QUEUED,
                run_after=NOW,
                deadline_at=NOW,
            )
        except Exception as exc:  # noqa: BLE001 - captured for assertion, not hidden
            errors[i] = exc
        finally:
            connections.close_all()

    threads = [threading.Thread(target=_create, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
        assert not t.is_alive()

    successes = [c for c in created if c is not None]
    failures = [e for e in errors if e is not None]
    assert len(successes) == 1, f"expected exactly one writer to win the race, got {len(successes)}"
    assert len(failures) == 1, f"expected exactly one writer to be refused, got {len(failures)}"
    assert isinstance(failures[0], IntegrityError), failures[0]

    assert Job.objects.filter(mission=mission, kind=JobKind.BASELINE).count() == 1


@_requires_real_row_locking
def test_ensure_jobs_enqueued_survives_a_real_concurrent_race(mission):
    """The actual bug (#176): two concurrent `ensure_jobs_enqueued()` calls (standing
    in for two `run_orchestrator` processes racing, or a retry racing an in-flight
    dispatch) for a mission with no `Job` row yet must not both create one.

    `default_deadline_seconds` is patched purely as a synchronization point — it runs
    inside `enqueue_job`'s transaction, after the mission row lock is acquired and
    before the `Job` row is created, mirroring `test_queue_claim_locking.py`'s
    `_slow_save` trick. The first caller is paused there, holding the real Postgres
    row lock open; the second caller's own `ensure_jobs_enqueued` reaches
    `enqueue_job` and must genuinely block waiting for that same lock (asserted via
    `t2.is_alive()` before releasing the first caller) rather than racing past it —
    the same "prove it actually contended for the row, not merely ran twice fast
    enough to look like a race" discipline `test_mission_lifecycle.py`'s
    `_run_concurrently` uses.
    """
    walk_to(mission, MissionState.BASELINE)
    assert not Job.objects.filter(mission=mission, kind=JobKind.BASELINE).exists()

    first_holds_lock = threading.Event()
    release_first = threading.Event()
    original = queue.default_deadline_seconds

    def _slow_default_deadline_seconds(kind, policy):
        first_holds_lock.set()
        release_first.wait(timeout=5)
        return original(kind, policy)

    results: dict[str, list[Job]] = {}

    def _tick(name: str) -> None:
        try:
            results[name] = queue.ensure_jobs_enqueued(now=NOW)
        finally:
            connections.close_all()

    with mock.patch.object(
        queue, "default_deadline_seconds", side_effect=_slow_default_deadline_seconds
    ):
        t1 = threading.Thread(target=_tick, args=("first",))
        t1.start()
        assert first_holds_lock.wait(timeout=5), "first caller never reached the lock"

        t2 = threading.Thread(target=_tick, args=("second",))
        t2.start()
        # Give the second caller a real chance to attempt (and block on) the mission
        # row lock Postgres is holding for the first caller before releasing it.
        time.sleep(0.3)
        assert t2.is_alive(), (
            "second caller should be blocked on the mission row lock, not racing "
            "past it — the race this test exists to force never happened"
        )

        release_first.set()
        t1.join(timeout=5)
        t2.join(timeout=5)

    assert not t1.is_alive() and not t2.is_alive()

    jobs = list(Job.objects.filter(mission=mission, kind=JobKind.BASELINE))
    assert len(jobs) == 1, (
        f"expected exactly one Job row, found {len(jobs)} — this is #176's own repro "
        "(two duplicate, independently claimable Job rows for one (mission, kind))"
    )

    # Both callers got a row back — neither raised — and it is the same row.
    first_result = results["first"]
    second_result = results["second"]
    assert len(first_result) == 1 and len(second_result) == 1
    assert first_result[0].id == second_result[0].id == jobs[0].id
