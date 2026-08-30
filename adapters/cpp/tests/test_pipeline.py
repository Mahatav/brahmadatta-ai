"""End-to-end pipeline behavior not already covered by test_ctest_report.py /
test_sanitizer.py: the StepFailure paths for a broken configure and a broken build, and
the shape of a successful BuildResult."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from adapters.cpp.detect import BuildSystem, DetectedTarget
from adapters.cpp.errors import BuildStep, StepFailure
from adapters.cpp.pipeline import _configure_argv, run_variant
from adapters.cpp.variants import Variant, spec_for
from packages.sandbox import Jail, JailPolicy


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


# ---------------------------------------------------------------------------------
# #300: `_configure_argv` must emit `-DCMAKE_CXX_FLAGS=` alongside `-DCMAKE_C_FLAGS=`
# for every sanitizer variant, or a C++ target's build is silently unsanitized while
# `configure_ok`/`build_ok` both still report `True`.
# ---------------------------------------------------------------------------------


def test_configure_argv_emits_cmake_cxx_flags_alongside_cmake_c_flags_for_every_sanitizer_variant() -> None:
    """Fast, no-toolchain-needed unit proof of the fix itself: `_configure_argv`'s
    literal output must carry `-DCMAKE_CXX_FLAGS=<flags>` for ASAN/UBSAN/ASAN_UBSAN,
    identical to the existing `-DCMAKE_C_FLAGS=<flags>` entry — not just for pktcfg's C
    sources, which could never surface this since CMake ignores CXX flags with no C++
    sources to apply them to."""
    detected = DetectedTarget(
        build_system=BuildSystem.C_CMAKE_CTEST,
        source_dir=Path("/fake/source"),
        marker=Path("/fake/source/CMakeLists.txt"),
        project_name="fake",
    )
    for variant in (Variant.ASAN, Variant.UBSAN, Variant.ASAN_UBSAN):
        spec = spec_for(variant)
        argv = _configure_argv("cmake", detected, Path("/fake/build"), spec)
        flags = " ".join(spec.sanitizer_flags)
        assert f"-DCMAKE_C_FLAGS={flags}" in argv
        assert f"-DCMAKE_CXX_FLAGS={flags}" in argv, (
            f"{variant}: -DCMAKE_CXX_FLAGS= is missing -- a C++ target under this "
            "variant would silently build unsanitized (#300)"
        )
        assert f"-DCMAKE_EXE_LINKER_FLAGS={flags}" in argv


def test_configure_argv_omits_cxx_flags_for_baseline_with_no_sanitizer_flags() -> None:
    """BASELINE has no `sanitizer_flags` at all -- confirms the fix does not start
    emitting empty/spurious `-DCMAKE_CXX_FLAGS=` entries for a variant that never
    wanted any flags in the first place."""
    detected = DetectedTarget(
        build_system=BuildSystem.C_CMAKE_CTEST,
        source_dir=Path("/fake/source"),
        marker=Path("/fake/source/CMakeLists.txt"),
        project_name="fake",
    )
    argv = _configure_argv("cmake", detected, Path("/fake/build"), spec_for(Variant.BASELINE))
    assert not any(arg.startswith("-DCMAKE_C_FLAGS=") for arg in argv)
    assert not any(arg.startswith("-DCMAKE_CXX_FLAGS=") for arg in argv)


_VERBOSE_CXX_COMPILE_RE = re.compile(r"\bc\+\+.*-c\s+.*\.cpp\b")


@pytest.mark.slow
def test_asan_ubsan_variant_real_cxx_compile_lines_carry_the_sanitizer_flag(
    tmp_path: Path, cxx_target_source: Path
) -> None:
    """#300's own real, hard-evidence regression proof — mirrors the exact method the
    original dogfooding session used against nlohmann/json: build a REAL C++ (not C)
    CMake target under `Variant.ASAN_UBSAN` with `CMAKE_VERBOSE_MAKEFILE=ON`, and
    inspect the REAL captured compile lines from the build log for `-fsanitize=`.

    Before the fix, `_configure_argv` only ever emitted `-DCMAKE_C_FLAGS=...` — CMake
    silently drops a `-D` cache entry with no effect on C++ compilation, so 0 of this
    fixture's real `.cpp` compile lines would carry `-fsanitize=address,undefined`
    while `configure_ok`/`build_ok` both still reported `True`. After the fix, every
    real C++ compile line must carry it.
    """
    spec = spec_for(Variant.ASAN_UBSAN)
    policy = JailPolicy(memory_bytes=spec.min_jail_memory_bytes)
    with Jail.create(policy, parent=tmp_path) as jail:
        result = run_variant(
            cxx_target_source,
            jail,
            Variant.ASAN_UBSAN,
            extra_cache_entries={"CMAKE_VERBOSE_MAKEFILE": "ON"},
        )
        assert result.configure_ok is True
        assert result.build_ok is True

        build_log = result.build.stdout + "\n" + result.build.stderr
        cxx_compile_lines = [
            line for line in build_log.splitlines() if _VERBOSE_CXX_COMPILE_RE.search(line)
        ]
        assert len(cxx_compile_lines) >= 2, (
            "expected at least one real c++ compile line per .cpp translation unit "
            f"(main.cpp, helper.cpp) in the verbose build log; found "
            f"{len(cxx_compile_lines)}. Full build log:\n{build_log}"
        )
        unsanitized = [line for line in cxx_compile_lines if "-fsanitize=address,undefined" not in line]
        assert unsanitized == [], (
            "#300 regression: every real C++ compile line must carry "
            "-fsanitize=address,undefined under Variant.ASAN_UBSAN. Lines missing it:\n"
            + "\n".join(unsanitized)
        )
