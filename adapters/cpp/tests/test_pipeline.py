"""End-to-end pipeline behavior not already covered by test_ctest_report.py /
test_sanitizer.py: the StepFailure paths for a broken configure and a broken build, and
the shape of a successful BuildResult."""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.cpp.errors import BuildStep, StepFailure
from adapters.cpp.pipeline import run_variant
from adapters.cpp.variants import Variant
from packages.sandbox import Jail


@pytest.mark.slow
def test_a_broken_cmakelists_raises_a_configure_step_failure(
    tmp_path: Path, broken_configure_source: Path
) -> None:
    """Injected violation: CMakeLists.txt that cannot parse. Every field #16's acceptance
    criteria name must be present and correct: step, target, command, exit code, first
    error line."""
    with Jail.create(parent=tmp_path) as jail:
        with pytest.raises(StepFailure) as excinfo:
            run_variant(broken_configure_source, jail, Variant.BASELINE)
    exc = excinfo.value
    assert exc.step is BuildStep.CONFIGURE
    assert exc.target == "pktcfg"
    assert exc.command[0].endswith("cmake")
    assert exc.exit_code != 0
    assert exc.first_error, "first_error must not be empty"
    assert "CMake Error" in exc.first_error
    # No durable log path with packages.sandbox.Jail (its scratch dir is gone by the time
    # this assertion runs) — `detail` carries the captured stderr tail instead.
    assert exc.detail, "detail must carry the captured stderr since there is no log_path"


@pytest.mark.slow
def test_a_broken_source_file_raises_a_build_step_failure(
    tmp_path: Path, broken_compile_source: Path
) -> None:
    """Injected violation: a source file that configures fine but will not compile."""
    with Jail.create(parent=tmp_path) as jail:
        with pytest.raises(StepFailure) as excinfo:
            run_variant(broken_compile_source, jail, Variant.BASELINE)
    exc = excinfo.value
    assert exc.step is BuildStep.BUILD
    assert exc.exit_code != 0
    assert exc.first_error


@pytest.mark.slow
def test_a_successful_build_result_has_the_expected_shape(
    tmp_path: Path, pktcfg_source: Path
) -> None:
    with Jail.create(parent=tmp_path) as jail:
        result = run_variant(pktcfg_source, jail, Variant.BASELINE)
        assert result.configure_ok is True
        assert result.build_ok is True
        assert result.duration_seconds > 0
        assert result.toolchain.compiler_id
        assert result.toolchain.compiler_version
        as_dict = result.as_dict()
        assert as_dict["variant"] == "BASELINE"
        ctest_dict = as_dict["ctest"]
        assert isinstance(ctest_dict, dict)
        assert ctest_dict["passed"] == 8


@pytest.mark.slow
def test_a_pre_cmake_3_5_target_fails_configure_without_the_escape_hatch(
    tmp_path: Path, pre_cmake_policy_floor_source: Path
) -> None:
    """#290 regression: without `extra_cache_entries`, a real, pre-2021-style CMake
    target (`cmake_minimum_required(VERSION 3.1)`, mirroring libpng) fails CONFIGURE
    outright on CMake >= 4.0 — clearly, as a `StepFailure`, never silently passed."""
    with Jail.create(parent=tmp_path) as jail:
        with pytest.raises(StepFailure) as excinfo:
            run_variant(pre_cmake_policy_floor_source, jail, Variant.BASELINE)
    exc = excinfo.value
    assert exc.step is BuildStep.CONFIGURE
    assert exc.exit_code != 0
    assert "CMake Error" in exc.first_error
    # CMake's own hint text ("Or, add -DCMAKE_POLICY_VERSION_MINIMUM=3.5 to try
    # configuring anyway.") is multi-line and lands in the captured stderr tail
    # (`detail`), not the single-line `first_error` — confirmed against the real
    # cmake binary in this environment before writing this assertion.
    assert "3.5" in exc.detail, (
        "expected CMake's own 'Compatibility with CMake < 3.5' / "
        "'-DCMAKE_POLICY_VERSION_MINIMUM=3.5' text in the captured stderr tail"
    )


@pytest.mark.slow
def test_a_pre_cmake_3_5_target_configures_and_builds_with_the_escape_hatch(
    tmp_path: Path, pre_cmake_policy_floor_source: Path
) -> None:
    """#290 regression, the other half: the identical target configures and builds
    cleanly once the operator supplies `-DCMAKE_POLICY_VERSION_MINIMUM=3.5` through
    `extra_cache_entries` — proving the escape hatch actually reaches CMake's
    configure invocation, not just that it is accepted as a parameter."""
    with Jail.create(parent=tmp_path) as jail:
        result = run_variant(
            pre_cmake_policy_floor_source,
            jail,
            Variant.BASELINE,
            extra_cache_entries={"CMAKE_POLICY_VERSION_MINIMUM": "3.5"},
        )
    assert result.configure_ok is True
    assert result.build_ok is True
    assert result.ctest.total == 8
    assert result.ctest.passed == 8
