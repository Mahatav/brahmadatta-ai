"""The `JobKind` executor interface (#168, T0).

**Read this file first if you are building T1/T2/T3/T4/T5/T6/T7.** This is the seam
between the `worker` process (executes jobs, per architecture spec §1.1) and the
`orchestrator` process (owns `Mission.state`, per the same table). It is deliberately
the first piece of T0 to land, ahead of the rest of the tick loop, so the other six
`JobKind` executors can be written against it in parallel — see D-062's staffing plan
(`.project/decisions.md`).

## The one rule that matters more than the type signatures

**An executor never calls `orchestrator.transitions.transition()`, and never writes
`Mission.state` / `paused_from` / `verdict` / `verification_started_at` directly.**
Architecture spec §1.1's process table: the `worker` "Must never: Write
`Mission.state`." D-061 §3 rule 1 names this as the mistake an implementer under
deadline pressure is most likely to make ("a worker with the mission id already in
hand and a stage that just succeeded will be tempted to call `transition()` directly
to save a hop"). `missions.lifecycle` (SEC-16) enforces the model-write half of this
structurally — a direct `mission.state = ...; mission.save()` from executor code
raises `MissionStateWriteError` rather than silently succeeding. There is no
equivalent structural guard against calling `transitions.transition()` itself (it is a
plain function, callable from anywhere the import resolves), so this is enforced by
review, not just by the ORM. If you find yourself importing
`orchestrator.transitions` from an executor module, stop — you want
`ExecutorResult.result` instead, read by the *orchestrator's* transition-policy
function (`register_transition_policy`, below), which is the only code that calls
`transition()` off a job's terminal row (`orchestrator.queue.dispatch_terminal_jobs`).

## The two halves of the contract

1. **Do the work.** `register_executor(kind)` decorates a function of type
   `Executor = Callable[[ExecutorContext], ExecutorResult]`. Called once per claimed
   `Job`, by `manage.py run_worker`. Returns an `ExecutorResult` — a `JobOutcome`, a
   free-text detail, an optional `ErrorCode`, and a JSON-serializable `result` dict.
   `result` is written verbatim to `Job.result` (architecture spec §3.1: "Summary the
   orchestrator reads to pick the next transition"). Put whatever your transition
   policy (below) needs to read there. Nothing else reads it, so its shape is yours to
   define per kind — there is no shared schema to satisfy beyond "JSON-serializable
   and no secrets" (`Job.payload`/`Job.result` docstring, `missions/models.py`).

2. **Decide what it means for the mission.** `register_transition_policy(kind)`
   decorates a function of type
   `TransitionPolicy = Callable[[Job, Mission], MissionState | None]`, called by
   `orchestrator.queue.dispatch_terminal_jobs` once a job you registered an executor
   for reaches a terminal `JobState`. Read `job.result` (what your executor wrote) and
   `job.state` (`SUCCEEDED`/`FAILED`/`TIMED_OUT`/`CANCELLED`) and return the
   `MissionState` the orchestrator should transition to, or `None` if this terminal
   job does not — by itself — justify a transition yet. The orchestrator calls
   `transitions.transition(mission.id, target, ...)` with whatever you return; if that
   target is not legal from the mission's current state,
   `contracts.state_machine.assert_transition` raises `InvalidStateTransitionError`
   (409) and the orchestrator logs it and retries next tick rather than crashing — but
   a policy that regularly returns an illegal target is a bug in the policy, not a
   safety net to lean on. **This is where the `STRESS_TEST` → `HUMAN_REVIEW` trap
   lives** (D-061 §2): `contracts.state_machine.TRANSITIONS[MissionState.STRESS_TEST]`
   has no `HUMAN_REVIEW` member, only `CORRELATE`. A `FUZZ` policy that reads "zero
   crashes found" out of `job.result` and returns `MissionState.HUMAN_REVIEW` directly
   gets a 409 the first time QA runs exactly that scenario. The reference
   implementation below (`_fuzz_transition_policy`) always returns `CORRELATE` for a
   terminal `FUZZ` job outcome that isn't an infrastructure fault; the "nothing to
   bind" → `HUMAN_REVIEW` decision belongs to the *`CORRELATE`* policy, one stage
   later, which is a legal edge (`TRANSITIONS[CORRELATE]` includes `HUMAN_REVIEW`).

Both registries are pre-populated with a stub for every `JobKind` that raises
`NotImplementedError` with a message naming which task owns it, so `run_worker`'s
dispatch table and `run_orchestrator`'s transition dispatch never `KeyError` on a kind
nobody has wired yet — they raise a clear, catchable error instead, which the tick
loop and claim loop both catch, log, and skip rather than crash on (see
`orchestrator/queue.py`). Call `register_executor`/`register_transition_policy` from
your own module (e.g. `workers/baseline/dispatch.py` or wherever your stage's code
already lives) to override a stub; import that module somewhere `run_worker`/
`run_orchestrator` load (a `ready()` hook or an explicit import list — see
`missions/management/commands/run_worker.py`'s own module docstring for the current
mechanism) so the registration actually runs before the loop starts.

## Two obligations D-061 §3 places on every executor, not enforced mechanically here

Both are named explicitly because they are easy to get backwards under deadline
pressure, and because nothing in this module *can* enforce them generically — they
depend on each stage's own storage shape:

1. **Check for your stage's terminal artifact before doing real work.** A worker that
   died after writing `BaselineReport` but before its `Job` row reached `SUCCEEDED`
   must not blindly re-run `run_baseline_stage` on restart — `BaselineReport` has a
   real per-mission unique constraint (D-047) and the second write raises
   `IntegrityError`. One query at the top of your executor, before the expensive part:
   "does this mission already have the row my stage produces?" If yes, skip straight
   to building the `ExecutorResult` your stage would have produced. `PATCH_GENERATE`
   is the one named exception (D-027's fan-out means "did *this attempt number*
   already produce a candidate" — `job.attempt` — not "has PATCH ever produced
   anything for this mission").
2. **`payload`/`result` never carry a secret or the raw archive.** Same rule
   `missions.models.Job`'s own docstring states. Model context, file paths,
   candidate ids, counts — never repository content, never a credential.

## What this module deliberately does not do

It does not extract a snapshot archive to a working directory — `ExecutorContext.
source_dir` is handed to you already resolved. That extraction utility
(`authorization/archive.py`, T0b) is a separate, parallel task; if it has not landed
yet, `run_worker` raises a clear, named error when it tries to build a `source_dir`
rather than silently handing your executor a missing or wrong path — see that
module's docstring.

It does not manage the job's lease or heartbeat. `run_worker` renews the lease on a
background thread for as long as your executor is running; you do not need to touch
`Job.lease_expires_at`/`heartbeat_at` yourself. If your stage needs to know "should I
stop" (cooperative cancellation, architecture spec §3.3.5:
`podman kill --signal TERM` then `SIGKILL` after 15s), read
`ExecutorContext.cancel_requested()` — a cheap, non-blocking check backed by the same
background thread, not a fresh DB query per call.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from contracts.enums import ErrorCode, MissionState
from missions.models import Job, JobKind, Mission

__all__ = [
    "CancelToken",
    "Executor",
    "ExecutorContext",
    "ExecutorResult",
    "JobOutcome",
    "TransitionPolicy",
    "executor_for",
    "register_executor",
    "register_transition_policy",
    "transition_policy_for",
]


class JobOutcome(StrEnum):
    """Terminal outcomes an executor may report.

    A deliberate subset of `missions.models.JobState`: `QUEUED`/`LEASED`/`RUNNING` are
    transport states the claim loop owns, not something a stage function decides —
    an executor is only ever called once its job is already `RUNNING`, and only ever
    reports how that run ended.
    """

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


class CancelToken(Protocol):
    """A cheap, non-blocking "should I stop" check.

    Backed by `run_worker`'s heartbeat thread, which re-reads `Job.cancel_requested`
    from the database every `WORKER_HEARTBEAT_INTERVAL_SECONDS` (architecture spec
    §3.3.5: "every 10s") and flips an in-process flag — calling this does not itself
    hit the database.
    """

    def __call__(self) -> bool: ...


@dataclass(frozen=True)
class ExecutorContext:
    """Everything a `JobKind` executor receives. Nothing more.

    `job` and `mission` are ordinary Django model instances, read freely — but see
    this module's docstring on why `mission.state` is never yours to write, and why
    `Mission.save()`/`Job.objects.filter(...).update(...)` on a lifecycle field would
    raise rather than help you route around that.
    """

    #: The claimed job, already `RUNNING` and leased to this worker.
    job: Job
    #: The mission this job belongs to. Read `mission.policy` for
    #: `MissionPolicy`-derived limits (fuzz budget, patch policy, ...); do not write
    #: any of the four SEC-16 lifecycle fields on it.
    mission: Mission
    #: A working directory already containing the mission's snapshot, extracted and
    #: ready to build/fuzz/patch. Not inside a jail; opening a `packages.sandbox.Jail`
    #: over (a copy of, or a bind mount into) this directory is the executor's own
    #: responsibility, mirroring `workers.baseline.run.run_baseline_stage`'s existing
    #: signature.
    source_dir: Path
    #: Scratch space for anything that must outlive a single `Jail` (durable log
    #: artifacts, corpora, `status.json` — architecture spec §3.3.4). Not deleted by
    #: the caller; the executor is responsible for its own cleanup if it produces
    #: anything not worth keeping.
    workspace_root: Path
    #: Propagated to every `orchestrator.events.emit` call this executor makes, so
    #: progress and outcome events trace back to the same request/run as the claim.
    trace_id: str
    #: Non-blocking cooperative-cancellation check. See `CancelToken` above.
    cancel_requested: CancelToken


@dataclass(frozen=True)
class ExecutorResult:
    """What an executor hands back to `run_worker` once its job is done.

    `result` is written to `Job.result` verbatim (must be JSON-serializable) and is
    the only channel a `TransitionPolicy` reads from — see this module's docstring,
    "The two halves of the contract".
    """

    outcome: JobOutcome
    #: Short, human-readable summary. Never a secret, never raw repository content —
    #: same rule as `result`. Surfaced in the `LOG`/outcome event `run_worker` emits.
    detail: str = ""
    #: JSON-serializable. Shape is per-kind; nothing outside your own executor and
    #: your own transition policy is required to understand it.
    result: dict[str, Any] = field(default_factory=dict)
    #: Set when `outcome` is not `SUCCEEDED`, from the frozen `ErrorCode` vocabulary
    #: (`contracts.enums.ErrorCode`) — architecture spec §6 already names one for
    #: every failure mode in scope. Left `None` on `SUCCEEDED`.
    error_code: ErrorCode | None = None
    #: Only meaningful when `outcome` is `FAILED`. Tells `run_worker` this attempt is
    #: retryable (architecture spec §3.4's `FUZZ`-stall case is the one named example:
    #: "Only when the *first attempt stalled*, never when it completed with no
    #: crash"). `run_worker` honours this only when `job.attempt < job.max_attempts`;
    #: a kind whose `MAX_ATTEMPTS_BY_KIND` is 1 (`BASELINE`, `VERIFY`, ...) can set
    #: this to `True` with no effect, but should not rely on that — set it `False`
    #: (the default) unless your kind's own retry policy says otherwise.
    retry: bool = False


class Executor(Protocol):
    def __call__(self, ctx: ExecutorContext) -> ExecutorResult: ...


class TransitionPolicy(Protocol):
    def __call__(self, job: Job, mission: Mission) -> MissionState | None: ...


def _not_implemented_executor(owner: str) -> Executor:
    def _stub(ctx: ExecutorContext) -> ExecutorResult:
        raise NotImplementedError(
            f"No executor is registered for JobKind.{ctx.job.kind}. Owned by {owner} "
            f"per D-062's staffing plan (.project/decisions.md). Register one with "
            f"orchestrator.executors.register_executor(JobKind.{ctx.job.kind})."
        )

    return _stub


def _not_implemented_policy(kind: JobKind, owner: str) -> TransitionPolicy:
    def _stub(job: Job, mission: Mission) -> MissionState | None:
        raise NotImplementedError(
            f"No transition policy is registered for JobKind.{kind}. Owned by "
            f"{owner} per D-062's staffing plan (.project/decisions.md). Register one "
            f"with orchestrator.executors.register_transition_policy(JobKind.{kind})."
        )

    return _stub


#: Who D-062 (.project/decisions.md) staffed each kind to, purely for the stub's error
#: message — not read by any code path, just so a `NotImplementedError` at 03:00 tells
#: whoever hits it which task to go find instead of just "not implemented".
_OWNER_BY_KIND: dict[JobKind, str] = {
    JobKind.BASELINE: "T1",
    JobKind.SANITIZER_BUILD: "T1/T2 (see this module's docstring — its orchestration "
    "point is genuinely unresolved as of T0; SANITIZER_BUILD has no MissionState row "
    "of its own in architecture spec §3.2's progress table)",
    JobKind.ANALYZE: "backend-developer (#22, D-144) -- workers.static_analysis.dispatch",
    JobKind.FUZZ: "T2 (a reference transition policy is registered below; the "
    "executor itself is not)",
    JobKind.MINIMIZE: "T2",
    JobKind.CORRELATE: "T3",
    JobKind.PATCH_GENERATE: "T4",
    JobKind.VERIFY: "T5",
    JobKind.EXPORT: "T6",
    JobKind.TEARDOWN: "T7",
}

EXECUTOR_REGISTRY: dict[JobKind, Executor] = {
    kind: _not_implemented_executor(owner) for kind, owner in _OWNER_BY_KIND.items()
}

TRANSITION_POLICY_REGISTRY: dict[JobKind, TransitionPolicy] = {
    kind: _not_implemented_policy(kind, owner) for kind, owner in _OWNER_BY_KIND.items()
}


def register_executor(kind: JobKind) -> Callable[[Executor], Executor]:
    """Decorator: `@register_executor(JobKind.BASELINE)` over your stage function."""

    def _register(fn: Executor) -> Executor:
        EXECUTOR_REGISTRY[kind] = fn
        return fn

    return _register


def register_transition_policy(kind: JobKind) -> Callable[[TransitionPolicy], TransitionPolicy]:
    """Decorator: `@register_transition_policy(JobKind.FUZZ)` over your policy function."""

    def _register(fn: TransitionPolicy) -> TransitionPolicy:
        TRANSITION_POLICY_REGISTRY[kind] = fn
        return fn

    return _register


def executor_for(kind: JobKind) -> Executor:
    return EXECUTOR_REGISTRY[JobKind(kind)]


def transition_policy_for(kind: JobKind) -> TransitionPolicy:
    return TRANSITION_POLICY_REGISTRY[JobKind(kind)]


# ---------------------------------------------------------------------------------
# Reference transition policy: JobKind.FUZZ, the STRESS_TEST -> CORRELATE trap.
#
# This is real, registered, tested code (orchestrator/tests/test_stress_test_routing.
# py) — not a stub — because D-061 §2 and D-062 both flag it by name as the one place
# an implementer optimizing for "fewest moving parts" gets this backwards under
# deadline pressure, and because T0 owns "the one function that reads a job's
# terminal row and calls transition()" (D-062's staffing plan), which is exactly what
# gets this right or wrong. The FUZZ *executor* itself (the libFuzzer campaign runner,
# stderr tailing, crash capture) is not built here and is not this policy's concern —
# only what `job.result` must say for this policy to route correctly. T2 owns the
# executor and should treat the two `result` keys read below
# (`infra_failure`, and — for informational/logging purposes only, never for routing —
# `crashes_found`) as the provisional contract; adjust in code review with T3 if the
# real FUZZ/CORRELATE executors need a different shape, not silently.
# ---------------------------------------------------------------------------------


@register_transition_policy(JobKind.FUZZ)
def _fuzz_transition_policy(job: Job, mission: Mission) -> MissionState | None:
    """A terminal FUZZ job always routes STRESS_TEST -> CORRELATE.

    Never `HUMAN_REVIEW` directly — `contracts.state_machine.TRANSITIONS
    [MissionState.STRESS_TEST]` is `{CORRELATE, PAUSED} | _ABORTS` and has no
    `HUMAN_REVIEW` member. This is true whether the campaign found crashes, ran clean
    to its budget, or exhausted its stall retries (architecture spec §6.3(a) and
    §6.3(b) both, read literally, describe a mission that "goes to HUMAN_REVIEW" —
    which can only mean "ends up there after CORRELATE finds nothing to bind", per
    D-061 §2, not a direct edge this table does not have).

    The one branch that does NOT go to `CORRELATE`: an infrastructure fault unrelated
    to the fuzz campaign itself (architecture spec §6.1, `SANDBOX_UNAVAILABLE` —
    "one retry after 5s, then job FAILED -> mission FAILED"). The executor is expected
    to set `result["infra_failure"] = True` to distinguish this from an ordinary
    "campaign ended" outcome; a `FAILED` job with no such marker is treated as a
    campaign-side failure (attempts exhausted) and still routed to `CORRELATE`,
    consistent with the rest of this function's reasoning — CORRELATE, not this
    policy, is where "the campaign never really produced anything to bind" is judged.
    """
    if job.state == "FAILED" and bool(job.result.get("infra_failure")):
        return MissionState.FAILED
    return MissionState.CORRELATE
