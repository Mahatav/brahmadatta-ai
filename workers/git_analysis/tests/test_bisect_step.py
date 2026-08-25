"""The per-step wrapper's exit-code contract (#24): classify() as a pure function,
run_bisect_step() against a real jail, and the CLI as an actual subprocess -- because
"git bisect run will see exit code 125" is only proven by really invoking the script,
not by calling a Python function that happens to compute the number 125.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from packages.sandbox import LimitKind
from packages.sandbox.jail import JailResult
from workers.git_analysis.bisect_step import (
    EXIT_CODE_FOR_VERDICT,
    Verdict,
    classify,
    main,
    run_bisect_step,
)

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "bisect_step.py"

# CI pins 3.12 (.github/workflows/ci.yml); StrEnum (used throughout this codebase's
# enums, including this wrapper's own Verdict) needs 3.11+. Use whichever interpreter
# is actually running this test file -- the same one pytest itself was invoked with.
PYTHON = sys.executable


def _jail_result(
    *,
    exit_code: int = 0,
    signal_number: int | None = None,
    limit_hit: LimitKind = LimitKind.NONE,
    wall_seconds: float = 1.0,
) -> JailResult:
    return JailResult(
        argv=("true",),
        exit_code=exit_code,
        signal_number=signal_number,
        stdout="",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        wall_seconds=wall_seconds,
        cpu_seconds=0.1,
        peak_memory_mb=10.0,
        limit_hit=limit_hit,
    )


# --- classify(): pure, no subprocess ------------------------------------------------


def test_classify_clean_exit_zero_is_good() -> None:
    verdict, _ = classify(_jail_result(exit_code=0))
    assert verdict is Verdict.GOOD


@pytest.mark.parametrize("exit_code", [1, 2, 66, 124, 126, 127, 200, 254])
def test_classify_nonzero_non_125_exit_is_bad(exit_code: int) -> None:
    verdict, _ = classify(_jail_result(exit_code=exit_code))
    assert verdict is Verdict.BAD


def test_classify_exit_125_is_skip() -> None:
    verdict, reason = classify(_jail_result(exit_code=125))
    assert verdict is Verdict.SKIP
    assert "125" in reason


def test_classify_wall_clock_limit_is_skip_not_hang_not_bad() -> None:
    verdict, reason = classify(_jail_result(exit_code=-9, limit_hit=LimitKind.WALL_CLOCK))
    assert verdict is Verdict.SKIP
    assert "WALL_CLOCK" in reason


@pytest.mark.parametrize(
    "limit", [LimitKind.CPU, LimitKind.MEMORY, LimitKind.FILE_SIZE, LimitKind.OUTPUT]
)
def test_classify_every_other_limit_kind_is_also_skip(limit: LimitKind) -> None:
    verdict, _ = classify(_jail_result(exit_code=-9, limit_hit=limit))
    assert verdict is Verdict.SKIP


def test_classify_signal_death_without_a_jail_limit_is_skip() -> None:
    # limit_hit is NONE: the jail did not kill it, the check command's own process
    # died to a signal on its own.
    verdict, reason = classify(_jail_result(exit_code=-11, signal_number=11))
    assert verdict is Verdict.SKIP
    assert "signal" in reason


def test_classify_limit_hit_wins_over_a_coincidentally_125_exit_code() -> None:
    # A command killed by RLIMIT_CPU (say) that happens to leave exit_code=125 behind
    # must still classify by the limit, not be misread as the check script's own
    # deliberate "untestable" signal.
    verdict, reason = classify(_jail_result(exit_code=125, limit_hit=LimitKind.CPU))
    assert verdict is Verdict.SKIP
    assert "CPU" in reason


@pytest.mark.parametrize(
    "exit_code,limit_hit,signal_number",
    [
        (0, LimitKind.NONE, None),
        (1, LimitKind.NONE, None),
        (125, LimitKind.NONE, None),
        (7, LimitKind.NONE, None),
        (-9, LimitKind.WALL_CLOCK, 9),
        (-11, LimitKind.NONE, 11),
        (255, LimitKind.NONE, None),
    ],
)
def test_classify_never_returns_anything_but_the_three_exit_codes(
    exit_code: int, limit_hit: LimitKind, signal_number: int | None
) -> None:
    verdict, _ = classify(_jail_result(exit_code=exit_code, limit_hit=limit_hit, signal_number=signal_number))
    assert EXIT_CODE_FOR_VERDICT[verdict] in (0, 1, 125)


# --- run_bisect_step(): a real Jail, real subprocess, no CLI layer -----------------


def python(code: str) -> list[str]:
    return [PYTHON, "-c", code]


def test_run_bisect_step_good() -> None:
    result = run_bisect_step(
        python("import sys; sys.exit(0)"),
        repo_path=Path.cwd(),
        timeout_seconds=10,
        append_repo_path=False,
    )
    assert result.verdict is Verdict.GOOD
    assert result.exit_code == 0


def test_run_bisect_step_bad() -> None:
    result = run_bisect_step(
        python("import sys; sys.exit(3)"),
        repo_path=Path.cwd(),
        timeout_seconds=10,
        append_repo_path=False,
    )
    assert result.verdict is Verdict.BAD
    assert result.exit_code == 1


def test_run_bisect_step_skip_passthrough() -> None:
    result = run_bisect_step(
        python("import sys; sys.exit(125)"),
        repo_path=Path.cwd(),
        timeout_seconds=10,
        append_repo_path=False,
    )
    assert result.verdict is Verdict.SKIP
    assert result.exit_code == 125


def test_run_bisect_step_timeout_is_skip_and_does_not_hang() -> None:
    """The core acceptance criterion: a hung check at one commit must not hang the
    whole bisect. A 30s sleep under a 1s budget must return close to 1s, not 30s."""
    started = time.monotonic()
    result = run_bisect_step(
        python("import time; time.sleep(30)"),
        repo_path=Path.cwd(),
        timeout_seconds=1.0,
        append_repo_path=False,
    )
    elapsed = time.monotonic() - started
    assert result.verdict is Verdict.SKIP
    assert result.exit_code == 125
    assert elapsed < 10.0, f"wrapper took {elapsed:.1f}s against a 1s budget -- the hang was not bounded"
    assert result.limit_hit == "WALL_CLOCK"


def test_run_bisect_step_appends_repo_path_by_default(tmp_path: Path) -> None:
    marker = tmp_path / "argv.txt"
    script = python(
        "import sys, pathlib; "
        f"pathlib.Path({str(marker)!r}).write_text(repr(sys.argv[1:]))"
    )
    fake_repo = tmp_path / "the-repo"
    fake_repo.mkdir()
    run_bisect_step(script, repo_path=fake_repo, timeout_seconds=10)
    assert str(fake_repo) in marker.read_text()


def test_run_bisect_step_no_append_repo_path_suppresses_it(tmp_path: Path) -> None:
    marker = tmp_path / "argv.txt"
    script = python(
        "import sys, pathlib; "
        f"pathlib.Path({str(marker)!r}).write_text(repr(sys.argv[1:]))"
    )
    fake_repo = tmp_path / "the-repo"
    fake_repo.mkdir()
    run_bisect_step(script, repo_path=fake_repo, timeout_seconds=10, append_repo_path=False)
    assert str(fake_repo) not in marker.read_text()


def test_run_bisect_step_jail_unavailable_is_skip() -> None:
    result = run_bisect_step(
        ["/no/such/binary/anywhere"], repo_path=Path.cwd(), timeout_seconds=5, append_repo_path=False
    )
    assert result.verdict is Verdict.SKIP
    assert result.exit_code == 125


# --- the CLI, as a real subprocess (what git bisect run actually invokes) ----------


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PYTHON, str(SCRIPT_PATH), *args], capture_output=True, text=True, timeout=30
    )


def test_cli_good_exit_code() -> None:
    proc = _cli("--timeout-seconds", "5", "--no-append-repo-path", "--", PYTHON, "-c", "import sys; sys.exit(0)")
    assert proc.returncode == 0


def test_cli_bad_exit_code() -> None:
    proc = _cli("--timeout-seconds", "5", "--no-append-repo-path", "--", PYTHON, "-c", "import sys; sys.exit(9)")
    assert proc.returncode == 1


def test_cli_skip_exit_code() -> None:
    proc = _cli("--timeout-seconds", "5", "--no-append-repo-path", "--", PYTHON, "-c", "import sys; sys.exit(125)")
    assert proc.returncode == 125


def test_cli_never_emits_an_abort_range_exit_code_even_for_a_weird_inner_code() -> None:
    """A check command that itself exits 200 must not reach git bisect run as 200 --
    128+ tells git bisect run to abort the whole bisection, which a single
    misbehaving commit's check script must never be able to trigger."""
    proc = _cli("--timeout-seconds", "5", "--no-append-repo-path", "--", PYTHON, "-c", "import sys; sys.exit(200)")
    assert proc.returncode == 1


def test_cli_no_command_is_skip_not_a_crash() -> None:
    proc = _cli("--timeout-seconds", "5")
    assert proc.returncode == 125


def test_cli_timeout_returns_promptly() -> None:
    started = time.monotonic()
    proc = _cli("--timeout-seconds", "1", "--no-append-repo-path", "--", PYTHON, "-c", "import time; time.sleep(20)")
    elapsed = time.monotonic() - started
    assert proc.returncode == 125
    assert elapsed < 10.0


def test_main_function_matches_subprocess_behaviour(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--timeout-seconds", "5", "--no-append-repo-path", "--", PYTHON, "-c", "import sys; sys.exit(0)"])
    assert code == 0
