"""Postgres advisory-lock singleton guard for `manage.py run_orchestrator`.

SEC-43 (issue #177), the other half of SEC-171/SEC-42's precondition: `queue.
claim_job`'s `SELECT ... FOR UPDATE SKIP LOCKED` already makes claiming one `Job` row
safe under concurrent workers, but nothing stops two full `run_orchestrator` *loops*
from running at once -- and `orchestrator/tests/test_sec171_adversarial.py::
test_two_concurrent_ensure_jobs_enqueued_calls_create_duplicate_job_rows` already
demonstrates a real consequence one level up: `ensure_jobs_enqueued`'s "does a Job
row already exist" check is a plain `SELECT` outside any row lock, so two concurrent
orchestrator ticks (e.g. an operator running the command twice, or a supervisor/
systemd misconfiguration starting a replacement before the old process actually
exited) can both decide "no job yet" and both insert one.

The fix here is a single Postgres session-level advisory lock
(`pg_try_advisory_lock`/`pg_advisory_unlock`), acquired once at process startup and
held for the process's entire life. `pg_try_advisory_lock` never blocks -- it returns
immediately, one way or the other -- so a second instance detects the conflict and
can fail fast (no polling, no timeout to tune, no risk of the "few seconds" budget
this feature owes an operator turning into a hang).

## Why this module opens its OWN `psycopg` connection, not `django.db.connection`

Advisory locks in Postgres are scoped to the *session* (the literal server-side
connection) that took them, and released automatically the instant that connection
closes -- by design, so a crashed holder can never leak the lock forever. That is
exactly the property this guard wants. But Django's own ORM-managed `connection`
object is NOT a fixed session for the life of a process: `config/settings/finale.py`
sets `CONN_MAX_AGE = 0`, and even `config/env.py`'s general `database_from_url`
default of 60s means Django's connection-recycling logic
(`BaseDatabaseWrapper.close_if_unusable_or_obsolete`, invoked on every query, not
just at HTTP request boundaries) will transparently close and reopen the underlying
server session once `CONN_MAX_AGE` elapses -- under the finale profile, on
essentially the very next query after the lock was taken. If this module took the
lock on `django.db.connection` itself, that silent reconnect would silently drop the
advisory lock mid-run, with no error and no log line, defeating the whole guard.

A dedicated `psycopg` connection this module opens, owns, and never hands to
Django's connection pool/recycling machinery is the only way the lock reliably
survives for as long as `run_orchestrator`'s tick loop runs -- which is the whole
point of a *singleton* guard, not a "singleton for the first `CONN_MAX_AGE` seconds"
guard.

## Why not `django-pglocks`

Not a dependency of this project (`apps/control-api/requirements.txt` has no such
entry), and it does not fix the `CONN_MAX_AGE` problem above either -- it is a thin
wrapper around the same two SQL calls, executed on whatever connection you hand it,
which would be `django.db.connection` in the normal case. Adding a dependency to
wrap two SQL statements this module already needs to call directly (correctly, on
its own private connection) is not proportionate.
"""

from __future__ import annotations

import logging

from django.db import connection as django_connection

logger = logging.getLogger("orchestrator.singleton_lock")

#: One 64-bit advisory-lock key for "one run_orchestrator instance at a time".
#: Postgres advisory locks share a single 64-bit keyspace across the whole database
#: cluster -- any other feature reaching for pg_try_advisory_lock/pg_advisory_lock
#: must pick a DIFFERENT constant, not this one. Chosen as the signed bigint
#: truncation of sha256(b"brahmadatta.run_orchestrator.singleton")'s first 8 bytes,
#: so it is deterministic across processes/hosts/runs without being a small, round,
#: easily-collided-with number:
#:
#:   >>> import hashlib
#:   >>> int.from_bytes(hashlib.sha256(b"brahmadatta.run_orchestrator.singleton")
#:   ...                 .digest()[:8], "big", signed=True)
#:   3467003920526387080
ORCHESTRATOR_SINGLETON_LOCK_KEY = 3467003920526387080


class OrchestratorAlreadyRunning(RuntimeError):
    """Raised by `acquire_or_die` when another session already holds the singleton
    advisory lock -- i.e. another `run_orchestrator` process is already running."""


class SingletonLock:
    """Owns one dedicated `psycopg` connection for the life of a `run_orchestrator`
    process. Not thread-safe and not meant to be shared -- one instance per process,
    created once in the management command's `handle()`.
    """

    def __init__(self) -> None:
        self._conn = None  # type: ignore[var-annotated]

    @property
    def held(self) -> bool:
        return self._conn is not None

    def acquire_or_die(self, *, key: int = ORCHESTRATOR_SINGLETON_LOCK_KEY) -> None:
        """Try to acquire the singleton advisory lock. Returns immediately either
        way (`pg_try_advisory_lock` never blocks). Raises `OrchestratorAlreadyRunning`
        if another session already holds it.

        No-op on a non-Postgres connection (`connection.vendor != "postgresql"` --
        the `sqlite://:memory:` test profile in `config/settings/test.py`): the
        mechanism is Postgres-specific by construction, and every real deployment of
        this command runs against Postgres (CLAUDE.md's stack table). Logged loudly
        rather than silently, since it is only ever expected under the test profile.
        """
        if self._conn is not None:  # pragma: no cover - defensive, not reachable via CLI
            raise RuntimeError("SingletonLock.acquire_or_die called twice on one instance.")

        if django_connection.vendor != "postgresql":
            logger.warning(
                "SEC-43 singleton advisory lock skipped: connection.vendor=%r is "
                "not 'postgresql'. Expected under the sqlite test profile only -- "
                "NOT expected in any real deployment.",
                django_connection.vendor,
            )
            return

        import psycopg  # imported lazily: only ever needed on the postgresql path

        settings_dict = django_connection.settings_dict
        conn_kwargs = {
            "dbname": settings_dict["NAME"],
            "autocommit": True,
        }
        if settings_dict.get("USER"):
            conn_kwargs["user"] = settings_dict["USER"]
        if settings_dict.get("PASSWORD"):
            conn_kwargs["password"] = settings_dict["PASSWORD"]
        if settings_dict.get("HOST"):
            conn_kwargs["host"] = settings_dict["HOST"]
        if settings_dict.get("PORT"):
            conn_kwargs["port"] = settings_dict["PORT"]

        conn = psycopg.connect(**conn_kwargs)
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(%s)", (key,))
                (acquired,) = cursor.fetchone()
        except Exception:
            conn.close()
            raise

        if not acquired:
            conn.close()
            raise OrchestratorAlreadyRunning(
                "Another run_orchestrator instance already holds the SEC-43 "
                "singleton advisory lock (key="
                f"{key}). Refusing to start a second instance -- two concurrent "
                "orchestrator loops are not safe (see orchestrator/singleton_lock.py "
                "and issue #177). The lock releases automatically the moment the "
                "other process's database connection closes (clean shutdown, kill, "
                "or crash); if you believe no other instance is actually running, "
                "look for a stuck process or a leaked connection rather than "
                "bypassing this check."
            )

        self._conn = conn
        logger.info("SEC-43 singleton advisory lock acquired (key=%s).", key)

    def release(self, *, key: int = ORCHESTRATOR_SINGLETON_LOCK_KEY) -> None:
        """Best-effort explicit release. Safe to call even if `acquire_or_die` was a
        no-op (non-Postgres) or was never called -- closing the process's own
        connection would release the lock anyway; this just makes the release
        observable and immediate rather than relying on process exit.
        """
        if self._conn is None:
            return
        conn = self._conn
        self._conn = None
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (key,))
            logger.info("SEC-43 singleton advisory lock released (key=%s).", key)
        finally:
            conn.close()
