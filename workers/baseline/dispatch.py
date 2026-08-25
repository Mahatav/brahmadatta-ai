"""Wires `workers.baseline.run.run_baseline_stage` into the `JobKind.BASELINE`
executor contract (#168, T1). Read `orchestrator/executors.py`'s module docstring
first — this file is built against it, not the other way around.

## What lives here

Both halves of the contract, since T1 owns `BASELINE` end to end (D-062's staffing
plan):

* `_baseline_executor` — `@register_executor(JobKind.BASELINE)`. Runs the stage (or
  skips straight to reporting a prior result — see "Idempotency" below), persists the
  `BaselineReport` row, and returns an `ExecutorResult` whose `result` dict is the one
  and only channel `_baseline_transition_policy` reads.
* `_baseline_transition_policy` — `@register_transition_policy(JobKind.BASELINE)`.
  Reads `job.state`/`job.result` and returns the `MissionState` the orchestrator
  should move to, or `None`.

This module intentionally does not import `orchestrator.transitions` — see this
package's own docstring, "The one rule that matters more than the type signatures."

## Idempotency (D-061 §3 rule 2)

`BaselineReport` is a `OneToOneField(Mission)` (`missions/models.py`), i.e. a real
per-mission unique constraint. Before doing any real work, `_baseline_executor` checks
for an existing row and, if one is there, reconstructs the `ExecutorResult` it would
have produced from the row rather than re-running `run_baseline_stage` — one query,
before the expensive part, exactly as D-061 §3 asks. `BaselineReport.objects.create`
is additionally wrapped so a genuine race (two workers claiming the same lease is not
supposed to be possible, per the `SKIP LOCKED` design, but "not supposed to be
possible" is not the same guarantee as "structurally prevented here") degrades to
reading the row the other writer produced, rather than propagating `IntegrityError`
past this function.

## The failure mapping (D-061 §2, architecture spec §6.2)

A green baseline (`configure_ok and build_ok and tests_total > 0 and tests_failed ==
0`) is the only outcome that reports `JobOutcome.SUCCEEDED`. Every other case —
configure/build failure, or a build that succeeded but `ctest` reported any failure —
reports `JobOutcome.FAILED`, with `ErrorCode.BASELINE_BUILD_FAILED` for the former and
`ErrorCode.BASELINE_FLAKY` for the latter, matching architecture spec §6.2 verbatim:
"`ctest` on the pristine tree reports any failure → `BASELINE_FLAKY` → `FAILED`. This
is non-negotiable: without a green baseline, 'regression preserved' has no
denominator." `retry=False` in both cases — `MAX_ATTEMPTS_BY_KIND[JobKind.BASELINE]`
is already `1` (`missions/models.py`), and §6.2 says it directly: "Not retried: a
build failure is a result, and retrying it hides it."

`_baseline_transition_policy` mirrors this on the mission side: `TRIAGE` only for a
terminal `SUCCEEDED` job whose `result["passed"]` is `True`; `FAILED` for every other
terminal state except `CANCELLED`, which returns `None` (see its own docstring for
why). `TRANSITIONS[MissionState.BASELINE]` (`contracts/state_machine.py`) is
`{TRIAGE, PAUSED} | {CANCELLING, FAILED}` — there is no `HUMAN_REVIEW` member to reach
for here even by mistake, unlike the `STRESS_TEST` trap `_fuzz_transition_policy`
guards against.

## Compiler diagnostics -> `Finding`/`StageToolRun` rows (#23, D-144)

`BaselineOutcome.compiler_diagnostics` (`workers/baseline/run.py`) is real, already
structurally parsed — this module's only job is turning each `warning`/`error`-severity
one into a `Finding` row (`orchestrator.findings.record_finding`, the same write path
`workers/fuzzing/dispatch.py` and #22's `workers/static_analysis/dispatch.py` both use)
plus one `StageToolRun` row recording the compiler identity (architecture spec §5.1:
tool name/version alongside the findings it produced) — mirroring #22's own
`StageToolRun` write for Semgrep exactly, not inventing a second shape.

`note`-severity diagnostics are never turned into findings — see `adapters/cpp/
compiler_diagnostics.py`'s own docstring: a `note:` only ever restates the location of
the `warning:`/`error:` it is attached to, never a new one.

### File-path normalization

A diagnostic's `file` field, as gcc/clang print it, is whatever path the compiler was
invoked with — in this stage's case, an absolute path into the mission's extracted
snapshot directory (`ctx.source_dir`), since `adapters/cpp/pipeline.py::_configure_argv`
passes `str(detected.source_dir)` to CMake's `-S`. `_normalize_file_path` strips that
prefix, the identical treatment `adapters/semgrep/parser.py::_strip_root` gives Semgrep's
own `file_path` — so the two tools' `Finding.file_path` values are directly comparable
(`src/config.c`, never an absolute host/container path), which the cross-tool dedup
below depends on.

### Dedup against a different tool's finding on the same line (#23's own acceptance
criterion: "Deduplicated against Semgrep findings on the same line")

`record_finding`'s own dedup is exact-`fingerprint` equality (`orchestrator/
findings.py`), which two different tools' fingerprints — each embedding its own
tool-specific material (a `-W` flag here, a Semgrep rule id there) — will essentially
never collide on by accident. "Same line, different tool" needs a second, explicit
check: before calling `record_finding` for a compiler diagnostic, `_line_already_has_a_
finding_from_another_tool` queries whether *this mission* already has a `Finding` (any
tool other than `COMPILER_DIAGNOSTIC` itself) at the exact same `(file_path, line)` —
and skips creating a new row if so, rather than recording a second, likely-redundant
finding for a location another tool already flagged.

This deliberately does NOT dedup two distinct compiler diagnostics against each other on
the same line (e.g. an unused-parameter warning and a shadow note both landing on line
3 of one function signature, a real case — see `adapters/cpp/tests/
test_compiler_diagnostics.py::test_a_distinct_diagnostic_on_the_same_line_is_not_dropped`)
— the `.exclude(tool=AnalyzerTool.COMPILER_DIAGNOSTIC)` below is exactly that
narrowing, so BASELINE's own two-real-warnings-one-line case still records both.

**Ordering note, stated rather than assumed.** Architecture spec's mission flow runs
`BASELINE` before `TRIAGE`/`ANALYZE` (#22's own `JobKind.ANALYZE` backs `TRIAGE`), so in
production this stage's compiler-diagnostic findings are always recorded FIRST — the
check above will find nothing to dedup against on the day #22 merges, because no
Semgrep finding exists yet when BASELINE runs. The check is still correct and still
worth having: it makes the dedup contract symmetric and stage-order-independent (a
`Finding` written by whichever tool runs first is what a same-line collision defers to,
not "whichever tool the code happens to name"), and it is the reciprocal half of what
#22's own `_finding_kwargs`/`_persist_outcome` (`workers/static_analysis/dispatch.py`,
uncommitted as of this writing) would need to add on its own side — an
`.exclude(tool=AnalyzerTool.SEMGREP)`-shaped query against `COMPILER_DIAGNOSTIC` rows —
for the criterion to hold in the direction that actually fires given real stage order.
Flagged in this PR's handoff for whoever finishes #22, not silently assumed to be their
problem alone: this module could not safely make that edit itself (#22's dispatch
module is uncommitted, owned by a different in-flight session, per this repository's
"never silently rewrite another role's prior work" rule).

## A real, documented gap: cooperative cancellation

`run_baseline_stage(mission_id, source_dir, workspace_root, *, jail_policy=None)`
takes no cancel token and does not expose the `packages.sandbox.Jail` it opens
internally — there is no hook for an external caller to invoke `Jail.cancel()` (which
does exist, `packages/sandbox/jail.py`) while `run_variant` is mid-command. This
executor therefore only checks `ctx.cancel_requested()` **once, before** calling
`run_baseline_stage` — enough to skip starting a configure/build/ctest cycle that is
already known to be unwanted, but not enough to interrupt one already running. A
worker that has already entered `run_baseline_stage` will run it to completion (or to
`packages.sandbox`'s own wall-clock/CPU limits) regardless of `cancel_requested()`
afterwards. Closing this for real needs a change to `workers/baseline/run.py` — e.g.
accepting a cancel token that `run_variant`/`Jail` thread through, or returning the
open `Jail` to the caller — which is out of this task's scope (that module belongs to
the compiler-toolchain-engineer seat, and D-061 §3's obligations are about *this*
executor's idempotency, not about extending someone else's already-tested module).
Flagged here, not silently accepted, per the assignment's own instruction not to fake
support that is not real.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction

from adapters.cpp.compiler_diagnostics import CompilerDiagnostic
from authorization import store
from contracts.enums import (
    AnalyzerTool,
    DiscoveryMethod,
    ErrorCode,
    FindingCategory,
    MissionStage,
    MissionState,
    Severity,
)
from contracts.schemas.common import ArtifactRef
from missions.models import (
    Artifact,
    BaselineReport,
    Finding,
    Job,
    JobKind,
    JobState,
    Mission,
    StageToolRun,
)
from orchestrator.executors import (
    ExecutorContext,
    ExecutorResult,
    JobOutcome,
    register_executor,
    register_transition_policy,
)
from orchestrator.findings import record_finding
from orchestrator.redaction import redact_sanitizer_report
from workers.baseline.run import BaselineOutcome, run_baseline_stage

__all__: list[str] = []

#: `Artifact.kind` for the one artifact this module ingests: the durable ctest JUnit
#: XML copy `run_baseline_stage` writes before its jail tears down. See
#: `_log_ref_artifact`'s own docstring for the bug this closes (D-100).
BASELINE_LOG_ARTIFACT_KIND = "baseline_ctest_junit"

#: `Finding.title`'s own field ceiling (`missions/models.py`).
_TITLE_MAX_CHARS = 300

#: Diagnostic severities that become a `Finding` row. `note` never does — see this
#: module's docstring, "Compiler diagnostics -> Finding/StageToolRun rows".
_FINDING_SEVERITIES = frozenset({"warning", "error"})

#: Conservative, substring-based mapping from a `-W` flag to a `FindingCategory` —
#: same spirit as `workers/fuzzing/dispatch.py::_category_for`'s kind-substring
#: matching. Deliberately narrow: most `-W` flags (`-Wunused-variable`, `-Wshadow`,
#: `-Wunused-parameter`, ...) are style/maintainability warnings with no security
#: category that honestly fits, and fall through to `FindingCategory.OTHER` rather
#: than being force-fit into one that does not apply.
_CATEGORY_BY_FLAG_SUBSTRING: tuple[tuple[str, FindingCategory], ...] = (
    ("conversion", FindingCategory.INTEGER_OVERFLOW),
    ("overflow", FindingCategory.INTEGER_OVERFLOW),
    ("sign-compare", FindingCategory.INTEGER_OVERFLOW),
    ("null-dereference", FindingCategory.NULL_DEREFERENCE),
)


def _classify(
    *, configure_ok: bool, build_ok: bool, tests_total: int, tests_failed: int
) -> tuple[bool, ErrorCode | None]:
    """The D3 gate formula (`BaselineOutcome.passed` / `BaselineReport.passed`,
    duplicated here rather than imported because one lives on a dataclass and the
    other on a schema's computed field and neither is importable from the other),
    paired with which `ErrorCode` a red result gets. Single source of truth so the
    fresh-run path and the already-recorded path can never disagree."""
    passed = configure_ok and build_ok and tests_total > 0 and tests_failed == 0
    if passed:
        return True, None
    if not (configure_ok and build_ok):
        return False, ErrorCode.BASELINE_BUILD_FAILED
    return False, ErrorCode.BASELINE_FLAKY


def _fields_from_outcome(outcome: BaselineOutcome) -> dict[str, Any]:
    return {
        "configure_ok": outcome.configure_ok,
        "build_ok": outcome.build_ok,
        "tests_total": outcome.tests_total,
        "tests_passed": outcome.tests_passed,
        "tests_failed": outcome.tests_failed,
        "duration_seconds": outcome.duration_seconds,
        "adapter": outcome.adapter,
        "log_ref": outcome.log_ref,
    }


def _fields_from_report(report: BaselineReport) -> dict[str, Any]:
    return {
        "configure_ok": report.configure_ok,
        "build_ok": report.build_ok,
        "tests_total": report.tests_total,
        "tests_passed": report.tests_passed,
        "tests_failed": report.tests_failed,
        "duration_seconds": report.duration_seconds,
        "adapter": report.adapter,
        "log_ref": report.log_ref,
    }


def _executor_result(fields: dict[str, Any], *, already_recorded: bool) -> ExecutorResult:
    """Build the `ExecutorResult` from a `BaselineReport`'s field values, whichever
    path (fresh run, or the idempotent skip) produced them. `result` carries every
    field `_baseline_transition_policy` (or a human reading `Job.result`) needs;
    nothing here is a secret or raw repository content — counts, a duration, an
    adapter name and a durable log path, matching `Job.result`'s own docstring."""
    passed, error_code = _classify(
        configure_ok=fields["configure_ok"],
        build_ok=fields["build_ok"],
        tests_total=fields["tests_total"],
        tests_failed=fields["tests_failed"],
    )
    result = {"passed": passed, "already_recorded": already_recorded, **fields}

    if passed:
        detail = (
            f"BASELINE_PASSED: {fields['tests_passed']}/{fields['tests_total']} "
            f"ctest cases passed"
        )
        return ExecutorResult(outcome=JobOutcome.SUCCEEDED, detail=detail, result=result)

    detail = (
        f"BASELINE_FAILED: configure_ok={fields['configure_ok']} "
        f"build_ok={fields['build_ok']} tests {fields['tests_passed']}/"
        f"{fields['tests_total']} passed ({fields['tests_failed']} failed)"
    )
    return ExecutorResult(
        outcome=JobOutcome.FAILED,
        detail=detail,
        result=result,
        error_code=error_code,
        retry=False,
    )


def _log_ref_artifact(mission: Mission, log_path: str | None) -> dict[str, Any] | None:
    """Turn `BaselineOutcome.log_ref` — a bare filesystem path to the durable ctest
    JUnit copy `run_baseline_stage` writes before its jail tears down, see that
    function's own docstring — into the `ArtifactRef`-shaped dict `BaselineReport.
    log_ref` is actually typed to hold and every reader downstream actually expects.

    **D-100** (`.project/decisions.md`). Before this, `_persist_report` wrote
    `outcome.log_ref` straight into the `log_ref` `JSONField` — a bare path string
    like `/var/.../<mission_id>-baseline-ctest-junit.xml`. That string round-trips
    through the field fine (a `JSONField` happily stores a bare string), so nothing
    caught this at write time. Every reader, though — `orchestrator.
    evidence_repository.get_baseline_report`'s `_artifact_ref(row.log_ref)`, and from
    there `orchestrator.evidence_bundle`/`orchestrator.evidence_export` for every
    mission's evidence bundle — unconditionally does `ArtifactRef(**value)`, which
    requires a mapping. A bare string blew up with `TypeError: contracts.schemas.
    common.ArtifactRef() argument after ** must be a mapping, not str` the moment any
    code tried to render the baseline section — which is every mission that reaches
    `EXPORTING`, since essentially every mission passes `BASELINE` on its way there.
    Reproduced live twice, #50 D7 gate rehearsal run 4 (D-098).

    Fixed at the write site, not by relaxing the read side: the whole point of
    `ArtifactRef` is that nothing downstream ever sees a raw filesystem path
    (architecture spec §5.2; `evidence_repository.py`'s own module docstring, "callers
    receive hash-addressed pointers, never artifact content"). Ingests the file into
    the same content-addressed `ARTIFACT_ROOT` store `orchestrator.evidence_export`
    already uses for the bundle tarball itself — same `store.ingest_from_path` /
    `Artifact.objects.get_or_create` / `ArtifactRef(...).model_dump(mode="json")`
    shape as that module's `export_mission`, rather than inventing a second mechanism
    for one more kind of artifact. Idempotent by construction (`ingest_from_path`'s
    own docstring): re-ingesting the same bytes under a retried job never duplicates
    the artifact.

    Returns `None` for `log_path is None` (build/configure failures never produce a
    durable log — see `run_baseline_stage`'s own `log_ref=None` comment), matching
    `BaselineReport.log_ref`'s `null=True`.
    """
    if not log_path:
        return None
    ingest = store.ingest_from_path(
        Path(settings.ARTIFACT_ROOT),
        Path(log_path),
        max_bytes=settings.BASELINE_LOG_ARTIFACT_MAX_BYTES,
    )
    artifact, _ = Artifact.objects.get_or_create(
        sha256=ingest.sha256,
        defaults={
            "kind": BASELINE_LOG_ARTIFACT_KIND,
            "size_bytes": ingest.bytes_written,
            "mission": mission,
        },
    )
    return ArtifactRef(
        uri=f"artifact://{mission.id}/{BASELINE_LOG_ARTIFACT_KIND}/{artifact.sha256}",
        kind=BASELINE_LOG_ARTIFACT_KIND,
        sha256=artifact.sha256,
        size_bytes=artifact.size_bytes,
    ).model_dump(mode="json")


def _persist_report(mission: Mission, outcome: BaselineOutcome) -> BaselineReport:
    """Write the terminal artifact. Wrapped against `IntegrityError` as a second line
    of defence behind the pre-flight existence check in `_baseline_executor` — see
    this module's docstring, "Idempotency".

    The `create()` call runs inside its own `transaction.atomic()` block (a savepoint
    when already inside a larger transaction, a real transaction otherwise) rather
    than bare. On both SQLite and PostgreSQL, a caught `IntegrityError` leaves the
    *surrounding* transaction unusable for further queries until it is rolled back —
    an uncaught detail that made the very first version of this fallback raise
    `TransactionManagementError` on the `.get()` right below it instead of the
    `IntegrityError` it meant to handle. Found by
    `orchestrator.tests.test_baseline_executor.
    test_persist_report_survives_a_genuine_race`, not by inspection.
    """
    log_ref = _log_ref_artifact(mission, outcome.log_ref)
    try:
        with transaction.atomic():
            return BaselineReport.objects.create(
                mission=mission,
                configure_ok=outcome.configure_ok,
                build_ok=outcome.build_ok,
                tests_total=outcome.tests_total,
                tests_passed=outcome.tests_passed,
                tests_failed=outcome.tests_failed,
                duration_seconds=outcome.duration_seconds,
                adapter=outcome.adapter,
                recorded_at=outcome.recorded_at,
                log_ref=log_ref,
            )
    except IntegrityError:
        # Someone else's write won the race. Report *their* row's outcome, not ours —
        # the database, not this in-memory result, is the terminal artifact. The
        # savepoint above has already been rolled back by the time we get here, so
        # this query runs against a clean transaction state.
        return BaselineReport.objects.get(mission=mission)


def _normalize_file_path(raw_file: str, source_dir: Path) -> str:
    """Strip `ctx.source_dir`'s absolute prefix off a compiler-reported path.

    gcc/clang print whatever path they were invoked with — an absolute path into the
    mission's extracted snapshot directory on this stage's own build (see this
    module's docstring). Never leaving that absolute prefix on a `Finding.file_path`
    matches `adapters/semgrep/parser.py::_strip_root`'s identical treatment for
    Semgrep matches, which is what makes the two tools' `file_path` values directly
    comparable for the same-line dedup below. Falls back to the raw string, stripped
    of a leading `/`, when the path is not actually under `source_dir` (e.g. a system
    header) — never raises on a path shape this stage does not control.
    """
    try:
        resolved = Path(raw_file).resolve()
        return str(resolved.relative_to(source_dir.resolve()))
    except ValueError:
        return raw_file.lstrip("/")


def _category_for_flag(flag: str | None) -> FindingCategory:
    if flag:
        lowered = flag.lower()
        for substring, category in _CATEGORY_BY_FLAG_SUBSTRING:
            if substring in lowered:
                return category
    return FindingCategory.OTHER


def _severity_for(diagnostic: CompilerDiagnostic, category: FindingCategory) -> Severity:
    if diagnostic.severity == "error":
        return Severity.HIGH
    if category is not FindingCategory.OTHER:
        return Severity.MEDIUM
    return Severity.LOW


def _fingerprint(compiler_id: str, flag: str | None, file_path: str, line: int, column: int | None) -> str:
    material = ":".join(
        ["compiler", compiler_id, flag or "unknown", file_path, str(line), str(column or "")]
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"compiler:{flag or 'unknown'}:{digest}"[:128]


def _title_for(diagnostic: CompilerDiagnostic, file_path: str) -> str:
    label = diagnostic.flag or diagnostic.severity
    title = f"{label}: {diagnostic.message} ({file_path}:{diagnostic.line})"
    return title[:_TITLE_MAX_CHARS]


def _finding_kwargs(diagnostic: CompilerDiagnostic, file_path: str, compiler_id: str) -> dict[str, Any]:
    category = _category_for_flag(diagnostic.flag)
    return {
        "category": category,
        "severity": _severity_for(diagnostic, category),
        "tool": AnalyzerTool.COMPILER_DIAGNOSTIC,
        "discovery_method": DiscoveryMethod.STATIC_ANALYSIS,
        "file_path": file_path,
        "line": diagnostic.line,
        "function": None,
        "fingerprint": _fingerprint(compiler_id, diagnostic.flag, file_path, diagnostic.line, diagnostic.column),
        "title": _title_for(diagnostic, file_path),
        # `diagnostic.raw`/`.message` are the compiler's own text, quoting whatever
        # source identifiers (variable/function names) appear on the offending line —
        # free text from the target, same redaction discipline `workers/fuzzing/
        # dispatch.py`/#22's `workers/static_analysis/dispatch.py` both already apply
        # to their own tool output before it reaches a `Finding` row.
        "sanitizer_report": redact_sanitizer_report(diagnostic.raw),
        "reproducible": False,
    }


def _line_already_has_a_finding_from_another_tool(
    mission: Mission, file_path: str, line: int
) -> bool:
    """See this module's docstring, "Dedup against a different tool's finding on the
    same line" — the `.exclude` is what keeps two distinct compiler diagnostics on the
    same line from being dropped against EACH OTHER; only a different tool's row at
    the identical location suppresses a new compiler-diagnostic `Finding`.
    """
    return (
        Finding.objects.filter(mission=mission, file_path=file_path, line=line)
        .exclude(tool=str(AnalyzerTool.COMPILER_DIAGNOSTIC))
        .exists()
    )


def _persist_compiler_diagnostics(
    mission: Mission, source_dir: Path, outcome: BaselineOutcome, trace_id: str
) -> int:
    """Turn every `warning`/`error`-severity `BaselineOutcome.compiler_diagnostics`
    entry into a `Finding` row, plus one `StageToolRun` row recording the compiler
    identity (#23's third acceptance criterion: "compiler version recorded with the
    findings") whenever a compiler actually ran (`outcome.compiler_id != "unknown"` —
    see `workers/baseline/run.py`'s own docstring for the one case it stays
    "unknown": a DETECT/PROBE_TOOLCHAIN/CONFIGURE failure, where no compiler ever ran
    at all).

    Called BEFORE `_persist_report` in `_baseline_executor`, not after — the same
    "findings before the terminal marker" ordering `workers/fuzzing/dispatch.py::
    _persist_outcome` and #22's `workers/static_analysis/dispatch.py::_persist_outcome`
    both use (see either module's own docstring): `BaselineReport` existing is what
    `_baseline_executor`'s own idempotency check reads, so writing it first would let a
    crash between the two calls permanently skip these findings on every future
    "already recorded" short-circuit, never writing them at all.

    Returns the number of `Finding` rows actually created (for `ExecutorResult.
    result`), which is not the same number as `len(outcome.compiler_diagnostics)`
    whenever `note` diagnostics or a same-line dedup skip are present.
    """
    recorded = 0
    for diagnostic in outcome.compiler_diagnostics:
        if diagnostic.severity not in _FINDING_SEVERITIES:
            continue
        file_path = _normalize_file_path(diagnostic.file, source_dir)
        if _line_already_has_a_finding_from_another_tool(mission, file_path, diagnostic.line):
            continue
        record_finding(
            mission.id,
            trace_id=trace_id,
            now=outcome.recorded_at,
            detected_at=outcome.recorded_at,
            **_finding_kwargs(diagnostic, file_path, outcome.compiler_id),
        )
        recorded += 1

    if outcome.compiler_id != "unknown":
        StageToolRun.objects.create(
            mission=mission,
            stage=str(MissionStage.BASELINE),
            tool_name=outcome.compiler_id,
            tool_version=outcome.compiler_version,
            image_digest=None,  # subprocess-jail path is unpinned — see toolchain.py
            flags=[f"diagnostics:{len(outcome.compiler_diagnostics)}", f"findings:{recorded}"],
            artifact_refs=[],
            started_at=outcome.recorded_at,
            finished_at=outcome.recorded_at,
        )

    return recorded


@register_executor(JobKind.BASELINE)
def _baseline_executor(ctx: ExecutorContext) -> ExecutorResult:
    """`JobKind.BASELINE` — configure, build, `ctest` on the pristine snapshot.

    Never raises on a red or broken build (that guarantee is `run_baseline_stage`'s;
    see its own docstring). Only a genuine programming error escapes, by design —
    swallowing it here would hide a real bug behind a fabricated `JobOutcome.FAILED`.
    """
    existing = BaselineReport.objects.filter(mission=ctx.mission).first()
    if existing is not None:
        return _executor_result(_fields_from_report(existing), already_recorded=True)

    if ctx.cancel_requested():
        return ExecutorResult(
            outcome=JobOutcome.CANCELLED,
            detail="Cancellation requested before the baseline stage started.",
            result={"cancelled_before_start": True},
        )

    outcome = run_baseline_stage(
        mission_id=ctx.mission.id,
        source_dir=ctx.source_dir,
        workspace_root=ctx.workspace_root,
    )
    # #23: findings before the terminal report — see `_persist_compiler_diagnostics`'s
    # own docstring for why the ordering matters.
    _persist_compiler_diagnostics(ctx.mission, ctx.source_dir, outcome, ctx.trace_id)
    report = _persist_report(ctx.mission, outcome)
    return _executor_result(_fields_from_report(report), already_recorded=False)


@register_transition_policy(JobKind.BASELINE)
def _baseline_transition_policy(job: Job, mission: Mission) -> MissionState | None:
    """A terminal `BASELINE` job routes `BASELINE -> TRIAGE` only on a green result;
    everything else routes to `FAILED`, except a cancelled job, which defers.

    `TRANSITIONS[MissionState.BASELINE]` is `{TRIAGE, PAUSED} | {CANCELLING, FAILED}`
    (`contracts/state_machine.py`) — there is no `HUMAN_REVIEW` member reachable from
    here, so unlike `_fuzz_transition_policy` there is no trap to guard against, only
    the §6.2 mapping to get right: a build/configure failure (`ErrorCode.
    BASELINE_BUILD_FAILED`) and a build that succeeded but `ctest` reported a failure
    (`ErrorCode.BASELINE_FLAKY`) are **both** `Mission.FAILED`, never a lesser state —
    "without a green baseline, 'regression preserved' has no denominator" (§6.2, D-009).
    A `TIMED_OUT` job (the deadline watchdog killed the stage before it produced any
    `BaselineOutcome`, so there is no `BaselineReport` to read) is treated the same
    way: no result to route on the happy path, so `FAILED`.

    `CANCELLED` returns `None` rather than guessing a target. A job is only cancelled
    because a mission-level cancel is already in flight, and that action is what
    transitions the mission (to `CANCELLING`, ultimately `CANCELLED` once `TEARDOWN`
    confirms release, per architecture spec §6.7) — this policy would otherwise be
    racing that transition with a stale view of `mission.state` and no way to tell
    which target is legal from wherever the mission actually is by the time this
    terminal row is read. "Does not — by itself — justify a transition yet"
    (`orchestrator/executors.py`'s own docstring) is exactly this case.
    """
    if job.state == JobState.CANCELLED:
        return None
    if job.state == JobState.SUCCEEDED and bool(job.result.get("passed")):
        return MissionState.TRIAGE
    return MissionState.FAILED
