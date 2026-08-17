"""`JobKind.TEARDOWN` executor and transition policy (#168, T7).

**No new teardown logic lives here.** `orchestrator/teardown.py` (#72) is already the
real, tested mechanism that releases a mission's sandbox containers and model-host
lease and writes a `TEARDOWN_CONFIRMED` event per resource — and it already runs today,
synchronously, from `orchestrator.transitions.transition`'s `_run_teardown_after_commit`
hook, for every transition into `CANCELLING` or a terminal `MissionState`
(`transitions._requires_teardown`). D-061 §4 names T7 as "mostly making sure a
`TEARDOWN` `JobKind` exists for symmetry with the spec's dispatch table" — this module
is that symmetry: a thin `Executor`/`TransitionPolicy` pair over the existing mechanism,
so a `TEARDOWN` `Job` (architecture spec §6.7: "every terminal transition enqueues a
`TEARDOWN` job, `max_attempts=3`") has something registered to run instead of hitting
`orchestrator.executors._not_implemented_executor`'s stub once T0's tick loop starts
enqueueing one.

Calling the same idempotent mechanism a second time (once synchronously via
`transition()`, again via a `TEARDOWN` job dispatched by the worker) is deliberate, not
a bug to dedupe away — see "Idempotency" below.

## The one policy decision this module owns: R3

Architecture spec §2.2 R3, verbatim: *"`CANCELLING → CANCELLED` requires a teardown
receipt. Without one it is `CANCELLING → FAILED`."* `contracts.state_machine.
TRANSITIONS[MissionState.CANCELLING]` is `{CANCELLED, FAILED}` — both legal, and
nothing before this module ever calls `transition()` to make that choice, which is
exactly the gap `.project/evidence/d7-gate-50-live-run-2026-08-17.md` found live: a
cancelled mission "left permanently in `CANCELLING`, not `CANCELLED`, in the database."
`teardown_transition_policy` below is that missing call: a terminal `TEARDOWN` job for a
mission currently in `CANCELLING` routes to `CANCELLED` only if its `result` shows every
resource released, and to `FAILED` otherwise — never silently stays put. For every other
teardown-triggering target (`VERIFIED`/`REJECTED`/`HUMAN_REVIEW`/`FAILED`/`CANCELLED`
itself), the mission is already terminal — `TRANSITIONS[...]` for all five is the empty
set — so the policy returns `None`: there is nowhere further to route, and the job's
outcome is already fully recorded as `TEARDOWN_CONFIRMED` events by the executor.

## Honest partial failure, not all-or-nothing

`teardown.teardown_started_compute` already refuses to hide a leak: it emits one
`TEARDOWN_CONFIRMED` event per resource (`released=True` or `False`) before raising
`TeardownFailedError`, so a partial failure is never silently swallowed at the event
level. This executor preserves that at the `Job.result` level too — `result["outcomes"]`
lists every resource this run touched with its own `released` flag, and `detail` states
the honest fraction ("released 2 of 3 resources; 1 failed to release") rather than
collapsing to a single SUCCEEDED/FAILED bit that would hide which resource, if any,
might still be running. `JobOutcome` itself only has room for one bit — `result` is
where the granularity a reviewer or an operator actually needs lives, per this module's
own contract (`orchestrator.executors.ExecutorResult.result` docstring).

## Idempotency (D-061 §3 obligation, `TEARDOWN`'s version of it)

D-061 §3 asks every executor to check for its stage's terminal artifact before doing
real work, so a crash-and-restart cannot double-write something with a uniqueness
constraint. `TEARDOWN` has no such artifact and no such constraint — its "terminal
artifact" check is structural, not a query: `teardown.teardown_started_compute` is
already written so that releasing an already-released (or never-started) resource is a
no-op, not an error (`DockerSandboxReaper`/`ModelHostReaper` both return `()` when they
find nothing to release, and `teardown_started_compute` reports a synthetic
`no-started-compute` outcome with `released=True` when every reaper comes back empty).
Re-running this executor on the same mission — after the synchronous
`_run_teardown_after_commit` call already tore it down, after a worker crash mid-job, or
because `max_attempts=3` retried it — is therefore safe by construction, not by a guard
added here. `test_second_teardown_run_is_a_safe_no_op` in this module's test file proves
it rather than asserting it.

## What this module deliberately does not do

It does not enqueue the `TEARDOWN` `Job` itself, and it does not decide whether the
existing synchronous `_run_teardown_after_commit` call in `orchestrator/transitions.py`
should be replaced by, or kept alongside, a `Job`-queue dispatch. Both are T0's tick-loop
scope (`orchestrator/queue.py`, not yet built on this branch — see this repo's git log).
This module registers against the contract T0's `executors.py` already defines
(`register_executor`, `register_transition_policy`) so that whichever enqueue path T0
lands has a real `TEARDOWN` executor and transition policy waiting for it, per D-061 §4.
"""

from __future__ import annotations

from django.utils import timezone

from contracts.enums import ErrorCode, MissionState
from missions.models import Job, JobKind, JobState, Mission
from orchestrator import teardown
from orchestrator.executors import (
    ExecutorContext,
    ExecutorResult,
    JobOutcome,
    register_executor,
    register_transition_policy,
)

__all__ = ["teardown_executor", "teardown_transition_policy"]


@register_executor(JobKind.TEARDOWN)
def teardown_executor(ctx: ExecutorContext) -> ExecutorResult:
    """Release every resource `teardown.default_reapers()` knows about for this mission.

    Never raises on a resource that fails to release — that is reported honestly in
    `result` and via `outcome=FAILED`, not hidden. Only a genuine inability to run the
    mechanism at all (e.g. the database write inside `teardown.teardown_started_compute`
    itself failing) is treated as a retryable infrastructure fault.
    """
    now = timezone.now()
    reason = str(ctx.job.payload.get("reason") or "") or (
        f"TEARDOWN job {ctx.job.id} for mission {ctx.mission.id}"
    )

    try:
        outcomes = teardown.teardown_started_compute(
            ctx.mission.id,
            trace_id=ctx.trace_id,
            reason=reason,
            now=now,
        )
    except teardown.TeardownFailedError as exc:
        # Outcomes — including the ones that DID release — are already persisted as
        # TEARDOWN_CONFIRMED events by teardown_started_compute before this raises.
        # Recovering them here is what lets `result` report the honest fraction
        # instead of collapsing a partial failure into "teardown failed, details lost".
        outcomes = exc.outcomes
    except Exception as exc:  # an infra fault becomes evidence, not a crash
        return ExecutorResult(
            outcome=JobOutcome.FAILED,
            detail=(
                f"Teardown mechanism itself could not run: {type(exc).__name__}: {exc}"
            ),
            result={
                "outcomes": [],
                "released_count": 0,
                "failed_count": 0,
                "total": 0,
                "infra_failure": True,
            },
            error_code=ErrorCode.INTERNAL_ERROR,
            retry=ctx.job.attempt < ctx.job.max_attempts,
        )

    released = [outcome for outcome in outcomes if outcome.released]
    failed = [outcome for outcome in outcomes if not outcome.released]
    total = len(outcomes)

    result = {
        "outcomes": [
            {
                "resource_kind": outcome.resource_kind,
                "resource_id": outcome.resource_id,
                "released": outcome.released,
                "detail": outcome.detail,
            }
            for outcome in outcomes
        ],
        "released_count": len(released),
        "failed_count": len(failed),
        "total": total,
    }

    if failed:
        detail = (
            f"Teardown released {len(released)} of {total} resource(s); "
            f"{len(failed)} failed to release."
        )
        return ExecutorResult(
            outcome=JobOutcome.FAILED,
            detail=detail,
            result=result,
            error_code=ErrorCode.INTERNAL_ERROR,
            retry=ctx.job.attempt < ctx.job.max_attempts,
        )

    detail = f"Teardown released {len(released)} of {total} resource(s); zero leaked."
    return ExecutorResult(outcome=JobOutcome.SUCCEEDED, detail=detail, result=result)


@register_transition_policy(JobKind.TEARDOWN)
def teardown_transition_policy(job: Job, mission: Mission) -> MissionState | None:
    """R3: `CANCELLING -> CANCELLED` only with a teardown receipt, else `-> FAILED`.

    Every other target that triggers teardown (`VERIFIED`/`REJECTED`/`HUMAN_REVIEW`/
    `FAILED`/`CANCELLED`) is already a terminal `MissionState` with no outgoing edge in
    `contracts.state_machine.TRANSITIONS` — this returns `None` for all of them, same as
    a `FUZZ` job that does not yet justify a transition (see `_fuzz_transition_policy`'s
    own docstring in `orchestrator/executors.py` for the shape this mirrors).

    "A receipt" means: the job actually reached `SUCCEEDED` (a `TIMED_OUT`/`CANCELLED`/
    `FAILED` job never gets the benefit of the doubt, even if `result` looks complete)
    *and* `result` reports at least one resource considered and zero failures. A job
    whose `result` is missing or malformed (e.g. a job that never got far enough to
    write one) defaults to "no receipt" via `dict.get`'s fallback, not to a crash.
    """
    if mission.state_enum is not MissionState.CANCELLING:
        return None

    result = job.result or {}
    has_receipt = (
        job.state == JobState.SUCCEEDED
        and result.get("total", 0) > 0
        and result.get("failed_count", 1) == 0
    )
    return MissionState.CANCELLED if has_receipt else MissionState.FAILED
