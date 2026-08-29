"""#290 regression, at the `run_baseline_stage` level: BASELINE has an escape hatch
for extra CMake `-D` cache flags a real, pre-2021 CMake target needs.

Reproduces the exact finding this issue reports — Magma's libpng target's own
`cmake_minimum_required(VERSION 3.1)` is rejected outright by CMake >= 4.0 unless
`-DCMAKE_POLICY_VERSION_MINIMUM=3.5` is also passed — using `pre_cmake_policy_floor_
source` (a real `cmake_minimum_required(VERSION 3.1)`, confirmed against the CMake
installed in this environment to genuinely fail without the flag) rather than a
mocked CMake error. Matches this codebase's "a red baseline is a valid, complete
result, never silently passed" discipline: the negative case must still be a full,
correctly-classified `BaselineOutcome`, not just "doesn't crash".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from workers.baseline.run import emit_baseline_events, run_baseline_stage

pytestmark = pytest.mark.slow


def test_extra_cmake_args_lets_a_pre_cmake_3_5_target_reach_baseline_passed(
    tmp_path: Path, pre_cmake_policy_floor_source: Path
) -> None:
    outcome = run_baseline_stage(
        "mission-libpng-style",
        pre_cmake_policy_floor_source,
        tmp_path / "workspace",
        extra_cmake_args={"CMAKE_POLICY_VERSION_MINIMUM": "3.5"},
    )
    assert outcome.configure_ok is True
    assert outcome.build_ok is True
    assert outcome.tests_total == 8
    assert outcome.tests_failed == 0
    assert outcome.passed is True
    assert outcome.failure is None

    events = emit_baseline_events(outcome)
    assert [e["type"] for e in events] == ["BASELINE_RECORDED", "BASELINE_PASSED"]


def test_omitting_extra_cmake_args_still_fails_clearly_not_silently(
    tmp_path: Path, pre_cmake_policy_floor_source: Path
) -> None:
    """The other half of the regression: without the escape hatch, the exact same
    target is recorded as a real, fully-classified red baseline — CONFIGURE failed,
    zero tests attempted, a populated `failure` detail — never a pass and never an
    unhandled exception escaping `run_baseline_stage`."""
    outcome = run_baseline_stage(
        "mission-libpng-style-no-flag",
        pre_cmake_policy_floor_source,
        tmp_path / "workspace",
    )
    assert outcome.passed is False
    assert outcome.configure_ok is False
    assert outcome.build_ok is False
    assert outcome.tests_total == 0
    assert outcome.failure is not None
    assert outcome.failure.step == "CONFIGURE"
    assert outcome.failure.first_error
    assert "3.5" in outcome.failure.detail

    events = emit_baseline_events(outcome)
    assert events[1]["type"] == "BASELINE_FAILED"
    assert events[1]["severity"] == "ERROR"
    assert "CONFIGURE" in events[1]["message"]


def test_extra_cmake_args_defaults_to_none_and_does_not_affect_pktcfg(
    tmp_path: Path, pktcfg_source: Path
) -> None:
    """pktcfg's own behavior (#290's own stated regression bar) is unaffected when no
    caller passes `extra_cmake_args` at all — the pre-#290 call shape still works."""
    outcome = run_baseline_stage("mission-pktcfg-unaffected", pktcfg_source, tmp_path / "workspace")
    assert outcome.passed is True
    assert outcome.tests_total == 8
    assert outcome.tests_passed == 8
