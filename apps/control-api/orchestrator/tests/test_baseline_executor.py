"""`JobKind.BASELINE`'s executor and transition policy (#168, T1).

`workers.baseline.dispatch` is imported for its registration side effect the same way
`missions.apps.MissionsConfig.ready()` does it at real startup — see that module's
docstring for why a `ready()` hook rather than a dispatch-table entry in a not-yet-built
`run_worker`.

Three shapes of test, per the assignment:

1. The terminal-artifact / no-double-run property (D-061 §3 rule 2) —
   `test_existing_report_short_circuits_no_double_run` and
   `test_persist_report_survives_a_genuine_race`.
2. Transition-policy routing, both directions —
   `test_transition_policy_*`, cross-checked against the real state machine via
   `orchestrator.transitions.transition` so a policy that returns an illegal target
   fails here, not in QA.
3. An integration-style pass against the real `pktcfg` demo target, mirroring
   `workers/baseline/tests`' own fixture pattern — green, build-broken and
   test-broken sources, each carried through the executor, the persisted
   `BaselineReport`, and the transition policy in one line per case.
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest

from contracts.enums import ErrorCode, MissionState
from missions.models import BaselineReport, Job, JobKind, JobState, Mission
from orchestrator import transitions
from orchestrator.executors import ExecutorContext, JobOutcome, executor_for, transition_policy_for
from orchestrator.tests.conftest import NOW, TRACE, walk_to
from workers.baseline import dispatch

pytestmark = pytest.mark.django_db

REPO_ROOT = Path(__file__).resolve().parents[4]
PKTCFG_SOURCE = REPO_ROOT / "demo" / "repositories" / "pktcfg"

requires_toolchain = pytest.mark.skipif(
    not PKTCFG_SOURCE.is_dir() or shutil.which("cmake") is None or shutil.which("ctest") is None,
    reason="demo/repositories/pktcfg or the CMake toolchain is not available in this checkout",
)


# ---------------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------------


@pytest.fixture
def broken_configure_source(tmp_path: Path) -> Path:
    dest = tmp_path / "pktcfg-broken"
    shutil.copytree(PKTCFG_SOURCE, dest)
    cmakelists = dest / "CMakeLists.txt"
    cmakelists.write_text("this is not valid CMake syntax (((\n" + cmakelists.read_text())
    return dest


@pytest.fixture
def warning_producing_source(tmp_path: Path) -> Path:
    """A real copy of pktcfg with one real, `-Wunused-variable`/`-Wconversion`-
    producing function appended to `src/config.c` (#23) — mirrors `workers/baseline/
    tests/conftest.py`'s fixture of the same name exactly (same injected snippet), so
    both suites are asserting on the identical real compiler output."""
    dest = tmp_path / "pktcfg-warnings"
    shutil.copytree(PKTCFG_SOURCE, dest)
    config_c = dest / "src" / "config.c"
    config_c.write_text(
        config_c.read_text()
        + "\n"
        "/* #23 test fixture: a real, intentional compiler diagnostic. */\n"
        "static int pkt_debug_probe_diagnostic(void)\n"
        "{\n"
        "    int diagnostic_probe_unused = 0;\n"
        "    long wide_value = 90000;\n"
        "    short narrowed_value = wide_value;\n"
        "    return narrowed_value;\n"
        "}\n"
    )
    return dest


@pytest.fixture
def deprecated_secret_source(tmp_path: Path) -> Path:
    """SEC-A PoC (cybersecurity, PR #278), reproduced against a real build: a
    function marked `__attribute__((deprecated("...")))` — the C spelling of the
    `[[deprecated("...")]]` attribute cybersecurity's report used — whose message
    string embeds a secret-shaped credential. gcc/clang echo that string verbatim
    into the `-Wdeprecated-declarations` diagnostic's `message` at every call site,
    with no flag beyond the `-Wall -Wextra` pktcfg already builds with (deprecated-
    declarations warnings are on by default). Reproduced locally against real
    AppleClang before writing this fixture:

        secret.c:4:25: warning: 'compute' is deprecated: rotate
        DATABASE_URL=postgresql://user:pass@host/db [-Wdeprecated-declarations]
    """
    dest = tmp_path / "pktcfg-deprecated-secret"
    shutil.copytree(PKTCFG_SOURCE, dest)
    config_c = dest / "src" / "config.c"
    config_c.write_text(
        config_c.read_text()
        + "\n"
        "/* SEC-A test fixture: this message must never reach Finding.title. */\n"
        '__attribute__((deprecated("rotate DATABASE_URL=postgresql://user:pass@host/db")))\n'
        "static int pkt_debug_probe_deprecated(int limit)\n"
        "{\n"
        "    return limit;\n"
        "}\n"
        "\n"
        "__attribute__((used))\n"
        "static int pkt_debug_probe_deprecated_caller(void)\n"
        "{\n"
        "    return pkt_debug_probe_deprecated(5);\n"
        "}\n"
    )
    return dest


@pytest.fixture
def line_directive_escape_source(tmp_path: Path) -> Path:
    """SEC-B PoC (cybersecurity, PR #278), reproduced against a real build: a
    `#line` directive redirecting every diagnostic that follows it to an absolute
    path far outside `source_dir`. Reproduced locally against real AppleClang before
    writing this fixture — the exact PoC from the cybersecurity report:

        #line 1 "/etc/passwd"
        int compute(int limit) { ... }

    produces `/etc/passwd:1:24: warning: unused parameter 'limit'
    [-Wunused-parameter]` under `cc -Wall -Wextra`."""
    dest = tmp_path / "pktcfg-line-escape"
    shutil.copytree(PKTCFG_SOURCE, dest)
    config_c = dest / "src" / "config.c"
    config_c.write_text(
        config_c.read_text()
        + "\n"
        "/* SEC-B test fixture: this diagnostic's reported location is forged. */\n"
        '#line 1 "/etc/passwd"\n'
        "static int pkt_debug_probe_line_escape(int limit)\n"
        "{\n"
        "    return 0;\n"
        "}\n"
        "\n"
        "__attribute__((used))\n"
        "static int pkt_debug_probe_line_escape_caller(void)\n"
        "{\n"
        "    return pkt_debug_probe_line_escape(5);\n"
        "}\n"
    )
    return dest


@pytest.fixture
def legitimate_line_directive_source(tmp_path: Path) -> Path:
    """The non-adversarial case SEC-B's fix must not break: a `#line` directive that
    re-points diagnostics at a DIFFERENT file, but one that is still genuinely
    in-tree, under `source_dir` — exactly the shape a bison/flex-generated parser
    uses to attribute its own diagnostics back to the `.y`/`.l` grammar file it was
    generated from (`src/decode.c` stands in for that grammar file here; it is a
    real, already-existing file in this copy of pktcfg). Reproduced locally against
    real AppleClang before writing this fixture: the diagnostic's reported file is
    printed exactly as given in the `#line` directive (`src/decode.c`, relative),
    unaffected by the compiler's actual working directory.
    """
    dest = tmp_path / "pktcfg-line-legitimate"
    shutil.copytree(PKTCFG_SOURCE, dest)
    config_c = dest / "src" / "config.c"
    config_c.write_text(
        config_c.read_text()
        + "\n"
        "/* Legitimate #line test fixture: still resolves under source_dir. */\n"
        '#line 1 "src/decode.c"\n'
        "static int pkt_debug_probe_generated(int limit)\n"
        "{\n"
        "    int unused_generated_probe = 0;\n"
        "    return limit;\n"
        "}\n"
        "\n"
        "__attribute__((used))\n"
        "static int pkt_debug_probe_generated_caller(void)\n"
        "{\n"
        "    return pkt_debug_probe_generated(5);\n"
        "}\n"
    )
    return dest


@pytest.fixture
def candidate_b_source(tmp_path: Path) -> Path:
    """configure/build succeed; ctest reports one real failure. Mirrors
    `workers/baseline/tests/conftest.py`'s own fixture of the same name."""
    if shutil.which("patch") is None:
        pytest.skip("`patch` not on PATH")
    dest = tmp_path / "pktcfg-candidate-b"
    shutil.copytree(PKTCFG_SOURCE, dest)
    patch_file = PKTCFG_SOURCE / "patches" / "candidate-b-rejected-crash-only-fix.patch"
    result = subprocess.run(
        ["patch", "-p1", "-i", str(patch_file)],
        cwd=dest,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"failed to apply candidate-b patch: {result.stderr}"
    return dest


def _job(mission: Mission, *, state: str = JobState.RUNNING, result: dict | None = None) -> Job:
    return Job.objects.create(
        mission=mission,
        kind=JobKind.BASELINE,
        state=state,
        result=result or {},
        attempt=1,
        max_attempts=1,
        run_after=NOW,
        deadline_at=NOW + timedelta(minutes=30),
    )


def _ctx(
    mission: Mission,
    job: Job,
    source_dir: Path,
    workspace_root: Path,
    *,
    cancelled: bool = False,
) -> ExecutorContext:
    return ExecutorContext(
        job=job,
        mission=mission,
        source_dir=Path(source_dir),
        workspace_root=Path(workspace_root),
        trace_id=TRACE,
        cancel_requested=lambda: cancelled,
    )


# ---------------------------------------------------------------------------------
# 1. Idempotency: the terminal-artifact check (D-061 §3 rule 2)
# ---------------------------------------------------------------------------------


def test_existing_report_short_circuits_no_double_run(mission: Mission, tmp_path: Path, monkeypatch):
    """A worker that died after writing `BaselineReport` but before its `Job` reached
    `SUCCEEDED` must not re-run the stage on restart — it would hit the OneToOne
    unique constraint (D-047). Proven here by making a real re-run raise if called."""
    walk_to(mission, MissionState.BASELINE)
    BaselineReport.objects.create(
        mission=mission,
        configure_ok=True,
        build_ok=True,
        tests_total=8,
        tests_passed=8,
        tests_failed=0,
        duration_seconds=1.23,
        adapter="C_CMAKE_CTEST",
        recorded_at=NOW,
        log_ref="/does/not/matter/for/this/test.xml",
    )

    def _must_not_run(*args, **kwargs):
        raise AssertionError("run_baseline_stage was called despite an existing BaselineReport")

    monkeypatch.setattr(dispatch, "run_baseline_stage", _must_not_run)

    job = _job(mission)
    # source_dir/workspace_root point nowhere real - if the short circuit did not
    # trigger, the real run_baseline_stage would fail anyway, but the monkeypatch
    # above is the actual assertion that no real work was attempted.
    ctx = _ctx(mission, job, tmp_path / "nonexistent-source", tmp_path / "workspace")

    result = executor_for(JobKind.BASELINE)(ctx)

    assert result.outcome == JobOutcome.SUCCEEDED
    assert result.result["passed"] is True
    assert result.result["already_recorded"] is True
    assert BaselineReport.objects.filter(mission=mission).count() == 1


def test_persist_report_survives_a_genuine_race(mission: Mission):
    """Two calls to `_persist_report` for the same mission (standing in for two
    workers that both got past the pre-flight check, which the `SKIP LOCKED` lease
    design says should not happen but this module does not trust blindly) must not
    surface `IntegrityError` — the second call reads back the first call's row."""
    from adapters.cpp.snapshot import hash_source_tree
    from workers.baseline.run import BaselineOutcome

    fake_outcome = BaselineOutcome(
        mission_id=str(mission.id),
        configure_ok=True,
        build_ok=True,
        tests_total=8,
        tests_passed=8,
        tests_failed=0,
        duration_seconds=1.0,
        adapter="C_CMAKE_CTEST",
        recorded_at=NOW,
        snapshot=hash_source_tree(PKTCFG_SOURCE) if PKTCFG_SOURCE.is_dir() else None,
        log_ref=None,
    )

    first = dispatch._persist_report(mission, fake_outcome)
    second = dispatch._persist_report(mission, fake_outcome)

    assert first.id == second.id
    assert BaselineReport.objects.filter(mission=mission).count() == 1


def test_persist_report_turns_a_log_ref_path_into_an_artifact_ref_dict(
    mission: Mission, tmp_path: Path, settings
):
    """D-100 (`.project/decisions.md`). #50 D7 gate rehearsal run 4 (D-098): every
    mission reaching `EXPORTING` crashed identically — `contracts.schemas.common.
    ArtifactRef() argument after ** must be a mapping, not str` — because
    `_persist_report` used to write `outcome.log_ref` (a bare filesystem path string
    `run_baseline_stage` produces; see that function's own docstring) straight into
    `BaselineReport.log_ref`, which every reader downstream
    (`orchestrator.evidence_repository.get_baseline_report`) unconditionally unpacks
    as `ArtifactRef(**row.log_ref)`.

    This test reproduces the failure end to end — a real log file on disk,
    `_persist_report` writing it, then the real downstream reader consuming exactly
    what was written, no mock on either half. Against the pre-D-100 code this fails
    at the `get_baseline_report` call with D-098's own `TypeError` (`report.log_ref`
    would still be the bare path string at that point, and `ArtifactRef(**"<path
    string>")` raises exactly that on the first character it tries to treat as a
    keyword — confirmed by reverting `_persist_report`'s `log_ref=log_ref` back to
    `log_ref=outcome.log_ref` locally and re-running this test).
    """
    import hashlib

    from adapters.cpp.snapshot import hash_source_tree
    from missions.models import Artifact
    from orchestrator.evidence_repository import get_baseline_report
    from workers.baseline.run import BaselineOutcome

    settings.ARTIFACT_ROOT = tmp_path / "artifacts"

    log_path = tmp_path / f"{mission.id}-baseline-ctest-junit.xml"
    log_bytes = b"<testsuite tests='8' failures='0'></testsuite>"
    log_path.write_bytes(log_bytes)

    outcome = BaselineOutcome(
        mission_id=str(mission.id),
        configure_ok=True,
        build_ok=True,
        tests_total=8,
        tests_passed=8,
        tests_failed=0,
        duration_seconds=1.0,
        adapter="C_CMAKE_CTEST",
        recorded_at=NOW,
        snapshot=hash_source_tree(PKTCFG_SOURCE) if PKTCFG_SOURCE.is_dir() else None,
        log_ref=str(log_path),
    )

    report = dispatch._persist_report(mission, outcome)

    # The write side: a mapping, never the bare path string.
    assert isinstance(report.log_ref, dict)
    assert report.log_ref["kind"] == dispatch.BASELINE_LOG_ARTIFACT_KIND
    assert report.log_ref["uri"].startswith(f"artifact://{mission.id}/")
    assert report.log_ref["sha256"] == hashlib.sha256(log_bytes).hexdigest()
    assert report.log_ref["size_bytes"] == len(log_bytes)

    # The artifact is actually durable, content-addressed, and indexed.
    artifact = Artifact.objects.get(sha256=report.log_ref["sha256"])
    assert artifact.mission_id == mission.id
    assert artifact.size_bytes == len(log_bytes)

    # The read side D-098 actually crashed on: the real downstream consumer.
    baseline_schema = get_baseline_report(mission.id)
    assert baseline_schema.log_ref is not None
    assert baseline_schema.log_ref.sha256 == hashlib.sha256(log_bytes).hexdigest()


def test_persist_report_leaves_log_ref_null_when_there_is_no_durable_log(
    mission: Mission,
):
    """A configure/build failure produces `BaselineOutcome.log_ref=None` (`workers/
    baseline/run.py`'s own comment: 'no durable artifact for a configure/build
    failure'). `_persist_report` must not try to ingest nothing, and the read side
    must see a real `None`, not a broken reference."""
    from adapters.cpp.snapshot import hash_source_tree
    from workers.baseline.run import BaselineOutcome

    outcome = BaselineOutcome(
        mission_id=str(mission.id),
        configure_ok=False,
        build_ok=False,
        tests_total=0,
        tests_passed=0,
        tests_failed=0,
        duration_seconds=0.1,
        adapter="UNKNOWN",
        recorded_at=NOW,
        snapshot=hash_source_tree(PKTCFG_SOURCE) if PKTCFG_SOURCE.is_dir() else None,
        log_ref=None,
    )

    report = dispatch._persist_report(mission, outcome)

    assert report.log_ref is None


def test_cancel_requested_before_start_short_circuits(mission: Mission, tmp_path: Path, monkeypatch):
    """A real, if coarse, cooperative-cancellation check: skip starting the stage at
    all if cancellation was already requested (see `workers/baseline/dispatch.py`'s
    module docstring, "A real, documented gap: cooperative cancellation" - this is
    the one hook that *is* implemented, not the mid-run one that is not)."""

    def _must_not_run(*args, **kwargs):
        raise AssertionError("run_baseline_stage was called despite cancel_requested()")

    monkeypatch.setattr(dispatch, "run_baseline_stage", _must_not_run)

    job = _job(mission)
    ctx = _ctx(mission, job, tmp_path / "src", tmp_path / "workspace", cancelled=True)

    result = executor_for(JobKind.BASELINE)(ctx)

    assert result.outcome == JobOutcome.CANCELLED
    assert BaselineReport.objects.filter(mission=mission).count() == 0


# ---------------------------------------------------------------------------------
# 2. Transition-policy routing (D-061 §2, architecture spec §6.2)
# ---------------------------------------------------------------------------------


def test_transition_policy_routes_a_green_baseline_to_triage(mission: Mission):
    walk_to(mission, MissionState.BASELINE)
    job = _job(mission, state=JobState.SUCCEEDED, result={"passed": True})

    target = transition_policy_for(JobKind.BASELINE)(job, mission)

    assert target is MissionState.TRIAGE
    # Cross-checked against the real state machine, not just the policy's own claim.
    transitions.transition(mission.id, target, trace_id=TRACE, now=NOW)
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.TRIAGE


@pytest.mark.parametrize(
    "job_state,result",
    [
        (JobState.FAILED, {"passed": False, "error_code": ErrorCode.BASELINE_BUILD_FAILED}),
        (JobState.FAILED, {"passed": False, "error_code": ErrorCode.BASELINE_FLAKY}),
        (JobState.TIMED_OUT, {}),
    ],
)
def test_transition_policy_routes_everything_red_to_failed(mission: Mission, job_state, result):
    walk_to(mission, MissionState.BASELINE)
    job = _job(mission, state=job_state, result=result)

    target = transition_policy_for(JobKind.BASELINE)(job, mission)

    assert target is MissionState.FAILED
    transitions.transition(mission.id, target, trace_id=TRACE, now=NOW)
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.FAILED


def test_transition_policy_defers_on_a_cancelled_job(mission: Mission):
    """A cancelled BASELINE job does not, by itself, justify a transition - the
    mission-level cancel already in flight owns that. Returning `None` here means
    `dispatch_terminal_jobs` does not call `transition()` off this job at all."""
    walk_to(mission, MissionState.BASELINE)
    job = _job(mission, state=JobState.CANCELLED, result={})

    target = transition_policy_for(JobKind.BASELINE)(job, mission)

    assert target is None


# ---------------------------------------------------------------------------------
# 3. Integration-style: the real pktcfg demo target through the whole executor
# ---------------------------------------------------------------------------------


@requires_toolchain
@pytest.mark.slow
def test_a_green_run_produces_a_sane_result_and_routes_to_triage(mission: Mission, tmp_path: Path):
    walk_to(mission, MissionState.BASELINE)
    job = _job(mission)
    ctx = _ctx(mission, job, PKTCFG_SOURCE, tmp_path / "workspace")

    result = executor_for(JobKind.BASELINE)(ctx)

    assert result.outcome == JobOutcome.SUCCEEDED
    assert result.error_code is None
    assert result.result["passed"] is True
    assert result.result["tests_total"] == 8
    assert result.result["tests_failed"] == 0

    report = BaselineReport.objects.get(mission=mission)
    assert report.configure_ok is True
    assert report.build_ok is True

    job.state = JobState.SUCCEEDED
    job.result = result.result
    target = transition_policy_for(JobKind.BASELINE)(job, mission)
    assert target is MissionState.TRIAGE
    transitions.transition(mission.id, target, trace_id=TRACE, now=NOW)
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.TRIAGE


@requires_toolchain
@pytest.mark.slow
def test_a_broken_configure_produces_build_failed_and_routes_to_failed(
    mission: Mission, tmp_path: Path, broken_configure_source: Path
):
    walk_to(mission, MissionState.BASELINE)
    job = _job(mission)
    ctx = _ctx(mission, job, broken_configure_source, tmp_path / "workspace")

    result = executor_for(JobKind.BASELINE)(ctx)

    assert result.outcome == JobOutcome.FAILED
    assert result.error_code == ErrorCode.BASELINE_BUILD_FAILED
    assert result.result["passed"] is False
    assert result.result["configure_ok"] is False

    report = BaselineReport.objects.get(mission=mission)
    assert report.configure_ok is False

    job.state = JobState.FAILED
    job.result = result.result
    target = transition_policy_for(JobKind.BASELINE)(job, mission)
    assert target is MissionState.FAILED
    transitions.transition(mission.id, target, trace_id=TRACE, now=NOW)
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.FAILED


class _FakeOutcome:
    """The three `BaselineOutcome` attributes `_persist_compiler_diagnostics` reads,
    without constructing a full real one (`SnapshotInfo` et al. are irrelevant here —
    this test is about the dedup query, not the build)."""

    def __init__(self, compiler_diagnostics):
        self.compiler_diagnostics = compiler_diagnostics
        self.compiler_id = "TestCompiler"
        self.compiler_version = "1.0"
        self.recorded_at = NOW


def test_a_compiler_diagnostic_defers_to_an_existing_finding_on_the_same_line(mission: Mission):
    """#23's own acceptance criterion: 'Deduplicated against Semgrep findings on the
    same line.' Simulates the post-#22 world directly (a pre-existing SEMGREP
    `Finding` on the exact file:line a compiler diagnostic also lands on) without
    depending on #22's own uncommitted code — see `workers/baseline/dispatch.py`'s
    module docstring, "Ordering note", for why this direction has to be simulated
    rather than reproduced through the real ANALYZE stage today."""
    from adapters.cpp.compiler_diagnostics import CompilerDiagnostic
    from contracts.enums import AnalyzerTool, DiscoveryMethod, FindingCategory, Severity
    from missions.models import Finding
    from workers.baseline import dispatch as baseline_dispatch

    Finding.objects.create(
        mission=mission,
        category=str(FindingCategory.OTHER),
        severity=str(Severity.MEDIUM),
        tool="SEMGREP",  # AnalyzerTool.SEMGREP does not exist on this branch yet (#22
        # is uncommitted) - the dedup query below excludes only COMPILER_DIAGNOSTIC,
        # so any other tool string, including one #22 has not landed yet, proves it.
        discovery_method=str(DiscoveryMethod.STATIC_ANALYSIS),
        file_path="src/config.c",
        line=73,
        fingerprint="semgrep:pre-existing:same-line",
        title="pre-existing semgrep finding on the same line",
        detected_at=NOW,
    )

    diagnostic_same_line = CompilerDiagnostic(
        severity="warning",
        file="/abs/src/config.c",
        line=73,
        column=9,
        message="unused variable 'diagnostic_probe_unused'",
        flag="-Wunused-variable",
        raw="src/config.c:73:9: warning: unused variable 'diagnostic_probe_unused' [-Wunused-variable]",
    )
    diagnostic_other_line = CompilerDiagnostic(
        severity="warning",
        file="/abs/src/config.c",
        line=75,
        column=19,
        message="implicit conversion",
        flag="-Wconversion",
        raw="src/config.c:75:19: warning: implicit conversion [-Wconversion]",
    )

    recorded = baseline_dispatch._persist_compiler_diagnostics(
        mission,
        Path("/abs"),
        _FakeOutcome((diagnostic_same_line, diagnostic_other_line)),
        TRACE,
    )

    # Only the line with NO pre-existing finding from another tool gets a new row.
    assert recorded == 1
    compiler_findings = Finding.objects.filter(
        mission=mission, tool=str(AnalyzerTool.COMPILER_DIAGNOSTIC)
    )
    assert compiler_findings.count() == 1
    assert compiler_findings.get().line == 75
    # The pre-existing SEMGREP finding on line 73 is untouched, not overwritten.
    assert Finding.objects.filter(mission=mission, line=73).count() == 1


@requires_toolchain
@pytest.mark.slow
def test_real_compiler_warnings_become_finding_and_stage_tool_run_rows(
    mission: Mission, tmp_path: Path, warning_producing_source: Path
):
    """End to end against a REAL build: the executor runs `cmake --build` once (the
    D3 gate's own build), and real `-Wunused-variable`/narrowing-conversion warnings
    it produces become real `Finding` rows plus one `StageToolRun` row carrying the
    real compiler identity — #23's three acceptance criteria, proven against real
    compiler output, not a mock."""
    from contracts.enums import AnalyzerTool, DiscoveryMethod, Severity
    from missions.models import Finding, StageToolRun

    walk_to(mission, MissionState.BASELINE)
    job = _job(mission)
    ctx = _ctx(mission, job, warning_producing_source, tmp_path / "workspace")

    result = executor_for(JobKind.BASELINE)(ctx)

    assert result.outcome == JobOutcome.SUCCEEDED  # warnings alone never fail BASELINE
    assert result.result["passed"] is True

    findings = list(
        Finding.objects.filter(mission=mission, tool=str(AnalyzerTool.COMPILER_DIAGNOSTIC))
    )
    assert findings, "expected at least one real COMPILER_DIAGNOSTIC finding"
    assert all(f.discovery_method == str(DiscoveryMethod.STATIC_ANALYSIS) for f in findings)
    # file:line:severity, structured — never the raw multi-line compiler transcript
    # sitting in a field meant for one location.
    assert all(f.file_path == "src/config.c" for f in findings)  # normalized, not absolute
    assert all(f.line and f.line > 0 for f in findings)
    # SEC-A (cybersecurity, PR #278): `Finding.title` is built from structured,
    # compiler-controlled fields only (flag/category/file/line) — never from
    # `diagnostic.message`, which can carry raw, attacker-influenced target source
    # text (see `_title_for`'s own docstring). Selecting by fingerprint, not by a
    # message-derived substring like the identifier name, is itself part of that
    # fix: this test no longer asserts on anything `title` deliberately excludes.
    unused_var = next(f for f in findings if f.fingerprint.startswith("compiler:-Wunused-variable:"))
    assert unused_var.severity == str(Severity.LOW)  # no security-relevant category
    assert "-Wunused-variable" in unused_var.title
    assert "src/config.c" in unused_var.title

    # Criterion 3: compiler version recorded alongside the findings.
    tool_run = StageToolRun.objects.get(mission=mission, stage="BASELINE")
    assert tool_run.tool_name  # real compiler id (e.g. "GNU", "AppleClang", "Clang")
    assert tool_run.tool_version and tool_run.tool_version != "unknown"

    # Idempotency: re-running the executor (standing in for a worker retrying the
    # same claimed job — `Job(mission, kind)` is unique, so a genuine second BASELINE
    # job for this mission cannot exist; see D-065 §1) must not duplicate rows.
    ctx2 = _ctx(mission, job, warning_producing_source, tmp_path / "workspace-2")
    result2 = executor_for(JobKind.BASELINE)(ctx2)
    assert result2.result["already_recorded"] is True
    assert (
        Finding.objects.filter(mission=mission, tool=str(AnalyzerTool.COMPILER_DIAGNOSTIC)).count()
        == len(findings)
    )
    assert StageToolRun.objects.filter(mission=mission, stage="BASELINE").count() == 1


@requires_toolchain
@pytest.mark.slow
def test_a_clean_baseline_build_records_no_compiler_findings(mission: Mission, tmp_path: Path):
    """`demo/repositories/pktcfg` builds clean (verified directly in this PR's
    handoff, `-Wall -Wextra -Wshadow -Wconversion` already on) — zero real findings
    is the correct, honest result, never a fabricated one."""
    from contracts.enums import AnalyzerTool
    from missions.models import Finding, StageToolRun

    walk_to(mission, MissionState.BASELINE)
    job = _job(mission)
    ctx = _ctx(mission, job, PKTCFG_SOURCE, tmp_path / "workspace")

    result = executor_for(JobKind.BASELINE)(ctx)

    assert result.result["passed"] is True
    assert (
        Finding.objects.filter(mission=mission, tool=str(AnalyzerTool.COMPILER_DIAGNOSTIC)).count()
        == 0
    )
    # The compiler identity is still recorded even with zero findings — #22's own
    # StageToolRun write for Semgrep does the identical thing on a zero-match scan.
    tool_run = StageToolRun.objects.get(mission=mission, stage="BASELINE")
    assert tool_run.tool_version != "unknown"


# ---------------------------------------------------------------------------------
# SEC-A / SEC-B (cybersecurity, PR #278) — HIGH-severity findings against #23.
#
# Each PoC is proven twice: a fast, deterministic unit test directly against the
# fixed functions (fabricated `CompilerDiagnostic`s carrying the exact strings
# cybersecurity's report reproduced, no toolchain required), and a real end-to-end
# test that actually compiles the PoC source and runs it through the real BASELINE
# executor. Both shapes fail against the pre-fix code and pass against the fix —
# see this PR's handoff for the actual `pytest` output confirming that on both
# sides of the fix.
# ---------------------------------------------------------------------------------


def test_title_for_never_carries_raw_diagnostic_message_text(mission: Mission):
    """SEC-A, fast unit reproduction: a `CompilerDiagnostic` shaped exactly like the
    real AppleClang capture in `deprecated_secret_source`'s own docstring —
    `message` embeds a `DATABASE_URL=postgresql://...` credential, echoed verbatim
    by the compiler from an untrusted target's `[[deprecated("...")]]`-equivalent
    attribute. `_finding_kwargs`'s `title` must never contain it. Against the
    pre-fix `_title_for` (which built `title` straight from `diagnostic.message`,
    truncated but never redacted) this assertion fails immediately."""
    from adapters.cpp.compiler_diagnostics import CompilerDiagnostic
    from workers.baseline import dispatch as baseline_dispatch

    secret = "DATABASE_URL=postgresql://user:pass@host/db"
    diagnostic = CompilerDiagnostic(
        severity="warning",
        file="/abs/src/config.c",
        line=4,
        column=25,
        message=f"'compute' is deprecated: rotate {secret}",
        flag="-Wdeprecated-declarations",
        raw=(
            f"src/config.c:4:25: warning: 'compute' is deprecated: rotate {secret} "
            "[-Wdeprecated-declarations]"
        ),
    )

    kwargs = baseline_dispatch._finding_kwargs(diagnostic, "src/config.c", "AppleClang")

    assert secret not in kwargs["title"]
    assert "postgresql://" not in kwargs["title"]
    assert "user:pass" not in kwargs["title"]
    assert "DATABASE_URL" not in kwargs["title"]
    # The title is still a real, useful title — structured fields only, not empty.
    assert "src/config.c:4" in kwargs["title"]
    assert "-Wdeprecated-declarations" in kwargs["title"]


def test_normalize_file_path_rejects_a_line_directive_escape(tmp_path: Path):
    """SEC-B, fast unit reproduction: the exact escaped path the real PoC produces
    (`#line 1 "/etc/passwd"`). Against the pre-fix `_normalize_file_path` (which
    fell back to `raw_file.lstrip("/")` == `"etc/passwd"` on this exact `ValueError`)
    this assertion fails immediately."""
    from workers.baseline import dispatch as baseline_dispatch

    source_dir = tmp_path / "source"
    source_dir.mkdir()

    assert baseline_dispatch._normalize_file_path("/etc/passwd", source_dir) is None


def test_normalize_file_path_rejects_a_symlink_escape(tmp_path: Path):
    """A symlink planted inside `source_dir` pointing back out to a real host path is
    the same class of escape as a `#line` directive, through a different mechanism —
    `Path.resolve()` follows the symlink to its real target before the `source_dir`
    membership check runs, so this is rejected the same way."""
    from workers.baseline import dispatch as baseline_dispatch

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    real_target = outside / "secret.c"
    real_target.write_text("")
    trap = source_dir / "trap.c"
    trap.symlink_to(real_target)

    assert baseline_dispatch._normalize_file_path(str(trap), source_dir) is None


def test_normalize_file_path_accepts_a_genuine_in_tree_relative_line_target(tmp_path: Path):
    """The legitimate case SEC-B's fix must not break: a `#line` (or any diagnostic)
    reporting a path that is relative but genuinely resolves under `source_dir` —
    e.g. a generated parser re-pointing at the real `.y`/`.l` grammar file it came
    from — is still accepted and still normalized the same way a same-file
    diagnostic would be."""
    from workers.baseline import dispatch as baseline_dispatch

    source_dir = tmp_path / "source"
    (source_dir / "src").mkdir(parents=True)
    (source_dir / "src" / "decode.c").write_text("")

    assert (
        baseline_dispatch._normalize_file_path("src/decode.c", source_dir) == "src/decode.c"
    )


def test_a_line_directive_escaped_diagnostic_is_not_recorded_as_a_finding(mission: Mission):
    """SEC-B, fast unit reproduction of the full `_persist_compiler_diagnostics`
    path: a diagnostic whose reported location escapes `source_dir` must never
    become a `Finding` row (dropping it, not fabricating a mislabeled one, is this
    fix's chosen mechanism — see `_normalize_file_path`'s own docstring for why),
    and the rejection is still visible on the `StageToolRun` row rather than being
    silently invisible."""
    from adapters.cpp.compiler_diagnostics import CompilerDiagnostic
    from contracts.enums import AnalyzerTool
    from missions.models import Finding, StageToolRun
    from workers.baseline import dispatch as baseline_dispatch

    escaped = CompilerDiagnostic(
        severity="warning",
        file="/etc/passwd",
        line=1,
        column=24,
        message="unused parameter 'limit'",
        flag="-Wunused-parameter",
        raw="/etc/passwd:1:24: warning: unused parameter 'limit' [-Wunused-parameter]",
    )
    legitimate = CompilerDiagnostic(
        severity="warning",
        file="/abs/src/config.c",
        line=9,
        column=5,
        message="unused variable 'x'",
        flag="-Wunused-variable",
        raw="src/config.c:9:5: warning: unused variable 'x' [-Wunused-variable]",
    )

    recorded = baseline_dispatch._persist_compiler_diagnostics(
        mission, Path("/abs"), _FakeOutcome((escaped, legitimate)), TRACE
    )

    # Only the diagnostic with a verifiable, in-tree location is recorded.
    assert recorded == 1
    compiler_findings = Finding.objects.filter(
        mission=mission, tool=str(AnalyzerTool.COMPILER_DIAGNOSTIC)
    )
    assert compiler_findings.count() == 1
    assert compiler_findings.get().file_path == "src/config.c"
    # No Finding row anywhere claims to be /etc/passwd or etc/passwd.
    assert not Finding.objects.filter(mission=mission, file_path__icontains="passwd").exists()

    tool_run = StageToolRun.objects.get(mission=mission, stage="BASELINE")
    assert "unverified-location:1" in tool_run.flags
    assert "findings:1" in tool_run.flags


@requires_toolchain
@pytest.mark.slow
def test_a_real_deprecated_attribute_secret_never_reaches_a_finding_title(
    mission: Mission, tmp_path: Path, deprecated_secret_source: Path
):
    """SEC-A, real end-to-end reproduction of cybersecurity's exact PoC: a real
    `cmake --build` compiles `deprecated_secret_source` (a genuine
    `-Wdeprecated-declarations` warning whose message embeds a
    `DATABASE_URL=postgresql://user:pass@host/db`-shaped credential, echoed
    verbatim by the real compiler), and the resulting `Finding.title` — the exact
    field that reaches the exported evidence bundle and the `FINDING_RECORDED` SSE
    event — must never contain it."""
    from missions.models import Finding

    walk_to(mission, MissionState.BASELINE)
    job = _job(mission)
    ctx = _ctx(mission, job, deprecated_secret_source, tmp_path / "workspace")

    result = executor_for(JobKind.BASELINE)(ctx)

    assert result.outcome == JobOutcome.SUCCEEDED
    findings = list(Finding.objects.filter(mission=mission))
    assert findings, "expected at least one real compiler-diagnostic finding"
    for finding in findings:
        assert "postgresql://" not in finding.title
        assert "DATABASE_URL" not in finding.title
        assert "user:pass" not in finding.title
    # The deprecated-declarations diagnostic itself was really recorded (not
    # silently dropped) — its title is just built from structured fields, never the
    # raw message.
    assert any("-Wdeprecated-declarations" in f.title for f in findings)


@requires_toolchain
@pytest.mark.slow
def test_a_real_line_directive_escape_is_not_recorded_as_a_finding(
    mission: Mission, tmp_path: Path, line_directive_escape_source: Path
):
    """SEC-B, real end-to-end reproduction of cybersecurity's exact PoC: a real
    `cmake --build` compiles `line_directive_escape_source` (a genuine
    `#line 1 "/etc/passwd"` redirect), and no `Finding` row anywhere may claim
    `/etc/passwd` (or `etc/passwd`) as its `file_path` — the previous, buggy
    fallback behaviour this fix closes."""
    from missions.models import Finding

    walk_to(mission, MissionState.BASELINE)
    job = _job(mission)
    ctx = _ctx(mission, job, line_directive_escape_source, tmp_path / "workspace")

    result = executor_for(JobKind.BASELINE)(ctx)

    assert result.outcome == JobOutcome.SUCCEEDED
    assert not Finding.objects.filter(mission=mission, file_path__icontains="passwd").exists()


@requires_toolchain
@pytest.mark.slow
def test_a_real_legitimate_line_directive_is_still_recorded(
    mission: Mission, tmp_path: Path, legitimate_line_directive_source: Path
):
    """The non-adversarial case SEC-B's fix must not break, proven end to end: a
    `#line` directive that re-points at a DIFFERENT file which is nonetheless
    genuinely in-tree (`src/decode.c`, standing in for a generated parser's real
    `.y`/`.l` grammar file) must still produce a real `Finding`, normalized to that
    in-tree path — the fix rejects escapes, not `#line` itself."""
    from missions.models import Finding

    walk_to(mission, MissionState.BASELINE)
    job = _job(mission)
    ctx = _ctx(mission, job, legitimate_line_directive_source, tmp_path / "workspace")

    result = executor_for(JobKind.BASELINE)(ctx)

    assert result.outcome == JobOutcome.SUCCEEDED
    findings = list(Finding.objects.filter(mission=mission))
    assert findings, "expected the legitimate #line-redirected diagnostic to be recorded"
    assert any(f.file_path == "src/decode.c" for f in findings)


@requires_toolchain
@pytest.mark.slow
def test_a_failing_test_suite_produces_flaky_and_routes_to_failed(
    mission: Mission, tmp_path: Path, candidate_b_source: Path
):
    walk_to(mission, MissionState.BASELINE)
    job = _job(mission)
    ctx = _ctx(mission, job, candidate_b_source, tmp_path / "workspace")

    result = executor_for(JobKind.BASELINE)(ctx)

    assert result.outcome == JobOutcome.FAILED
    assert result.error_code == ErrorCode.BASELINE_FLAKY
    assert result.result["configure_ok"] is True
    assert result.result["build_ok"] is True
    assert result.result["tests_failed"] == 1

    job.state = JobState.FAILED
    job.result = result.result
    target = transition_policy_for(JobKind.BASELINE)(job, mission)
    assert target is MissionState.FAILED
