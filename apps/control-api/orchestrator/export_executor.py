"""`JobKind.EXPORT` executor and transition policy (#168, T6).

Read `orchestrator/executors.py`'s module docstring first. This is the piece D-061 §4
and §5 both flag by name as a **hard dependency of #168 closing #50, not parallel
slack**: a mission that reaches `VERIFY`'s terminal state with no `EXPORT` executor
hangs in `EXPORTING` exactly the way the original bug hung in `VALIDATING` — one stage
later, and worse, because `EXPORTING` is the state a judge's own read of "did this
mission finish" depends on (`P0-12`: "a mission is not `VERIFIED` until the evidence
bundle that justifies it exists").

## The two halves

* `_export_executor` (`@register_executor(JobKind.EXPORT)`) — calls `orchestrator.
  evidence_export.export_mission`, which does the actual assembly/render/tar/ingest
  work (see that module's own docstring for the idempotency and partial-data rules).
  This function's only job is translating its `ExportOutcome` into `ExecutorResult`.
* `_export_transition_policy` (`@register_transition_policy(JobKind.EXPORT)`) —
  `contracts.state_machine.TRANSITIONS[MissionState.EXPORTING]` is `{VERIFIED,
  REJECTED, HUMAN_REVIEW} | {CANCELLING, FAILED}`. A successful export does **not**
  by itself say which of the three verdict states is correct — that is a function of
  the mission's own `VerificationRecord`s, exactly like `orchestrator.transitions.
  transition`'s own `assert_verdict_is_evidenced` guard re-derives independently.
  This policy calls the same reduction (`contracts.state_machine.
  derive_mission_outcome`, backed by `contracts.verdict.derive_mission_verdict`) over
  the same read (`orchestrator.repository.load_verifications`) that `transition()`
  itself will use to check the target it is handed — so a target this policy returns
  can never be inconsistent with the guard that gates it. A **failed** export
  (`JobOutcome.FAILED`/`TIMED_OUT`) does not get the benefit of the doubt: `P0-12`
  means a verdict is never granted without the evidence that backs it existing, so an
  export that could not be written routes to `FAILED`, not to whatever verdict the
  gates would otherwise have supported. `CANCELLED` defers, same reasoning as every
  other terminal-job policy in this codebase (`_baseline_transition_policy`'s own
  docstring explains why).

## Idempotency

`evidence_export.export_mission`'s own `reuse_existing=True` default (used by
`_export_executor` below) is the D-061 §3 check — see that module's docstring for why
`Export` has no per-mission uniqueness constraint but a re-run of this executor still
never redoes real work or duplicates bundle bytes on disk.
"""

from __future__ import annotations

from contracts.enums import ErrorCode, MissionState
from contracts.state_machine import derive_mission_outcome
from missions.models import Job, JobKind, JobState, Mission
from orchestrator import repository
from orchestrator.evidence_bundle import EvidenceUnavailableError
from orchestrator.evidence_export import export_mission
from orchestrator.executors import (
    ExecutorContext,
    ExecutorResult,
    JobOutcome,
    register_executor,
    register_transition_policy,
)

__all__ = ["export_executor", "export_transition_policy"]


@register_executor(JobKind.EXPORT)
def export_executor(ctx: ExecutorContext) -> ExecutorResult:
    """Assemble (or reuse) this mission's evidence bundle and write it to durable
    storage. Never raises on missing/partial evidence — `evidence_bundle.assemble_
    evidence_bundle` already represents that honestly inside the bundle itself
    (`None`/empty sections, never fabricated); only a genuine failure to assemble at
    all (`EvidenceUnavailableError` — no snapshot or authorization on file, which no
    real pipeline path reaches, since `EXPORTING` sits downstream of both) or an
    infrastructure fault (disk full, artifact store unwritable) is reported as
    `FAILED`.
    """
    try:
        outcome = export_mission(
            ctx.mission.id,
            reuse_existing=True,
            workspace_root=ctx.workspace_root,
        )
    except EvidenceUnavailableError as exc:
        return ExecutorResult(
            outcome=JobOutcome.FAILED,
            detail=f"Cannot export: {exc.message}",
            result={"error": exc.message},
            error_code=ErrorCode.CONFLICT,
            retry=False,
        )
    except Exception as exc:  # an infra fault becomes evidence, not a crash
        return ExecutorResult(
            outcome=JobOutcome.FAILED,
            detail=f"Evidence export failed: {type(exc).__name__}: {exc}",
            result={"error": str(exc)},
            error_code=ErrorCode.INTERNAL_ERROR,
            retry=ctx.job.attempt < ctx.job.max_attempts,
        )

    receipt = outcome.receipt
    detail = (
        f"Evidence bundle exported (export_id={receipt.export_id}, "
        f"{'reused existing' if outcome.reused_existing else 'freshly written'})."
    )
    return ExecutorResult(
        outcome=JobOutcome.SUCCEEDED,
        detail=detail,
        result={
            "export_id": str(receipt.export_id),
            "formats": receipt.formats,
            "artifact_count": len(receipt.artifacts),
            "reused_existing": outcome.reused_existing,
        },
    )


@register_transition_policy(JobKind.EXPORT)
def export_transition_policy(job: Job, mission: Mission) -> MissionState | None:
    """A terminal `EXPORT` job routes `EXPORTING -> {VERIFIED, REJECTED,
    HUMAN_REVIEW}` on success, derived from this mission's own verification records
    (never guessed, never copied from `job.result`); `FAILED` on any non-`CANCELLED`
    failure; `None` (defer) on `CANCELLED`.

    **The trap this function exists to not fall into — found by reading
    `contracts.state_machine.assert_verdict_is_evidenced`, not by running into it live**
    (same category as `_fuzz_transition_policy`'s `STRESS_TEST -> HUMAN_REVIEW` trap,
    `orchestrator/executors.py`'s own docstring). That guard raises
    `VerificationRequiredError` for **every** verdict target — `VERIFIED`, `REJECTED`,
    *and* `HUMAN_REVIEW` alike — when `verifications` is empty: "a verdict state must be
    justified by at least one gate matrix" is unconditional, not "unless the target is
    the cautious one." A policy that reads zero verification records and reaches for
    `HUMAN_REVIEW` as the "safe" choice is wrong for the same reason `derive_
    mission_outcome`/`STATE_FOR_VERDICT` would suggest it: `HUMAN_REVIEW` is *also* a
    verdict state, gated by the exact same guard, and `dispatch_terminal_jobs` would
    catch the resulting `VerificationRequiredError`, log it, and retry forever — the
    mission stuck in `EXPORTING`, one stage past where #50 originally stalled it, which
    is the literal failure D-061 §6 names this task to prevent.

    In the intended pipeline this case should not arise — `CORRELATE`'s own transition
    policy (T3) is supposed to route "nothing to bind" straight to `HUMAN_REVIEW` before
    `PATCH`/`VERIFY` ever run, per D-061 §2, so `EXPORTING` is only reached once at
    least one `VerificationRecord` exists. T3/T5 are not both landed on this branch as
    of T6 (checked directly), so this function does not get to assume that invariant
    holds by the time it runs. `MissionState.FAILED` is the one target in
    `TRANSITIONS[EXPORTING]` that is **not** gated by `assert_verdict_is_evidenced`
    (`VERDICT_FOR_STATE` has no `FAILED` entry, so the guard returns immediately for
    it) — a real export with zero evidence to derive a verdict from is reported as a
    pipeline failure, honestly, rather than either a fabricated verdict or a mission
    that hangs. Flagged in this task's handoff as a real integration gap for QA's Day-3
    pass to exercise once T3/T5 land, not silently assumed away here.
    """
    if job.state == JobState.CANCELLED:
        return None
    if job.state != JobState.SUCCEEDED:
        return MissionState.FAILED

    verifications = repository.load_verifications(mission.id)
    if not verifications:
        return MissionState.FAILED

    return derive_mission_outcome([record.verdict for record in verifications])
