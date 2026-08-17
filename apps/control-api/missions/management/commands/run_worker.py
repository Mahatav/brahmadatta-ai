"""`manage.py run_worker` — the process architecture spec §1.1 names.

Claims one job at a time (`orchestrator.queue.claim_job`, `SELECT ... FOR UPDATE SKIP
LOCKED`), materializes the mission's snapshot (`orchestrator.snapshot.
materialize_snapshot`, T0b) into `ExecutorContext.source_dir`, runs the `JobKind`'s
registered executor (`orchestrator.executors.executor_for`), and reports the result.

## `--kinds` and the two worker fleets (D-073)

`FUZZ`/`MINIMIZE` need `packages.sandbox.container.ContainerJail`, which shells out to
a `docker` binary. The containerized `worker` service has no docker CLI, and D-036
forbids ever mounting the host's Docker socket into it — so that container can never
run those two kinds. D-073's answer is to split the worker *fleet* by `JobKind`, not
by transport: this same command, invoked twice.

    # the containerized `worker` service — unchanged, no flag needed
    python manage.py run_worker

    # `fuzz-worker` — bare-metal on the finale host (infrastructure/scripts/
    # run-fuzz-worker.sh), the only process anywhere in this system given
    # container-runtime access
    python manage.py run_worker --kinds FUZZ,MINIMIZE

**The fail-closed property this file is responsible for.** `--kinds` is resolved to a
concrete `frozenset[JobKind]` once, in `handle()`, before the claim loop starts, and
that set is what gets passed to `orchestrator.queue.claim_job` on *every* call —
never `None`. Omitting `--kinds` therefore does not mean "no filter, claim anything"
(`claim_job`'s own default, kept for other callers); it resolves to
`orchestrator.queue.DEFAULT_WORKER_KINDS`, which excludes `FUZZ`/`MINIMIZE` by
construction (see that constant's own docstring for why exclusion, not an
inclusion list, is the safer default). A `worker` process started with no flags at
all — the compose default — can therefore never claim a `FUZZ`/`MINIMIZE` job it has
no way to run, and a `fuzz-worker` process is only ever given container-runtime access
in the deployment that also passes it `--kinds FUZZ,MINIMIZE` explicitly. See
`orchestrator/tests/test_queue_kind_filter.py` and `missions/tests/
test_run_worker_kinds.py` for the tests proving both halves.

**Never calls `orchestrator.transitions.transition()` and never writes
`Mission.state`.** That is the orchestrator's job, reading this process's terminal
`Job` rows (`orchestrator.queue.dispatch_terminal_jobs`) — see `orchestrator/
executors.py`'s module docstring for why this boundary is load-bearing, not
stylistic, and `missions.lifecycle` (SEC-16) for the structural half of the guard
that catches a direct model write if this rule is ever broken by accident.

## How registration is expected to work

`EXECUTOR_REGISTRY`/`TRANSITION_POLICY_REGISTRY` (`orchestrator/executors.py`) are
populated by *importing* the module that calls `register_executor`/
`register_transition_policy` at import time — a decorator has no effect until its
module is imported at least once. This command imports every module named in
`WORKER_EXECUTOR_MODULES` (a plain list, below) before starting its claim loop, so a
`JobKind` owner's only integration step is: write your executor in your own module,
decorate it, and add that module's dotted path to this list. T0 ships the list with
no entries beyond `orchestrator.executors` itself (which registers the one reference
`FUZZ` transition policy) — every other kind runs its `NotImplementedError` stub
until its owning task adds itself here.
"""

from __future__ import annotations

import logging
import platform
import signal
import threading
import time
import uuid
from importlib import import_module

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from authorization.errors import UnreadableArchiveError
from contracts.errors import ContractError
from missions.models import Job, JobKind, JobState, Mission
from orchestrator import queue, snapshot
from orchestrator.executors import ExecutorContext, ExecutorResult, JobOutcome, executor_for

logger = logging.getLogger("orchestrator.run_worker")

#: Modules to import (for their `register_executor`/`register_transition_policy`
#: side effects) before the claim loop starts. `orchestrator.executors` itself is
#: always imported by this command already; listed here too for clarity that it is
#: part of the same mechanism. Each `JobKind` task adds its own module's dotted path
#: when it lands — e.g. `"workers.baseline.dispatch"` for T1 — rather than this file
#: growing a per-kind `if` branch.
WORKER_EXECUTOR_MODULES: tuple[str, ...] = ("orchestrator.executors",)


class _HeartbeatThread(threading.Thread):
    """Renews a job's lease every `heartbeat_interval` seconds while the executor
    runs (architecture spec §3.3.5), and exposes a cheap, non-blocking
    `cancel_requested()`/`fenced_out()` check the executor and the claim loop read
    without hitting the database themselves.

    A closed-over `threading.Event` pair rather than a `queue.CancelToken` subclass:
    `CancelToken` in `orchestrator/executors.py` is a `Protocol`, and this thread's
    bound method already satisfies it structurally.
    """

    def __init__(
        self,
        job_id,
        worker_id: str,
        *,
        lease_seconds: int,
        heartbeat_interval: int,
    ) -> None:
        super().__init__(daemon=True, name=f"heartbeat-{job_id}")
        self._job_id = job_id
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._interval = heartbeat_interval
        self._stop_event = threading.Event()
        self._cancel_requested = threading.Event()
        self._fenced = threading.Event()

    def cancel_requested(self) -> bool:
        return self._cancel_requested.is_set()

    def fenced_out(self) -> bool:
        return self._fenced.is_set()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:  # pragma: no cover - exercised via integration, not unit
        try:
            while not self._stop_event.wait(self._interval):
                ok = queue.heartbeat(
                    self._job_id, self._worker_id, lease_seconds=self._lease_seconds
                )
                if not ok:
                    self._fenced.set()
                    return
                cancel_flag = (
                    Job.objects.filter(pk=self._job_id)
                    .values_list("cancel_requested", flat=True)
                    .first()
                )
                if cancel_flag:
                    self._cancel_requested.set()
        finally:
            connections.close_all()


def _load_executor_modules(paths: tuple[str, ...]) -> None:
    for dotted in paths:
        import_module(dotted)


def parse_kinds(raw: str | None) -> frozenset[JobKind]:
    """`--kinds` (D-073) -> a concrete `frozenset[JobKind]`, never `None`.

    `raw is None` (the flag was omitted) resolves to `orchestrator.queue.
    DEFAULT_WORKER_KINDS` — every kind except `FUZZ`/`MINIMIZE` — which is the
    fail-closed default this module's docstring describes. `raw` is otherwise a
    comma-separated list of `JobKind` names (case-insensitive, whitespace-tolerant);
    an empty or unparseable value is a startup error (`CommandError`), never a silent
    fall-through to "claim everything" — an operator who typed `--kinds` clearly meant
    to scope this worker, and a typo there must not quietly reopen `DEFAULT_WORKER_
    KINDS`'s exclusion.
    """
    if raw is None:
        return queue.DEFAULT_WORKER_KINDS

    names = [chunk.strip() for chunk in raw.split(",") if chunk.strip()]
    if not names:
        raise CommandError(
            "--kinds was passed but named no kinds. Omit the flag entirely for the "
            "default set (every kind except FUZZ/MINIMIZE), or name at least one, "
            "e.g. --kinds FUZZ,MINIMIZE."
        )

    valid = {member.value: member for member in JobKind}
    resolved: set[JobKind] = set()
    unknown: list[str] = []
    for name in names:
        member = valid.get(name.upper())
        if member is None:
            unknown.append(name)
        else:
            resolved.add(member)
    if unknown:
        raise CommandError(
            f"--kinds: unrecognized JobKind value(s) {unknown!r}. "
            f"Valid values: {', '.join(sorted(valid))}."
        )
    return frozenset(resolved)


class Command(BaseCommand):
    help = "Run the worker claim loop: claim one job, materialize its snapshot, execute it, report the result."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--once",
            action="store_true",
            help="Claim and run at most one job, then exit (nothing queued exits cleanly too).",
        )
        parser.add_argument("--worker-id", default=None, help="Defaults to hostname-<random>.")
        parser.add_argument("--poll-interval", type=float, default=None)
        parser.add_argument(
            "--kinds",
            default=None,
            metavar="KIND[,KIND...]",
            help=(
                "Comma-separated JobKind names this worker claims, e.g. "
                "FUZZ,MINIMIZE. Default (flag omitted): every JobKind except FUZZ "
                "and MINIMIZE (D-073) — the containerized worker has no docker CLI "
                "and D-036 forbids mounting the socket into it, so those two kinds "
                "are excluded unless explicitly requested. Only the bare-metal "
                "fuzz-worker deployment (infrastructure/scripts/run-fuzz-worker.sh) "
                "should ever pass --kinds FUZZ,MINIMIZE."
            ),
        )

    def handle(self, *args, **options) -> None:
        _load_executor_modules(WORKER_EXECUTOR_MODULES)

        worker_id = options["worker_id"] or f"{platform.node()}-{uuid.uuid4().hex[:8]}"
        poll_interval = options["poll_interval"]
        if poll_interval is None:
            poll_interval = float(getattr(settings, "WORKER_POLL_INTERVAL_SECONDS", 1.0))
        lease_seconds = int(getattr(settings, "WORKER_JOB_LEASE_SECONDS", 60))
        heartbeat_interval = int(getattr(settings, "WORKER_HEARTBEAT_INTERVAL_SECONDS", 10))

        # Resolved once, here, and passed explicitly on every claim — never `None` —
        # so the fail-closed default lives in this command, not by chance in
        # `queue.claim_job`'s own (deliberately permissive, for other callers)
        # default. See `parse_kinds` and this module's docstring.
        kinds = parse_kinds(options["kinds"])
        self.stdout.write(
            f"worker {worker_id}: claiming kinds "
            f"{{{', '.join(sorted(k.value for k in kinds))}}}"
        )

        if options["once"]:
            ran = self._claim_and_run(
                worker_id, lease_seconds=lease_seconds, heartbeat_interval=heartbeat_interval, kinds=kinds
            )
            self.stdout.write(
                self.style.SUCCESS(f"worker {worker_id}: ran one job" if ran else "worker: nothing queued")
            )
            return

        stop = {"requested": False}

        def _handle_stop(signum, frame) -> None:  # noqa: ANN001
            stop["requested"] = True

        signal.signal(signal.SIGTERM, _handle_stop)
        signal.signal(signal.SIGINT, _handle_stop)

        self.stdout.write(
            self.style.SUCCESS(f"worker {worker_id}: polling every {poll_interval}s (Ctrl-C to stop)")
        )
        while not stop["requested"]:
            ran = self._claim_and_run(
                worker_id, lease_seconds=lease_seconds, heartbeat_interval=heartbeat_interval, kinds=kinds
            )
            if not ran:
                time.sleep(poll_interval)
        self.stdout.write(self.style.SUCCESS("worker: stopped"))

    # -- one claim-execute-report cycle ---------------------------------------------

    def _claim_and_run(
        self,
        worker_id: str,
        *,
        lease_seconds: int,
        heartbeat_interval: int,
        kinds: frozenset[JobKind],
    ) -> bool:
        job = queue.claim_job(worker_id, lease_seconds=lease_seconds, kinds=kinds)
        if job is None:
            return False

        if not queue.mark_running(job.id, worker_id):
            # Claimed, but lost the fence before we could even start (a reaper swept
            # it in the gap between claim and mark_running — only possible with a
            # near-zero lease, effectively unreachable at the 60s default, but
            # checked rather than assumed). Nothing to run; report nothing.
            logger.warning("Job %s: lost lease before RUNNING; skipping", job.id)
            return True

        heartbeat = _HeartbeatThread(
            job.id, worker_id, lease_seconds=lease_seconds, heartbeat_interval=heartbeat_interval
        )
        heartbeat.start()
        try:
            result = self._run_executor(job, heartbeat.cancel_requested)
        finally:
            heartbeat.stop()
            heartbeat.join(timeout=5)

        if heartbeat.fenced_out():
            logger.warning(
                "Job %s: lease reclaimed mid-run; discarding this worker's result", job.id
            )
            return True

        self._report_result(job, worker_id, result)
        return True

    def _run_executor(self, job: Job, cancel_requested) -> ExecutorResult:
        """Never lets an executor's own exception escape uncaught — an unhandled
        error in stage code must become a `FAILED` job with a real detail, not a
        crashed worker process that stops claiming for every other mission too."""
        try:
            mission = Mission.objects.get(pk=job.mission_id)
        except Mission.DoesNotExist:
            return ExecutorResult(
                outcome=JobOutcome.FAILED,
                detail=f"Mission {job.mission_id} no longer exists.",
            )

        try:
            materialized = snapshot.materialize_snapshot(mission.id)
        except ContractError as exc:
            return ExecutorResult(
                outcome=JobOutcome.FAILED,
                detail=f"Could not materialize this mission's snapshot: {exc.message}",
            )
        except UnreadableArchiveError as exc:
            return ExecutorResult(
                outcome=JobOutcome.FAILED, detail=f"Snapshot archive unreadable: {exc.message}"
            )

        ctx = ExecutorContext(
            job=job,
            mission=mission,
            source_dir=materialized.path,
            workspace_root=materialized.path.parent,
            trace_id=f"job-{job.id}",
            cancel_requested=cancel_requested,
        )
        try:
            executor = executor_for(job.kind)
            return executor(ctx)
        except NotImplementedError as exc:
            # The stub every unwired JobKind ships with (orchestrator/executors.py).
            # A clean, informative FAILED result -- never a crashed process -- so this
            # is visible on the dashboard/logs rather than silently stalling the
            # worker for every other mission's jobs too.
            return ExecutorResult(outcome=JobOutcome.FAILED, detail=str(exc))
        except Exception as exc:  # noqa: BLE001 - a stage bug must not crash the worker
            logger.exception("Executor for %s raised on job %s", job.kind, job.id)
            return ExecutorResult(
                outcome=JobOutcome.FAILED, detail=f"Unhandled error in {job.kind} executor: {exc}"
            )

    def _report_result(self, job: Job, worker_id: str, result: ExecutorResult) -> None:
        job_state = {
            JobOutcome.SUCCEEDED: JobState.SUCCEEDED,
            JobOutcome.FAILED: JobState.FAILED,
            JobOutcome.TIMED_OUT: JobState.TIMED_OUT,
            JobOutcome.CANCELLED: JobState.CANCELLED,
        }[result.outcome]

        if result.outcome is JobOutcome.FAILED and result.retry:
            if queue.retry_job(job.id, worker_id):
                logger.info("Job %s: retrying (attempt %s)", job.id, job.attempt + 1)
                return
            # attempts exhausted; fall through and report FAILED for real.

        payload = dict(result.result)
        if result.detail:
            payload.setdefault("detail", result.detail)
        if result.error_code is not None:
            payload.setdefault("error_code", str(result.error_code))

        queue.complete_job(job.id, worker_id, job_state, result=payload)
