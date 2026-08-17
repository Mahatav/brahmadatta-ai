"""Fresh-worktree deterministic verification for patch candidates (#38).

The verifier deliberately accepts a raw diff, never a persisted ``PatchCandidate``.
That keeps provenance, model name, confidence and rationale out of the verification
path: deterministic gates produce a ``GateMatrix`` and ``derive_verdict`` remains the
only verdict reducer.

SEC-47: every command this module runs (``git apply``, ``cmake`` configure/build, the
compiled patched binary, ``ctest``) executes inside exactly one ``packages.sandbox.Jail``
per ``run_verification`` call, mirroring ``workers/baseline/run.py``'s existing pattern
for the BASELINE stage's own configure+build+ctest sequence. This bounds CPU, address
space, process count and wall-clock time on the one pipeline stage that compiles and
executes a diff whose provenance may be ``MODEL_GENERATED`` — it does not, on its own,
stop credential exfiltration (SEC-44's explicit env allowlist is what does that; see
``_ENV_ALLOWLIST`` below and ``Jail.run()``'s own environment scrubbing).

``git apply`` cannot take the candidate diff over stdin here — ``Jail.run()`` hardcodes
``stdin=subprocess.DEVNULL`` (``packages/sandbox/jail.py``) — so ``run_verification``
writes it to a file inside the jail first and invokes ``git apply <path>`` instead of
piping it in. This is standard ``git apply`` usage; nothing about ``Jail`` needed to
change.

PR #175 functional re-review (commit 8ffdccd): ``VerificationBaseline.configure_args``
defaults to turning pktcfg's own sanitizers on (``-DPKTCFG_SANITIZE=ON``), and
``JailPolicy``'s generic ``memory_bytes`` default (2 GiB ``RLIMIT_AS``) is not large
enough for AddressSanitizer to even start — ``adapters/cpp/variants.py``'s module
docstring documents the ~28 TiB shadow-memory reservation this requires, measured
directly on Linux, which is exactly why every sanitizer ``VariantSpec`` in that module
sets ``min_jail_memory_bytes = MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS`` and
``workers/replay/run.py`` builds its ``Jail`` from that value. This module does not
route through ``adapters.cpp.pipeline.run_variant``/``VariantSpec`` — it drives
``cmake``/``ctest`` directly against ``VerificationBaseline.configure_args`` — so
``_sanitizers_enabled`` inspects those raw configure args instead of looking up a
``Variant``, and ``run_verification`` sizes its ``Jail``'s ``memory_bytes`` from
``MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS`` whenever they turn a sanitizer on. Getting this
wrong does not raise: every ASan-instrumented process aborts at startup with
``AddressSanitizer failed to allocate ...``/``ReserveShadowMemoryRange failed``, which
``ctest`` reports as an ordinary failing test — on real Linux (the deploy target;
``RLIMIT_AS`` is unenforced on Darwin, which is why this passed locally before), that
turned every gate FAIL, meaning VERIFY could never produce a ``VERIFIED`` verdict for any
candidate, correct or not.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
import shutil
import subprocess
from collections.abc import Callable, Sequence

from adapters.cpp.variants import MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS
from contracts.enums import EvidenceSource, GateName, GateStatus
from contracts.verdict import GateMatrix, GateResult
from packages.sandbox import Jail, JailPolicy
from packages.sandbox.policy import DEFAULT_ENV_ALLOWLIST

#: Environment variables a verification subprocess (`git apply`, `cmake` configure/build,
#: the compiled patched binary, `ctest`) is allowed to inherit. Everything else the
#: worker process holds — `DATABASE_URL` foremost, a real Postgres connection string set
#: directly as a container env var (`infrastructure/compose/docker-compose.yml`'s
#: `worker` service) — is dropped before the child is spawned (SEC-44).
#:
#: This is reachable without an external adversary: D-008 sanctions an operator-authored
#: diff through this identical pipeline, and a one-line `CMakeLists.txt` addition
#: (`add_test(NAME x COMMAND sh -c "env")`) is registered as a regression test and run by
#: the `ctest` gate with whatever environment this process handed it. An allowlist, not a
#: blocklist: a blocklist only protects against the secrets someone thought to name, and
#: misses the next one added to the environment later.
#:
#: Imported directly from `packages.sandbox.policy` — one allowlist, not a second one that
#: could drift. Earlier in this PR this was a locally-duplicated tuple: `packages.sandbox`
#: was not importable from `apps/control-api`'s runtime path at the time (verified
#: directly, twice — see `.project/decisions.md`, D-067 §5). #168 T1's merge
#: (`config/settings/base.py`, D-066 §3) added a `sys.path` shim putting the repository
#: root on `sys.path` for every Django entrypoint including `pytest-django`, which
#: resolved that import boundary — `Jail.run()` itself (below) already scrubs to this
#: same allowlist, so this constant now exists mainly for `_subprocess_runner`, the
#: still-available, still-tested non-jailed runner.
_ENV_ALLOWLIST: tuple[str, ...] = DEFAULT_ENV_ALLOWLIST


#: Matches a CMake cache-entry flag (`-D<NAME>=<VALUE>`) whose name mentions "SANITIZE",
#: case-insensitively — covers pktcfg's own `-DPKTCFG_SANITIZE=ON` switch without hardcoding
#: that project-specific name, the same way `adapters/cpp/pipeline.py::_configure_argv`
#: applies sanitizer flags generically rather than assuming a target-specific option exists.
_SANITIZE_CACHE_ENTRY_RE = re.compile(r"^-D(?P<name>[\w-]*SANITIZE[\w-]*)=(?P<value>.+)$", re.IGNORECASE)
#: CMake boolean "true" spellings a cache entry's value might use. `cmake --help-policy` /
#: `if()` command docs list these as the ON-equivalent constants; anything else (`OFF`, `0`,
#: `FALSE`, `NO`, an empty string, or an unrecognised token) is treated as sanitizers-off.
_CMAKE_TRUTHY_BOOL = {"on", "1", "true", "yes", "y"}


def _sanitizers_enabled(configure_args: tuple[str, ...]) -> bool:
    """Whether `configure_args` turns on sanitizer instrumentation the `Jail`'s
    `RLIMIT_AS` must be sized for (see the module docstring's PR #175 functional
    re-review note). Recognises both a raw `-fsanitize=...` compiler flag (the generic
    path `adapters/cpp/pipeline.py::_configure_argv` uses for a target with no cache
    switch of its own) and a CMake `-D<...SANITIZE...>=<truthy>` cache entry (pktcfg's
    own `-DPKTCFG_SANITIZE=ON`, this module's actual default) — either is a positive.
    """
    for arg in configure_args:
        if "-fsanitize=" in arg:
            return True
        match = _SANITIZE_CACHE_ENTRY_RE.match(arg)
        if match is not None and match.group("value").strip().lower() in _CMAKE_TRUTHY_BOOL:
            return True
    return False


def _minimal_subprocess_env() -> dict[str, str]:
    """The explicit environment every verification subprocess runs under.

    Only variables in `_ENV_ALLOWLIST` that are actually set on this process survive;
    everything else — every secret the worker process holds — is dropped. Computed
    fresh on every call (never cached at import time) so it always reflects the real,
    current environment rather than a snapshot that could go stale.
    """
    return {name: os.environ[name] for name in _ENV_ALLOWLIST if name in os.environ}


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


def _jail_command_runner(jail: Jail) -> CommandRunner:
    """Adapt `packages.sandbox.Jail.run()` to this module's `CommandRunner` shape.

    SEC-47: this is `run_verification`'s default runner now — every command routes
    through `Jail`'s CPU/address-space/process-count/wall-clock ceilings, the same
    isolation primitive `workers/baseline/run.py` already uses for BASELINE's own
    configure+build+ctest sequence (`adapters/cpp/pipeline.py::run_variant`), instead
    of a bare `subprocess.run` bounded only by SEC-44's env allowlist. `Jail` itself
    does not stop credential exfiltration on its own — its own docstring is explicit
    that it "does not constrain what the command does once running" beyond resource
    limits and a scratch-directory jail; `Jail.run()`'s environment scrubbing (to
    `JailPolicy.env_allowlist`, the same `DEFAULT_ENV_ALLOWLIST` this module imports
    above) is the part that does that, and it applies unconditionally, whether or not
    this adapter is the one calling it.

    `Jail.run()` has no `stdin` parameter (hardcoded `stdin=subprocess.DEVNULL`), so
    this raises rather than silently discarding one — `run_verification` never calls
    it with a non-`None` `stdin` (see the module docstring for how the `git apply` step
    avoids needing one), and a future caller that tries would get a loud error instead
    of a silently-ignored patch.
    """

    def _run(
        argv: Sequence[str],
        cwd: Path,
        stdin: str | None,
        timeout_seconds: int,
    ) -> CommandResult:
        del timeout_seconds  # the Jail's own JailPolicy.wall_clock_seconds governs every run
        if stdin is not None:
            raise ValueError(
                "the Jail-backed command runner has no stdin channel (Jail.run() "
                "hardcodes stdin=subprocess.DEVNULL); write the input to a file inside "
                "the jail and pass its path as an argument instead"
            )
        result = jail.run(list(argv), cwd=cwd)
        return CommandResult(
            argv=result.argv,
            returncode=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    return _run


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
    source = Path(worktree).resolve()
    if not source.exists() or not source.is_dir():
        raise ValueError(
            f"verification source does not exist or is not a directory: {source}"
        )

    # SEC-47: exactly one Jail for the whole configure+build+ctest sequence, mirroring
    # `workers/baseline/run.py`'s pattern for BASELINE. `wall_clock_seconds` always
    # overrides the generic JailPolicy default, sized for this call's own timeout.
    #
    # `memory_bytes` also needs overriding, but only when `baseline.configure_args` turns
    # a sanitizer on (this module's own default does, via pktcfg's `-DPKTCFG_SANITIZE=ON`):
    # PR #175's functional re-review caught that `JailPolicy`'s generic 2 GiB `RLIMIT_AS`
    # default is not large enough for ASan to even reserve its shadow memory on Linux — see
    # the module docstring and `adapters/cpp/variants.py` for the full explanation. Every
    # other JailPolicy default (CPU, process count, output/file-size caps) stays generic,
    # same as `adapters/cpp/pipeline.py::run_variant`'s own usage.
    policy_overrides: dict[str, object] = {"wall_clock_seconds": float(baseline.timeout_seconds)}
    if _sanitizers_enabled(baseline.configure_args):
        policy_overrides["memory_bytes"] = MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS
    policy = JailPolicy(**policy_overrides)
    with Jail.create(policy) as jail:
        command_runner = runner or _jail_command_runner(jail)
        # `_copy_source_tree`'s destination lives inside `jail.root` so `jail.resolve()`'s
        # containment check (every `cwd` this module hands `Jail.run()`) is checking
        # something real, not a directory the jail has no relationship to.
        verify_root = jail.root / source.name
        _copy_source_tree(source, verify_root, baseline.ignored_names)

        # `Jail.run()` has no `stdin` (see module docstring): write the candidate diff to
        # a file inside the jail and pass its path to `git apply` instead of piping it.
        # Written outside `verify_root` so it never becomes a stray file inside the copied
        # source tree that the build/ctest steps could see.
        diff_path = jail.root / ".brahmadatta-candidate.patch"
        diff_path.write_text(candidate_diff)

        apply_result = command_runner(
            ["git", "apply", "--whitespace=nowarn", str(diff_path)],
            verify_root,
            None,
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

    failed = _ctest_failed(result.output)
    detail_prefix = "Regression suite failed or a new fault appeared."
    if total is not None and failed is not None:
        # Structured signal (two integers pulled from a fixed regex capture group),
        # never the surrounding raw ctest output — see `_fail`/`_summarize` (SEC-45).
        detail_prefix = f"Regression suite failed: {failed} of {total} tests failed."
    return _fail(
        GateName.REGRESSION_PRESERVED,
        "ctest",
        result,
        detail_prefix,
    )


def _subprocess_runner(
    argv: Sequence[str],
    cwd: Path,
    stdin: str | None,
    timeout_seconds: int,
) -> CommandResult:
    """A bare `subprocess.run`, still scrubbed to `_ENV_ALLOWLIST` (SEC-44), but with
    none of `Jail`'s resource ceilings. No longer `run_verification`'s default runner
    as of SEC-47 (`_jail_command_runner` is) — kept available and directly tested as an
    explicit, non-jailed alternative a caller can still inject via `runner=`, and as a
    standalone proof that the env allowlist itself works independent of `Jail`.
    """
    try:
        completed = subprocess.run(
            list(argv),
            cwd=cwd,
            input=stdin,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
            env=_minimal_subprocess_env(),
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
        detail=_summarize(result, tool=tool, prefix=detail),
    )


def _not_run(name: GateName, reason: str) -> GateResult:
    return GateResult.not_run(name, reason)


_CTEST_TOTAL_RE = re.compile(r"out of\s+(\d+)", re.IGNORECASE)
_CTEST_FAILED_RE = re.compile(r"(\d+)\s+tests?\s+failed", re.IGNORECASE)


def _ctest_total(output: str) -> int | None:
    match = _CTEST_TOTAL_RE.search(output)
    if match is None:
        return None
    return int(match.group(1))


def _ctest_failed(output: str) -> int | None:
    match = _CTEST_FAILED_RE.search(output)
    if match is None:
        return None
    return int(match.group(1))


def _summarize(result: CommandResult, *, tool: str, prefix: str | None = None) -> str:
    """Build `GateResult.detail`'s text with no raw subprocess output in it (SEC-45).

    `contracts/verdict.py`'s `GateResult.detail` docstring is explicit: "User-safe
    summary. Never raw target output, never secrets." This used to splice the last six
    non-empty lines of the command's actual combined stdout/stderr straight into that
    field — the concrete leak channel a `CMakeLists.txt`-injected `env` dump (SEC-44)
    would have exploited, and the reason a field whose own contract says "never" must
    not depend on nothing upstream going wrong to keep that promise.

    Only already-known-safe values go into the returned string: the tool name, the
    exit code, and an optional caller-supplied `prefix` that is itself always a fixed,
    hand-written literal or a structured extraction of bare integers (see
    `_run_regressions`'s "N of M tests failed" — pulled from a regex capture group,
    never the surrounding text). Raw `result.stdout`/`result.stderr` are read nowhere
    in this function, and this module does not persist them anywhere else either: with
    no evidence/artifact store wired into this pure verification function today, "don't
    capture it into anything that leaves this call" is the safe stopping point rather
    than inventing a second, separately-secured logging channel under deadline
    pressure. See this PR's handoff for that reasoning spelled out in full.
    """
    base = f"exit={result.returncode}"
    if prefix:
        base = f"{prefix} {base}"
    return f"{tool}: {base}"[:2000]
