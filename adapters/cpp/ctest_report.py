"""Structural CTest result parsing.

The whole point of this module is the sentence in #16's acceptance criteria: *"parses
pass/fail counts structurally, never by scraping a log blob."* CTest gives two structural
sources and this module uses both, cross-checked against each other:

1. ``ctest --output-junit <path>`` — a machine-generated JUnit XML file. Parsed with
   `xml.etree.ElementTree`, never a regex over ``ctest``'s human-readable stdout.
2. ``ctest --show-only=json-v1`` — the enumerated test list *before* anything runs.
   :func:`enumerate_tests` reads it to get the test names and labels CMake actually
   registered, independent of the run's outcome.

:func:`parse_ctest_junit` cross-checks (2) against (1)'s test names and raises
`ToolchainError` on a mismatch — a JUnit file with fewer `<testcase>` elements than CTest
enumerated is what a crashed `ctest` process leaves behind, and that is a truncated report,
not a real 8/8.

Status mapping, verified against synthetic fixtures during development (a passing test, a
failing one with stderr output, one `DISABLED` via `set_tests_properties`, and — the one
that was missing on the first pass and is the reason this note exists — a test CTest could
not locate the executable for):

============  ============================================  ==========================
CTest state    JUnit shape                                   :class:`TestCaseResult.status`
============  ============================================  ==========================
passed         ``status="run"``, no ``<failure>``/``<skipped>`` child  ``"passed"``
failed         ``status="fail"``, has ``<failure>`` child     ``"failed"``
not run        ``status="notrun"``, has ``<skipped>`` child   ``"not_run"``
disabled       ``status="disabled"``                          ``"disabled"``
============  ============================================  ==========================

**The `not_run` row is here because the first version of this parser did not have it.**
Running the parser against a build directory that had been configured but never compiled
produced ``status="notrun"`` / ``<skipped message="Unable to find executable"/>`` for every
test, and the original mapping — "anything without a `<failure>` child is a pass" — read
that as 8 green tests. That is precisely the standing failure mode the brief calls out: a
check that passes by not looking. `test_ctest_report.py::test_notrun_is_not_counted_as_passed`
pins the fix by asserting a `notrun` JUnit fixture reports `all_passed=False`, and would
fail against the original mapping.

Disabled tests are excluded from :attr:`CTestSummary.total` — CTest's own JUnit dump
counts them in ``tests=`` alongside run tests, but a test that never executed is not part
of the denominator #17 exists to protect. It is still visible via
:attr:`CTestSummary.disabled_tests`, so a red vs. "conveniently disabled" baseline is
distinguishable in the report rather than silently identical. `not_run` tests, by contrast,
count against the baseline — see :attr:`CTestSummary.failed`, which folds in both genuine
assertion failures and tests that never ran, because neither is evidence of a pass.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from packages.sandbox import Jail

from .errors import BuildStep, StepFailure, ToolchainError, first_error_line

__all__ = [
    "CTestSummary",
    "TestCaseResult",
    "enumerate_tests",
    "parse_ctest_junit",
    "run_ctest",
]

_KNOWN_STATUSES = frozenset({"passed", "failed", "not_run", "disabled"})


@dataclass(frozen=True, slots=True)
class TestCaseResult:
    """One `<testcase>` element, decoded."""

    name: str
    status: str
    duration_seconds: float
    labels: tuple[str, ...] = ()
    message: str = ""
    output: str = ""

    def __post_init__(self) -> None:
        if self.status not in _KNOWN_STATUSES:
            raise ValueError(
                f"unrecognised CTest status {self.status!r} for test {self.name!r}; "
                f"expected one of {sorted(_KNOWN_STATUSES)}. A status this parser does not "
                "recognise is refused rather than silently counted as a pass."
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "duration_seconds": self.duration_seconds,
            "labels": list(self.labels),
            "message": self.message,
            "output": self.output,
        }


@dataclass(frozen=True, slots=True)
class CTestSummary:
    """The structural result of one `ctest` invocation."""

    tests: tuple[TestCaseResult, ...]
    wall_duration_seconds: float
    junit_path: str

    @property
    def total(self) -> int:
        """Tests CTest was expected to run. Disabled tests are not counted — see module
        docstring. `not_run` tests ARE counted: CTest tried and failed to produce a
        verdict for them, which is a red result, not an absent one."""
        return sum(1 for t in self.tests if t.status != "disabled")

    @property
    def passed(self) -> int:
        return sum(1 for t in self.tests if t.status == "passed")

    @property
    def failed(self) -> int:
        """Assertion failures plus tests that never ran. Both are non-passes; folding
        `not_run` in here is what makes `passed + failed == total` hold without a third
        bucket the `BaselineReport` schema has no field for."""
        return sum(1 for t in self.tests if t.status in ("failed", "not_run"))

    @property
    def not_run_tests(self) -> tuple[str, ...]:
        """Tests CTest could not execute at all — missing binary, crashed fixture, etc.
        A subset of `failed`; broken out because "the binary would not run" and "the
        binary ran and asserted" are different bugs for an operator to chase."""
        return tuple(t.name for t in self.tests if t.status == "not_run")

    @property
    def disabled_tests(self) -> tuple[str, ...]:
        return tuple(t.name for t in self.tests if t.status == "disabled")

    @property
    def failing_tests(self) -> tuple[TestCaseResult, ...]:
        """Both `failed` and `not_run` cases — everything that keeps `all_passed` False."""
        return tuple(t for t in self.tests if t.status in ("failed", "not_run"))

    @property
    def all_passed(self) -> bool:
        """True iff at least one test ran and none failed. Mirrors
        `contracts.schemas.evidence.BaselineReport.passed`'s test-count half."""
        return self.total > 0 and self.failed == 0

    def by_label(self, label: str) -> tuple[TestCaseResult, ...]:
        return tuple(t for t in self.tests if label in t.labels)

    def as_dict(self) -> dict[str, object]:
        return {
            "tests": [t.as_dict() for t in self.tests],
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "disabled_tests": list(self.disabled_tests),
            "wall_duration_seconds": self.wall_duration_seconds,
            "junit_path": self.junit_path,
        }


def enumerate_tests(build_dir: Path, jail: Jail, ctest_path: str) -> tuple[str, ...]:
    """The test names CMake registered, from ``ctest --show-only=json-v1``.

    Used only to cross-check the JUnit file's completeness; the pass/fail verdict never
    comes from here. ``build_dir`` is passed as a jail-relative ``cwd`` — it must resolve
    inside ``jail.root``, which is true for anything `pipeline.run_variant` created.
    """
    result = jail.run([ctest_path, "--show-only=json-v1"], cwd=build_dir)
    if not result.ok:
        raise StepFailure(
            step=BuildStep.TEST_ENUMERATE,
            target=str(build_dir),
            command=result.argv,
            exit_code=result.exit_code,
            first_error=first_error_line(result.stderr, result.stdout),
            timed_out=result.limit_hit.value == "WALL_CLOCK",
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ToolchainError(
            f"ctest --show-only=json-v1 did not produce valid JSON: {exc}"
        ) from exc
    return tuple(entry["name"] for entry in payload.get("tests", []))


def _case_labels(testcase: ET.Element) -> tuple[str, ...]:
    labels: list[str] = []
    for prop in testcase.findall("./properties/property"):
        if prop.get("name") == "cmake_labels":
            value = prop.get("value", "")
            labels.extend(part for part in value.split(";") if part)
    return tuple(labels)


def parse_ctest_junit(
    junit_path: Path, *, expected_tests: tuple[str, ...] | None = None
) -> CTestSummary:
    """Parse a `ctest --output-junit` file into a :class:`CTestSummary`.

    Raises :class:`ToolchainError` when the file is missing, malformed, or — if
    ``expected_tests`` is given — short of what CTest enumerated before the run. A short
    JUnit file is what a crashed `ctest` leaves behind and must not be read as "everything
    not listed passed."
    """
    if not junit_path.is_file():
        raise ToolchainError(f"ctest did not produce a JUnit report at {junit_path}")
    try:
        root = ET.parse(junit_path).getroot()  # noqa: S314 - our own jailed process's output
    except ET.ParseError as exc:
        raise ToolchainError(f"ctest JUnit output at {junit_path} is not valid XML: {exc}") from exc

    cases: list[TestCaseResult] = []
    for testcase in root.findall("testcase"):
        name = testcase.get("name", "")
        status_attr = testcase.get("status", "")
        failure = testcase.find("failure")
        skipped = testcase.find("skipped")
        # Order matters: check every non-passing marker CTest is known to emit before
        # falling through to "passed". `status="run"` with neither child is the only shape
        # that means the test actually executed and asserted nothing.
        if status_attr == "disabled":
            status = "disabled"
        elif failure is not None:
            status = "failed"
        elif status_attr == "notrun" or skipped is not None:
            # CTest could not run the test at all — missing executable (the case that
            # exposed this branch's absence during development), a crashed fixture
            # dependency, or a resource lock. None of those are a pass.
            status = "not_run"
        else:
            status = "passed"
        system_out = testcase.find("system-out")
        message = ""
        if failure is not None:
            message = failure.get("message", "")
        elif skipped is not None:
            message = skipped.get("message", "")
        cases.append(
            TestCaseResult(
                name=name,
                status=status,
                duration_seconds=float(testcase.get("time", "0") or 0.0),
                labels=_case_labels(testcase),
                message=message,
                output=(system_out.text or "") if system_out is not None else "",
            )
        )

    if expected_tests is not None:
        found_names = {c.name for c in cases}
        missing = [name for name in expected_tests if name not in found_names]
        if missing:
            raise ToolchainError(
                f"ctest JUnit report at {junit_path} is missing {len(missing)} test(s) that "
                f"CTest enumerated before the run: {missing}. This is what a crashed or "
                "aborted ctest process leaves behind — treated as an incomplete run, not "
                "as those tests having passed."
            )

    wall = float(root.get("time", "0") or 0.0)
    return CTestSummary(tests=tuple(cases), wall_duration_seconds=wall, junit_path=str(junit_path))


def run_ctest(
    build_dir: Path,
    jail: Jail,
    ctest_path: str,
    *,
    junit_name: str = "ctest-junit.xml",
) -> CTestSummary:
    """Enumerate, run, and structurally parse — the one function the baseline stage calls.

    Does not raise on test failures; a red suite is a valid, fully-parsed
    :class:`CTestSummary`. Raises :class:`StepFailure`/`ToolchainError` only when CTest
    itself could not be made to produce a trustworthy report (crash, timeout, malformed
    output) — a genuinely different failure mode from "the code under test is broken,"
    which is exactly the distinction #16's acceptance criteria draw.

    There is no per-call timeout parameter: `packages.sandbox.Jail`'s wall clock is set
    once, on the `JailPolicy` passed to `Jail.create()`, and applies to every command run
    inside that jail. Give the caller of `pipeline.run_variant` a `JailPolicy` sized for
    "configure + build + ctest, once," not per-step.
    """
    expected = enumerate_tests(build_dir, jail, ctest_path)
    junit_path = build_dir / junit_name
    result = jail.run([ctest_path, "--output-junit", str(junit_path)], cwd=build_dir)
    # A non-zero exit here means "at least one test failed," which CTest signals the same
    # way whether one test failed or the whole binary would not launch. That distinction is
    # exactly what the JUnit file resolves, so exit code is not treated as the verdict —
    # only a timeout (nothing to parse) is.
    if result.limit_hit.value == "WALL_CLOCK":
        raise StepFailure(
            step=BuildStep.TEST_RUN,
            target=str(build_dir),
            command=result.argv,
            exit_code=result.exit_code,
            first_error=first_error_line(result.stderr, result.stdout),
            timed_out=True,
        )
    return parse_ctest_junit(junit_path, expected_tests=expected)
