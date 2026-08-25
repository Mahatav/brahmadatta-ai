#!/usr/bin/env python3
"""The per-commit `git bisect run` step (#24): one arbitrary check command, one hard
wall-clock timeout, exactly one of three exit codes back to `git bisect run`.

`git bisect run <cmd>` has its own documented exit-code contract, and it is strict:

    0        good  -- this commit does not have the bug
    1-124    bad   -- this commit has the bug (anything in this range, not just 1)
    125      skip  -- this commit cannot be tested at all; bisect keeps searching
                       around it instead of trusting the result
    126-127  bisect run itself could not execute the command -- treated as a hard
                       error, NOT part of the good/bad/skip vocabulary
    128-255  bisect run ABORTS the whole bisection -- reserved for "something is
                       badly wrong", never a legitimate step outcome

The bug class this wrapper exists to close: a bare check script has no way to stop a
build or a test binary that hangs at one particular commit, and `git bisect run` itself
has no timeout of its own -- a single wedged step burns the whole session (the exact
failure #24 was filed to prevent; see the issue's "why"). Wrapping the check command in
`packages.sandbox.Jail` gets a hard wall-clock kill of the whole process group for free
(orphans included -- see `packages/sandbox/jail.py`'s SEC-33/SEC-38 fixes), reusing the
one timeout implementation this codebase already has rather than building a second one.

**Design choice: timeout -> skip (125), not bad (1).** A hung step tells you nothing
about whether the code at that commit is correct -- it tells you the check took too
long *in this environment*, which can be true independent of the regression being
bisected (a noisy neighbour process, a slow disk, a compiler that happened to spend
longer optimising one revision). Reporting it as `bad` would let environmental noise
silently steer bisection to the wrong commit with no visible sign anything was wrong.
`git bisect run`'s own `skip` contract exists exactly for "this revision cannot be
judged" and instructs `git bisect` to keep searching around it rather than trust a
verdict that was never actually reached -- that is a closer match to what a timeout
means than either `good` or `bad` is, so this wrapper's exit-code table treats every
form of "the check did not reach a clean, trustworthy exit" (timeout, a resource limit,
the check process itself dying to an unexpected signal, the jail failing to start at
all) as `skip`, uniformly, and reserves `bad` for the one case that actually is
positive evidence of a defect: the check command ran to completion and reported one
via a controlled nonzero exit.

**"Nothing overloaded" (the issue's own acceptance criterion).** Every path through
`main()` returns via `EXIT_CODE_FOR_VERDICT`, a 3-entry table -- there is no code path
that can emit 126, 127, or anything >= 128, even if the wrapped command itself does (a
misbehaving check script exiting 137, say, gets collapsed into `bad`, not passed
through and misread by `git bisect run` as "abort the whole bisection"). An unexpected
exception inside this script itself is caught and reported as `skip`, not left to
propagate as a raw traceback with whatever exit code Python happens to pick -- an
infrastructure failure in the wrapper is exactly as untestable as a hung build, not
evidence about the commit under test.

Usage
-----

    git bisect run /abs/path/to/bisect_step.py [--timeout-seconds N] \\
        [--memory-bytes N] [--cpu-seconds N] [--no-append-repo-path] \\
        -- <check-command> [check-args...]

`git bisect run` executes this script with its cwd already set to the commit under
test (whichever repository is being bisected) -- so this file is invoked with an
absolute path, its own module import of `packages.sandbox` cannot rely on the caller's
cwd containing this repository at all, hence the `sys.path` bootstrap immediately
below, before any local import. Same reasoning `packages/sandbox/tests/test_jail.py`
already uses for the same problem, one directory shallower.

The check command receives the bisected repository's path as its final positional
argument (the same convention `demo/repositories/pktcfg-bisect-check.sh` already uses:
`pktcfg-bisect-check.sh [path-to-pktcfg-checkout]`), plus a `BISECT_REPO_PATH`
environment variable carrying the same value for a check command that would rather
read it from the environment. Pass `--no-append-repo-path` to suppress the positional
argument for a check command that takes none.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

# `git bisect run` always runs this script with cwd set to the bisected repository, not
# to brahmadatta-ai's own root -- an absolute-path invocation is the only thing that
# reliably reaches this file at all, so the same absolute path is used here to recover
# where `packages.sandbox` and `adapters.cpp` actually live. Guarded so re-importing
# this module (e.g. from a test that already has the repo root on sys.path) is a no-op.
_REPO_ROOT = _Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_REPO_ROOT))

import argparse  # noqa: E402
import time  # noqa: E402
from collections.abc import Sequence  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from enum import StrEnum  # noqa: E402
from typing import Any, TextIO  # noqa: E402

from adapters.cpp.variants import MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS  # noqa: E402
from packages.sandbox import (  # noqa: E402
    Jail,
    JailPolicy,
    JailResult,
    JailUnavailableError,
    LimitKind,
)

__all__ = [
    "EXIT_CODE_FOR_VERDICT",
    "GIT_BISECT_ABORT_EXIT_FLOOR",
    "BisectStepResult",
    "Verdict",
    "classify",
    "main",
    "run_bisect_step",
]

#: `git bisect run`'s own contract -- see the module docstring's table. Any exit code at
#: or above this value tells `git bisect run` to abandon the bisection entirely, which
#: this wrapper must never trigger by accident.
GIT_BISECT_ABORT_EXIT_FLOOR = 128

#: The one other exit code `git bisect run` treats specially rather than as "bad": see
#: the module docstring.
GIT_BISECT_SKIP_EXIT_CODE = 125


class Verdict(StrEnum):
    """The three, and only three, meanings this wrapper ever reports."""

    GOOD = "GOOD"
    BAD = "BAD"
    SKIP = "SKIP"


#: The whole "nothing overloaded" guarantee lives in this table being total and
#: `main()` never returning anything that did not pass through it.
EXIT_CODE_FOR_VERDICT: dict[Verdict, int] = {
    Verdict.GOOD: 0,
    Verdict.BAD: 1,
    Verdict.SKIP: GIT_BISECT_SKIP_EXIT_CODE,
}

#: How much of a run's captured output is kept in `BisectStepResult`, for a caller (a
#: test, a future evidence record) that wants to see *why* without re-running anything.
#: `JailResult` already caps total captured output well above this; this is a second,
#: smaller cap so one wrapper result stays small enough to log or embed in a mission
#: event without needing its own truncation policy.
_OUTPUT_TAIL_CHARS = 2000


@dataclass(frozen=True, slots=True)
class BisectStepResult:
    """What one `git bisect run` step actually did. `exit_code` is always one of
    `EXIT_CODE_FOR_VERDICT`'s three values -- that is the whole point of this type."""

    verdict: Verdict
    exit_code: int
    reason: str
    wall_seconds: float
    argv: tuple[str, ...]
    inner_exit_code: int | None
    inner_signal: int | None
    limit_hit: str

    #: `stdout_tail`/`stderr_tail` -- see `_OUTPUT_TAIL_CHARS`. Empty when the jail
    #: itself never started (`JailUnavailableError`), since nothing ran to produce any.
    stdout_tail: str = ""
    stderr_tail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "exit_code": self.exit_code,
            "reason": self.reason,
            "wall_seconds": self.wall_seconds,
            "argv": list(self.argv),
            "inner_exit_code": self.inner_exit_code,
            "inner_signal": self.inner_signal,
            "limit_hit": self.limit_hit,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
        }

    def summary(self) -> str:
        return (
            f"bisect_step: {self.verdict.value} (exit {self.exit_code}) in "
            f"{self.wall_seconds:.2f}s -- {self.reason}"
        )


def classify(result: JailResult) -> tuple[Verdict, str]:
    """Turn one `JailResult` into exactly one `Verdict`, with the reason spelled out.

    Pure and jail-free by design -- every branch here is exercised in
    `tests/test_bisect_step.py` against a hand-built `JailResult`, no real subprocess
    required for the classification logic itself (the real-subprocess behaviour is
    covered separately, end to end, by the tests that actually spawn a `Jail`).

    Branch order matters: `limit_hit` is checked before `exit_code`/`signal_number`
    because a command a jail limit killed can still leave a nonzero (even a
    coincidentally-125) `exit_code` on the `JailResult` -- the limit is the true reason
    it stopped, so it must win the classification, not be shadowed by a numeric
    coincidence in the exit code underneath it.
    """
    if result.limit_hit is not LimitKind.NONE:
        # Every resource limit the jail enforces -- wall clock, CPU, memory, one-file
        # size, or the output cap -- means the jail itself intervened before the check
        # command reached its own, trustworthy exit. None of those are evidence about
        # the commit under test; all of them are "this environment could not evaluate
        # this commit under the configured limits" -- see the module docstring's
        # "timeout -> skip, not bad" rationale, which applies identically to every
        # other limit kind, not just WALL_CLOCK.
        return (
            Verdict.SKIP,
            f"jail limit hit: {result.limit_hit.value} "
            f"(wall={result.wall_seconds:.1f}s cpu={result.cpu_seconds:.1f}s "
            f"peak_mem={result.peak_memory_mb:.0f}MB) -- untestable under the "
            f"configured limits, not evidence about this commit",
        )
    if result.signal_number is not None:
        # The jail did not kill it (limit_hit is NONE here), so this is the check
        # command's own process dying to a signal on its own -- e.g. the check driver
        # script's own shell segfaulting. That is a broken evaluation, not a verdict
        # about the code under test: the exit code checked below is not even reliable
        # in this branch (`JailResult.exit_code` is negative for a signal death), so
        # the wrapper does not risk misreading a negative number as anything.
        return (
            Verdict.SKIP,
            f"check command terminated by signal {result.signal_number}, not a clean "
            f"exit -- cannot trust this as a good/bad verdict",
        )
    if result.exit_code == 0:
        return Verdict.GOOD, "check command exited 0"
    if result.exit_code == GIT_BISECT_SKIP_EXIT_CODE:
        # The check command already speaks git bisect run's own convention (e.g.
        # `pktcfg-bisect-check.sh` exits 125 when configure/build itself cannot
        # complete). Passed through rather than reinterpreted -- the inner script has
        # more context about why this commit is untestable than this wrapper does.
        return Verdict.SKIP, "check command itself exited 125 (untestable at this commit)"
    # Every other exit code -- 1-124 except 125, and 126/127/128+ too, which a
    # misbehaving or unusual check command could technically return -- collapses to
    # BAD. This is what makes "nothing overloaded" true regardless of what the wrapped
    # command does: a check command that exits 137 (say, killed by a signal *inside*
    # its own subshell logic rather than propagated as this process's own signal death)
    # never reaches git bisect run as a raw 137, which git bisect run would otherwise
    # treat as "abort the whole bisection" -- it is normalised to 1 here first.
    return Verdict.BAD, f"check command exited {result.exit_code}"


def run_bisect_step(
    check_argv: Sequence[str],
    *,
    repo_path: _Path,
    timeout_seconds: float,
    memory_bytes: int = MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS,
    cpu_seconds: int | None = None,
    append_repo_path: bool = True,
    extra_env: dict[str, str] | None = None,
) -> BisectStepResult:
    """Run one check command under a hard wall-clock timeout and classify the result.

    `memory_bytes` defaults to the same ~64 TiB `RLIMIT_AS` ceiling
    `adapters/cpp/variants.py` documents as required for an AddressSanitizer-built
    process to even start on Linux (`RLIMIT_AS` and ASan's shadow-memory reservation do
    not coexist at any "reasonable" value) -- the primary use case this wrapper was
    built for is bisecting a sanitizer-confirmed crash (#5's pktcfg fixture), so a
    caller gets a working default for that case without needing to know the pitfall
    exists. A caller bisecting an unsanitized check can pass a tighter value.

    `cpu_seconds` defaults to comfortably above `timeout_seconds` (never below the
    jail's own 300s floor) specifically so `RLIMIT_CPU` -- a *per-process* CPU-time
    budget, not the wall-clock budget this function exists to enforce -- cannot fire
    first and get misclassified as a CPU-limit skip when the real, intended limit is
    the wall clock. `packages.sandbox.Jail` requires `cpu_seconds` to be a positive
    int, so it is never allowed to be smaller than the wall-clock float actually
    configured here.
    """
    started = time.monotonic()
    argv = list(check_argv)
    if append_repo_path:
        argv.append(str(repo_path))
    env = {"BISECT_REPO_PATH": str(repo_path), **(extra_env or {})}
    effective_cpu_seconds = (
        cpu_seconds if cpu_seconds is not None else max(300, int(timeout_seconds) + 60)
    )
    policy = JailPolicy(
        wall_clock_seconds=timeout_seconds,
        memory_bytes=memory_bytes,
        cpu_seconds=effective_cpu_seconds,
    )

    try:
        with Jail.create(policy) as jail:
            jail_result = jail.run(argv, extra_env=env)
    except JailUnavailableError as exc:
        # The jail itself could not be created or start the command (e.g. the check
        # command is not on PATH, or the machine cannot allocate a scratch directory).
        # This is exactly as untestable as a hung build -- skip, not a fabricated bad.
        return BisectStepResult(
            verdict=Verdict.SKIP,
            exit_code=EXIT_CODE_FOR_VERDICT[Verdict.SKIP],
            reason=f"jail unavailable: {exc}",
            wall_seconds=time.monotonic() - started,
            argv=tuple(argv),
            inner_exit_code=None,
            inner_signal=None,
            limit_hit="NONE",
        )

    verdict, reason = classify(jail_result)
    return BisectStepResult(
        verdict=verdict,
        exit_code=EXIT_CODE_FOR_VERDICT[verdict],
        reason=reason,
        wall_seconds=jail_result.wall_seconds,
        argv=tuple(argv),
        inner_exit_code=jail_result.exit_code,
        inner_signal=jail_result.signal_number,
        limit_hit=jail_result.limit_hit.value,
        stdout_tail=jail_result.stdout[-_OUTPUT_TAIL_CHARS:],
        stderr_tail=jail_result.stderr[-_OUTPUT_TAIL_CHARS:],
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bisect_step.py",
        description=(
            "Run one git-bisect step's check command under a hard wall-clock timeout, "
            "and report exactly one of git bisect run's three step outcomes (0 good, "
            "1 bad, 125 skip)."
        ),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=120.0,
        help="hard wall-clock budget for the whole check command (default: 120s)",
    )
    parser.add_argument(
        "--memory-bytes",
        type=int,
        default=MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS,
        help=(
            "RLIMIT_AS ceiling passed to the jail; defaults to the sanitizer-safe "
            "~64TiB ceiling documented in adapters/cpp/variants.py"
        ),
    )
    parser.add_argument(
        "--cpu-seconds",
        type=int,
        default=None,
        help="RLIMIT_CPU ceiling; defaults to comfortably above --timeout-seconds",
    )
    parser.add_argument(
        "--repo-path",
        type=_Path,
        default=None,
        help="the bisected repository's path (default: this process's own cwd, which "
        "is where git bisect run already checked out the commit under test)",
    )
    parser.add_argument(
        "--no-append-repo-path",
        action="store_true",
        help="do not append --repo-path as the check command's final positional argument",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="the check command and its arguments, after a literal --",
    )
    return parser


def _strip_leading_separator(command: list[str]) -> list[str]:
    if command and command[0] == "--":
        return command[1:]
    return command


def main(argv: list[str] | None = None, *, stderr: TextIO = _sys.stderr) -> int:
    args = _build_parser().parse_args(argv)
    command = _strip_leading_separator(list(args.command))

    if not command:
        print(
            "bisect_step: no check command given (usage: bisect_step.py [opts] -- "
            "<command> [args...]) -- this commit cannot be evaluated, skipping",
            file=stderr,
        )
        return EXIT_CODE_FOR_VERDICT[Verdict.SKIP]

    repo_path = args.repo_path if args.repo_path is not None else _Path.cwd()

    try:
        result = run_bisect_step(
            command,
            repo_path=repo_path,
            timeout_seconds=args.timeout_seconds,
            memory_bytes=args.memory_bytes,
            cpu_seconds=args.cpu_seconds,
            append_repo_path=not args.no_append_repo_path,
        )
    except Exception as exc:
        # An unanticipated bug in this wrapper (or in packages.sandbox underneath it)
        # is exactly as untestable as a hung build from git bisect run's point of view
        # -- reported as skip, never left to propagate as a raw traceback with
        # whatever exit code the interpreter happens to pick (which could easily land
        # in the 126-255 range git bisect run treats as "stop the whole bisection").
        print(
            f"bisect_step: unexpected internal failure, treating as skip: "
            f"{exc.__class__.__name__}: {exc}",
            file=stderr,
        )
        return EXIT_CODE_FOR_VERDICT[Verdict.SKIP]

    print(result.summary(), file=stderr)
    assert result.exit_code in EXIT_CODE_FOR_VERDICT.values()  # nothing overloaded, by construction
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
