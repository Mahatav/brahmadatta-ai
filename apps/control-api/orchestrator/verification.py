"""Fresh-worktree deterministic verification for patch candidates (#38).

The verifier deliberately accepts a raw diff, never a persisted ``PatchCandidate``.
That keeps provenance, model name, confidence and rationale out of the verification
path: deterministic gates produce a ``GateMatrix`` and ``derive_verdict`` remains the
only verdict reducer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence

from contracts.enums import EvidenceSource, GateName, GateStatus
from contracts.verdict import GateMatrix, GateResult


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def output(self) -> str:
        return "\n".join(part for part in (self.stdout, self.stderr) if part)


CommandRunner = Callable[[Sequence[str], Path, str | None, int], CommandResult]


@dataclass(frozen=True)
class VerificationBaseline:
    """Deterministic checks expected for a CMake/CTest target."""

    build_dir: str = ".brahmadatta-verify-build"
    configure_args: tuple[str, ...] = (
        "-DPKTCFG_SANITIZE=ON",
        "-DPKTCFG_WERROR=ON",
    )
    reproducer_repeats: int = 1
    expected_regression_tests: int | None = None
    timeout_seconds: int = 120
    ignored_names: tuple[str, ...] = (
        ".git",
        ".brahmadatta-verify-build",
        "build",
        "cmake-build-debug",
        "cmake-build-release",
    )


def run_verification(
    worktree: Path,
    candidate_diff: str,
    reproducer: Path,
    baseline: VerificationBaseline | None = None,
    *,
    runner: CommandRunner | None = None,
) -> GateMatrix:
    """Apply ``candidate_diff`` in a fresh worktree and return deterministic gates.

    No ``PatchCandidate`` object is accepted here. Callers may record provenance in
    evidence, but the verifier cannot see it and therefore cannot use it.
    """

    baseline = baseline or VerificationBaseline()
    command_runner = runner or _subprocess_runner
    source = Path(worktree).resolve()
    if not source.exists() or not source.is_dir():
        raise ValueError(
            f"verification source does not exist or is not a directory: {source}"
        )

    with tempfile.TemporaryDirectory(prefix="brahmadatta-verify-") as temp:
        verify_root = Path(temp) / source.name
        _copy_source_tree(source, verify_root, baseline.ignored_names)

        apply_result = command_runner(
            ["git", "apply", "--whitespace=nowarn", "-"],
            verify_root,
            candidate_diff,
            baseline.timeout_seconds,
        )
        if not apply_result.ok:
            return _matrix(
                compile_=_fail(GateName.COMPILE, "git apply", apply_result),
                reproducer=_not_run(
                    GateName.REPRODUCER_ELIMINATED,
                    "Not run: candidate diff did not apply in the fresh worktree.",
                ),
                regression=_not_run(
                    GateName.REGRESSION_PRESERVED,
                    "Not run: candidate diff did not apply in the fresh worktree.",
                ),
            )

        build_dir = verify_root / baseline.build_dir
        configure_result = command_runner(
            ["cmake", "-S", ".", "-B", baseline.build_dir, *baseline.configure_args],
            verify_root,
            None,
            baseline.timeout_seconds,
        )
        if not configure_result.ok:
            return _matrix(
                compile_=_fail(GateName.COMPILE, "cmake configure", configure_result),
                reproducer=_not_run(
                    GateName.REPRODUCER_ELIMINATED,
                    "Not run: configure failed before a replay binary existed.",
                ),
                regression=_not_run(
                    GateName.REGRESSION_PRESERVED,
                    "Not run: configure failed before the regression suite existed.",
                ),
            )

        build_result = command_runner(
            ["cmake", "--build", baseline.build_dir],
            verify_root,
            None,
            baseline.timeout_seconds,
        )
        if not build_result.ok:
            return _matrix(
                compile_=_fail(GateName.COMPILE, "cmake build", build_result),
                reproducer=_not_run(
                    GateName.REPRODUCER_ELIMINATED,
                    "Not run: build failed before a replay binary existed.",
                ),
                regression=_not_run(
                    GateName.REGRESSION_PRESERVED,
                    "Not run: build failed before the regression suite could run.",
                ),
            )

        compile_gate = _pass(GateName.COMPILE, "cmake")
        reproducer_gate = _run_reproducer(
            command_runner,
            verify_root,
            build_dir,
            Path(reproducer).resolve(),
            baseline,
        )
        regression_gate = _run_regressions(command_runner, verify_root, baseline)
        return _matrix(
            compile_=compile_gate,
            reproducer=reproducer_gate,
            regression=regression_gate,
        )


def _copy_source_tree(
    source: Path,
    destination: Path,
    ignored_names: tuple[str, ...],
) -> None:
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns(*ignored_names),
    )


def _run_reproducer(
    runner: CommandRunner,
    verify_root: Path,
    build_dir: Path,
    reproducer: Path,
    baseline: VerificationBaseline,
) -> GateResult:
    if not reproducer.exists():
        return _not_run(
            GateName.REPRODUCER_ELIMINATED,
            f"Not run: reproducer file is missing: {reproducer}",
        )

    replay_binary = build_dir / "pktcfg_replay"
    if not replay_binary.exists():
        return _not_run(
            GateName.REPRODUCER_ELIMINATED,
            "Not run: pktcfg_replay was not produced by the build.",
        )

    result = runner(
        [str(replay_binary), str(reproducer), str(baseline.reproducer_repeats)],
        verify_root,
        None,
        baseline.timeout_seconds,
    )
    if result.ok:
        return _pass(
            GateName.REPRODUCER_ELIMINATED,
            "pktcfg_replay",
            "Crash reproducer replay completed without a sanitizer fault.",
        )
    return _fail(
        GateName.REPRODUCER_ELIMINATED,
        "pktcfg_replay",
        result,
        "Crash reproducer still faults after the candidate patch.",
    )


def _run_regressions(
    runner: CommandRunner,
    verify_root: Path,
    baseline: VerificationBaseline,
) -> GateResult:
    result = runner(
        ["ctest", "--test-dir", baseline.build_dir, "--output-on-failure"],
        verify_root,
        None,
        baseline.timeout_seconds,
    )
    total = _ctest_total(result.output)
    if (
        result.ok
        and baseline.expected_regression_tests is not None
        and total is not None
        and total < baseline.expected_regression_tests
    ):
        return GateResult(
            name=GateName.REGRESSION_PRESERVED,
            status=GateStatus.FAIL,
            evidence_source=EvidenceSource.TOOL_EXECUTION,
            tool="ctest",
            detail=(
                "Regression coverage dropped: "
                f"ran {total}/{baseline.expected_regression_tests} expected tests."
            ),
        )

    if result.ok:
        detail = "Regression suite passed."
        if total is not None:
            detail = f"Regression suite passed: {total} tests ran."
        return _pass(GateName.REGRESSION_PRESERVED, "ctest", detail)

    return _fail(
        GateName.REGRESSION_PRESERVED,
        "ctest",
        result,
        "Regression suite failed or a new fault appeared.",
    )


def _subprocess_runner(
    argv: Sequence[str],
    cwd: Path,
    stdin: str | None,
    timeout_seconds: int,
) -> CommandResult:
    try:
        completed = subprocess.run(
            list(argv),
            cwd=cwd,
            input=stdin,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            argv=tuple(argv),
            returncode=124,
            stdout=exc.stdout or "",
            stderr=(exc.stderr or "") + "\ncommand timed out",
        )
    except OSError as exc:
        return CommandResult(argv=tuple(argv), returncode=127, stderr=str(exc))

    return CommandResult(
        argv=tuple(argv),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _matrix(
    *,
    compile_: GateResult,
    reproducer: GateResult,
    regression: GateResult,
) -> GateMatrix:
    return GateMatrix(
        compile=compile_,
        reproducer_eliminated=reproducer,
        regression_preserved=regression,
    )


def _pass(name: GateName, tool: str, detail: str = "") -> GateResult:
    return GateResult(
        name=name,
        status=GateStatus.PASS,
        evidence_source=EvidenceSource.TOOL_EXECUTION,
        tool=tool,
        detail=detail,
    )


def _fail(
    name: GateName,
    tool: str,
    result: CommandResult,
    detail: str | None = None,
) -> GateResult:
    return GateResult(
        name=name,
        status=GateStatus.FAIL,
        evidence_source=EvidenceSource.TOOL_EXECUTION,
        tool=tool,
        detail=_summarize(result, prefix=detail),
    )


def _not_run(name: GateName, reason: str) -> GateResult:
    return GateResult.not_run(name, reason)


_CTEST_TOTAL_RE = re.compile(r"out of\s+(\d+)", re.IGNORECASE)


def _ctest_total(output: str) -> int | None:
    match = _CTEST_TOTAL_RE.search(output)
    if match is None:
        return None
    return int(match.group(1))


def _summarize(result: CommandResult, *, prefix: str | None = None) -> str:
    text = _clean_output(result.output)
    base = f"exit={result.returncode}"
    if text:
        base = f"{base}; {text}"
    if prefix:
        base = f"{prefix} {base}"
    return base[:2000]


def _clean_output(output: str) -> str:
    output = output.replace("\x00", "")
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return " | ".join(lines[-6:])
