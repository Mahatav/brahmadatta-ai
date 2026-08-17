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
