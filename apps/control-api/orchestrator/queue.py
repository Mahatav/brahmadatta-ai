"""The job queue: enqueue, claim, lease, and the one call-site for `transition()` off
a job's terminal result (#168, T0).

Architecture spec §3.1: "One table, no broker." Everything here is `SELECT ... FOR
UPDATE [SKIP LOCKED]` against `missions.models.Job`, mirroring the locking discipline
`authorization.service._lock_mission` and `orchestrator.transitions.transition`
already establish for `Mission` — see this module's docstrings for where each
function takes which lock and why.

## The two processes this module serves, and what each may call

`manage.py run_worker` (the claim loop) calls: `claim_job`, `mark_running`,
`heartbeat`, `complete_job`, `retry_job`. It executes one job at a time via
`orchestrator.executors.executor_for`, and it **never** calls `transition()` —
see `orchestrator/executors.py`'s module docstring for why that boundary is load-
bearing, not stylistic.

`manage.py run_orchestrator` (the tick loop) calls: `tick`, which runs, in order:

1. `reap_expired_leases` — a `LEASED`/`RUNNING` job whose lease expired (a crashed
   worker) is requeued (if attempts remain) or failed.
2. `reap_missed_deadlines` — belt-and-suspenders against a worker that failed to
   self-timeout at its own `deadline_at` (architecture spec §3.3.3 — the worker is
   expected to do this itself; this is what catches it if that worker also crashed).
3. `dispatch_terminal_jobs` — **the only function in this codebase, outside
   `authorization.service`'s own callers, that invokes
   `orchestrator.transitions.transition()`.** Reads every mission sitting in a
   job-backed state whose job for that state has reached a terminal `JobState`, asks
   that kind's `orchestrator.executors.TransitionPolicy` what it means, and commits
   the transition.
4. `advance_out_of_validating` — `VALIDATING -> BASELINE` is not a job-backed
   transition (nothing runs *during* `VALIDATING`; it is the state preflight leaves a
   mission in). Per D-060 §1, `start_mission` only ever drives `SNAPSHOTTED ->
   VALIDATING` — getting a mission the rest of the way into the autonomous pipeline
   ("after `start`, `BASELINE` through a terminal state runs with no human in the
   loop", architecture spec §2.4) is this function's job, run every tick against
   every mission still sitting in `VALIDATING`. A guard failure here (authorization
   expired between `start` and this tick, say) is caught and the mission is left
   exactly where it is for the next tick to retry — never raised into the caller,
   since one mission's stale authorization must not stop every other mission's tick
   from running.
5. `advance_through_triage` — `TRIAGE` has no `JobKind` (architecture spec §2.5: a
   near-stub, "must emit `STAGE_STARTED`, then a `LOG` event ... then
   `STAGE_COMPLETED`", "must not fabricate a finding count"). Nothing about that
   requires a sandboxed worker, so T0 drives it directly rather than leaving a mission
   stuck in `TRIAGE` — the exact shape of bug #168 itself, one stage later. Flagged
   for T3 (owns `CORRELATE`, and per D-062's task breakdown is adjacent to this) to
   review and replace if a different design is wanted; nothing about the frozen
   transition table changes either way (`TRIAGE -> STRESS_TEST` is already legal).
6. `ensure_jobs_enqueued` — for every mission now sitting in a job-backed state with
   no `Job` row yet for that state's kind, enqueue one.

Steps 3–6 each iterate every non-terminal mission and are independently idempotent —
a crash between any two steps, or between any two missions within one step, leaves
nothing to undo on the next tick (architecture spec §3.3.2: "Every process is
restartable with no loss").
"""

from __future__ import annotations

import logging
from datetime import timedelta
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from contracts.enums import EventStatus, EventType, MissionStage, MissionState, Severity
from contracts.errors import ContractError
from missions.models import Job, JobKind, JobState, MAX_ATTEMPTS_BY_KIND, Mission
from orchestrator import events, transitions
from orchestrator.executors import transition_policy_for

logger = logging.getLogger("orchestrator.queue")

#: Which JobKind runs while a mission sits in a given job-backed state. Deliberately
#: excludes `MissionState.TRIAGE` (no `JobKind` — see `advance_through_triage`).
#: `JobKind.SANITIZER_BUILD` and `JobKind.MINIMIZE` are deliberately absent too: they
#: are sub-steps of the `STRESS_TEST` stage's own work, not stages with their own
#: mission-state row in architecture spec §3.2's progress table — composing them is
#: T2's call (enqueue directly, or run inline inside the `FUZZ` executor), not
#: something this top-level map should guess at. See `orchestrator/executors.py`.
#:
#: `MissionState.CANCELLING` (D-069, fixing the gap PR #173's own review round found):
#: previously excluded here on the theory that "teardown is already driven by
#: `orchestrator.transitions._run_teardown_after_commit` on every terminal/cancelling
#: transition, not by this map" — true, but incomplete. That hook releases resources
#: synchronously; it never calls `transitions.transition()` afterward, so nothing ever
#: moved a mission out of `CANCELLING` (`contracts.state_machine.TRANSITIONS[CANCELLING]
#: == {CANCELLED, FAILED}`, both reachable only through `dispatch_terminal_jobs` +
#: `orchestrator.teardown_executor.teardown_transition_policy`'s R3 rule). `CANCELLING`
#: is now job-backed exactly like every other row in this table: `ensure_jobs_enqueued`
#: enqueues a `TEARDOWN` job on entry, `dispatch_terminal_jobs` reads its terminal result
#: and asks the policy where to go next. This is what closes `.project/evidence/
#: d7-gate-50-live-run-2026-08-17.md`'s repro for real — see D-069 for why the
#: synchronous hook is kept rather than removed (both now run for a `CANCELLING`
#: mission; verified safe under real, not just sequential, double-invocation).
JOB_BACKED_STATES: dict[MissionState, JobKind] = {
    MissionState.BASELINE: JobKind.BASELINE,
    MissionState.STRESS_TEST: JobKind.FUZZ,
    MissionState.CORRELATE: JobKind.CORRELATE,
    MissionState.PATCH: JobKind.PATCH_GENERATE,
    MissionState.VERIFY: JobKind.VERIFY,
    MissionState.EXPORTING: JobKind.EXPORT,
    MissionState.CANCELLING: JobKind.TEARDOWN,
}

#: JobState values `run_worker`/the reaper treat as "in flight" vs "done".
_IN_FLIGHT_STATES = (JobState.QUEUED, JobState.LEASED, JobState.RUNNING)
_TERMINAL_STATES = (
    JobState.SUCCEEDED,
    JobState.FAILED,
    JobState.TIMED_OUT,
    JobState.CANCELLED,
)

#: Defaults, overridable per call. Architecture spec §3.5: "Backend developer (#12)
#: decides: ... lease duration (60s suggested); heartbeat interval (10s suggested)."
DEFAULT_LEASE_SECONDS = 60


# ------------------------------------------------------------------------------------
# Enqueue
# ------------------------------------------------------------------------------------


def default_deadline_seconds(kind: JobKind, policy: dict) -> int:
    """`deadline_at` is mandatory at enqueue (architecture spec §3.3.3) and comes from
    `MissionPolicy`, not a global constant, for the one kind the policy actually names
    a budget for. Every other kind gets a fixed, generous default — none of the
    executors that would use those defaults are built by T0, so these are starting
    points for T1/T3/T4/T5/T6/T7 to override at their own enqueue call, not settled
    numbers.
    """
    if kind == JobKind.FUZZ:
        return int(policy.get("fuzz_seconds", 1800))
    sandbox = policy.get("sandbox") or {}
    return int(sandbox.get("max_seconds", 5400))


def enqueue_job(
    mission_id: UUID,
    kind: JobKind,
    *,
    payload: dict | None = None,
    deadline_seconds: int | None = None,
    max_attempts: int | None = None,
    now=None,
) -> Job:
    """Insert one `Job` row. Locks the mission row for the duration, so a caller that
    checks mission state right before enqueuing (`ensure_jobs_enqueued`,
    `advance_out_of_validating`) is not racing a concurrent `pause`/`cancel` HTTP call
    between its check and the insert — the same discipline
    `orchestrator.transitions.transition` uses for `Mission`, applied here because a
    `Job` row is only ever meaningful in the context of the mission row that owns it.
    """
    now = now or timezone.now()
    with transaction.atomic():
        mission = Mission.objects.select_for_update().get(pk=mission_id)
        deadline = now + timedelta(
            seconds=(
                deadline_seconds
                if deadline_seconds is not None
                else default_deadline_seconds(kind, mission.policy or {})
            )
        )
        return Job.objects.create(
            mission=mission,
            kind=kind,
            state=JobState.QUEUED,
            payload=payload or {},
            attempt=1,
            max_attempts=max_attempts or MAX_ATTEMPTS_BY_KIND.get(kind, 1),
            run_after=now,
            deadline_at=deadline,
        )


def ensure_jobs_enqueued(*, now=None) -> list[Job]:
    """One `Job` per (mission, `JobKind`) for as long as that kind serves the
    mission's current state — see `JOB_BACKED_STATES`. Never a second one: every kind
    in scope runs at most once per mission on the happy path (`BaselineReport`'s own
    unique constraint is the storage-level version of the same invariant for
    `BASELINE`; `PATCH_GENERATE`/`VERIFY` are one job each with fan-out *inside* them,
    architecture spec §3.4), and `PAUSED -> X` only ever resumes into the state a
    mission paused *from* (D-047), never back into an earlier one — so a mission never
    legitimately needs two live jobs of the same kind. If a retry is needed, the
    existing row moves back to `QUEUED` (`reap_expired_leases`, or a `JobKind`'s own
    retry via `retry_job`) rather than a new row appearing — which is what makes "does
    a `Job` row for (mission, kind) exist at all" a correct, no-extra-bookkeeping
    "already enqueued" check.
    """
    now = now or timezone.now()
    created: list[Job] = []
    missions = Mission.objects.filter(state__in=[str(s) for s in JOB_BACKED_STATES])
    for mission in missions:
        state = mission.state_enum
        kind = JOB_BACKED_STATES[state]
        if Job.objects.filter(mission_id=mission.id, kind=kind).exists():
            continue
        try:
            created.append(enqueue_job(mission.id, kind, now=now))
        except Exception:  # noqa: BLE001 - one mission's failure must not stop the tick
            logger.exception(
                "Failed to enqueue %s for mission %s", kind, mission.id
            )
    return created


# ------------------------------------------------------------------------------------
# Claim / lease / complete — called by run_worker
# ------------------------------------------------------------------------------------


def claim_job(worker_id: str, *, lease_seconds: int = DEFAULT_LEASE_SECONDS, now=None) -> Job | None:
    """`SELECT ... FOR UPDATE SKIP LOCKED`, architecture spec §3.1, verbatim.

    Two (or more) workers calling this concurrently each get a *different* queued
    job, or `None` once the queue is drained — never the same row twice. Proven under
    real Postgres locking in
    `orchestrator/tests/test_queue_claim_locking.py::test_two_concurrent_claimers_never_get_the_same_job`.
    SQLite compiles `SKIP LOCKED` to a no-op (same caveat `api/tests/test_mission_lifecycle.py`
    already documents for `pause`/`cancel`), so that test is Postgres-only.
    """
    now = now or timezone.now()
    with transaction.atomic():
        job = (
            Job.objects.select_for_update(skip_locked=True)
            .filter(state=JobState.QUEUED, run_after__lte=now)
            .order_by("created_at")
            .first()
        )
        if job is None:
            return None
        job.state = JobState.LEASED
        job.lease_owner = worker_id
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        job.heartbeat_at = now
        job.save(
            update_fields=["state", "lease_owner", "lease_expires_at", "heartbeat_at"]
        )
        return job


def mark_running(job_id: UUID, worker_id: str, *, now=None) -> bool:
    """`LEASED -> RUNNING`. Returns `False` (and writes nothing) if `worker_id` no
    longer holds the lease — the fencing check every write in this module past
    `claim_job` performs, so a worker whose lease was reclaimed while it was slow to
    start never mutates a job another worker (or the reaper) has already moved on."""
    now = now or timezone.now()
    with transaction.atomic():
        job = Job.objects.select_for_update().filter(pk=job_id).first()
        if job is None or job.lease_owner != worker_id or job.state != JobState.LEASED:
            return False
        job.state = JobState.RUNNING
        job.started_at = job.started_at or now
        job.heartbeat_at = now
        job.save(update_fields=["state", "started_at", "heartbeat_at"])
        return True


def heartbeat(
    job_id: UUID, worker_id: str, *, lease_seconds: int = DEFAULT_LEASE_SECONDS, now=None
) -> bool:
    """Extend the lease. Returns `False` if this worker has been fenced out (lease
    reclaimed by the reaper) — the caller's cooperative-cancellation thread should
    stop touching the job and let the executor's own cancellation path (or an
    eventual timeout) end it; it must not keep calling `complete_job` as though it
    still owned the lease."""
    now = now or timezone.now()
    with transaction.atomic():
        job = Job.objects.select_for_update().filter(pk=job_id).first()
        if job is None or job.lease_owner != worker_id:
            return False
        if job.state not in (JobState.LEASED, JobState.RUNNING):
            return False
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        job.heartbeat_at = now
        job.save(update_fields=["lease_expires_at", "heartbeat_at"])
        return True


def complete_job(
    job_id: UUID,
    worker_id: str,
    state: JobState,
    *,
    result: dict | None = None,
    now=None,
) -> bool:
    """Write a terminal `JobState`. Returns `False` if fenced out (see `heartbeat`) —
    the caller must not treat its own result as authoritative if this returns `False`,
    since the reaper may already have requeued or failed this job under a new attempt
    number."""
    now = now or timezone.now()
    with transaction.atomic():
        job = Job.objects.select_for_update().filter(pk=job_id).first()
        if job is None or job.lease_owner != worker_id:
            return False
        if job.state not in (JobState.LEASED, JobState.RUNNING):
            return False
        job.state = state
        job.result = result or {}
        job.finished_at = now
        job.save(update_fields=["state", "result", "finished_at"])
        return True


def retry_job(job_id: UUID, worker_id: str, *, now=None) -> bool:
    """Move a job back to `QUEUED` for another attempt, incrementing `attempt`.

    Distinct from `complete_job(..., JobState.FAILED)`: this is for the case an
    executor's own `ExecutorResult.retry=True` names (architecture spec §3.4's `FUZZ`
    stall retry is the one currently specified) — a failure the *kind's own policy*
    has decided is worth another attempt, as opposed to a terminal `FAILED`. Refuses
    (returns `False`, caller falls back to `complete_job(..., FAILED)`) once
    `attempt >= max_attempts`, so a kind cannot retry past its own ceiling by mistake.
    """
    now = now or timezone.now()
    with transaction.atomic():
        job = Job.objects.select_for_update().filter(pk=job_id).first()
        if job is None or job.lease_owner != worker_id:
            return False
        if job.state not in (JobState.LEASED, JobState.RUNNING):
            return False
        if job.attempt >= job.max_attempts:
            return False
        job.state = JobState.QUEUED
        job.attempt += 1
        job.lease_owner = ""
        job.lease_expires_at = None
        job.heartbeat_at = None
        job.started_at = None
        job.run_after = now
        job.save(
            update_fields=[
                "state",
                "attempt",
                "lease_owner",
                "lease_expires_at",
                "heartbeat_at",
                "started_at",
                "run_after",
            ]
        )
        return True


# ------------------------------------------------------------------------------------
# Reaping — called by run_orchestrator's tick
# ------------------------------------------------------------------------------------


def reap_expired_leases(*, now=None) -> list[Job]:
    """Any `LEASED`/`RUNNING` job whose lease expired: requeue (attempts remain) or
    fail (they don't). Architecture spec §3.4: "the orchestrator's tick moves any
    LEASED/RUNNING job with lease_expires_at < now to FAILED (or QUEUED if attempt <
    max_attempts), and emits a LOG event saying the worker died." `SKIP LOCKED` here
    too: a job the claim loop or another tick is already touching is left for next
    time rather than contended over.
    """
    now = now or timezone.now()
    reaped: list[Job] = []
    with transaction.atomic():
        stale = list(
            Job.objects.select_for_update(skip_locked=True)
            .filter(state__in=[JobState.LEASED, JobState.RUNNING], lease_expires_at__lt=now)
            .select_related("mission")
        )
        for job in stale:
            requeued = job.attempt < job.max_attempts
            job.state = JobState.QUEUED if requeued else JobState.FAILED
            job.lease_owner = ""
            job.lease_expires_at = None
            job.heartbeat_at = None
            if requeued:
                job.attempt += 1
                job.run_after = now
                job.started_at = None
            else:
                job.finished_at = now
            job.save(
                update_fields=[
                    "state",
                    "lease_owner",
                    "lease_expires_at",
                    "heartbeat_at",
                    "attempt",
                    "run_after",
                    "started_at",
                    "finished_at",
                ]
            )
            reaped.append(job)

    # One event per reclaimed job, each under its own mission lock — deliberately a
    # second, separate transaction per job rather than inside the sweep above: the
    # sweep's own lock is over `job` rows (in mission-id order only incidentally),
    # and `events.emit` requires a lock over the *mission* row. Taking both kinds of
    # lock inside one transaction, across a multi-row sweep, is exactly the shape of
    # lock-ordering bug that produces a deadlock against `orchestrator.transitions.
    # transition` (which always locks mission-first) the day two missions reap in the
    # same tick. Splitting them means the job-table lock is released before any
    # mission lock is taken.
    for job in reaped:
        _emit_lease_reclaimed(job, now=now)
    return reaped


def _emit_lease_reclaimed(job: Job, *, now) -> None:
    with transaction.atomic():
        mission = Mission.objects.select_for_update().filter(pk=job.mission_id).first()
        if mission is None:
            return
        events.emit(
            mission,
            EventType.LOG,
            f"Worker lease expired for {job.kind} job {job.id}; "
            f"{'requeued (attempt ' + str(job.attempt) + ')' if job.state == JobState.QUEUED else 'attempts exhausted, marked FAILED'}.",
            {
                "kind": "lease_reclaimed",
                "job_id": str(job.id),
                "job_kind": job.kind,
                "new_state": job.state,
                "attempt": job.attempt,
                "max_attempts": job.max_attempts,
            },
            trace_id="orchestrator-reaper",
            severity=Severity.MEDIUM,
            timestamp=now,
        )


def reap_missed_deadlines(*, now=None) -> list[Job]:
    """Belt-and-suspenders against a worker that did not self-timeout at
    `deadline_at` (architecture spec §3.3.3 says the worker does this itself via its
    heartbeat thread; this is what still catches it if that worker has also crashed
    or wedged). Marks the job `TIMED_OUT` — "a result, not a failure" (§3.3.3) — and
    leaves the mission-level consequence to `dispatch_terminal_jobs`/the kind's own
    `TransitionPolicy`, same as a worker-initiated timeout would.
    """
    now = now or timezone.now()
    timed_out: list[Job] = []
    with transaction.atomic():
        overdue = list(
            Job.objects.select_for_update(skip_locked=True)
            .filter(state__in=_IN_FLIGHT_STATES, deadline_at__lt=now)
        )
        for job in overdue:
            job.state = JobState.TIMED_OUT
            job.finished_at = now
            job.lease_owner = ""
            job.lease_expires_at = None
            job.save(
                update_fields=["state", "finished_at", "lease_owner", "lease_expires_at"]
            )
            timed_out.append(job)
    return timed_out


# ------------------------------------------------------------------------------------
# Dispatch — the one call-site for transition() off a job's terminal result
# ------------------------------------------------------------------------------------


def dispatch_terminal_jobs(*, trace_id: str = "orchestrator-tick", now=None) -> list[UUID]:
    """For every mission whose current state has a terminal job of the matching
    `JobKind`, ask that kind's `TransitionPolicy` where the mission goes next, and
    commit it. The only function in this module — and, outside
    `authorization.service`'s existing callers, in this codebase — that calls
    `orchestrator.transitions.transition()`.

    A policy returning `None` means "not yet" and is a no-op this tick. A policy
    raising `NotImplementedError` (the stub every unwired `JobKind` ships with) is
    caught and logged, not raised into the caller — an unimplemented kind must not
    stop every other mission's tick. A transition that `assert_transition` refuses
    (`InvalidStateTransitionError`) is likewise caught and logged; the terminal job
    row is untouched, so the same mission is picked up again next tick once whatever
    is wrong is fixed (or, for a genuinely wrong policy, every tick forever — visible
    in the logs, not a silent stall).
    """
    now = now or timezone.now()
    advanced: list[UUID] = []
    missions = Mission.objects.filter(state__in=[str(s) for s in JOB_BACKED_STATES])
    for mission in missions:
        state = mission.state_enum
        kind = JOB_BACKED_STATES[state]
        job = (
            Job.objects.filter(mission_id=mission.id, kind=kind, state__in=_TERMINAL_STATES)
            .order_by("-finished_at")
            .first()
        )
        if job is None:
            continue
        try:
            policy = transition_policy_for(kind)
            target = policy(job, mission)
        except NotImplementedError as exc:
            logger.info("Skipping dispatch for mission %s: %s", mission.id, exc)
            continue
        except Exception:  # noqa: BLE001 - one mission's bad policy must not wedge the tick
            logger.exception(
                "Transition policy for %s raised on mission %s", kind, mission.id
            )
            continue
        if target is None:
            continue
        try:
            transitions.transition(
                mission.id,
                target,
                trace_id=trace_id,
                reason=f"{kind} job {job.id} -> {job.state}",
                now=now,
            )
            advanced.append(mission.id)
        except ContractError:
            logger.exception(
                "transition(%s -> %s) refused for mission %s", state, target, mission.id
            )
    return advanced


# ------------------------------------------------------------------------------------
# VALIDATING -> BASELINE, and the TRIAGE stub
# ------------------------------------------------------------------------------------


def advance_out_of_validating(*, trace_id: str = "orchestrator-tick", now=None) -> list[UUID]:
    """`VALIDATING -> BASELINE` for every mission ready to leave it.

    Not job-backed — see this module's docstring. Runs the exact same guards
    `assert_transition` would run for any other caller (authorization, snapshot,
    stage-can-run); a guard failure here means "not ready yet", not an error, and is
    swallowed so one mission's unmet precondition never blocks another mission's tick.
    """
    now = now or timezone.now()
    advanced: list[UUID] = []
    for mission_id in Mission.objects.filter(
        state=str(MissionState.VALIDATING)
    ).values_list("id", flat=True):
        try:
            transitions.transition(
                mission_id,
                MissionState.BASELINE,
                trace_id=trace_id,
                reason="orchestrator: preflight satisfied, entering the pipeline",
                now=now,
            )
            advanced.append(mission_id)
        except ContractError:
            continue
    return advanced


def advance_through_triage(*, trace_id: str = "orchestrator-tick", now=None) -> list[UUID]:
    """`TRIAGE` has no `JobKind` (architecture spec §2.5). Emit the three events its
    "hollow stage" contract requires, then transition straight to `STRESS_TEST`.

    See this module's docstring for why T0 drives this directly rather than leaving
    it for a future `JobKind`, and why that is flagged for T3's review rather than
    treated as settled.
    """
    now = now or timezone.now()
    advanced: list[UUID] = []
    for mission_id in Mission.objects.filter(
        state=str(MissionState.TRIAGE)
    ).values_list("id", flat=True):
        try:
            _emit_triage_stub_events(mission_id, trace_id=trace_id, now=now)
            transitions.transition(
                mission_id,
                MissionState.STRESS_TEST,
                trace_id=trace_id,
                reason="orchestrator: no static analyzers configured in this build",
                now=now,
            )
            advanced.append(mission_id)
        except ContractError:
            continue
    return advanced


def _emit_triage_stub_events(mission_id: UUID, *, trace_id: str, now) -> None:
    with transaction.atomic():
        mission = Mission.objects.select_for_update().get(pk=mission_id)
        for event_type, status, message in (
            (EventType.STAGE_STARTED, EventStatus.RUNNING, "TRIAGE started"),
            (
                EventType.LOG,
                EventStatus.RUNNING,
                "No static analyzers configured in this build — see the gate matrix.",
            ),
            (EventType.STAGE_COMPLETED, EventStatus.SUCCEEDED, "TRIAGE completed"),
        ):
            events.emit(
                mission,
                event_type,
                message,
                {"kind": "triage_stub"},
                trace_id=trace_id,
                stage=MissionStage.ANALYZE,
                state=MissionState.TRIAGE,
                status=status,
                severity=Severity.INFO,
                timestamp=now,
            )


# ------------------------------------------------------------------------------------
# The tick
# ------------------------------------------------------------------------------------


def tick(*, trace_id: str = "orchestrator-tick", now=None) -> dict[str, list]:
    """One full pass. `manage.py run_orchestrator` calls this in a loop; every test in
    this package calls it directly, once, against a fixture mission — same function
    either way, so a passing test is a real proof of what one tick does, not a proxy
    for it."""
    now = now or timezone.now()
    result = {
        "reaped_leases": reap_expired_leases(now=now),
        "reaped_deadlines": reap_missed_deadlines(now=now),
        "dispatched": dispatch_terminal_jobs(trace_id=trace_id, now=now),
        "advanced_from_validating": advance_out_of_validating(trace_id=trace_id, now=now),
        "advanced_through_triage": advance_through_triage(trace_id=trace_id, now=now),
        "enqueued": ensure_jobs_enqueued(now=now),
    }
    return result
