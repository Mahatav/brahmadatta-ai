"""Adapts `packages.sandbox.container.ContainerJail` to `packages.sandbox.jail.Jail`'s
call surface (#181/SEC-57), so a caller written against `Jail` — `adapters/cpp/
pipeline.py::run_variant`, `adapters/cpp/toolchain.py::probe_build_tools`,
`adapters/cpp/ctest_report.py::run_ctest`/`enumerate_tests`, and
`orchestrator/verification.py`'s own `CommandRunner` — can be handed a
`ContainerJailRunner` instead and drive the exact same configure/build/ctest/git-apply
sequence inside D-024's `--network none`/`--cap-drop ALL`/`--read-only` container,
with no changes to the logic in any of those callers beyond accepting the wider type.

Why this file exists instead of just passing a `ContainerJail` directly
------------------------------------------------------------------------
`Jail` and `ContainerJail` are deliberately NOT the same shape (`packages/sandbox/
container.py`'s own module docstring: this is a different backend, not a drop-in). Three
real differences a caller written against `Jail` depends on, and what this class does
about each:

1. **`cwd` is a per-call `Jail.run()` argument; `ContainerJail.run()` has none** — every
   container command runs at the container's fixed `-w /workspace`. `run()` below
   translates a `cwd` (always a HOST path somewhere under `self.root`, because every
   caller in this codebase builds `cwd` from `jail.root`/`build_dir` — never an arbitrary
   external path) into a `cd <container-relative-path> && exec ...` wrapper.

2. **A `Jail`-backed caller's argv/cwd values are HOST paths that are valid because the
   subprocess shares the host filesystem; a container only ever sees ONE thing, the
   single `-v {root}:/workspace:rw` bind mount** (`container.py::_docker_run_args`).
   Every argv element that is a host-absolute path starting with `self.root` gets the
   same `str(self.root)` prefix rewritten to `/workspace` before the command runs — see
   `_translate`. An argv element that is NOT under `self.root` (a bare command name such
   as `"cmake"`, or a host path this class did not create — e.g. an externally-supplied
   reproducer artifact under `settings.ARTIFACT_ROOT`) is passed through unchanged; the
   latter case is a caller bug, not something this class can fix by rewriting text — see
   `orchestrator/verification.py`'s own container wiring for how that case is actually
   avoided (stage the file under `self.root` first, then reference the staged copy).

3. **`shutil.which("cmake")` resolves against the ORCHESTRATOR HOST's `PATH`, not the
   pinned image's** — a real gap for `adapters/cpp/toolchain.py::probe_build_tools`,
   which calls `jail.which(name)` (added alongside this class) before handing the
   result to `jail.run([path, "--version"])`. `Jail.which` returns the host-resolved
   absolute path (correct for that backend, since it runs on the host). This class's
   `which()` returns the bare `name` unresolved: this container's `sh -c` wrapper below
   resolves it against the PINNED IMAGE's own `PATH` at exec time, which is the only
   resolution that means anything once the two filesystems are no longer the same one.
   `ToolVersion.path` therefore records a bare command name, not a host path, when
   built under this backend — an honest reflection of "this jail cannot report an
   absolute path because none was ever resolved," not a lost measurement.

`JailResult` fields this backend genuinely cannot measure
-----------------------------------------------------------
`ContainerJailResult` carries no per-run CPU time, peak RSS, or per-limit
`limits_applied` breakdown — `docker wait`/`docker logs` do not expose them the way
`resource.getrusage(RUSAGE_CHILDREN)` does for a same-namespace subprocess. `_to_jail_result`
below reports `cpu_seconds=0.0`, `peak_memory_mb=0.0`, `limits_applied={}`, and
`signal_number=None` for those — `{}`  is `JailResult.limits_applied`'s own documented
"the measurement itself could not be recovered" case (its docstring, `jail.py`), which is
exactly true here, not a guess dressed up as zero. `exit_code`/`ok`/`stdout`/`stderr`/
`wall_seconds`/`limit_hit` are all real, measured values either way — every property
`BaselineOutcome`/`StepFailure`/`CTestSummary` actually read is preserved.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from types import TracebackType

from packages.sandbox.container import ContainerJail, ContainerJailPolicy, ContainerJailResult
from packages.sandbox.errors import LimitKind, PathEscapeError
from packages.sandbox.jail import JailResult

#: `ContainerJailPolicy` never varies this — see `container.py::_docker_run_args`,
#: `-w /workspace` is unconditional. Kept as a named constant here rather than a
#: string literal repeated three times below.
_CONTAINER_WORKDIR = "/workspace"


class ContainerJailRunner:
    """A `Jail`-shaped wrapper around one `ContainerJail`. Use it exactly like `Jail`:

        policy = ContainerJailPolicy(image="pinned-build-toolchain@sha256:...")
        with ContainerJailRunner.create(policy, parent=workspace) as jail:
            result = run_variant(source, jail, Variant.BASELINE)  # unmodified call
    """

    def __init__(self, container_jail: ContainerJail) -> None:
        self._jail = container_jail

    @classmethod
    def create(
        cls,
        policy: ContainerJailPolicy,
        *,
        parent: Path | None = None,
        mission_ref: str = "unlabelled",
    ) -> ContainerJailRunner:
        return cls(ContainerJail.create(policy, parent=parent, mission_ref=mission_ref))

    @property
    def root(self) -> Path:
        return self._jail.root

    @property
    def policy(self) -> ContainerJailPolicy:
        return self._jail.policy

    @property
    def closed(self) -> bool:
        return self._jail.closed

    def __enter__(self) -> ContainerJailRunner:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def cancel(self) -> None:
        self._jail.cancel()

    def close(self) -> None:
        self._jail.close()

    # -- the Jail-compatible surface ------------------------------------------------

    def resolve(self, candidate: str | Path) -> Path:
        """Same containment check and exception type as `Jail.resolve()`, against the
        HOST side of this runner's one bind mount. `adapters/cpp/pipeline.py::
        run_reproducer` is the only caller in this codebase; it is not on BASELINE's
        own call path (`Variant.BASELINE` never calls `run_reproducer`) but is
        implemented here for the same reason `Jail.resolve()` exists: refuse before
        running, not after.
        """
        root = self._jail.root.resolve()
        raw = Path(candidate)
        resolved = (root / raw).resolve() if not raw.is_absolute() else raw.resolve()
        if resolved != root and root not in resolved.parents:
            raise PathEscapeError(
                f"{candidate!r} resolves to {resolved}, which is outside the jail at "
                f"{root}. Refused before the command ran."
            )
        return resolved

    def which(self, name: str) -> str:
        """Deliberately unresolved — see the module docstring's point 3. The pinned
        image's own `PATH`, not the orchestrator host's, is what resolves this at run
        time inside `run()`'s `sh -c` wrapper below."""
        return name

    def run(
        self,
        argv: list[str],
        *,
        cwd: str | Path | None = None,
        extra_env: dict[str, str] | None = None,
        raise_on_limit: bool = False,
    ) -> JailResult:
        """Run one command inside the container. Mirrors `Jail.run()`'s signature and
        return type so `adapters/cpp/pipeline.py`/`toolchain.py`/`ctest_report.py` need
        no changes beyond the type they accept.

        `extra_env` is refused rather than silently dropped: `ContainerJailPolicy.
        extra_env` is fixed once, at `ContainerJail.create()` time (`container.py`'s own
        docstring — a container does not inherit an ambient environment to layer a
        per-call override on top of the way a forked subprocess does), so there is no
        per-call channel to honour it through. Nothing on BASELINE's own call path
        passes `extra_env` today (`Variant.BASELINE` never calls `run_reproducer`, the
        one caller that does) — this raises loudly if that ever changes, the same
        "loud error instead of a silently-ignored feature" rule `orchestrator/
        verification.py::_jail_command_runner` already applies to `Jail.run()`'s
        missing `stdin` parameter.
        """
        if extra_env:
            raise ValueError(
                "ContainerJailRunner.run() has no per-call extra_env channel "
                "(ContainerJailPolicy.extra_env is fixed at ContainerJail.create() "
                "time); pass it via the policy instead of extending this call."
            )
        container_argv = self._wrap_for_cwd(argv, cwd)
        result = self._jail.run(container_argv, raise_on_limit=False)
        jail_result = self._to_jail_result(result)
        if raise_on_limit and jail_result.limit_hit is not LimitKind.NONE:
            raise self._limit_error(jail_result)
        return jail_result

    # -- internals --------------------------------------------------------------------

    def _translate(self, value: str) -> str:
        """Rewrite a host-absolute path under `self.root` to its container path.

        `self.root` (the host mkdtemp directory) and `/workspace` (this exact
        directory, bind-mounted `rw` — `container.py::_docker_run_args`, `-v
        {self._root}:/workspace:rw`) are the same bytes on disk under two different
        paths; this is the one mechanical fact that makes an argv value built from
        `jail.root` (every caller in `adapters/cpp/pipeline.py` builds `build_dir`,
        `verify_root`, and diff/junit paths this way) translatable at all. A value
        that is not a `self.root`-rooted absolute path is returned unchanged — either
        a bare command name (handled by `which()` returning it unresolved), or an
        external host path the caller was responsible for staging under `self.root`
        first (see the module docstring's point 2).
        """
        root_str = str(self._jail.root)
        if value == root_str:
            return _CONTAINER_WORKDIR
        if value.startswith(root_str + "/"):
            return _CONTAINER_WORKDIR + value[len(root_str) :]
        return value

    def _wrap_for_cwd(self, argv: list[str], cwd: str | Path | None) -> list[str]:
        translated_argv = [self._translate(str(part)) for part in argv]
        if cwd is None:
            container_cwd = _CONTAINER_WORKDIR
        else:
            container_cwd = self._translate(str(cwd))
        if container_cwd == _CONTAINER_WORKDIR:
            # No wrapper needed: `-w /workspace` (container.py::_docker_run_args) is
            # already the default working directory for every container this policy
            # starts.
            return translated_argv
        # `sh -c SCRIPT $0 $1 ...`: `$0` here is the (unused) script name convention,
        # `$1` is the cwd, and `shift` drops it so `"$@"` is exactly the original argv
        # from that point on — the standard way to pass argv through a `-c` wrapper
        # without re-quoting it into the script string itself (which would break on
        # any argument containing a space or shell metacharacter).
        return [
            "sh",
            "-c",
            'cd "$1" && shift && exec "$@"',
            "sh",
            container_cwd,
            *translated_argv,
        ]

    @staticmethod
    def _to_jail_result(result: ContainerJailResult) -> JailResult:
        return JailResult(
            argv=result.argv,
            exit_code=result.exit_code,
            signal_number=None,
            stdout=result.stdout,
            stderr=result.stderr,
            stdout_truncated=result.stdout_truncated,
            stderr_truncated=result.stderr_truncated,
            wall_seconds=result.wall_seconds,
            cpu_seconds=0.0,
            peak_memory_mb=0.0,
            limit_hit=result.limit_hit,
            limits_applied={},
            isolation_mode=result.isolation_mode,
        )

    def _limit_error(self, result: JailResult) -> Exception:
        from packages.sandbox.errors import (
            CpuExceededError,
            FileSizeExceededError,
            MemoryExceededError,
            WallClockExceededError,
        )

        kind = result.limit_hit
        policy = self._jail.policy
        if kind is LimitKind.WALL_CLOCK:
            return WallClockExceededError(policy.wall_clock_seconds)
        if kind is LimitKind.MEMORY:
            return MemoryExceededError(policy.memory_mb * 1024 * 1024, result.summary())
        if kind is LimitKind.CPU:
            return CpuExceededError(int(policy.cpu_limit))
        if kind is LimitKind.FILE_SIZE:
            return FileSizeExceededError(0)
        return WallClockExceededError(policy.wall_clock_seconds)


def shlex_join_for_log(argv: list[str]) -> str:
    """Debug/log-friendly rendering of a translated argv — not used on any evidence
    path (that stays `result.argv`, the real thing the container ran), just handy
    while wiring this up by hand."""
    return shlex.join(argv)
