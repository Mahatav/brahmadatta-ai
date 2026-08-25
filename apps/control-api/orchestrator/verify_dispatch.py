"""`JobKind.VERIFY` — the executor and transition policy (#168, T5).

Read `orchestrator/executors.py`'s module docstring first; this file is written
against the contract it defines. The two functions below do not invent any new
verification logic — `orchestrator/verification.py::run_verification` (the gate
matrix: compile, reproducer replay, regression suite) and
`orchestrator/candidates.py::record_verification` (persistence, mission binding,
D-046's candidate-set freeze) are already built and already tested. This module's job
is narrow: read a `VERIFY` job's payload, call those two functions in the right order
against `ExecutorContext`, and decide the one thing D-061 §2 says only the transition
policy may decide — which `MissionState` a terminal `VERIFY` job justifies.

## The one fact that shapes both halves: VERIFY fans out, one job per candidate

Architecture spec §2.3, decision (b): `PATCH` produces a *set* of `PatchCandidate`
rows; `VERIFY` produces one `VerificationRecord` per policy-accepted candidate — not
one `VERIFY` job per mission. `VerificationRecord.patch` is a real `OneToOneField`
(`missions/models.py`), so "one job per candidate" is enforced by a unique
constraint, not by convention. This module assumes each `VERIFY` `Job.payload`
carries exactly one `"patch_id"` — the candidate this job verifies — mirroring how
`PATCH_GENERATE` is expected to enqueue one job per attempt. Whoever wires
`PATCH_GENERATE`'s fan-out (T4) is the producer of that payload shape; it is recorded
here as the contract this executor consumes, and should move to `04-api-plan.md` or
an equivalent internal-contract note if T4 needs a different shape — flagged in this
task's handoff rather than assumed silently.

## Idempotency key: the candidate, not the mission and not `job.attempt`

D-061 §3 rule 1 names `PATCH_GENERATE` as the one kind that checks "did *this attempt
number* already produce a candidate" (`job.attempt`) instead of "does this mission
already have the row my stage produces." `VERIFY` is a third shape, distinct from
both named in that rule:

* Not mission-scoped like `BASELINE` — a mission's terminal `VERIFY` artifact is not
  one row, it is one row *per candidate*, so "does this mission have a
  `VerificationRecord`" would wrongly skip verifying the second candidate once the
  first one exists.
* Not attempt-scoped like `PATCH_GENERATE` — `MAX_ATTEMPTS_BY_KIND[JobKind.VERIFY]` is
  1 (`missions/models.py`, and asserted directly by
  `missions/tests/test_models.py::test_verify_jobs_are_not_retryable`), so
  `job.attempt` is always `1` and carries no information to key on.

The real per-job identity is *which candidate* — `job.payload["patch_id"]` — and
`VerificationRecord.patch`'s `OneToOneField` is the same kind of real per-unit
constraint `BaselineReport` has per mission. The check below queries on `patch_id`
for exactly that reason: a worker that died after `record_verification` committed but
before this job's row reached `SUCCEEDED` must not retry into an `IntegrityError` —
it reports the existing record and moves on.

## Where the FUZZ reference policy's trap reappears, in `VERIFY`'s own shape

`_fuzz_transition_policy` (`orchestrator/executors.py`) exists because
`STRESS_TEST`'s transition table has no `HUMAN_REVIEW` member — only `CORRELATE` does
— so a policy that reads "nothing found" and jumps straight to `HUMAN_REVIEW` 409s.
`VERIFY`'s table (`contracts/state_machine.TRANSITIONS[MissionState.VERIFY]`) is
`{EXPORTING, PAUSED, HUMAN_REVIEW} | _ABORTS` — `HUMAN_REVIEW` *is* a legal direct
target here, which makes the opposite mistake tempting: routing straight to
`HUMAN_REVIEW` the moment one candidate's gates come back inconclusive (any required
gate `NOT_RUN`/`ERROR` — see `contracts.verdict.derive_verdict`). That would be wrong
for the same underlying reason D-061 §2 gives for `STRESS_TEST`: the mission's
terminal verdict is derived from the **whole candidate set**
(`derive_mission_outcome`, architecture spec §2.3), not from whichever candidate's
job finishes first or last, and `contracts.state_machine.assert_verdict_is_evidenced`
only runs on transitions *out of* `EXPORTING`. Deciding `HUMAN_REVIEW` here, from one
job, is exactly the "generate until pass"-adjacent shortcut D-046 exists to close —
just on the losing side instead of the winning one. `EXPORTING` is always the next
stop for a job that produced a real verdict; `EXPORTING`'s own transition-out
decides `VERIFIED`/`REJECTED`/`HUMAN_REVIEW` once every candidate has a record.

## Wiring: no `run_worker`/`run_orchestrator` yet to import this automatically

T0's dispatch loop (`manage.py run_worker`, `manage.py run_orchestrator`) has not
landed on this branch. `missions/apps.py::MissionsConfig.ready()` imports this module
so `@register_executor`/`@register_transition_policy` run at Django app-startup —
which fires for *every* entry point that loads the app registry (management
commands including the two not yet built, ASGI/WSGI boot, `manage.py check`, the test
suite), not only a hand-picked import list. T1/T2/T3/T4/T6/T7 should add the same one
import line for their own dispatch module to `MissionsConfig.ready()` (or T0 can
consolidate all seven into one explicit list there) rather than each inventing a
separate wiring mechanism.

## What this module deliberately does not do

It does not open a `packages.sandbox.Jail` itself — SEC-47 closed that gap inside
`orchestrator/verification.py` instead. `run_verification` now opens exactly one
`Jail` per call (`git apply`'s candidate diff is written to a file inside the jail
and applied via a path argument rather than piped over stdin, since `Jail.run()`
hardcodes `stdin=subprocess.DEVNULL`), sized for the sanitizer build
`VerificationBaseline`'s own default turns on (`memory_bytes` from
`adapters.cpp.variants.MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS`, PR #175's functional
re-review). This module calls `run_verification(ctx.source_dir, patch.diff,
reproducer_path, baseline)` with no `runner=` override, so it inherits that
isolation and sizing for free rather than needing to open or size a `Jail` of its
own.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from authorization.store import path_for as artifact_path_for
from contracts.enums import ErrorCode, MissionState, PatchPolicyStatus
from contracts.errors import ContractError
from contracts.schemas.missions import MissionPolicy
from contracts.verdict import GateMatrix
from missions.models import (
    BaselineReport,
    Job,
    JobKind,
    Mission,
    PatchCandidate,
    VerificationRecord,
)
from orchestrator import candidates as candidate_writes
from orchestrator.executors import (
    ExecutorContext,
    ExecutorResult,
    JobOutcome,
    register_executor,
    register_transition_policy,
)
from orchestrator.verification import RenewedFuzzConfig, VerificationBaseline, run_verification
from packages.sandbox.container import ContainerJailPolicy

#: Wall-clock buffer on top of the renewed-fuzz budget for configure, build, and the
#: campaign's own graceful exit — the same fixed value and reasoning
#: `workers/fuzzing/dispatch.py`'s `_CONTAINER_WALL_CLOCK_BUFFER_SECONDS` uses for the
#: original discovery campaign's `ContainerJailPolicy.wall_clock_seconds`. Kept as its
#: own constant here rather than importing that one: it is deliberately not coupled to
#: `JobKind.FUZZ`'s dispatch module, and #40's own budget is a different, smaller
#: number (`MissionPolicy.renewed_fuzz_seconds`, not `fuzz_seconds`).
_RENEWED_FUZZ_WALL_CLOCK_BUFFER_SECONDS = 180.0

#: Sentinel path handed to `run_verification` when no reproducer artifact can be
#: resolved for this candidate's finding. `run_verification`'s own reproducer gate
#: already treats a missing file as `NOT_RUN` (with a stated reason) rather than
#: raising — see `orchestrator/verification.py::_run_reproducer` — so this produces a
#: legitimate, disclosed gate outcome (which `derive_verdict` turns into
#: `HUMAN_REVIEW_REQUIRED`, never a silent pass) instead of a crash.
_MISSING_REPRODUCER_NAME = "no-reproducer-recorded"


@register_executor(JobKind.VERIFY)
def _verify_executor(ctx: ExecutorContext) -> ExecutorResult:
    """Run the deterministic gate matrix for one candidate and record it.

    Never reads or writes anything that looks like a confidence score — the diff and
    the reproducer are the only inputs `run_verification` accepts (see
    `orchestrator/tests/test_fan_out.py::test_run_verification_signature_is_provenance_blind`
    for the standing check that this stays true at the `verification.py` layer), and
    `record_verification` re-derives the verdict from the returned `GateMatrix`
    itself — nothing this function computes or passes through can override it.
    """
    job, mission = ctx.job, ctx.mission
    patch_id = job.payload.get("patch_id")
    if not patch_id:
        return ExecutorResult(
            outcome=JobOutcome.FAILED,
            detail="VERIFY job payload is missing 'patch_id'; nothing to verify.",
            error_code=ErrorCode.INTERNAL_ERROR,
            result={"infra_failure": True},
        )

    # Idempotency, keyed on the candidate — see this module's docstring.
    existing = VerificationRecord.objects.filter(patch_id=patch_id).first()
    if existing is not None:
        return ExecutorResult(
            outcome=JobOutcome.SUCCEEDED,
            detail=(
                f"Candidate {patch_id} was already verified ({existing.verdict}); "
                f"skipping re-run."
            ),
            result={
                "patch_id": str(patch_id),
                "verification_id": str(existing.id),
                "verdict": existing.verdict,
                "already_verified": True,
            },
        )

    try:
        patch = PatchCandidate.objects.select_related("finding").get(pk=patch_id)
    except PatchCandidate.DoesNotExist:
        return ExecutorResult(
            outcome=JobOutcome.FAILED,
            detail=f"Patch candidate {patch_id} does not exist.",
            error_code=ErrorCode.INTERNAL_ERROR,
            result={"infra_failure": True, "patch_id": str(patch_id)},
        )

    if patch.mission_id != mission.id:
        return ExecutorResult(
            outcome=JobOutcome.FAILED,
            detail=(
                f"Patch candidate {patch_id} belongs to mission {patch.mission_id}, "
                f"not {mission.id}."
            ),
            error_code=ErrorCode.INTERNAL_ERROR,
            result={"infra_failure": True, "patch_id": str(patch_id)},
        )

    if patch.policy_status != PatchPolicyStatus.ACCEPTED.value:
        # A dispatch bug (PATCH_GENERATE enqueuing VERIFY for a policy-rejected
        # candidate), not a gate outcome — `record_verification` would refuse this
        # exact case too (see its own `InvalidStateTransitionError` branch), so
        # failing here is the same call one layer earlier with a clearer message.
        return ExecutorResult(
            outcome=JobOutcome.FAILED,
            detail=(
                f"Patch candidate {patch_id} was rejected by policy "
                f"({patch.policy_status}) and must never reach VERIFY."
            ),
            error_code=ErrorCode.INTERNAL_ERROR,
            result={"infra_failure": True, "patch_id": str(patch_id)},
        )

    reproducer_path = _resolve_reproducer_path(ctx, patch)
    baseline = _baseline_for(mission)
    renewed_fuzz = _renewed_fuzz_config_for(mission)

    started_at = timezone.now()
    try:
        gates = run_verification(
            ctx.source_dir,
            patch.diff,
            reproducer_path,
            baseline,
            renewed_fuzz=renewed_fuzz,
        )
    except Exception as exc:  # noqa: BLE001 - an infra fault, never a verdict
        return ExecutorResult(
            outcome=JobOutcome.FAILED,
            detail=f"Verification could not run for candidate {patch_id}: {exc}",
            error_code=ErrorCode.SANDBOX_UNAVAILABLE,
            result={"infra_failure": True, "patch_id": str(patch_id)},
        )
    finished_at = timezone.now()

    gate_matrix_ref = _write_gate_matrix_artifact(ctx, patch_id, gates)

    try:
        record = candidate_writes.record_verification(
            mission.id,
            patch_id=patch.id,
            gates=gates,
            started_at=started_at,
            finished_at=finished_at,
            trace_id=ctx.trace_id,
        )
    except ContractError as exc:
        # The gates ran; the write was refused (mission not in VERIFY, cross-mission
        # candidate, no active authorization, ...). Still an infra/dispatch fault, not
        # a verdict — nothing was recorded, so there is nothing to stand behind.
        return ExecutorResult(
            outcome=JobOutcome.FAILED,
            detail=f"Verification ran but could not be recorded: {exc}",
            error_code=ErrorCode.INTERNAL_ERROR,
            result={"infra_failure": True, "patch_id": str(patch_id)},
        )

    return ExecutorResult(
        outcome=JobOutcome.SUCCEEDED,
        detail=f"Verification complete for candidate {patch_id}: {record.verdict}.",
        result={
            "patch_id": str(patch_id),
            "verification_id": str(record.id),
            "verdict": record.verdict,
            "gate_matrix_ref": gate_matrix_ref,
        },
    )


def _resolve_reproducer_path(ctx: ExecutorContext, patch: PatchCandidate) -> Path:
    """The on-disk path to this candidate's finding's reproducer, or a sentinel.

    Reproducer bytes are content-addressed (architecture spec §5.2,
    `authorization/store.py`), so resolving one is a direct `path_for(ARTIFACT_ROOT,
    sha256)` lookup — no archive to extract, unlike `ExecutorContext.source_dir`. A
    minimized reproducer is preferred over an unminimized one when both exist, same
    preference `MissionPolicy.reproducer_replay_attempts`'s docstring implies for
    "reproducible" generally. Missing artifact metadata resolves to a sentinel path
    that does not exist on disk rather than raising — see the module-level constant's
    docstring for why that is the honest outcome, not a workaround.
    """
    reproducer = patch.finding.reproducers.order_by("-minimized", "created_at").first()
    sha256 = (reproducer.artifact or {}).get("sha256") if reproducer else None
    if not sha256:
        return ctx.workspace_root / _MISSING_REPRODUCER_NAME
    return artifact_path_for(Path(settings.ARTIFACT_ROOT), sha256)


def _baseline_for(mission: Mission) -> VerificationBaseline:
    """`VerificationBaseline.expected_regression_tests` from this mission's own
    `BaselineReport`, if one exists.

    `BaselineReport.tests_total` is documented as "the denominator for 'regression
    preserved'" (P0-5, `missions/models.py`) — using anything else here (a hardcoded
    default, or nothing) would let the regression gate pass without ever comparing
    against this mission's own measured baseline. Falls back to
    `VerificationBaseline()`'s default (no coverage-drop check) when no baseline was
    recorded yet, which should not happen on the happy path but must not crash this
    stage if it does.
    """
    report = BaselineReport.objects.filter(mission_id=mission.id).first()
    if report is None or not report.tests_total:
        return VerificationBaseline()
    return VerificationBaseline(expected_regression_tests=report.tests_total)


def _renewed_fuzz_config_for(mission: Mission) -> RenewedFuzzConfig:
    """#40 — build the `RENEWED_FUZZING` gate's config from this mission's own policy.

    Mirrors `workers/fuzzing/dispatch.py::_container_policy`'s image/runtime/cpu/memory
    sizing exactly (same `SANDBOX_FUZZ_IMAGE` setting, same `MissionPolicy.sandbox`
    fields) rather than importing that private helper — `VERIFY` and `FUZZ` are
    different executors with different lifecycles and this keeps the coupling to "same
    reasoning, independently applied" instead of a cross-module private import. Two
    honest "not configured" outcomes, both routed to `container_policy=None` so
    `_run_renewed_fuzz` discloses `NOT_RUN` rather than raising:

    * `SANDBOX_FUZZ_IMAGE` unset — no deployment-pinned image to fuzz with.
    * `MissionPolicy.renewed_fuzz_seconds == 0` — the mission explicitly asked for no
      renewed-fuzz budget.
    """
    mission_policy = _mission_policy(mission)
    budget_seconds = mission_policy.renewed_fuzz_seconds
    image = getattr(settings, "SANDBOX_FUZZ_IMAGE", "") or ""
    if not image or budget_seconds <= 0:
        return RenewedFuzzConfig(container_policy=None, budget_seconds=budget_seconds)

    sandbox = mission_policy.sandbox
    runtime = sandbox.runtime if sandbox.runtime in ("docker", "podman") else "docker"
    container_policy = ContainerJailPolicy(
        image=image,
        runtime=runtime,
        cpu_limit=float(sandbox.cpu_limit),
        memory_mb=sandbox.memory_mb,
        wall_clock_seconds=float(budget_seconds) + _RENEWED_FUZZ_WALL_CLOCK_BUFFER_SECONDS,
    )
    return RenewedFuzzConfig(
        container_policy=container_policy,
        budget_seconds=budget_seconds,
        mission_ref=f"renewed-fuzz-{mission.id}",
    )


def _mission_policy(mission: Mission) -> MissionPolicy:
    return MissionPolicy.model_validate(mission.policy or {})


def _write_gate_matrix_artifact(ctx: ExecutorContext, patch_id, gates: GateMatrix) -> str:
    """Persist the gate matrix under `workspace_root` — durable, outlives this `Jail`
    (there isn't one yet, see this module's docstring) or worker process, and is what
    a restart-safe re-run of the idempotency check above would summarize back into an
    `ExecutorResult` without needing to be recomputed. Never a secret, never raw
    target output beyond what `GateResult.detail` already caps and sanitizes
    (`contracts/verdict.py`).
    """
    verify_dir = ctx.workspace_root / "verify"
    verify_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = verify_dir / f"{patch_id}.json"
    artifact_path.write_text(
        json.dumps(gates.model_dump(mode="json"), indent=2, sort_keys=True)
    )
    return str(artifact_path)


@register_transition_policy(JobKind.VERIFY)
def _verify_transition_policy(job: Job, mission: Mission) -> MissionState | None:
    """Route a terminal `VERIFY` job. See this module's docstring for the reasoning;
    summarized here at the call site:

    * Not `SUCCEEDED` (`FAILED`/`TIMED_OUT`): `MAX_ATTEMPTS_BY_KIND[VERIFY]` is 1, so
      there is no retry to fall back on, and per D-061 §2 a legitimate gate failure is
      always reported as `SUCCEEDED` with a failing `GateResult` inside it, never as a
      failed job — so a job that reaches `FAILED`/`TIMED_OUT` means the gates never
      ran to completion for this candidate, an infrastructure fault, not a verdict.
      Route straight to `FAILED` rather than leaving the mission stuck in `VERIFY`
      waiting on a job that will never complete (issue #168's own failure mode, one
      stage later).
    * `CANCELLED`: the one exception. A `VERIFY` job is cancelled because the
      *mission* was cancelled, and that path already routes the mission through
      `CANCELLING` on its own; forcing `FAILED` here would race it. Returns `None`.
    * `SUCCEEDED`, but this mission's candidate set is not fully verified yet (fewer
      `VerificationRecord`s than policy-accepted `PatchCandidate`s): `None` — this job
      does not by itself justify a transition. Another `VERIFY` job for a sibling
      candidate is expected to finish later and re-evaluate.
    * `SUCCEEDED`, and every accepted candidate now has a record: `EXPORTING`, always
      — never `HUMAN_REVIEW` directly, even though it is a legal target from `VERIFY`.
      `EXPORTING`'s own transition-out is where `VERIFIED`/`REJECTED`/`HUMAN_REVIEW`
      gets decided, from the whole candidate set at once.
    """
    if job.state != "SUCCEEDED":
        if job.state == "CANCELLED":
            return None
        return MissionState.FAILED

    accepted = PatchCandidate.objects.filter(
        mission_id=mission.id, policy_status=PatchPolicyStatus.ACCEPTED.value
    ).count()
    verified = VerificationRecord.objects.filter(mission_id=mission.id).count()
    if accepted == 0 or verified < accepted:
        return None

    return MissionState.EXPORTING
