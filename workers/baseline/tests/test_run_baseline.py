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

    # packages.sandbox.Jail deletes its own scratch directory (and everything CTest wrote
    # into it) the moment run_baseline_stage's `with Jail.create(...)` block closes —
    # which has already happened by the time run_baseline_stage returns. This is the
    # regression test for that: log_ref must point at a real, readable file *after* the
    # call returns, not at a path that quietly no longer exists. Proves the durable-copy
    # step actually ran, rather than trusting the source read.
    assert outcome.log_ref is not None
    log_path = Path(outcome.log_ref)
    assert log_path.is_file(), f"log_ref does not exist on disk: {log_path}"
    assert "<testsuite" in log_path.read_text()

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


def test_a_clean_build_records_no_compiler_diagnostics(
    tmp_path: Path, pktcfg_source: Path
) -> None:
    """#23: `demo/repositories/pktcfg` builds clean today, even with `-Wall -Wextra
    -Wshadow -Wconversion` already on (`CMakeLists.txt`) — verified directly, not
    assumed. Zero real diagnostics is the correct, honest result for this target, not
    a sign the parser is broken; `test_the_build_actually_produced_real_diagnostics`
    below proves the parser positively finds real ones when they exist."""
    outcome = run_baseline_stage("mission-no-warnings", pktcfg_source, tmp_path / "workspace")
    assert outcome.passed is True
    assert outcome.compiler_diagnostics == ()
    assert outcome.compiler_id != "unknown"
    assert outcome.compiler_version != "unknown"


def test_the_build_actually_produced_real_diagnostics(
    tmp_path: Path, warning_producing_source: Path
) -> None:
    """#23, end to end against a REAL build: `run_baseline_stage` runs the real
    `cmake --build` once (the D3 gate's own build, not a second one), and
    `BaselineOutcome.compiler_diagnostics` carries real, structurally parsed
    diagnostics out of it — file:line:severity, not a text blob. The build itself
    still passes (warnings are not `-Werror`); a red baseline is not required to
    observe a real warning."""
    outcome = run_baseline_stage(
        "mission-real-warnings", warning_producing_source, tmp_path / "workspace"
    )
    assert outcome.passed is True  # warnings alone never fail the D3 gate
    assert outcome.compiler_id != "unknown"
    assert outcome.compiler_version != "unknown"

    diagnostics = outcome.compiler_diagnostics
    assert diagnostics, "expected real compiler diagnostics, found none"
    assert all(d.file.endswith("src/config.c") for d in diagnostics)
    assert all(d.severity in ("warning", "error") for d in diagnostics)
    assert all(d.line > 0 for d in diagnostics)

    by_flag = {d.flag: d for d in diagnostics}
    # -Wconversion's exact flag name differs by compiler (clang:
    # -Wimplicit-int-conversion, gcc: -Wconversion) for this specific narrowing —
    # assert on the two flags that are identical across both real toolchains this
    # project builds with (macOS AppleClang locally, gcc in the real Linux worker
    # image), rather than hardcoding one compiler's naming.
    assert "-Wunused-variable" in by_flag
    assert by_flag["-Wunused-variable"].message == "unused variable 'diagnostic_probe_unused'"
    assert any(d.flag and "onversion" in d.flag for d in diagnostics), (
        f"expected a narrowing-conversion warning, got flags: {sorted(by_flag)}"
    )

    # as_dict() round-trips into what workers/baseline/dispatch.py will hand to
    # orchestrator.findings.record_finding — never a raw dataclass past this boundary.
    outcome_dict = outcome.as_dict()
    assert len(outcome_dict["compiler_diagnostics"]) == len(diagnostics)
    assert outcome_dict["compiler_id"] == outcome.compiler_id


def test_mission_id_is_carried_through_to_the_report(tmp_path: Path, pktcfg_source: Path) -> None:
    mission_id = "12345678-1234-1234-1234-123456789abc"
    outcome = run_baseline_stage(mission_id, pktcfg_source, tmp_path / "workspace")
    assert outcome.mission_id == mission_id
    events = emit_baseline_events(outcome)
    assert all(e["mission_id"] == mission_id for e in events)
