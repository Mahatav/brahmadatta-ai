"""Structural CTest parsing, including the regression this module's docstring describes:
a `notrun`/`<skipped>` test being silently counted as a pass."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from adapters.cpp.ctest_report import parse_ctest_junit
from adapters.cpp.errors import ToolchainError
from adapters.cpp.jail import Jail
from adapters.cpp.pipeline import run_variant
from adapters.cpp.variants import Variant

# A real `ctest --output-junit` fixture for a build that was configured but never
# compiled — every test is `status="notrun"` with a `<skipped>` child. This is the exact
# shape captured from a real `ctest` run against an uncompiled pktcfg build directory
# during development of this module (see adapters/cpp/ctest_report.py's module docstring).
_NOTRUN_JUNIT = dedent(
    """\
    <?xml version="1.0" encoding="UTF-8"?>
    <testsuite name="(empty)" tests="2" failures="0" disabled="0" skipped="2" time="0">
      <testcase name="test_header" classname="test_header" time="0" status="notrun">
        <skipped message="Unable to find executable"/>
        <properties/>
        <system-out>Unable to find executable: /build/test_header</system-out>
      </testcase>
      <testcase name="test_entries" classname="test_entries" time="0" status="notrun">
        <skipped message="Unable to find executable"/>
        <properties/>
        <system-out>Unable to find executable: /build/test_entries</system-out>
      </testcase>
    </testsuite>
    """
)

_MIXED_JUNIT = dedent(
    """\
    <?xml version="1.0" encoding="UTF-8"?>
    <testsuite name="(empty)" tests="3" failures="1" disabled="1" time="1">
      <testcase name="t_ok" classname="t_ok" time="0.2" status="run">
        <properties/>
        <system-out></system-out>
      </testcase>
      <testcase name="t_bad" classname="t_bad" time="0.25" status="fail">
        <failure message="Failed"/>
        <properties/>
        <system-out>boom: assertion failed</system-out>
      </testcase>
      <testcase name="t_skip" classname="t_skip" time="0" status="disabled">
        <properties><property name="cmake_labels" value="asymmetry"/></properties>
        <system-out>Disabled</system-out>
      </testcase>
    </testsuite>
    """
)


def test_notrun_is_not_counted_as_passed(tmp_path: Path) -> None:
    """The regression test for the bug this parser shipped with during development: the
    first version of `parse_ctest_junit` treated 'no <failure> child' as 'passed', which
    read an unbuilt tree's `status="notrun"` tests as a green 8/8. Reverting the status
    logic in `adapters/cpp/ctest_report.py` to `else: status = "passed"` (dropping the
    `notrun`/`<skipped>` branch) makes this fail — confirmed by hand while writing it.
    """
    junit_path = tmp_path / "notrun.xml"
    junit_path.write_text(_NOTRUN_JUNIT)
    summary = parse_ctest_junit(junit_path)
    assert summary.all_passed is False
    assert summary.passed == 0
    assert summary.failed == 2
    assert set(summary.not_run_tests) == {"test_header", "test_entries"}


def test_mixed_pass_fail_disabled(tmp_path: Path) -> None:
    junit_path = tmp_path / "mixed.xml"
    junit_path.write_text(_MIXED_JUNIT)
    summary = parse_ctest_junit(junit_path)
    assert summary.total == 2  # t_skip (disabled) excluded
    assert summary.passed == 1
    assert summary.failed == 1
    assert summary.disabled_tests == ("t_skip",)
    assert summary.all_passed is False
    failing = summary.failing_tests
    assert len(failing) == 1
    assert failing[0].name == "t_bad"
    assert "assertion failed" in failing[0].output
    assert summary.by_label("asymmetry")[0].name == "t_skip"


def test_an_unknown_status_is_refused_not_silently_passed() -> None:
    """Injected violation: a status this parser has never seen. Must raise, not default
    to 'passed' the way the pre-fix code effectively did for `notrun`."""
    from adapters.cpp.ctest_report import TestCaseResult

    with pytest.raises(ValueError, match="unrecognised CTest status"):
        TestCaseResult(name="x", status="something-new-and-unhandled", duration_seconds=0.0)


def test_missing_junit_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ToolchainError, match="did not produce"):
        parse_ctest_junit(tmp_path / "does-not-exist.xml")


def test_malformed_xml_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.xml"
    bad.write_text("<not-valid-xml")
    with pytest.raises(ToolchainError, match="not valid XML"):
        parse_ctest_junit(bad)


def test_a_short_junit_file_is_rejected_against_the_enumeration(tmp_path: Path) -> None:
    """Injected violation: CTest enumerated 3 tests but the JUnit file only has 2 — what a
    crashed `ctest` process leaves behind. Must not be read as '2 tests, both fine.'"""
    junit_path = tmp_path / "short.xml"
    junit_path.write_text(_MIXED_JUNIT)  # has t_ok, t_bad, t_skip = 3 names
    # Ask for a 4th name that is not in the file.
    with pytest.raises(ToolchainError, match="missing"):
        parse_ctest_junit(
            junit_path, expected_tests=("t_ok", "t_bad", "t_skip", "t_never_enumerated")
        )


@pytest.mark.slow
def test_pktcfg_baseline_is_really_eight_of_eight(tmp_path: Path, pktcfg_source: Path) -> None:
    """End-to-end: real cmake configure + build + ctest against the real target."""
    jail = Jail(tmp_path)
    result = run_variant(pktcfg_source, jail, Variant.BASELINE)
    assert result.ctest.total == 8
    assert result.ctest.passed == 8
    assert result.ctest.failed == 0
    assert result.ctest.all_passed is True
    assert {t.name for t in result.ctest.tests} == {
        "test_header",
        "test_entries",
        "test_escapes",
        "test_tab_expansion",
        "test_truncation",
        "test_limits",
        "test_lookup",
        "test_fuzz_entry",
    }
    assert result.ctest.by_label("asymmetry")[0].name == "test_tab_expansion"


@pytest.mark.slow
def test_candidate_b_produces_the_documented_seven_of_eight(
    tmp_path: Path, candidate_b_source: Path
) -> None:
    """The asymmetry the whole demo depends on: the crash-only patch eliminates the
    defect but breaks `test_tab_expansion`, dropping the count from 8/8 to 7/8. This test
    proves the structural parser reports that drop — not the target's own build, which is
    proven by `demo/repositories/pktcfg`'s own CTest suite and is out of scope for this
    adapter's tests (standing prohibition, #41: never make the target's baseline red)."""
    jail = Jail(tmp_path)
    result = run_variant(candidate_b_source, jail, Variant.BASELINE)
    assert result.ctest.total == 8
    assert result.ctest.passed == 7
    assert result.ctest.failed == 1
    failing_names = {t.name for t in result.ctest.failing_tests}
    assert failing_names == {"test_tab_expansion"}


@pytest.mark.slow
def test_candidate_a_preserves_all_eight(tmp_path: Path, candidate_a_source: Path) -> None:
    """The correct fix: crash gone, all 8 tests still pass."""
    jail = Jail(tmp_path)
    result = run_variant(candidate_a_source, jail, Variant.BASELINE)
    assert result.ctest.total == 8
    assert result.ctest.passed == 8
    assert result.ctest.failed == 0
