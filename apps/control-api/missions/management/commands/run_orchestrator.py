"""`manage.py run_orchestrator` — the process architecture spec §1.1 names.

Owns `MissionState`. Never runs a subprocess, never touches a repository, never
holds an inference client (that process table's own "Must never" column). Every tick
is `orchestrator.queue.tick()` — see that module for what each of the six steps does
and in what order.

Runs forever by default. `--once` runs a single tick and exits, which is what the
test suite and a manual smoke check use — the loop shape itself (`while True: tick();
sleep(interval)`) has nothing in it worth a test; `tick()` is what is tested, and it
is the same function either way.

## SEC-43 (issue #177): singleton guard

Both `--once` and the forever-loop first acquire `orchestrator.singleton_lock`'s
Postgres advisory lock, *before* running any tick. A second `run_orchestrator`
instance started while one already holds the lock fails fast — `CommandError`,
non-zero exit, clear stderr message — rather than hanging or silently racing the
first. See `orchestrator/singleton_lock.py`'s module docstring for the full
rationale (in particular why it is not just `django.db.connection`), and
`orchestrator/tests/test_singleton_lock.py` for the proof, including a real
second-OS-process reproduction mirroring `orchestrator/tests/
test_sec171_adversarial.py`'s own precedent.

Skipped (with a loud log line, not silently) under the sqlite test profile — the
mechanism is Postgres-specific and every real deployment runs Postgres.
"""

from __future__ import annotations

import logging
import signal
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from orchestrator import queue
from orchestrator.singleton_lock import OrchestratorAlreadyRunning, SingletonLock

logger = logging.getLogger("orchestrator.run_orchestrator")


class Command(BaseCommand):
    help = "Run the orchestrator tick loop: enqueue jobs, reap dead leases, dispatch terminal jobs into transitions."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run a single tick and exit, instead of looping forever.",
        )
        parser.add_argument(
            "--interval",
            type=float,
            default=None,
            help="Seconds between ticks (default: ORCHESTRATOR_TICK_INTERVAL_SECONDS).",
        )

    def handle(self, *args, **options) -> None:
        interval = options["interval"]
        if interval is None:
            interval = float(getattr(settings, "ORCHESTRATOR_TICK_INTERVAL_SECONDS", 1.0))

        lock = SingletonLock()
        try:
            lock.acquire_or_die()
        except OrchestratorAlreadyRunning as exc:
            # CommandError -> BaseCommand prints this to stderr and exits non-zero
            # (`SystemExit(1)`), never a hang and never a silent fall-through into
            # ticking anyway.
            raise CommandError(str(exc)) from exc

        try:
            if options["once"]:
                result = queue.tick()
                self.stdout.write(self.style.SUCCESS(f"tick: {result}"))
                return

            stop = {"requested": False}

            def _handle_stop(signum, frame) -> None:  # noqa: ANN001 - signal handler signature
                stop["requested"] = True

            signal.signal(signal.SIGTERM, _handle_stop)
            signal.signal(signal.SIGINT, _handle_stop)

            self.stdout.write(
                self.style.SUCCESS(f"orchestrator: ticking every {interval}s (Ctrl-C to stop)")
            )
            while not stop["requested"]:
                try:
                    queue.tick()
                except Exception:  # noqa: BLE001 - one bad tick must not kill the process
                    logger.exception("Unhandled error in orchestrator tick")
                time.sleep(interval)
            self.stdout.write(self.style.SUCCESS("orchestrator: stopped"))
        finally:
            lock.release()
