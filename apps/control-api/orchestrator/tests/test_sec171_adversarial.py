"""Adversarial concurrency review for PR #171 (issue #168, T0). Not part of the
feature's own test suite -- written by the cybersecurity reviewer to independently
reproduce (not just read) the claim-locking property, and to push on the
enqueue-side race the author's own tests do not cover. Run against real Postgres:

    DATABASE_URL=postgresql://brahmadatta:secpg171@localhost:55432/brahmadatta_sec171 \
        python -m pytest orchestrator/tests/test_sec171_adversarial.py -q -s

SEC-42 (#176) / D-086 update: the enqueue-side race this file's §2 originally found
(no unique constraint on `Job(mission, kind)`, live duplicate rows reproduced under
real Postgres) has a real fix now -- `job_mission_kind_unique`
(`missions/models.py`, conditional: excludes `kind="VERIFY"`, which fans out one job
per candidate by design, see that constraint's own comment) plus an `IntegrityError`
catch in `orchestrator.queue.enqueue_job`. The three tests in §2 below are updated in
place to assert the fixed behavior rather than deleted -- this file is this project's
adversarial record of SEC-42/#171, and a record that silently stopped matching
reality would be worse than none. Every other section (§1, §3) is untouched; neither
finding it covers has changed.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from datetime import timedelta
from unittest import mock

import pytest


from contracts.enums import MissionState
from missions.models import Job, JobKind, JobState
from orchestrator import queue
from orchestrator.tests.conftest import NOW, walk_to

pytestmark = pytest.mark.django_db(transaction=True)

_requires_real_row_locking = pytest.mark.skipif(
    __import__("django.db", fromlist=["connection"]).connection.vendor != "postgresql",
    reason="Requires real Postgres row locking.",
)


# ------------------------------------------------------------------------------------
# 1. Push claim_job harder than the author's own test: 50 real threads, real separate
#    DB connections, on ONE queued job, plus a repeat of the pair-race with tighter
#    forced timing (lock acquired and released within the same DB round trip window).
# ------------------------------------------------------------------------------------


@_requires_real_row_locking
def test_50_concurrent_claimers_on_one_job_exactly_one_wins(mission):
    walk_to(mission, MissionState.BASELINE)
    job = Job.objects.create(
        mission=mission,
        kind=JobKind.BASELINE,
        state=JobState.QUEUED,
        run_after=NOW,
        deadline_at=NOW + timedelta(hours=1),
    )

    n = 50
    results = [None] * n
    barrier = threading.Barrier(n)

    def _claim(i):
        from django.db import connections
        try:
            barrier.wait(timeout=10)
            results[i] = queue.claim_job(f"worker-{i}", now=NOW)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=_claim, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
        assert not t.is_alive()

    winners = [r for r in results if r is not None]
    assert len(winners) == 1, f"expected exactly one winner of 50, got {len(winners)}: {winners}"
    assert winners[0].id == job.id
    job.refresh_from_db()
    assert job.state == JobState.LEASED


@_requires_real_row_locking
def test_claim_job_across_real_separate_processes(mission):
    """Threads inside one pytest process still share a Python interpreter and a
    Django app registry. Two real OS processes, each with `django.setup()` run fresh
    and their own psycopg connection, is the closer approximation of "two worker
    containers" this system will actually run as.
    """
    walk_to(mission, MissionState.BASELINE)
    job = Job.objects.create(
        mission=mission,
        kind=JobKind.BASELINE,
        state=JobState.QUEUED,
        run_after=NOW,
        deadline_at=NOW + timedelta(hours=1),
    )
    script = os.path.join(os.path.dirname(__file__), "_sec171_claim_subprocess.py")
    env = dict(os.environ)
    # pytest-django runs the whole suite against Django's own test database
    # (default naming: "test_<db>"), not the DATABASE_URL's literal target -- point
    # the subprocess at the same database the parent process's transaction is
    # actually using, or it will correctly see zero jobs and prove nothing.
    from django.db import connection as _conn
    env["DATABASE_URL"] = (
        f"postgresql://{_conn.settings_dict['USER']}:{_conn.settings_dict['PASSWORD']}"
        f"@{_conn.settings_dict['HOST']}:{_conn.settings_dict['PORT']}"
        f"/{_conn.settings_dict['NAME']}"
    )

    procs = [
        subprocess.Popen(
            [sys.executable, script, f"proc-{i}"],
            cwd=os.path.dirname(os.path.dirname(__file__)).rsplit("/orchestrator", 1)[0],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for i in range(6)
    ]
    outs = [p.communicate(timeout=30) for p in procs]

    results = []
    for i, (out, err) in enumerate(outs):
        claimed = out.strip().splitlines()[-1] if out.strip() else "NONE"
        if claimed == "NONE":
            claimed = None
        results.append((f"proc-{i}", claimed, err))

    winners = [r for r in results if r[1] is not None]
    if len(winners) != 1:
        for name, claimed, err in results:
            print(f"[SEC-171] {name}: claimed={claimed} stderr_tail={err[-500:] if err else ''}")
    assert len(winners) == 1, f"expected exactly one cross-process winner, got {[(r[0], r[1]) for r in results]}"
    assert winners[0][1] == str(job.id)
    print(f"\n[SEC-171] cross-process claim: 6 real OS processes raced one Job row, "
          f"exactly one winner ({winners[0][0]}) -- confirmed under real Postgres")


# ------------------------------------------------------------------------------------
# 2. The enqueue-side race: ensure_jobs_enqueued's "does a Job row exist" check is a
#    plain SELECT outside the mission-row lock enqueue_job takes. Two overlapping
#    calls (two orchestrator ticks, or one tick overlapping a restarted second
#    process) can both see "no job yet" and both insert -- there is no unique
#    constraint on (mission, kind) in the Job model to catch this at the DB level.
# ------------------------------------------------------------------------------------


def test_a_db_constraint_now_prevents_two_job_rows_for_the_same_mission_and_kind(mission):
    """SEC-42 (#176) / D-086: this used to be
    `test_no_db_constraint_prevents_two_job_rows_for_the_same_mission_and_kind` and
    proved the opposite of what it now asserts -- `job_mission_kind_unique` plus
    `enqueue_job`'s `IntegrityError` catch mean a second `enqueue_job` call for a
    `(mission, kind)` pair that already has a row now returns *that* row instead of
    creating a second one, even with no timing/locking involved at all.
    """
    walk_to(mission, MissionState.BASELINE)
    job1 = queue.enqueue_job(mission.id, JobKind.BASELINE, now=NOW)
    job2 = queue.enqueue_job(mission.id, JobKind.BASELINE, now=NOW)
    assert job1.id == job2.id
    assert Job.objects.filter(mission_id=mission.id, kind=JobKind.BASELINE).count() == 1


@_requires_real_row_locking
def test_two_concurrent_ensure_jobs_enqueued_calls_no_longer_create_duplicate_job_rows(
    mission,
):
    """Forces the real race: two threads both run ensure_jobs_enqueued() for the same
    mission, with thread A paused (via a monkeypatched Job.objects.create) *after* its
    `exists()` check returns False but *before* its INSERT commits. Thread B's own
    `exists()` check runs inside that window and also sees "no job yet".

    This reproduces exactly the "two orchestrator processes" scenario nothing in
    run_orchestrator.py's management command prevents (no advisory lock, no PID
    file, no singleton check) -- e.g. a supervisor restart that starts a new
    `run_orchestrator` before confirming the old one exited.

    SEC-42 (#176) / D-086: previously an informational test ("the point is whether
    n == 1 or n == 2") because nothing yet made n == 1 guaranteed. `job_mission_kind_
    unique` plus `enqueue_job`'s `IntegrityError` catch now make it a hard assertion.
    Thread B's own `Job.objects.create` call (inside `enqueue_job`, after it acquires
    the mission row lock thread A already committed and released by the time B gets
    there) hits the constraint and is caught, returning thread A's row instead.
    """
    walk_to(mission, MissionState.BASELINE)
    assert not Job.objects.filter(mission_id=mission.id, kind=JobKind.BASELINE).exists()

    a_past_exists_check = threading.Event()
    release_a = threading.Event()
    original_create = Job.objects.create

    call_count = {"n": 0}

    def _slow_create(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            a_past_exists_check.set()
            release_a.wait(timeout=5)
        return original_create(*args, **kwargs)

    results = {}

    def _run(name):
        from django.db import connections
        try:
            results[name] = queue.ensure_jobs_enqueued(now=NOW)
        finally:
            connections.close_all()

    with mock.patch.object(type(Job.objects), "create", side_effect=_slow_create, autospec=False):
        t1 = threading.Thread(target=_run, args=("A",))
        t1.start()
        assert a_past_exists_check.wait(timeout=5), "thread A never reached create()"

        t2 = threading.Thread(target=_run, args=("B",))
        t2.start()
        t2.join(timeout=10)
        assert not t2.is_alive()

        release_a.set()
        t1.join(timeout=10)

    rows = Job.objects.filter(mission_id=mission.id, kind=JobKind.BASELINE)
    n = rows.count()
    print(f"\n[SEC-171] duplicate-enqueue race (post-D-086 fix): {n} Job row(s) "
          f"created for one (mission, kind) pair from two concurrent "
          f"ensure_jobs_enqueued() calls")
    assert n == 1, f"expected exactly one Job row, found {n}: {[str(r.id) for r in rows]}"
    # Neither caller raised -- both got a (the same) row back.
    assert len(results["A"]) == 1 and len(results["B"]) == 1
    assert results["A"][0].id == results["B"][0].id == rows.first().id


@_requires_real_row_locking
def test_duplicate_job_rows_can_no_longer_be_independently_claimed_by_different_workers(
    mission,
):
    """This used to confirm the consequence of the (then-real) duplicate-row bug: two
    different workers could each successfully claim one row and both would then run
    the same JobKind's executor concurrently for the same mission -- the
    double-execution outcome D-064 #1's idempotency reasoning assumes cannot happen.

    SEC-42 (#176) / D-086: there is no second row to claim anymore.
    `queue.enqueue_job` called twice for the same `(mission, kind)` now returns the
    *same* row both times, so only one worker can ever claim it -- the second
    `claim_job` call correctly finds nothing left to claim.
    """
    walk_to(mission, MissionState.BASELINE)
    job1 = queue.enqueue_job(mission.id, JobKind.BASELINE, now=NOW)
    job2 = queue.enqueue_job(mission.id, JobKind.BASELINE, now=NOW)
    assert job1.id == job2.id
    assert Job.objects.filter(mission_id=mission.id, kind=JobKind.BASELINE).count() == 1

    claimed1 = queue.claim_job("worker-1", now=NOW)
    claimed2 = queue.claim_job("worker-2", now=NOW)

    assert claimed1 is not None and claimed1.id == job1.id
    assert claimed2 is None
    print(f"\n[SEC-171] no duplicate row to claim (post-D-086 fix): "
          f"worker-1={claimed1.id} worker-2=None -- only one worker can ever run "
          f"BASELINE for mission {mission.id}")


# ------------------------------------------------------------------------------------
# 3. Split-brain lease check: does a "slow but not actually dead" worker's late
#    complete_job/heartbeat call get correctly fenced off after the reaper reclaims
#    its lease and a second worker starts on the same job?
# ------------------------------------------------------------------------------------


def test_stalled_original_worker_is_fenced_after_reclaim_even_if_it_finishes_late(mission):
    walk_to(mission, MissionState.BASELINE)
    job = queue.enqueue_job(mission.id, JobKind.BASELINE, now=NOW)
    job.max_attempts = 2
    job.save(update_fields=["max_attempts"])

    claimed = queue.claim_job("worker-slow", now=NOW)
    assert claimed.id == job.id
    assert queue.mark_running(job.id, "worker-slow", now=NOW) is True

    # Lease expires; worker-slow is stalled, not dead -- it never got the memo and
    # will still try to report a result later.
    expired_at = NOW + timedelta(seconds=queue.DEFAULT_LEASE_SECONDS + 1)
    reaped = queue.reap_expired_leases(now=expired_at)
    assert [j.id for j in reaped] == [job.id]

    job.refresh_from_db()
    assert job.state == JobState.QUEUED  # requeued, attempt incremented

    # A second, live worker claims the same row fresh.
    reclaimed = queue.claim_job("worker-fast", now=expired_at)
    assert reclaimed.id == job.id
    assert queue.mark_running(job.id, "worker-fast", now=expired_at) is True

    # worker-fast finishes first and reports.
    assert queue.complete_job(
        job.id, "worker-fast", JobState.SUCCEEDED, result={"ok": True}, now=expired_at
    ) is True

    # worker-slow -- still technically alive, was never told it lost the lease --
    # finally finishes its stale attempt and tries to report too.
    still_fenced = queue.complete_job(
        job.id, "worker-slow", JobState.SUCCEEDED, result={"ok": "stale"}, now=expired_at
    )
    assert still_fenced is False, "the stalled original worker must not be able to overwrite the new owner's result"

    job.refresh_from_db()
    assert job.result == {"ok": True}
    assert job.lease_owner == "worker-fast" or job.state == JobState.SUCCEEDED
    print("\n[SEC-171] split-brain check: stalled original worker's late complete_job "
          "correctly rejected (fencing on lease_owner holds)")

    # worker-slow's heartbeat should be fenced off too, not just complete_job.
    assert queue.heartbeat(job.id, "worker-slow", now=expired_at) is False
