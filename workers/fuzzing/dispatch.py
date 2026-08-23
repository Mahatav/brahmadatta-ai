"""Wires `workers.fuzzing.run.run_fuzzing_stage` into the `JobKind.FUZZ` executor
contract, and registers `JobKind.MINIMIZE` (#168, T2). Read
`orchestrator/executors.py`'s module docstring first — this file is built against
it, not the other way around. `_fuzz_transition_policy` (the `STRESS_TEST ->
CORRELATE` routing, D-061 §2's named trap) already exists there, real and tested;
this module owns the `FUZZ` *executor* only, plus everything `MINIMIZE` gets.

## What lives here

* `_fuzz_executor` — `@register_executor(JobKind.FUZZ)`. Builds the
  `packages.sandbox.container.ContainerJailPolicy` a campaign runs under, calls
  `run_fuzzing_stage` with `ctx.workspace_root` so real crash-artifact bytes survive
  the `ContainerJail`'s own teardown (D-106; `run_fuzzing_stage`'s own `workspace_root`
  parameter), persists a `FuzzingReport` plus one `Finding` per sanitizer-confirmed
  crash (`orchestrator.findings.record_finding`, #168) and — when a durable artifact
  survived to pair with it — one real, unminimized `Reproducer` row
  (`orchestrator.findings.record_reproducer`, D-106; see `_record_reproducers`'s own
  docstring for the pairing rule), and reports `crashes_found`/`infra_failure` in
  `ExecutorResult.result` — the two keys `_fuzz_transition_policy` reads, per its own
  docstring.
* `_minimize_executor` — `@register_executor(JobKind.MINIMIZE)`. Real, registered,
  and honest about a structural blocker in the module it wires (see "MINIMIZE: what
  this executor can and cannot do" below) rather than faking a pass.
* `_minimize_transition_policy` — `@register_transition_policy(JobKind.MINIMIZE)`.
  Always defers (`None`). `MINIMIZE` has no `MissionState` of its own — see
  `orchestrator/queue.py`'s `JOB_BACKED_STATES` docstring: "`JobKind.SANITIZER_BUILD`
  and `JobKind.MINIMIZE` are deliberately absent too: they are sub-steps of the
  `STRESS_TEST` stage's own work... composing them is T2's call." Registered anyway,
  not left a `NotImplementedError` stub, for registry symmetry and because a future
  caller enqueueing a `MINIMIZE` job directly should get a real answer, not a crash.

This module intentionally does not import `orchestrator.transitions` — see
`orchestrator/executors.py`'s own docstring, "The one rule that matters more than
the type signatures."

## Sandboxing: `ContainerJail`, not `packages.sandbox.jail.Jail` — and why the
sanitizer-memory trap T5/D-067 hit for `VERIFY` does not apply here

`run_libfuzzer_campaign` (`adapters/cpp/fuzzing.py`; D-106 added its own
`workspace_root`-driven crash-artifact copy-out, but not a second sandbox)
already opens its own `packages.sandbox.container.ContainerJail` internally — this
executor's job is to hand it a correctly-sized `ContainerJailPolicy`, not to open a
second sandbox around it. `run_fuzzing_stage`'s own signature
(`policy: ContainerJailPolicy`) is the tell: unlike `run_baseline_stage`
(`jail_policy: JailPolicy | None`, `packages.sandbox.jail.Jail`,
`RLIMIT_AS`-based) and `orchestrator/verification.py` (same `Jail`,
`RLIMIT_AS`-based — D-067 §3/SEC-47), `FUZZ` was already built against the
container-isolation path #15/D-024 exists for.

Checked directly, not assumed: `adapters/cpp/variants.py`'s own module docstring
names the *mechanism* of the sanitizer-memory trap precisely — `RLIMIT_AS`
(`ulimit -v`) constrains *virtual* address space, and AddressSanitizer's shadow
region reserves tens of TiB of it regardless of how much memory the instrumented
program actually touches, so no "reasonable" `RLIMIT_AS` value accommodates it
(measured there: 64 GiB still aborts, 64 TiB passes). That module's own closing
section says the durable fix is "an `RLIMIT_DATA`- or cgroup-based memory limit
that actually constrains an ASan-instrumented process" — which is exactly what
`ContainerJailPolicy.memory_mb` already is: Docker's `--memory` flag sets a cgroup
`memory.max`/`memory.limit_in_bytes` ceiling on *resident, charged* pages, not on
reserved virtual address space. ASan's shadow-memory reservation is a sparse
`PROT_NONE`-backed mmap that is not charged against a cgroup memory limit until
actually touched, so it does not collide with a `--memory` ceiling the way it
collides with `RLIMIT_AS`. `FUZZ` always builds with `-DPKTCFG_SANITIZE=ON`
(`run_libfuzzer_campaign`'s own configure step, unconditional), so the target this
executor fuzzes is always sanitizer-instrumented — and `SANDBOX_MEMORY_MB`'s
existing default (8192 MiB, `config/settings/base.py`) is correct for it
unmodified. There is no `MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS`-equivalent override
to add here. This was verified, not assumed by analogy to T1/T5's `Jail` usage —
see `.project/decisions.md` for the recorded reasoning.

## Idempotency (D-061 §3 rule 2)

`FuzzingReport` (`missions/models.py`) carries no per-mission unique constraint,
unlike `BaselineReport`'s `OneToOneField` — multiple rows per mission are schema-
legal (`evidence_repository.get_fuzzing_report` reads the most recent one by
design). This executor only ever writes one, because it only persists a report on
a campaign that actually ran to completion (crash or not); a stalled or
infrastructure-faulted attempt writes nothing, so a retry (`MAX_ATTEMPTS_BY_KIND
[JobKind.FUZZ]` is 2) never has an existing report to collide with. The
pre-execution check is therefore "does this mission already have a `FuzzingReport`
row at all" — same shape as `workers.baseline.dispatch`'s check against
`BaselineReport`, and the reasoning above is why treating that as safe does not
need `BaselineReport`'s `IntegrityError` fallback: a genuine second writer for the
same mission cannot exist under the one-job-per-`(mission, kind)` invariant D-065
§1 already established, and `FuzzingReport`/`Finding` are both written inside one
`transaction.atomic()` block per campaign, so a crash mid-persist leaves nothing
half-written to collide with on retry.

## Sizing the container's wall clock against the job's own deadline

`ContainerJailPolicy.wall_clock_seconds` is **not** set from
`SandboxPolicy.max_seconds` (`MissionPolicy.policy["sandbox"]["max_seconds"]`,
default 5400s) the way `SANDBOX_POLICY`'s other fields are. `orchestrator.queue.
default_deadline_seconds` sizes a `FUZZ` job's own `Job.deadline_at` from
`policy["fuzz_seconds"]` (default 1800s) — a much smaller number. Reusing
`max_seconds` (sized for `BASELINE`'s configure+build+ctest cycle, a different
budget entirely) as the container's own kill timer would leave a ~3600s gap in
which the job-level deadline watchdog (`orchestrator.queue.
reap_missed_deadlines`, a separate process) could mark this mission's `Job` row
`TIMED_OUT` while this worker process is still blocked inside `run_fuzzing_stage`,
unaware — the same "no cooperative-cancellation hook" gap
`workers/baseline/dispatch.py` already flagged for `BASELINE`, just with a much
wider blast radius here if left at the `SandboxPolicy` default. Instead, the
container's wall clock is `budget_seconds` (libFuzzer's own `-max_total_time`,
what `run_libfuzzer_campaign` is actually asked to run for) plus a fixed 180s
buffer — enough for configure+build+libFuzzer's own graceful exit and stats
printing, tightly coupled to the same number the job's own deadline is sized from,
mirroring how `BASELINE`'s job deadline and `Jail` wall clock already come from the
same `sandbox.max_seconds` value today. Flagged as a real, load-bearing choice, not
a default — see `.project/decisions.md`.

## MINIMIZE: what this executor can and cannot do (updated by D-106)

Before D-106, `FuzzingOutcome.artifact_refs` (`workers/fuzzing/run.py`) were paths
*inside* `ContainerJail`'s ephemeral worktree — `run_libfuzzer_campaign` opens that
jail with `with ContainerJail.create(...) as sandbox:` and the jail's `close()` (run
on every `with`-block exit, `packages/sandbox/container.py`) does
`shutil.rmtree(self._root, ...)`, and nothing copied a crash artifact's bytes out
before that ran. D-106 closed that half of the gap: `run_fuzzing_stage` now takes a
`workspace_root` parameter (this executor passes `ctx.workspace_root`), and when the
campaign finds a crash, `adapters.cpp.fuzzing._copy_crash_artifacts_durably` copies
the real bytes out before the jail tears down — `FuzzingOutcome.durable_artifacts`
carries the result, and `_record_reproducers` (this module) turns it into a real
`Reproducer` row.

**What D-106 explicitly did NOT authorize, and this executor still does not do:**
wiring `JobKind.MINIMIZE` into `orchestrator/queue.py`'s stage-to-job map, or
building libFuzzer's own `-minimize_crash=1` logic. `_minimize_executor` below is
still real, registered code — not a `NotImplementedError` stub — but its blocker is
no longer "the bytes do not survive" (D-106 fixed that); it is that no `MINIMIZE`
algorithm exists in this codebase and no production code path ever enqueues this
`JobKind` (`orchestrator/queue.py`'s own comment: "`SANITIZER_BUILD` and `MINIMIZE`
are deliberately absent... composing them is T2's call" — unchanged by D-106).
`Finding.reproducible` therefore still stays `False` for every `FUZZ`-discovered
finding — the honest reading of that field's own docstring ("True only when a
*minimized* input replayed... from a clean build," `missions/models.py`): D-106
records a real, unminimized reproducer, not a minimized one, and does not touch that
field's semantics.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from django.conf import settings

from adapters.cpp.errors import BuildStep
from adapters.cpp.fuzzing import DurableArtifact
from adapters.cpp.sanitizer import SanitizerFinding, parse_sanitizer_output
from authorization.errors import UnreadableArchiveError
from authorization.store import ingest_from_path
from contracts.enums import (
    AnalyzerTool,
    DiscoveryMethod,
    ErrorCode,
    FindingCategory,
    MissionState,
    Severity,
)
from contracts.schemas.missions import MissionPolicy
from missions.models import Finding, FuzzingReport, Job, JobKind, Mission
from orchestrator.executors import (
    ExecutorContext,
    ExecutorResult,
    JobOutcome,
    register_executor,
    register_transition_policy,
)
from orchestrator.findings import record_finding, record_reproducer
from orchestrator.redaction import redact_sanitizer_report
from packages.sandbox.container import ContainerJailPolicy
from packages.sandbox.errors import JailError
from workers.fuzzing.run import FuzzingOutcome, run_fuzzing_stage

__all__: list[str] = []

#: Configure/build/toolchain steps whose failure is the *harness's* fault
#: (`adapters/cpp/errors.BuildStep`), not the sandbox's — routed through CORRELATE
#: like any other campaign-side failure, per `_fuzz_transition_policy`'s own
#: docstring ("a FAILED job with no [infra_failure] marker is treated as a
#: campaign-side failure ... and still routed to CORRELATE").
_HARNESS_BUILD_STEPS = frozenset({BuildStep.CONFIGURE.value, BuildStep.BUILD.value, "FUZZ_ARTIFACT_DIR"})

#: Wall-clock buffer added on top of the libFuzzer budget for configure, build, the
#: campaign's own graceful `-max_total_time` exit, and log collection. See this
#: module's docstring, "Sizing the container's wall clock against the job's own
#: deadline".
_CONTAINER_WALL_CLOCK_BUFFER_SECONDS = 180.0


def _mission_policy(mission: Mission) -> MissionPolicy:
    return MissionPolicy.model_validate(mission.policy or {})


def _container_policy(mission_policy: MissionPolicy, *, budget_seconds: int) -> ContainerJailPolicy:
    image = getattr(settings, "SANDBOX_FUZZ_IMAGE", "") or ""
    if not image:
        raise _SandboxNotConfigured(
            "SANDBOX_FUZZ_IMAGE is not set; FUZZ has no safe default image "
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
        wall_clock_seconds=float(budget_seconds) + _CONTAINER_WALL_CLOCK_BUFFER_SECONDS,
    )


class _SandboxNotConfigured(Exception):
    """`SANDBOX_FUZZ_IMAGE` unset — a deployment gap, not a per-mission fault."""


def _existing_report(mission: Mission) -> FuzzingReport | None:
    return (
        FuzzingReport.objects.filter(mission=mission).order_by("-recorded_at", "-id").first()
    )


def _result_from_existing(report: FuzzingReport) -> ExecutorResult:
    detail = (
        f"FUZZ_ALREADY_RECORDED: {report.unique_crashes} unique crash(es) in "
        f"{report.executions} executions ({report.runtime_seconds:.1f}s)"
    )
    return ExecutorResult(
        outcome=JobOutcome.SUCCEEDED,
        detail=detail,
        result={
            "already_recorded": True,
            "crashes_found": report.crashes_found,
            "unique_crashes": report.unique_crashes,
            "executions": report.executions,
        },
    )


@register_executor(JobKind.FUZZ)
def _fuzz_executor(ctx: ExecutorContext) -> ExecutorResult:
    """`JobKind.FUZZ` — build the harness with sanitizers on, run the libFuzzer
    campaign in a `ContainerJail`, persist the report and any crash `Finding`s.

    Never raises on a campaign-side failure (build/configure/toolchain) — that
    guarantee is `run_fuzzing_stage`'s own (see its docstring: "never re-raised past
    this function"). A genuine sandbox/infrastructure fault
    (`packages.sandbox.errors.JailError` and subclasses, e.g.
    `ContainerUnavailableError` when the daemon is unreachable) is caught here and
    reported as `infra_failure`, per architecture spec §6.1 — `run_fuzzing_stage`
    itself does not catch that family (checked directly against its `except`
    clauses: `StepFailure`, `AdapterError`, `ValueError` only), so this executor is
    the layer responsible for it.
    """
    existing = _existing_report(ctx.mission)
    if existing is not None:
        return _result_from_existing(existing)

    if ctx.cancel_requested():
        return ExecutorResult(
            outcome=JobOutcome.CANCELLED,
            detail="Cancellation requested before the fuzz campaign started.",
            result={"cancelled_before_start": True},
        )

    mission_policy = _mission_policy(ctx.mission)
    budget_seconds = mission_policy.fuzz_seconds

    try:
        policy = _container_policy(mission_policy, budget_seconds=budget_seconds)
    except _SandboxNotConfigured as exc:
        return ExecutorResult(
            outcome=JobOutcome.FAILED,
            detail=str(exc),
            result={"infra_failure": True, "crashes_found": 0},
            error_code=ErrorCode.SANDBOX_UNAVAILABLE,
            retry=False,
        )

    try:
        outcome = run_fuzzing_stage(
            ctx.mission.id,
            ctx.source_dir,
            policy=policy,
            budget_seconds=budget_seconds,
            workspace_root=ctx.workspace_root,
        )
    except JailError as exc:
        return ExecutorResult(
            outcome=JobOutcome.FAILED,
            detail=f"Sandbox unavailable for the fuzz campaign: {exc}",
            result={"infra_failure": True, "crashes_found": 0},
            error_code=ErrorCode.SANDBOX_UNAVAILABLE,
            retry=ctx.job.attempt < ctx.job.max_attempts,
        )

    return _result_from_outcome(ctx, outcome)


def _result_from_outcome(ctx: ExecutorContext, outcome: FuzzingOutcome) -> ExecutorResult:
    if outcome.failure is not None:
        infra = outcome.failure.step not in _HARNESS_BUILD_STEPS
        return ExecutorResult(
            outcome=JobOutcome.FAILED,
            detail=(
                f"Fuzz campaign did not run: {outcome.failure.step} failed "
                f"({outcome.failure.first_error})"
            ),
            result={
                "infra_failure": infra,
                "crashes_found": 0,
                "failure_step": outcome.failure.step,
            },
            error_code=ErrorCode.SANDBOX_UNAVAILABLE if infra else None,
            retry=False,
        )

    if not outcome.ran:
        # `mode != "LIVE_CAMPAIGN"` with no `failure` set should not happen given
        # `run_fuzzing_stage`'s own contract, but a defensive FAILED beats a crashed
        # worker if it ever does.
        return ExecutorResult(
            outcome=JobOutcome.FAILED,
            detail=f"Fuzz campaign did not produce a live result (mode={outcome.mode}).",
            result={"infra_failure": False, "crashes_found": 0},
            retry=False,
        )

    if outcome.executions == 0:
        # No progress at all recorded — the closest signal available to architecture
        # spec §6.3(b)'s "genuinely stalled" without a `stall_seconds`-aware
        # heartbeat hook into a running campaign (that hook does not exist in
        # `run_libfuzzer_campaign` today — see this module's docstring on
        # cooperative cancellation for the same class of gap). Retried once, per
        # `MAX_ATTEMPTS_BY_KIND[JobKind.FUZZ] == 2` and the "only when the first
        # attempt stalled" rule (architecture spec §3.4).
        return ExecutorResult(
            outcome=JobOutcome.FAILED,
            detail="Fuzz campaign produced zero executions; treating as a stall.",
            result={"infra_failure": False, "crashes_found": 0, "stalled": True},
            retry=ctx.job.attempt < ctx.job.max_attempts,
        )

    _persist_outcome(ctx.mission, outcome, ctx.trace_id)

    detail = (
        f"FUZZ_COMPLETE: {outcome.executions} executions, {outcome.unique_crashes} "
        f"unique crash(es) in {outcome.runtime_seconds:.1f}s"
    )
    return ExecutorResult(
        outcome=JobOutcome.SUCCEEDED,
        detail=detail,
        result={
            "crashes_found": outcome.crashes_found,
            "unique_crashes": outcome.unique_crashes,
            "executions": outcome.executions,
            "infra_failure": False,
        },
    )


def _persist_outcome(mission: Mission, outcome: FuzzingOutcome, trace_id: str) -> None:
    """Write the `FuzzingReport` plus one `Finding` (and, where possible, one real
    `Reproducer`, D-106) per structurally-parsed crash.

    Findings and reproducers first, report last — see this module's docstring,
    "Idempotency": a crash between them leaves `Finding` rows that `record_finding`'s
    own `(mission, fingerprint)` dedup makes safe to rediscover, `Reproducer` rows
    that `record_reproducer`'s own `(finding, sha256)` dedup makes equally safe to
    rediscover, and no `FuzzingReport` row yet, so the pre-execution check above
    still re-runs the campaign rather than reporting a phantom success. Recording
    reproducers *before* the report (not after) matters here specifically: once
    `FuzzingReport.objects.create()` below succeeds, `_fuzz_executor`'s pre-execution
    check (`_existing_report`) short-circuits any retry straight to
    `_result_from_existing` — a reproducer write placed after the report would never
    get a second chance to run if it failed on the first attempt.
    """
    finding_rows: list[Finding] = []
    if outcome.unique_crashes > 0:
        for finding_kwargs in _findings_from_outcome(outcome):
            finding_rows.append(
                record_finding(
                    mission.id, trace_id=trace_id, now=outcome.recorded_at, **finding_kwargs
                )
            )
        _record_reproducers(mission, finding_rows, outcome, trace_id)

    FuzzingReport.objects.create(
        mission=mission,
        mode=outcome.mode,
        harness=outcome.harness,
        engine=outcome.engine,
        runtime_seconds=outcome.runtime_seconds,
        executions=outcome.executions,
        crashes_found=outcome.crashes_found,
        unique_crashes=outcome.unique_crashes,
        corpus_size=outcome.corpus_size,
        sanitizers=list(outcome.sanitizers),
        replay_source=outcome.replay_source,
        recorded_at=outcome.recorded_at,
    )


def _record_reproducers(
    mission: Mission,
    findings: list[Finding],
    outcome: FuzzingOutcome,
    trace_id: str,
) -> None:
    """Ingest each durably-copied crash artifact (D-106; `outcome.durable_artifacts`,
    populated by `run_fuzzing_stage` when it was given `ctx.workspace_root`) into the
    content-addressed store, and write one real `Reproducer` row per `Finding`.

    Paired by discovery order, one `Finding` per durable artifact, and only when the
    two lists are the same length — the one case this project's own live rehearsals
    (D-098, D-105) have ever actually produced: a campaign that finds exactly one
    unique crash, backed by exactly one crash-artifact file. `adapters.cpp.sanitizer.
    parse_sanitizer_output` does not associate a parsed sanitizer report with the
    specific artifact file that produced it, so a campaign that somehow reports more
    than one distinct crash in a single run has no reliable way to say which artifact
    belongs to which `Finding` here. A length mismatch (including "some artifacts
    were rejected by `_copy_crash_artifacts_durably`'s symlink/size safeguards, so
    fewer durable artifacts came back than crashes were found") means no `Reproducer`
    row is written for *any* finding in this batch, rather than guessing a pairing —
    `VERIFY`'s `REPRODUCER_ELIMINATED` staying an honest `NOT_RUN` is the correct
    outcome for an ambiguous mapping, not a `Reproducer` that might not actually
    reproduce the finding it would be attached to.
    """
    if not findings or len(findings) != len(outcome.durable_artifacts):
        return

    artifact_root = Path(settings.ARTIFACT_ROOT)
    max_bytes = settings.FUZZ_REPRODUCER_ARTIFACT_MAX_BYTES

    for finding, artifact in zip(findings, outcome.durable_artifacts, strict=True):
        _record_one_reproducer(mission, finding, artifact, artifact_root, max_bytes, trace_id, outcome)


def _record_one_reproducer(
    mission: Mission,
    finding: Finding,
    artifact: DurableArtifact,
    artifact_root: Path,
    max_bytes: int,
    trace_id: str,
    outcome: FuzzingOutcome,
) -> None:
    try:
        ingest = ingest_from_path(artifact_root, Path(artifact.host_path), max_bytes=max_bytes)
    except UnreadableArchiveError:
        # The durable copy vanished or exceeds FUZZ_REPRODUCER_ARTIFACT_MAX_BYTES
        # (a second, independently-configurable ceiling from `adapters.cpp.fuzzing.
        # MAX_DURABLE_ARTIFACT_BYTES`'s own copy-out check — see this module's
        # docstring). No Reproducer for this finding; VERIFY's gate stays NOT_RUN
        # rather than pointing at bytes that were never actually ingested.
        return

    name = Path(artifact.relative_path).name
    record_reproducer(
        finding.id,
        sha256=ingest.sha256,
        size_bytes=ingest.bytes_written,
        uri=f"artifact://{mission.id}/reproducer/{ingest.sha256}",
        test_command=f"./pktcfg_replay {name} x1",
        trace_id=trace_id,
        now=outcome.recorded_at,
    )


def _findings_from_outcome(outcome: FuzzingOutcome) -> list[dict[str, Any]]:
    """Structurally parse `outcome.run_output_excerpt` for sanitizer reports.

    `run_output_excerpt` is the *tail* (last 12000 chars, `workers/fuzzing/run.py`)
    of the campaign's combined stdout/stderr, not the full transcript
    `run_fuzzing_stage` itself saw — a caller-side truncation this module does not
    control (see this file's docstring on why `workers/fuzzing/run.py` is not
    rewritten here). In practice a crash report is the last thing libFuzzer prints
    before the process aborts, so this is expected to capture it; flagged as a real,
    if narrow, limitation rather than assumed complete.

    When the sanitizer grammar (`adapters.cpp.sanitizer.parse_sanitizer_output`)
    finds nothing structural — a plain crash/timeout/OOM with no ASan/UBSan report,
    or a report that fell outside the excerpt — one generic `Finding` per crash
    artifact is still recorded rather than the crash being silently dropped, using
    `AnalyzerTool.LIBFUZZER` and the artifact path as its only location material.
    """
    text = outcome.run_output_excerpt
    parsed = parse_sanitizer_output(text) if text else ()

    findings: list[dict[str, Any]] = [_finding_kwargs_from_sanitizer(f) for f in parsed]

    if not findings:
        for artifact_ref in outcome.artifact_refs:
            findings.append(_finding_kwargs_from_artifact(artifact_ref))

    for kwargs in findings:
        kwargs["detected_at"] = outcome.recorded_at

    return findings


def _category_for(finding: SanitizerFinding) -> FindingCategory:
    kind = finding.kind.lower()
    if "heap-buffer-overflow" in kind:
        return FindingCategory.HEAP_BUFFER_OVERFLOW
    if "stack-buffer-overflow" in kind:
        return FindingCategory.STACK_BUFFER_OVERFLOW
    if "global-buffer-overflow" in kind:
        return FindingCategory.GLOBAL_BUFFER_OVERFLOW
    if "use-after-free" in kind:
        return FindingCategory.USE_AFTER_FREE
    if "double-free" in kind:
        return FindingCategory.DOUBLE_FREE
    if "leak" in kind:
        return FindingCategory.MEMORY_LEAK
    if finding.tool == AnalyzerTool.UNDEFINED_BEHAVIOUR_SANITIZER.value:
        return FindingCategory.UNDEFINED_BEHAVIOUR
    return FindingCategory.OTHER


def _fingerprint(tool: str, kind: str, function: str, file: str | None, line: int | None) -> str:
    material = ":".join(["fuzz", tool, kind, function, file or "", str(line or "")])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"fuzz:{tool}:{kind}:{function}:{digest}"[:128]


def _title_for(category: FindingCategory, function: str | None, file_path: str, line: int | None) -> str:
    location = f"{file_path}:{line}" if line is not None else file_path
    bug = category.value.replace("_", " ").lower()
    if function:
        return f"{bug} in {function} ({location})"
    return f"{bug} at {location}"


def _finding_kwargs_from_sanitizer(finding: SanitizerFinding) -> dict[str, Any]:
    category = _category_for(finding)
    function = None if finding.function == "<unknown>" else finding.function
    file_path = finding.file or "<unknown>"
    return {
        "category": category,
        "severity": Severity.CRITICAL if category.value.endswith("BUFFER_OVERFLOW") else Severity.HIGH,
        "tool": AnalyzerTool(finding.tool),
        "discovery_method": DiscoveryMethod.FUZZING_CAMPAIGN,
        "file_path": file_path,
        "line": finding.line,
        "function": function,
        "fingerprint": _fingerprint(finding.tool, finding.kind, function or "<unknown>", finding.file, finding.line),
        "title": _title_for(category, function, file_path, finding.line),
        # SEC-50 (#191): `finding.raw` is `adapters.cpp.sanitizer`'s verbatim capture
        # of the sandboxed process's own stdout/stderr — exactly the kind of raw tool
        # output `record_finding`'s own docstring says a caller must redact *before*
        # this boundary ("callers are responsible for redaction before this
        # boundary, this function does not scan for one"). `redact_sanitizer_report`
        # (`orchestrator/redaction.py`) is the redaction pass that promise requires,
        # applied here rather than deeper in, so nothing ever reads an unredacted
        # `finding.raw` back out of a `Finding` row again.
        "sanitizer_report": redact_sanitizer_report(finding.raw),
        "reproducible": False,
    }


def _finding_kwargs_from_artifact(artifact_ref: str) -> dict[str, Any]:
    name = artifact_ref.rsplit("/", 1)[-1]
    digest = hashlib.sha256(artifact_ref.encode("utf-8")).hexdigest()[:16]
    return {
        "category": FindingCategory.OTHER,
        "severity": Severity.HIGH,
        "tool": AnalyzerTool.LIBFUZZER,
        "discovery_method": DiscoveryMethod.FUZZING_CAMPAIGN,
        "file_path": artifact_ref,
        "line": None,
        "function": None,
        "fingerprint": f"fuzz:LIBFUZZER:unstructured:{name}:{digest}"[:128],
        "title": f"libFuzzer crash artifact {name} (no sanitizer report captured)",
        "sanitizer_report": "",
        "reproducible": False,
    }


# ---------------------------------------------------------------------------------
# JobKind.MINIMIZE — real, registered, structurally blocked. See this module's
# docstring, "MINIMIZE: what this executor can and cannot do".
# ---------------------------------------------------------------------------------


@register_executor(JobKind.MINIMIZE)
def _minimize_executor(ctx: ExecutorContext) -> ExecutorResult:
    """No `JobKind.MINIMIZE` job is ever enqueued today —
    `orchestrator.queue.JOB_BACKED_STATES` deliberately excludes it (see that
    module's own docstring). This exists so a future direct enqueue gets a real,
    informative answer, not a `NotImplementedError` stub or a silent no-op.
    """
    return ExecutorResult(
        outcome=JobOutcome.FAILED,
        detail=(
            "MINIMIZE cannot run: no libFuzzer -minimize_crash=1 algorithm is "
            "implemented anywhere in this codebase, and JobKind.MINIMIZE is "
            "deliberately absent from orchestrator/queue.py's stage-to-job map (D-106 "
            "explicitly did not authorize wiring it). D-106 (workers/fuzzing/run.py, "
            "adapters/cpp/fuzzing.py, workers/fuzzing/dispatch.py) already durably "
            "persists the real, unminimized crash-artifact bytes FUZZ discovers as a "
            "Reproducer row, which is what VERIFY's REPRODUCER_ELIMINATED gate needs. "
            "See workers/fuzzing/dispatch.py's module docstring and "
            ".project/decisions.md."
        ),
        result={"infra_failure": True, "blocked_reason": "minimize_not_implemented"},
        error_code=ErrorCode.SANDBOX_UNAVAILABLE,
        retry=False,
    )


@register_transition_policy(JobKind.MINIMIZE)
def _minimize_transition_policy(job: Job, mission: Mission) -> MissionState | None:
    """Always defers. `MINIMIZE` has no `MissionState` of its own — see
    `orchestrator/queue.py`'s `JOB_BACKED_STATES` docstring — so nothing about a
    terminal `MINIMIZE` job, by itself, ever justifies a mission transition. Real
    routing decisions stay with `_fuzz_transition_policy`
    (`STRESS_TEST -> CORRELATE`) regardless of whether a `MINIMIZE` job ever ran.
    """
    return None
