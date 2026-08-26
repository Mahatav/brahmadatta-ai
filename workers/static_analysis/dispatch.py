"""Wires `workers.static_analysis.run.run_analyze_stage` into the `JobKind.ANALYZE`
executor contract, and its transition policy (#22, D-144).

Read `orchestrator/executors.py`'s module docstring first — this file is built
against it, not the other way around. Mirrors `workers/fuzzing/dispatch.py`'s own
structure closely; differences from that reference are called out below rather than
assumed obvious.

## What lives here

* `_analyze_executor` — `@register_executor(JobKind.ANALYZE)`. Builds the
  `packages.sandbox.container.ContainerJailPolicy` the scan runs under, calls
  `run_analyze_stage`, persists one `StageToolRun` row (tool name/version, the
  vendored ruleset's version, the pinned image digest — architecture spec §5.1,
  never populated by any production stage before this one, see `orchestrator.
  evidence_bundle._tool_versions`'s own docstring) and one `Finding` per real Semgrep
  match (`orchestrator.findings.record_finding`), and reports `matches_found`/
  `infra_failure` in `ExecutorResult.result` — the two keys `_analyze_transition_
  policy` reads.
* `_analyze_transition_policy` — `@register_transition_policy(JobKind.ANALYZE)`.
  `TRIAGE -> STRESS_TEST` on every terminal outcome except a genuine infrastructure
  fault (`TRIAGE -> FAILED`) — the same shape `_fuzz_transition_policy`
  (`orchestrator/executors.py`) uses for `STRESS_TEST -> CORRELATE`, for the same
  reason: `contracts.state_machine.TRANSITIONS[MissionState.TRIAGE]` is
  `{STRESS_TEST, PAUSED} | _ABORTS` and has no other member a "zero findings" or
  "findings but no crash" outcome could legally reach directly.

This module intentionally does not import `orchestrator.transitions` — see
`orchestrator/executors.py`'s own docstring, "The one rule that matters more than the
type signatures."

## Redaction discipline (SEC-48/SEC-50, D-071b/D-071c/D-125/D-131/D-143)

Every `Finding.sanitizer_report`/`code_slice` value written here goes through
`orchestrator.redaction.redact_sanitizer_report` first — the exact same helper
`workers/fuzzing/dispatch.py::_finding_kwargs_from_sanitizer` uses for ASan/UBSan
text, reused rather than reinvented (see that function's own SEC-50 comment for why
this is the right tool for "strip absolute paths and secret-shaped lines, keep
everything else" on free-text tool output). A Semgrep match's `code_snippet`
(`adapters/semgrep/parser.py::SemgrepMatch`) is real matched source text — the same
class of content `redact_sanitizer_report` was built to sanitize, not raw,
unredacted repository content reaching a `Finding` row.

## Idempotency (D-061 §3 rule 2)

`StageToolRun` carries no per-mission unique constraint (multiple rows per mission
are schema-legal, mirroring `FuzzingReport`), so the pre-execution check is "does
this mission already have a `StageToolRun` row for `(stage=ANALYZE, tool_name=
'semgrep')`" — same shape as `workers/fuzzing/dispatch.py::_existing_report`.
`JobKind.ANALYZE`'s `MAX_ATTEMPTS_BY_KIND` is 1 (`missions/models.py`, matching
`BASELINE`/`VERIFY`) so a genuine retry of this executor is rare (only the lease-
expiry reaper's own first-attempt path, and `attempt < max_attempts` is false for a
1-attempt kind) — the check exists anyway, for the same "not supposed to happen is
not the same as structurally prevented" reasoning every other stage's dispatch
module states explicitly.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from django.conf import settings

from adapters.semgrep.parser import SemgrepMatch
from contracts.enums import (
    AnalyzerTool,
    DiscoveryMethod,
    ErrorCode,
    FindingCategory,
    MissionStage,
    MissionState,
    Severity,
)
from contracts.schemas.missions import MissionPolicy
from missions.models import Finding, Job, JobKind, Mission, StageToolRun
from orchestrator.executors import (
    ExecutorContext,
    ExecutorResult,
    JobOutcome,
    register_executor,
    register_transition_policy,
)
from orchestrator.findings import record_finding
from orchestrator.redaction import redact_sanitizer_report
from packages.sandbox.container import ContainerJailPolicy
from packages.sandbox.errors import JailError
from workers.static_analysis.run import AnalyzeOutcome, run_analyze_stage

__all__: list[str] = []

#: Wall-clock budget for the whole containerized scan (copy + probe + Semgrep run).
#: Not derived from `MissionPolicy.sandbox.max_seconds` (sized for BASELINE's
#: configure+build+ctest cycle, architecture spec §3, a much larger budget than a
#: pattern-based static scan needs) or from a new mission-policy field (avoided
#: deliberately in this change — see this PR's handoff for why a dedicated
#: `analyze_seconds` knob was not added). A fixed, generous ceiling instead: Semgrep
#: against `demo/repositories/pktcfg` (7 files) completed in well under 5s in this
#: session's real container runs; 600s leaves two orders of magnitude of headroom for
#: a much larger authorized target before this needs to become a real knob.
_ANALYZE_WALL_CLOCK_SECONDS = 600.0

#: `Finding.title`/`StageToolRun.flags` entries' own field ceilings (missions/models.py).
_TITLE_MAX_CHARS = 300
_FLAG_MAX_CHARS = 300

_CATEGORY_FALLBACK = FindingCategory.OTHER
_SEVERITY_FALLBACK = Severity.MEDIUM


class _SandboxNotConfigured(Exception):
    """`SANDBOX_ANALYZE_IMAGE` unset — a deployment gap, not a per-mission fault."""


def _mission_policy(mission: Mission) -> MissionPolicy:
    return MissionPolicy.model_validate(mission.policy or {})


def _container_policy(mission_policy: MissionPolicy) -> ContainerJailPolicy:
    image = getattr(settings, "SANDBOX_ANALYZE_IMAGE", "") or ""
    if not image:
        raise _SandboxNotConfigured(
            "SANDBOX_ANALYZE_IMAGE is not set; ANALYZE has no safe default image "
            "(packages/sandbox/container.py: 'there is no safe default image for "
            "running untrusted target code'). See .env.example."
        )
    sandbox = mission_policy.sandbox
    runtime = sandbox.runtime if sandbox.runtime in ("docker", "podman") else "docker"
    return ContainerJailPolicy(
        image=image,
        runtime=runtime,
        cpu_limit=float(sandbox.cpu_limit),
        memory_mb=sandbox.memory_mb,
        wall_clock_seconds=_ANALYZE_WALL_CLOCK_SECONDS,
        # Semgrep writes a settings file to $HOME/.semgrep before it does anything
        # else, including on a scan that touches no network — see
        # adapters/semgrep/run_semgrep.py's own docstring ("HOME=/tmp") for the real,
        # reproduced crash this works around under D-024's --read-only root. This is
        # the CONTAINER's own /tmp (ContainerJail's sized tmpfs), not the host's —
        # same non-issue `packages/sandbox/container.py`'s own `--tmpfs` flag already
        # silences the identical way.
        extra_env={"HOME": "/tmp"},  # noqa: S108 - the CONTAINER's /tmp, not the host's
    )


def _rules_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "adapters" / "semgrep" / "rules"


def _existing_stage_tool_run(mission: Mission) -> StageToolRun | None:
    return (
        StageToolRun.objects.filter(
            mission=mission, stage=str(MissionStage.ANALYZE), tool_name="semgrep"
        )
        .order_by("-created_at")
        .first()
    )


def _result_from_existing(row: StageToolRun) -> ExecutorResult:
    matches_found = Finding.objects.filter(
        mission=row.mission, tool=str(AnalyzerTool.SEMGREP)
    ).count()
    return ExecutorResult(
        outcome=JobOutcome.SUCCEEDED,
        detail=f"ANALYZE_ALREADY_RECORDED: {matches_found} semgrep finding(s)",
        result={"already_recorded": True, "matches_found": matches_found, "infra_failure": False},
    )


@register_executor(JobKind.ANALYZE)
def _analyze_executor(ctx: ExecutorContext) -> ExecutorResult:
    """`JobKind.ANALYZE` — run Semgrep in a `ContainerJail`, persist the
    `StageToolRun` row and any real findings.

    Never raises on a scan-side failure (bad ruleset, unreadable source) — that
    guarantee is `run_analyze_stage`'s own. A genuine sandbox/infrastructure fault
    (`packages.sandbox.errors.JailError`) is caught here and reported as
    `infra_failure`, matching `workers/fuzzing/dispatch.py::_fuzz_executor`'s own
    handling of the identical exception family.
    """
    existing = _existing_stage_tool_run(ctx.mission)
    if existing is not None:
        return _result_from_existing(existing)

    if ctx.cancel_requested():
        return ExecutorResult(
            outcome=JobOutcome.CANCELLED,
            detail="Cancellation requested before the Semgrep scan started.",
            result={"cancelled_before_start": True},
        )

    mission_policy = _mission_policy(ctx.mission)
    try:
        policy = _container_policy(mission_policy)
    except _SandboxNotConfigured as exc:
        return ExecutorResult(
            outcome=JobOutcome.FAILED,
            detail=str(exc),
            result={"infra_failure": True, "matches_found": 0},
            error_code=ErrorCode.SANDBOX_UNAVAILABLE,
            retry=False,
        )

    try:
        outcome = run_analyze_stage(
            ctx.mission.id,
            ctx.source_dir,
            policy=policy,
            rules_dir=_rules_dir(),
        )
    except JailError as exc:
        return ExecutorResult(
            outcome=JobOutcome.FAILED,
            detail=f"Sandbox unavailable for the Semgrep scan: {exc}",
            result={"infra_failure": True, "matches_found": 0},
            error_code=ErrorCode.SANDBOX_UNAVAILABLE,
            retry=False,
        )

    return _result_from_outcome(ctx, outcome)


def _result_from_outcome(ctx: ExecutorContext, outcome: AnalyzeOutcome) -> ExecutorResult:
    if not outcome.ran:
        return ExecutorResult(
            outcome=JobOutcome.FAILED,
            detail=f"Semgrep scan did not run: {outcome.failure_reason or 'unknown reason'}",
            result={"infra_failure": False, "matches_found": 0},
            retry=False,
        )

    _persist_outcome(ctx.mission, outcome, ctx.trace_id)

    detail = (
        f"ANALYZE_COMPLETE: {len(outcome.matches)} finding(s) across "
        f"{outcome.files_scanned} file(s) in {outcome.runtime_seconds:.2f}s "
        f"(ruleset {outcome.ruleset_version})"
    )
    return ExecutorResult(
        outcome=JobOutcome.SUCCEEDED,
        detail=detail,
        result={
            "matches_found": len(outcome.matches),
            "files_scanned": outcome.files_scanned,
            "ruleset_version": outcome.ruleset_version,
            "tool_version": outcome.tool_version,
            "infra_failure": False,
        },
    )


def _persist_outcome(mission: Mission, outcome: AnalyzeOutcome, trace_id: str) -> None:
    """Write the `StageToolRun` row plus one `Finding` per real Semgrep match.

    Findings first, `StageToolRun` last — same ordering reasoning as `workers/
    fuzzing/dispatch.py::_persist_outcome`'s own docstring: a crash between them
    leaves `Finding` rows that `record_finding`'s `(mission, fingerprint)` dedup makes
    safe to rediscover, and no `StageToolRun` row yet, so `_existing_stage_tool_run`
    still lets a retried job attempt (should one ever reach this executor) do real
    work rather than reporting a phantom success.
    """
    for match in outcome.matches:
        record_finding(
            mission.id,
            trace_id=trace_id,
            now=outcome.recorded_at,
            detected_at=outcome.recorded_at,
            **_finding_kwargs(match),
        )

    flags = [
        f"config:{outcome.ruleset_version}",
        f"matches:{len(outcome.matches)}",
        f"files_scanned:{outcome.files_scanned}",
    ]
    if outcome.tool_errors:
        flags.append(f"tool_errors:{len(outcome.tool_errors)}")
    flags = [flag[:_FLAG_MAX_CHARS] for flag in flags]

    image_digest = None
    if outcome.image_digest and "@sha256:" in outcome.image_digest:
        image_digest = "sha256:" + outcome.image_digest.rsplit("@sha256:", 1)[1]

    StageToolRun.objects.create(
        mission=mission,
        stage=str(MissionStage.ANALYZE),
        tool_name="semgrep",
        tool_version=f"{outcome.tool_version}+ruleset:{outcome.ruleset_version}",
        image_digest=image_digest,
        flags=flags,
        artifact_refs=[],
        started_at=outcome.recorded_at,
        finished_at=outcome.recorded_at,
    )


def _category_for(raw: str) -> FindingCategory:
    try:
        return FindingCategory(raw)
    except ValueError:
        return _CATEGORY_FALLBACK


def _severity_for(raw: str) -> Severity:
    try:
        return Severity(raw)
    except ValueError:
        return _SEVERITY_FALLBACK


def _fingerprint(rule_id: str, file_path: str, start_line: int) -> str:
    material = ":".join(["semgrep", rule_id, file_path, str(start_line)])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"semgrep:{rule_id}:{digest}"[:128]


def _title_for(rule_id: str, file_path: str, start_line: int) -> str:
    title = f"{rule_id} in {file_path}:{start_line}"
    return title[:_TITLE_MAX_CHARS]


def _finding_kwargs(match: SemgrepMatch) -> dict[str, Any]:
    category = _category_for(match.brahmadatta_category)
    severity = _severity_for(match.brahmadatta_severity)
    # SEC-48/SEC-50 discipline (see this module's docstring): a Semgrep match's own
    # message is a hand-authored, fixed string from `adapters/semgrep/rules/` (never
    # target-controlled), but `code_snippet` is real matched source text and goes
    # through the same redaction pass ASan/UBSan reports do before reaching a
    # `Finding` row.
    report_lines = [
        f"semgrep: {match.rule_id}",
        f"severity: {match.tool_severity}",
        f"cwe: {match.cwe or 'n/a'}",
        f"category: {match.category}",
        match.message,
        "",
        redact_sanitizer_report(match.code_snippet),
    ]
    return {
        "category": category,
        "severity": severity,
        "tool": AnalyzerTool.SEMGREP,
        "discovery_method": DiscoveryMethod.STATIC_ANALYSIS,
        "file_path": match.file_path,
        "line": match.start_line,
        "function": None,
        "fingerprint": _fingerprint(match.rule_id, match.file_path, match.start_line),
        "title": _title_for(match.rule_id, match.file_path, match.start_line),
        "sanitizer_report": redact_sanitizer_report("\n".join(report_lines)),
        "code_slice": redact_sanitizer_report(match.code_snippet),
        "reproducible": False,
    }


@register_transition_policy(JobKind.ANALYZE)
def _analyze_transition_policy(job: Job, mission: Mission) -> MissionState | None:
    """A terminal ANALYZE job always routes TRIAGE -> STRESS_TEST.

    Never anywhere else — `contracts.state_machine.TRANSITIONS[MissionState.TRIAGE]`
    is `{STRESS_TEST, PAUSED} | _ABORTS` and has no other member a scan outcome could
    legally reach directly, the same D-061 §2 trap `_fuzz_transition_policy`
    (`orchestrator/executors.py`) documents for `STRESS_TEST -> CORRELATE`. The one
    branch that does NOT go to `STRESS_TEST`: a genuine infrastructure fault
    (`result["infra_failure"]`, set by `_analyze_executor` above) routes straight to
    `FAILED` — legal via `_ABORTS`, matching `_fuzz_transition_policy`'s identical
    infra-failure branch.
    """
    if job.state == "FAILED" and bool(job.result.get("infra_failure")):
        return MissionState.FAILED
    return MissionState.STRESS_TEST
