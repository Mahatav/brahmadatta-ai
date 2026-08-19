"""SEC-43 (issue #177): proof that `manage.py run_orchestrator` refuses to start a
second instance while one is already running, and that the first instance's own
ticking is completely unaffected by the second instance's failed attempt.

Two layers, both against REAL Postgres (a Postgres advisory lock has no sqlite
equivalent — see `orchestrator/singleton_lock.py`'s own module docstring, and the
`_requires_real_postgres` skip below):

1. In-process proof of the underlying mechanism (`SingletonLock` itself): one
   acquire wins, a second concurrent acquire attempt is refused immediately (no
   blocking/hanging), release lets a subsequent acquire succeed again.

2. Real cross-process proof, mirroring `orchestrator/tests/
   test_sec171_adversarial.py::test_claim_job_across_real_separate_processes`'s own
   precedent for "prove it with a real second process, not a mock": start the real
   `manage.py run_orchestrator` command as one OS process, confirm (by watching a
   real Job row appear for a fixture mission) that it is actually ticking, then start
   a second real `manage.py run_orchestrator` process pointed at the same database
   and confirm it is refused — non-zero exit, clear stderr message, within a few
   seconds, never a hang — while the first process keeps running, keeps holding the
   lock, and shuts down cleanly and releases it on SIGTERM.

Run against real Postgres:

    DATABASE_URL=postgresql://<user>:<password>@<host>:<port>/<db> \\
        python -m pytest orchestrator/tests/test_singleton_lock.py -q -s
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

from contracts.enums import MissionState
from missions.models import Job, JobKind
from orchestrator.singleton_lock import OrchestratorAlreadyRunning, SingletonLock
from orchestrator.tests.conftest import walk_to

pytestmark = pytest.mark.django_db(transaction=True)

_requires_real_postgres = pytest.mark.skipif(
    __import__("django.db", fromlist=["connection"]).connection.vendor != "postgresql",
    reason=(
        "Postgres advisory locks (pg_try_advisory_lock/pg_advisory_unlock) have no "
        "sqlite equivalent -- this feature cannot be meaningfully verified against "
        "the sqlite test profile at all. See orchestrator/singleton_lock.py's module "
        "docstring and this file's own docstring."
    ),
)

# `apps/control-api` -- two levels up from `orchestrator/tests/test_singleton_lock.py`
# -- is `manage.py`'s directory and the real `run_orchestrator` command's cwd.
_CONTROL_API_ROOT = Path(__file__).resolve().parents[2]


def _subprocess_database_url() -> str:
    """The real DATABASE_URL the CURRENT test's Postgres connection is actually
    using. pytest-django runs the whole suite against Django's own test database
    (default naming: "test_<db>"), not the DATABASE_URL env var's literal target --
    point the subprocess at the same database the parent process is actually using,
    exactly as test_sec171_adversarial.py's cross-process test already does, or the
    subprocess will see an empty/different database and prove nothing.
    """
    from django.db import connection as _conn

    d = _conn.settings_dict
    return f"postgresql://{d['USER']}:{d['PASSWORD']}@{d['HOST']}:{d['PORT']}/{d['NAME']}"


def _run_orchestrator_env() -> dict[str, str]:
    env = dict(os.environ)
    env["DATABASE_URL"] = _subprocess_database_url()
    env.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
    return env


def _wait_until_lock_held(*, timeout: float = 10.0, interval: float = 0.1) -> bool:
    """Poll the real singleton advisory lock (via the SAME production code path a
    `run_orchestrator` process uses) until some OTHER session holds it. Each failed
    probe acquires-then-immediately-releases, so it never itself creates a false
    conflict for whichever process this is waiting on.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        probe = SingletonLock()
        try:
            probe.acquire_or_die()
        except OrchestratorAlreadyRunning:
            return True
        probe.release()
        time.sleep(interval)
    return False


def _wait_until_lock_free(*, timeout: float = 10.0, interval: float = 0.1) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        probe = SingletonLock()
        try:
            probe.acquire_or_die()
        except OrchestratorAlreadyRunning:
            time.sleep(interval)
            continue
        probe.release()
        return True
    return False


# ------------------------------------------------------------------------------------
# 1. In-process proof of the mechanism itself.
# ------------------------------------------------------------------------------------


@_requires_real_postgres
def test_second_acquire_refused_while_first_holds_the_lock(mission):
    first = SingletonLock()
    first.acquire_or_die()
    assert first.held

    second = SingletonLock()
    with pytest.raises(OrchestratorAlreadyRunning):
        second.acquire_or_die()
    assert not second.held, "a refused acquire must not leave a half-open connection behind"

    first.release()
    assert not first.held


@_requires_real_postgres
def test_release_lets_a_subsequent_acquire_succeed(mission):
    first = SingletonLock()
    first.acquire_or_die()
    first.release()

    second = SingletonLock()
    second.acquire_or_die()  # must not raise -- the lock was actually released
    assert second.held
    second.release()


@_requires_real_postgres
def test_pg_try_advisory_lock_never_blocks(mission):
    """The whole point of `pg_try_advisory_lock` over `pg_advisory_lock`: a refused
    acquire returns immediately, it does not wait for the holder to release. Asserted
    with a wall-clock budget tight enough that any accidental blocking call would
    fail this test.
    """
    first = SingletonLock()
    first.acquire_or_die()
    try:
        started = time.monotonic()
        with pytest.raises(OrchestratorAlreadyRunning):
            SingletonLock().acquire_or_die()
        elapsed = time.monotonic() - started
        assert elapsed < 2.0, f"acquire_or_die took {elapsed:.2f}s -- pg_try_advisory_lock must not block"
    finally:
        first.release()


def test_skips_cleanly_on_a_non_postgres_connection():
    """Unit-level, no real Postgres required (runs under the plain sqlite test
    profile too): a non-postgresql `connection.vendor` must be a clean no-op, never
    a crash and never a silent lie about holding a lock it never actually took.
    """
    fake_connection = mock.Mock()
    fake_connection.vendor = "sqlite"
    with mock.patch("orchestrator.singleton_lock.django_connection", fake_connection):
        lock = SingletonLock()
        lock.acquire_or_die()  # must not raise
        assert not lock.held
        lock.release()  # must also be a safe no-op


# ------------------------------------------------------------------------------------
# 2. Real cross-process proof: two actual `manage.py run_orchestrator` OS processes.
# ------------------------------------------------------------------------------------


@_requires_real_postgres
def test_second_run_orchestrator_process_refused_first_process_unaffected(mission):
    walk_to(mission, MissionState.BASELINE)
    assert not Job.objects.filter(mission_id=mission.id, kind=JobKind.BASELINE).exists()

    env = _run_orchestrator_env()
    first = subprocess.Popen(
        [sys.executable, "manage.py", "run_orchestrator", "--interval", "0.2"],
        cwd=str(_CONTROL_API_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        # --- process 1 is actually up and holding the lock -----------------------
        assert _wait_until_lock_held(timeout=15.0), (
            "first run_orchestrator process never took the singleton lock within "
            "15s -- see its captured output below"
        )
        assert first.poll() is None, "first process exited unexpectedly before ticking"

        # --- process 1 is actually TICKING, not just alive: a real Job row for the
        # fixture mission (in BASELINE) must appear via a real tick against the real
        # DB, with no worker involved.
        job = None
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            job = Job.objects.filter(mission_id=mission.id, kind=JobKind.BASELINE).first()
            if job is not None:
                break
            time.sleep(0.2)
        assert job is not None, "first process never enqueued the expected BASELINE job -- it is not ticking"
        print(f"\n[SEC-43] first run_orchestrator process ticking for real: enqueued job {job.id}")

        # --- attempt a second, real run_orchestrator process against the SAME db --
        second = subprocess.Popen(
            [sys.executable, "manage.py", "run_orchestrator", "--interval", "0.2"],
            cwd=str(_CONTROL_API_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            second_out, second_err = second.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            second.kill()
            second_out, second_err = second.communicate(timeout=10)
            pytest.fail(
                "second run_orchestrator process did not exit within 15s -- it "
                f"hung instead of failing fast. stdout={second_out!r} stderr={second_err!r}"
            )

        print(f"[SEC-43] second process exit code: {second.returncode}")
        print(f"[SEC-43] second process stderr: {second_err.strip()}")
        assert second.returncode != 0, (
            "a second run_orchestrator process must exit non-zero when the "
            f"singleton lock is already held; got 0. stdout={second_out!r}"
        )
        assert "CommandError" in second_err and "singleton advisory lock" in second_err, (
            f"expected a clear CommandError about the singleton advisory lock on "
            f"stderr, got: {second_err!r}"
        )

        # --- process 1 is COMPLETELY unaffected by the second process's failed
        # attempt: still alive, still holds the lock.
        assert first.poll() is None, "first process died as a side effect of the second process's failed start"
        assert _wait_until_lock_held(timeout=2.0), "lock is no longer held after the second process's failed attempt"

        jobs_after = Job.objects.filter(mission_id=mission.id, kind=JobKind.BASELINE).count()
        assert jobs_after == 1, (
            f"expected exactly one BASELINE job row (ensure_jobs_enqueued's "
            f"existence check), got {jobs_after} -- a second orchestrator loop may "
            f"have gotten in and duplicated it"
        )
    finally:
        first.terminate()
        try:
            first_out, first_err = first.communicate(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover - cleanup safety net
            first.kill()
            first_out, first_err = first.communicate(timeout=10)

    assert first.returncode == 0, f"first process did not shut down cleanly: {first_err!r}"
    assert "orchestrator: stopped" in first_out, f"first process stdout: {first_out!r}"
    print(f"[SEC-43] first process shut down cleanly on SIGTERM: {first_out.strip()}")

    # --- the lock releases when the holder's process/connection actually closes ---
    assert _wait_until_lock_free(timeout=10.0), "lock was not released after the first process exited"

    # --- and a fresh instance can now start where the first one left off ---------
    third = subprocess.run(
        [sys.executable, "manage.py", "run_orchestrator", "--once"],
        cwd=str(_CONTROL_API_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert third.returncode == 0, f"third (post-shutdown) instance should start cleanly: {third.stderr!r}"
    print(f"[SEC-43] a fresh instance started cleanly after the first released the lock: {third.stdout.strip()}")


@_requires_real_postgres
def test_run_orchestrator_once_also_refused_while_loop_instance_running(mission):
    """`--once` is still one `run_orchestrator` instance -- SEC-43 covers it too, not
    only the forever-loop shape."""
    env = _run_orchestrator_env()
    loop_proc = subprocess.Popen(
        [sys.executable, "manage.py", "run_orchestrator", "--interval", "0.2"],
        cwd=str(_CONTROL_API_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert _wait_until_lock_held(timeout=15.0), "loop instance never took the lock"

        once_result = subprocess.run(
            [sys.executable, "manage.py", "run_orchestrator", "--once"],
            cwd=str(_CONTROL_API_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert once_result.returncode != 0
        assert "singleton advisory lock" in once_result.stderr
        assert loop_proc.poll() is None, "loop instance died as a side effect of the refused --once attempt"
    finally:
        loop_proc.terminate()
        try:
            loop_proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover - cleanup safety net
            loop_proc.kill()
            loop_proc.communicate(timeout=10)
