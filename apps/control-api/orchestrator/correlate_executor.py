"""`JobKind.CORRELATE` executor and transition policy (#168, T3).

Read `orchestrator/executors.py`'s module docstring first — this file is built
against its contract, not the other way around. Read that module's own reference
`_fuzz_transition_policy` too: it always routes a terminal `FUZZ` job to `CORRELATE`
(D-061 §2), whatever the campaign found, precisely so that **this** module is where
"is there anything here worth acting on" actually gets decided. `contracts.
state_machine.TRANSITIONS[MissionState.CORRELATE]` is `{PATCH, PAUSED, HUMAN_REVIEW}
| _ABORTS` — `HUMAN_REVIEW` is a legal edge from here, unlike from `STRESS_TEST`, which
is the whole reason D-061 §2 assigns "nothing to bind" to this stage and not the one
before it.

## What "correlate" means here, and why it is this narrow

D-061 §4's full brief for T3 is "bind the sanitizer-confirmed crash to a
`SourceLocation`/`FindingDetail.code_slice`". This module does not do that binding —
it does the smaller, honest thing the current state of the codebase actually supports,
per this task's own instruction not to fabricate a scoring/correlation algorithm that
does not exist: **if there is something recorded (or reported) worth turning into a
patch attempt, say so and route to `PATCH`; if there is nothing, say so and route to
`HUMAN_REVIEW`.** No new model, no invented "correlation score" — `missions.models`
belongs to the database-engineer, and this task's scope note is explicit that schema
changes are their call, not this one.

## Two signals, checked in priority order, and why both exist

`FUZZ` (T2, #168) is being built in parallel on `feat/168-t2-fuzz-minimize` and — as of
this module landing — has not merged a `record_finding`-shaped function into `main`
(checked directly: `git diff main...feat/168-t2-fuzz-minimize` is empty at the point
this was written; the branch exists but no FUZZ executor commits are on it yet). D-061
§4 itself names this gap: "there is no `record_finding`-shaped function anywhere in the
codebase today ... This executor (or T3) has to write it" — but writing `FUZZ`'s own
producer function is not this task's scope (T2 owns `FUZZ` end to end per D-062's
staffing plan), and this module does not add one. Instead:

1. **`missions.models.Finding` rows for this mission, if any exist.** The model is
   already fully migrated and already has a real producer path in this codebase today
   (`workers/replay/run.py`'s `_EVENT_FINDING_RECORDED`, outside this `JobKind` chain,
   and the `finding` fixture every orchestrator test already uses) — so checking for
   real rows first, rather than only ever reading the raw `Job.result`, means this
   executor is already correct the day T2 (or anyone else) lands a `record_finding`
   call in the `FUZZ`/`MINIMIZE` path, with zero changes needed here. This is the
   authoritative signal: a `Finding` row is what `PATCH_GENERATE` (T4) actually needs a
   `finding_id` for (`orchestrator.candidates.record_patch_candidate`'s required
   `finding_id` parameter) — routing to `PATCH` because a `Finding` exists means T4
   has something real to work from.
2. **The terminal `FUZZ` job's raw `Job.result["crashes_found"]`, as a fallback.**
   This is the interface T0's own reference `_fuzz_transition_policy` already reads
   and names as "the provisional contract" for `FUZZ`'s executor
   (`orchestrator/executors.py`, `_OWNER_BY_KIND[JobKind.FUZZ]`'s comment). Used only
   when no `Finding` row exists yet, so a mission whose `FUZZ` stage genuinely found
   crashes is not sent to `HUMAN_REVIEW` for the accident of timing (T2's producer not
   being wired yet), while still being honest in `result["source"]` about which signal
   actually justified the decision — a provisional route on a raw crash count, not a
   real bound finding, and `PATCH_GENERATE`'s own future work will need to close that
   gap for the demo to be end-to-end real (flagged below, "What is incomplete").

No `Finding` row and no terminal `FUZZ` job reporting `crashes_found > 0` — including
the common no-op case in tests that walk a mission straight to `CORRELATE` with no
`FUZZ` job at all — is "nothing to bind" and routes to `HUMAN_REVIEW`, per D-061 §2.

## Idempotency (D-061 §3 obligation)

`CORRELATE` writes nothing — no new row, no field on `Mission`. Its "terminal
artifact" is the decision captured in `Job.result` itself, which the queue already
treats as immutable once a job reaches a terminal state (`orchestrator.queue.
complete_job` only ever writes a `LEASED`/`RUNNING` job). Re-running this executor
against the same mission (a worker crash-and-restart before its `Job` row reached
`SUCCEEDED`, or a fresh attempt after `reap_expired_leases` reclaims a lease) reads the
same `Finding` rows and the same terminal `FUZZ` job every time and produces the same
answer — safe by construction, the same shape `orchestrator/teardown_executor.py`
documents for its own no-artifact case, not a guard added here. There is no
uniqueness constraint this module could violate on retry, unlike `BaselineReport`
(D-061 §3's own named example).

## What is incomplete, named rather than hidden

* **No `SourceLocation`/`code_slice` binding.** D-061 §4's fuller brief for `CORRELATE`
  is not implemented — a `Finding` row already carries `file_path`/`line`/
  `code_slice` on its own (`missions/models.py`), so there is nothing left for this
  stage to compute once a real `Finding` exists; this module's job is only the
  routing decision, not enrichment.
* **The `crashes_found`-only fallback path never creates a `Finding` row.** A mission
  that reaches `PATCH` via `result["source"] == "fuzz_result_crashes_found"` has no
  `Finding` for `PATCH_GENERATE` (T4) to bind a candidate to yet — this is the fast-
  follow this module's own docstring above points at, to be closed once T2's real
  `record_finding` lands (at which point the `Finding`-rows branch takes over and this
  fallback stops being exercised for real traffic; it stays as a documented, tested
  degradation path rather than being deleted, since a `FUZZ` executor without a
  `record_finding` call is still possible in a future build).
"""

from __future__ import annotations

from contracts.enums import MissionState
from missions.models import Finding, Job, JobKind, JobState, Mission
from orchestrator.executors import (
    ExecutorContext,
    ExecutorResult,
    JobOutcome,
    register_executor,
    register_transition_policy,
)

__all__: list[str] = []

#: Same terminal-state set `orchestrator.queue` uses to decide a job is done.
_TERMINAL_JOB_STATES = (
    JobState.SUCCEEDED,
    JobState.FAILED,
    JobState.TIMED_OUT,
    JobState.CANCELLED,
)


def _latest_terminal_fuzz_job(mission: Mission) -> Job | None:
    """The same "one job per (mission, kind)" query `orchestrator.queue.
    dispatch_terminal_jobs` runs to find the terminal row it dispatches off — read
    here, not written, since this module only ever reads `FUZZ`'s output, never its
    lifecycle (`orchestrator/executors.py`'s "one rule that matters more than the type
    signatures")."""
    return (
        Job.objects.filter(
            mission=mission, kind=JobKind.FUZZ, state__in=_TERMINAL_JOB_STATES
        )
        .order_by("-finished_at")
        .first()
    )


@register_executor(JobKind.CORRELATE)
def _correlate_executor(ctx: ExecutorContext) -> ExecutorResult:
    """Decide whether `FUZZ` produced anything worth a patch attempt.

    Always reports `JobOutcome.SUCCEEDED` — deciding "nothing to bind" is a legitimate
    business outcome of this stage, not an infrastructure failure, the same reasoning
    D-061 §2 already applies to `VERIFY`'s `REJECTED` verdict ("do not conflate 'our
    system broke' with 'the patch was bad'"). A genuine programming error (a query
    raising for a reason unrelated to what it found) is not caught here — it escapes to
    `run_worker`'s own outer handler, which reports a `FAILED` job with no `result`
    payload; this executor's transition policy already treats a job with no
    `correlated` key in its result as "nothing to bind" (see below), so that failure
    mode still routes somewhere legal rather than wedging the mission.
    """
    findings = list(Finding.objects.filter(mission=ctx.mission).order_by("detected_at"))
    if findings:
        finding_ids = [str(row.id) for row in findings]
        detail = (
            f"CORRELATED: {len(findings)} Finding row(s) already recorded for this "
            f"mission."
        )
        result = {
            "correlated": True,
            "source": "finding_rows",
            "finding_count": len(findings),
            "finding_ids": finding_ids,
        }
        return ExecutorResult(outcome=JobOutcome.SUCCEEDED, detail=detail, result=result)

    fuzz_job = _latest_terminal_fuzz_job(ctx.mission)
    crashes_found = int((fuzz_job.result or {}).get("crashes_found", 0) or 0) if fuzz_job else 0

    if crashes_found > 0:
        detail = (
            f"CORRELATED (provisional): terminal FUZZ job reported {crashes_found} "
            f"crash(es) but no Finding row exists yet for this mission -- routing to "
            f"PATCH on the raw FUZZ signal. See this module's docstring, 'What is "
            f"incomplete'."
        )
        result = {
            "correlated": True,
            "source": "fuzz_result_crashes_found",
            "finding_count": 0,
            "finding_ids": [],
            "crashes_found": crashes_found,
        }
        return ExecutorResult(outcome=JobOutcome.SUCCEEDED, detail=detail, result=result)

    detail = "NOTHING_TO_CORRELATE: no Finding rows, and FUZZ reported no crashes."
    result = {
        "correlated": False,
        "source": "no_signal",
        "finding_count": 0,
        "finding_ids": [],
        "crashes_found": crashes_found,
    }
    return ExecutorResult(outcome=JobOutcome.SUCCEEDED, detail=detail, result=result)


@register_transition_policy(JobKind.CORRELATE)
def _correlate_transition_policy(job: Job, mission: Mission) -> MissionState | None:
    """`CORRELATE -> PATCH` when something was bound; `CORRELATE -> HUMAN_REVIEW` — the
    exact "nothing to bind" edge D-061 §2 assigns to this stage — otherwise.

    `TRANSITIONS[MissionState.CORRELATE]` (`contracts/state_machine.py`) is `{PATCH,
    PAUSED, HUMAN_REVIEW} | _ABORTS`; both targets this function can return are legal
    members of that set, so unlike `_fuzz_transition_policy`'s own trap there is no
    illegal edge to guard against here — the judgment call is only which of the two
    legal ones is true.

    A `CANCELLED` job defers (`None`) for the same reason `_baseline_transition_policy`
    does: a mission-level cancel is already in flight and owns the mission's next
    transition, and this policy has no reliable view of which target is legal by the
    time a stale `CANCELLED` row is read. Any other non-`SUCCEEDED` terminal state
    (`FAILED`, `TIMED_OUT` — `MAX_ATTEMPTS_BY_KIND[CORRELATE]` is `1`, so neither is
    ever retried) means the correlate step itself did not complete its decision, which
    for this stage's read-only, single-query work is treated as an infrastructure-level
    problem, not a legitimate "we looked and found nothing" outcome — that legitimate
    case always reports `SUCCEEDED` (see `_correlate_executor`'s own docstring) — so it
    routes to `Mission.FAILED` rather than guessing `HUMAN_REVIEW` for a job that never
    actually looked.
    """
    if job.state == JobState.CANCELLED:
        return None
    if job.state == JobState.SUCCEEDED:
        if bool((job.result or {}).get("correlated")):
            return MissionState.PATCH
        return MissionState.HUMAN_REVIEW
    return MissionState.FAILED
