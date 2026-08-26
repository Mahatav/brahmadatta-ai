"""`JobKind.ANALYZE`'s executor and transition policy (#22, D-144).

`workers.static_analysis.dispatch` is imported for its registration side effect the
same way `test_fuzz_executor.py` does for `workers.fuzzing.dispatch` — see that
file's own header comment. Mirrors its four-shape structure:

1. Idempotency / cancellation.
2. The sandbox layer: unconfigured image, a genuine `JailError`.
3. Outcome classification: zero matches succeeds with no `Finding`; real matches
   persist a `StageToolRun` and one `Finding` per match, redacted.
4. `TRIAGE -> STRESS_TEST` transition-policy routing, including the infra-failure
   branch to `FAILED`.

`test_a_real_semgrep_scan_end_to_end` (bottom) is opt-in and needs a reachable
docker daemon, mirroring `adapters/semgrep/tests/test_real_scan.py`'s own gate —
this is the same real path, but exercised through the full `JobKind.ANALYZE`
executor rather than `run_semgrep_scan` directly, proving `record_finding`/
`StageToolRun` persistence against a genuine scan, not a mocked one.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest

from adapters.semgrep.parser import SemgrepMatch
from contracts.enums import ErrorCode, MissionState
from missions.models import Finding, Job, JobKind, JobState, Mission, StageToolRun
from orchestrator.executors import ExecutorContext, JobOutcome, executor_for, transition_policy_for
from orchestrator.tests.conftest import NOW, TRACE, walk_to
from packages.sandbox.errors import ContainerUnavailableError
from workers.static_analysis import dispatch
from workers.static_analysis.run import AnalyzeOutcome

pytestmark = pytest.mark.django_db(transaction=True)

PINNED_IMAGE = "brahmadatta-analyze-toolchain@sha256:" + "c" * 64


def _job(mission: Mission, *, state: str = JobState.RUNNING, attempt: int = 1) -> Job:
    return Job.objects.create(
        mission=mission,
        kind=JobKind.ANALYZE,
        state=state,
        attempt=attempt,
        max_attempts=1,
        run_after=NOW,
        deadline_at=NOW + timedelta(minutes=30),
    )


def _ctx(mission: Mission, job: Job, *, cancelled: bool = False, source_dir: Path | None = None) -> ExecutorContext:
    return ExecutorContext(
        job=job,
        mission=mission,
        source_dir=source_dir or Path("/does/not/matter"),
        workspace_root=Path("/does/not/matter/either"),
        trace_id=TRACE,
        cancel_requested=lambda: cancelled,
    )


def _match(
    rule_id: str = "brahmadatta-c-memcpy-review-bounds",
    *,
    category: str = "OTHER",
    severity: str = "LOW",
    line: int = 114,
) -> SemgrepMatch:
    return SemgrepMatch(
        rule_id=rule_id,
        raw_check_id=f"rules.c.{rule_id}",
        file_path="src/parse.c",
        start_line=line,
        end_line=line,
        message="memcpy()/memmove() call. Review bounds.",
        tool_severity="INFO",
        cwe="CWE-787",
        category="security",
        brahmadatta_category=category,
        brahmadatta_severity=severity,
        code_snippet="memcpy(entry->name, name, name_len);",
    )


def _outcome(*, matches: tuple[SemgrepMatch, ...] = (), files_scanned: int = 7) -> AnalyzeOutcome:
    return AnalyzeOutcome(
        mission_id="whatever",
        mode="LIVE_SCAN",
        tool_version="1.173.0",
        ruleset_version="brahmadatta-c-cpp-2026-08-24",
        image_digest=PINNED_IMAGE,
        runtime_seconds=1.5,
        files_scanned=files_scanned,
        matches=matches,
        recorded_at=NOW,
    )


@pytest.fixture(autouse=True)
def _analyze_image(settings):
    settings.SANDBOX_ANALYZE_IMAGE = PINNED_IMAGE


# ---------------------------------------------------------------------------------
# 1. Idempotency / cancellation
# ---------------------------------------------------------------------------------


def test_existing_stage_tool_run_short_circuits_no_double_run(mission: Mission, monkeypatch):
    walk_to(mission, MissionState.TRIAGE)
    StageToolRun.objects.create(
        mission=mission,
        stage="ANALYZE",
        tool_name="semgrep",
        tool_version="1.173.0+ruleset:v1",
        flags=[],
        artifact_refs=[],
    )
    Finding.objects.create(
        mission=mission,
        category="OTHER",
        severity="LOW",
        tool="SEMGREP",
        discovery_method="STATIC_ANALYSIS",
        file_path="src/parse.c",
        line=114,
        fingerprint="semgrep:already-recorded",
        title="already recorded",
        detected_at=NOW,
    )

    def _must_not_run(*args, **kwargs):
        raise AssertionError("run_analyze_stage was called despite an existing StageToolRun")

    monkeypatch.setattr(dispatch, "run_analyze_stage", _must_not_run)

    job = _job(mission)
    result = executor_for(JobKind.ANALYZE)(_ctx(mission, job))

    assert result.outcome == JobOutcome.SUCCEEDED
    assert result.result["already_recorded"] is True
    assert result.result["matches_found"] == 1
    assert StageToolRun.objects.filter(mission=mission).count() == 1


def test_cancel_requested_before_start_short_circuits(mission: Mission, monkeypatch):
    def _must_not_run(*args, **kwargs):
        raise AssertionError("run_analyze_stage was called despite cancel_requested()")

    monkeypatch.setattr(dispatch, "run_analyze_stage", _must_not_run)

    job = _job(mission)
    result = executor_for(JobKind.ANALYZE)(_ctx(mission, job, cancelled=True))

    assert result.outcome == JobOutcome.CANCELLED
    assert StageToolRun.objects.filter(mission=mission).count() == 0


# ---------------------------------------------------------------------------------
# 2. Sandbox layer
# ---------------------------------------------------------------------------------


def test_unconfigured_image_is_an_infra_failure_not_a_crash(mission: Mission, settings, monkeypatch):
    settings.SANDBOX_ANALYZE_IMAGE = ""

    def _must_not_run(*args, **kwargs):
        raise AssertionError("run_analyze_stage was called with no image configured")

    monkeypatch.setattr(dispatch, "run_analyze_stage", _must_not_run)

    job = _job(mission)
    result = executor_for(JobKind.ANALYZE)(_ctx(mission, job))

    assert result.outcome == JobOutcome.FAILED
    assert result.result["infra_failure"] is True
    assert result.error_code == ErrorCode.SANDBOX_UNAVAILABLE
    assert result.retry is False


def test_a_genuine_jail_error_is_an_infra_failure(mission: Mission, monkeypatch):
    def _raise_unavailable(*args, **kwargs):
        raise ContainerUnavailableError("docker daemon did not respond")

    monkeypatch.setattr(dispatch, "run_analyze_stage", _raise_unavailable)

    job = _job(mission)
    result = executor_for(JobKind.ANALYZE)(_ctx(mission, job))

    assert result.outcome == JobOutcome.FAILED
    assert result.result["infra_failure"] is True
    assert result.error_code == ErrorCode.SANDBOX_UNAVAILABLE
    assert result.retry is False  # JobKind.ANALYZE's MAX_ATTEMPTS_BY_KIND is 1


# ---------------------------------------------------------------------------------
# 3. Outcome classification
# ---------------------------------------------------------------------------------


def test_a_not_run_outcome_is_not_an_infra_failure(mission: Mission, monkeypatch):
    outcome = AnalyzeOutcome(
        mission_id="whatever",
        mode="NOT_RUN",
        recorded_at=NOW,
        failure_reason="semgrep reported a scan-level error; see tool_errors",
        tool_errors=("unable to find a config",),
    )
    monkeypatch.setattr(dispatch, "run_analyze_stage", lambda *a, **k: outcome)

    job = _job(mission)
    result = executor_for(JobKind.ANALYZE)(_ctx(mission, job))

    assert result.outcome == JobOutcome.FAILED
    assert result.result["infra_failure"] is False
    assert result.error_code is None
    assert StageToolRun.objects.filter(mission=mission).count() == 0


def test_a_clean_scan_with_no_matches_succeeds_with_no_finding(mission: Mission, monkeypatch):
    outcome = _outcome(matches=())
    monkeypatch.setattr(dispatch, "run_analyze_stage", lambda *a, **k: outcome)

    job = _job(mission)
    result = executor_for(JobKind.ANALYZE)(_ctx(mission, job))

    assert result.outcome == JobOutcome.SUCCEEDED
    assert result.result["matches_found"] == 0
    row = StageToolRun.objects.get(mission=mission)
    assert row.tool_name == "semgrep"
    assert row.stage == "ANALYZE"
    assert "brahmadatta-c-cpp-2026-08-24" in row.tool_version
    assert Finding.objects.filter(mission=mission).count() == 0


def test_real_matches_persist_a_stage_tool_run_and_a_finding_per_match(mission: Mission, monkeypatch):
    outcome = _outcome(
        matches=(
            _match("brahmadatta-c-memcpy-review-bounds", category="OTHER", severity="LOW", line=114),
            _match(
                "brahmadatta-c-malloc-arithmetic-size",
                category="INTEGER_OVERFLOW",
                severity="MEDIUM",
                line=120,
            ),
        )
    )
    monkeypatch.setattr(dispatch, "run_analyze_stage", lambda *a, **k: outcome)

    job = _job(mission)
    result = executor_for(JobKind.ANALYZE)(_ctx(mission, job))

    assert result.outcome == JobOutcome.SUCCEEDED
    assert result.result["matches_found"] == 2

    row = StageToolRun.objects.get(mission=mission)
    assert row.image_digest == "sha256:" + "c" * 64

    findings = list(Finding.objects.filter(mission=mission).order_by("line"))
    assert len(findings) == 2

    memcpy_finding, malloc_finding = findings
    assert memcpy_finding.category == "OTHER"
    assert memcpy_finding.severity == "LOW"
    assert memcpy_finding.tool == "SEMGREP"
    assert memcpy_finding.discovery_method == "STATIC_ANALYSIS"
    assert memcpy_finding.file_path == "src/parse.c"
    assert memcpy_finding.line == 114
    assert memcpy_finding.reproducible is False
    assert "brahmadatta-c-memcpy-review-bounds" in memcpy_finding.title

    assert malloc_finding.category == "INTEGER_OVERFLOW"
    assert malloc_finding.severity == "MEDIUM"
    assert malloc_finding.line == 120


def test_an_unrecognised_category_or_severity_falls_back_safely(mission: Mission, monkeypatch):
    """A future rule with a typo'd `metadata.brahmadatta_category`/`_severity` must
    not crash the whole scan — falls back to OTHER/MEDIUM, same defensive discipline
    `adapters.semgrep.parser._one_match` already applies."""
    outcome = _outcome(matches=(_match(category="NOT_A_REAL_CATEGORY", severity="NOT_A_REAL_SEVERITY"),))
    monkeypatch.setattr(dispatch, "run_analyze_stage", lambda *a, **k: outcome)

    job = _job(mission)
    result = executor_for(JobKind.ANALYZE)(_ctx(mission, job))

    assert result.outcome == JobOutcome.SUCCEEDED
    finding = Finding.objects.get(mission=mission)
    assert finding.category == "OTHER"
    assert finding.severity == "MEDIUM"


def test_a_matchs_code_snippet_is_redacted_before_it_is_stored(mission: Mission, monkeypatch):
    """SEC-48/SEC-50 discipline, applied to Semgrep matches: a matched line
    containing an absolute path or a secret-shaped assignment must not reach
    `Finding.sanitizer_report`/`code_slice` unredacted."""
    poisoned = _match()
    poisoned = SemgrepMatch(
        rule_id=poisoned.rule_id,
        raw_check_id=poisoned.raw_check_id,
        file_path=poisoned.file_path,
        start_line=poisoned.start_line,
        end_line=poisoned.end_line,
        message=poisoned.message,
        tool_severity=poisoned.tool_severity,
        cwe=poisoned.cwe,
        category=poisoned.category,
        brahmadatta_category=poisoned.brahmadatta_category,
        brahmadatta_severity=poisoned.brahmadatta_severity,
        code_snippet=(
            "/* /Users/someone/secret-project/pktcfg/src/parse.c */\n"
            "DATABASE_URL=postgresql://svc_user:hunter2@db.internal:5432/missions\n"
            "memcpy(entry->name, name, name_len);"
        ),
    )
    outcome = _outcome(matches=(poisoned,))
    monkeypatch.setattr(dispatch, "run_analyze_stage", lambda *a, **k: outcome)

    job = _job(mission)
    result = executor_for(JobKind.ANALYZE)(_ctx(mission, job))
    assert result.outcome == JobOutcome.SUCCEEDED

    finding = Finding.objects.get(mission=mission)
    assert "/Users/someone/secret-project" not in finding.sanitizer_report
    assert "/Users/someone/secret-project" not in finding.code_slice
    assert "DATABASE_URL=postgresql://" not in finding.sanitizer_report
    assert "hunter2" not in finding.sanitizer_report
    assert "hunter2" not in finding.code_slice
    # Still useful: the real, non-secret matched line survives.
    assert "memcpy(entry->name, name, name_len)" in finding.code_slice


def test_re_running_a_completed_scan_does_not_duplicate_findings(mission: Mission, monkeypatch):
    outcome = _outcome(matches=(_match(),))
    monkeypatch.setattr(dispatch, "run_analyze_stage", lambda *a, **k: outcome)

    job = _job(mission)
    executor_for(JobKind.ANALYZE)(_ctx(mission, job))
    assert Finding.objects.filter(mission=mission).count() == 1
    assert StageToolRun.objects.filter(mission=mission).count() == 1

    def _must_not_run_again(*args, **kwargs):
        raise AssertionError("run_analyze_stage was called despite an existing StageToolRun")

    monkeypatch.setattr(dispatch, "run_analyze_stage", _must_not_run_again)

    result2 = executor_for(JobKind.ANALYZE)(_ctx(mission, job))
    assert result2.outcome == JobOutcome.SUCCEEDED
    assert Finding.objects.filter(mission=mission).count() == 1
    assert StageToolRun.objects.filter(mission=mission).count() == 1


# ---------------------------------------------------------------------------------
# 4. Transition policy: TRIAGE -> STRESS_TEST, and the infra-failure branch
# ---------------------------------------------------------------------------------


def test_transition_policy_routes_a_successful_scan_to_stress_test(mission: Mission):
    job = Job(kind=JobKind.ANALYZE, state=JobState.SUCCEEDED, result={"infra_failure": False, "matches_found": 2})
    assert transition_policy_for(JobKind.ANALYZE)(job, mission) == MissionState.STRESS_TEST


def test_transition_policy_routes_a_scan_level_failure_to_stress_test_not_failed(mission: Mission):
    """Mirrors `_fuzz_transition_policy`'s own reasoning: a non-infra failure (bad
    ruleset, semgrep internal error) still lets the mission continue — CORRELATE (via
    STRESS_TEST here) is where "nothing useful came back" is judged, not this policy."""
    job = Job(kind=JobKind.ANALYZE, state=JobState.FAILED, result={"infra_failure": False})
    assert transition_policy_for(JobKind.ANALYZE)(job, mission) == MissionState.STRESS_TEST


def test_transition_policy_routes_an_infra_failure_to_failed(mission: Mission):
    job = Job(kind=JobKind.ANALYZE, state=JobState.FAILED, result={"infra_failure": True})
    assert transition_policy_for(JobKind.ANALYZE)(job, mission) == MissionState.FAILED


# ---------------------------------------------------------------------------------
# 5. Real, live, opt-in end-to-end run — mirrors adapters/semgrep/tests/
# test_real_scan.py's own gate, but through the full JobKind.ANALYZE executor.
# ---------------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[4]
BUILD_SCRIPT = REPO_ROOT / "infrastructure" / "scripts" / "build-analyze-image.sh"
PKTCFG_SOURCE = REPO_ROOT / "demo" / "repositories" / "pktcfg"

HAS_DOCKER = shutil.which("docker") is not None and (
    subprocess.run(["docker", "info"], capture_output=True, timeout=10).returncode == 0
    if shutil.which("docker")
    else False
)
OPTED_IN = os.environ.get("BRAHMADATTA_RUN_REAL_ANALYZE_SCAN") == "1"

needs_real_analyze_run = pytest.mark.skipif(
    not (HAS_DOCKER and OPTED_IN),
    reason=(
        "real Semgrep-scan executor test skipped: needs a reachable docker daemon AND "
        f"BRAHMADATTA_RUN_REAL_ANALYZE_SCAN=1. HAS_DOCKER={HAS_DOCKER} OPTED_IN={OPTED_IN}."
    ),
)


@needs_real_analyze_run
def test_a_real_semgrep_scan_end_to_end(mission: Mission, settings):
    result = subprocess.run([str(BUILD_SCRIPT)], capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stderr
    digest = result.stdout.strip().splitlines()[-1]
    assert "@sha256:" in digest
    settings.SANDBOX_ANALYZE_IMAGE = digest

    job = _job(mission)
    outcome_result = executor_for(JobKind.ANALYZE)(_ctx(mission, job, source_dir=PKTCFG_SOURCE))

    assert outcome_result.outcome == JobOutcome.SUCCEEDED, outcome_result.detail
    assert outcome_result.result["matches_found"] == 2

    findings = {f.file_path: f for f in Finding.objects.filter(mission=mission)}
    assert "src/parse.c" in findings
    row = StageToolRun.objects.get(mission=mission)
    assert row.tool_version.startswith("1.173.0")
    assert row.image_digest == "sha256:" + digest.rsplit("@sha256:", 1)[1]
