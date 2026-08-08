"""The baseline stage, including a direct rehearsal of the D3 gate: cold start with an
empty workspace, reach `BASELINE_PASSED` carrying real ctest counts, twice consecutively.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from workers.baseline.run import emit_baseline_events, run_baseline_stage

pytestmark = pytest.mark.slow


def test_green_baseline_reaches_baseline_passed_with_real_counts(
    tmp_path: Path, pktcfg_source: Path
) -> None:
    outcome = run_baseline_stage("mission-green", pktcfg_source, tmp_path / "workspace")
    assert outcome.passed is True
    assert outcome.configure_ok is True
    assert outcome.build_ok is True
    assert outcome.tests_total == 8
    assert outcome.tests_passed == 8
    assert outcome.tests_failed == 0
    assert outcome.failure is None
    assert outcome.snapshot.snapshot_sha256

    events = emit_baseline_events(outcome)
    assert [e["type"] for e in events] == ["BASELINE_RECORDED", "BASELINE_PASSED"]
    assert events[1]["payload"]["report"]["tests_passed"] == 8
    assert events[1]["status"] == "COMPLETED"


def test_the_d3_gate_reproduces_twice_consecutively(tmp_path: Path, pktcfg_source: Path) -> None:
    """The literal D3 rehearsal: cold start (an empty, never-used workspace directory) to
    BASELINE_PASSED, inside a generous ceiling, run twice back to back. Two separate
    workspaces stand in for two separate mission runs against the same immutable input."""
    deadline_seconds = 900  # 15 minutes, the D3 gate's stated ceiling
    results = []
    for i in range(2):
        started = time.monotonic()
        outcome = run_baseline_stage(f"mission-gate-{i}", pktcfg_source, tmp_path / f"cold-{i}")
        elapsed = time.monotonic() - started
        events = emit_baseline_events(outcome)
        assert elapsed < deadline_seconds, (
            f"run {i} took {elapsed:.1f}s, over the {deadline_seconds}s D3 ceiling"
        )
        assert events[1]["type"] == "BASELINE_PASSED", f"run {i} did not reach BASELINE_PASSED"
        results.append(outcome)

    # Reproduced, not just repeated: identical snapshot and identical counts both times.
    assert results[0].snapshot.snapshot_sha256 == results[1].snapshot.snapshot_sha256
    assert results[0].tests_passed == results[1].tests_passed == 8
    assert results[0].tests_total == results[1].tests_total == 8


def test_a_red_baseline_from_a_build_failure_is_recorded_not_hidden(
    tmp_path: Path, broken_configure_source: Path
) -> None:
    """Injected violation: a CMakeLists.txt that cannot configure. The stage must not
    raise past this function (role file rule 2: 'A baseline that was never green is a
    finding, not a blocker to hide') and must not report passed=True."""
    outcome = run_baseline_stage(
        "mission-red-build", broken_configure_source, tmp_path / "workspace"
    )
    assert outcome.passed is False
    assert outcome.configure_ok is False
    assert outcome.tests_total == 0
    assert outcome.failure is not None
    assert outcome.failure.step == "CONFIGURE"
    assert outcome.failure.first_error

    events = emit_baseline_events(outcome)
    assert events[1]["type"] == "BASELINE_FAILED"
    assert events[1]["severity"] == "ERROR"
    assert "CONFIGURE" in events[1]["message"]


def test_a_red_baseline_from_a_failing_test_is_recorded_not_hidden(
    tmp_path: Path, candidate_b_source: Path
) -> None:
    """Injected violation: the rejected crash-only patch, which is documented to drop
    test_tab_expansion. configure_ok and build_ok are True here — the build itself is
    fine — only the test count is red, and that must still produce BASELINE_FAILED."""
    outcome = run_baseline_stage("mission-red-tests", candidate_b_source, tmp_path / "workspace")
    assert outcome.passed is False
    assert outcome.configure_ok is True
    assert outcome.build_ok is True
    assert outcome.tests_total == 8
    assert outcome.tests_passed == 7
    assert outcome.tests_failed == 1
    assert outcome.failure is None  # the pipeline itself did not fail — the suite did

    events = emit_baseline_events(outcome)
    assert events[1]["type"] == "BASELINE_FAILED"
    assert "7" in events[0]["message"] or "1" in events[1]["message"]


def test_mission_id_is_carried_through_to_the_report(tmp_path: Path, pktcfg_source: Path) -> None:
    mission_id = "12345678-1234-1234-1234-123456789abc"
    outcome = run_baseline_stage(mission_id, pktcfg_source, tmp_path / "workspace")
    assert outcome.mission_id == mission_id
    events = emit_baseline_events(outcome)
    assert all(e["mission_id"] == mission_id for e in events)
