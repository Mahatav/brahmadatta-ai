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
