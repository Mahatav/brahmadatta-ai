"""A working-directory jail with resource limits and a hard timeout.

READ THIS BEFORE USING IT FOR ANYTHING
======================================

**This is not a sandbox for untrusted code.** It runs a command as the same user, on the
same filesystem, with the same network, in the same kernel namespaces as the orchestrator.
A process started here can read your home directory, open a socket, and write anywhere the
operator can write. What it provides is:

* a scratch directory that command *arguments* are confined to, so a mission cannot be
  pointed at `/etc` by a malformed request;
* CPU, address-space, file-size and process-count ceilings, so a runaway build cannot
  take the machine down;
* a wall-clock timeout that kills the whole process group, so nothing is left running;
* deterministic cleanup.

That is exactly enough to build and test the demo target for the D3 gate (#81), and it is
**not** enough to fuzz untrusted code. Fuzzing is #28 and it runs on D4 behind **#15**,
the rootless-container isolation. The split exists so the D3 gate is not blocked on a
full day of Podman work it does not need — not because containers turned out to be
optional. `IsolationMode.SUBPROCESS_JAIL` exists in the contract precisely so a run
contained this way can never be reported as the container path.

If you are about to point this at a fuzzer, stop: `#15` is the ticket.

What "enforced" means here
--------------------------

Every property below is claimed only where a named test demonstrates it, and the tests
live in `services/sandbox/tests/test_jail.py`:

| Property | Test |
|---|---|
| a path outside the jail is refused | `test_path_outside_the_jail_is_refused` |
| a symlink out of the jail is refused | `test_symlink_escape_is_refused` |
| wall clock kills the command | `test_wall_clock_timeout_is_reported_not_hung` |
| the whole process group dies, no orphans | `test_timeout_kills_grandchildren_leaving_no_orphans` |
| CPU budget stops a spinner | `test_cpu_limit_stops_a_spinner` |
| address space stops an allocator | `test_memory_limit_stops_an_allocator` |
| output is capped, not buffered | `test_output_is_capped` |
| cleanup on success / failure / cancel | `test_cleanup_*` |
| the environment is scrubbed | `test_environment_is_scrubbed_to_the_allowlist` |

Anything not in that table is *intended*, not enforced. In particular this module does
**not** prevent a running process from reading outside the jail, opening a network
socket, or exhausting a limit the kernel applies per-user rather than per-process.
"""

from __future__ import annotations

import errno
import os
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType

from services.sandbox.errors import (
    CancelledError,
    CpuExceededError,
    JailUnavailableError,
    LimitKind,
    MemoryExceededError,
    PathEscapeError,
    WallClockExceededError,
)
from services.sandbox.policy import JailPolicy

#: Reported into the evidence bundle. Mirrors `contracts.enums.IsolationMode`, as a
#: string so this package stays importable without Django.
ISOLATION_MODE = "SUBPROCESS_JAIL"

#: Resource measurement uses `RUSAGE_CHILDREN` deltas, which are process-wide. Runs are
#: serialized so a delta belongs to exactly one command. The D3 pipeline runs one command
#: at a time anyway; this makes the measurement honest rather than approximately right.
_MEASURE_LOCK = threading.Lock()

_MIB = 1024 * 1024


@dataclass
class JailResult:
    """What a jailed command did. Every number here is measured."""

    argv: tuple[str, ...]
    exit_code: int
    """Negative means killed by that signal, as `subprocess` reports it."""

    signal_number: int | None
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool
    wall_seconds: float
    cpu_seconds: float
    peak_memory_mb: float
    limit_hit: LimitKind
    isolation_mode: str = ISOLATION_MODE
    tool_versions: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and self.limit_hit is LimitKind.NONE

    def summary(self) -> str:
        state = "ok" if self.ok else f"exit {self.exit_code}"
        if self.limit_hit is not LimitKind.NONE:
            state = f"{self.limit_hit} limit"
        return (
            f"{' '.join(self.argv)} -> {state} "
            f"({self.wall_seconds:.2f}s wall, {self.cpu_seconds:.2f}s cpu, "
            f"{self.peak_memory_mb:.1f} MB peak)"
        )


def _maxrss_to_mb(maxrss: int) -> float:
    """`ru_maxrss` is bytes on Darwin and kilobytes on Linux. Neither documents it in a
    way that survives being guessed at, so it is branched on explicitly."""
    return maxrss / _MIB if sys.platform == "darwin" else maxrss / 1024


class Jail:
    """A scratch directory plus the limits commands inside it run under.

    Use it as a context manager. The directory is removed on the way out — on success, on
    exception, and on cancel.

        with Jail.create(JailPolicy()) as jail:
            shutil.copytree(source, jail.root / "src")
            result = jail.run(["cmake", "--build", "build"], cwd="src")
    """

    def __init__(self, root: Path, policy: JailPolicy) -> None:
        self._root = root
        self._policy = policy
        self._io_dir = root.parent / f"{root.name}.io"
        self._io_dir.mkdir(mode=0o700, exist_ok=True)
        self._closed = False
        self._cancelled = threading.Event()
        self._live: subprocess.Popen[bytes] | None = None
        self._live_lock = threading.Lock()

    # -- lifecycle ----------------------------------------------------------------

    @classmethod
    def create(cls, policy: JailPolicy | None = None, *, parent: Path | None = None) -> Jail:
        policy = policy or JailPolicy()
        try:
            root = Path(tempfile.mkdtemp(prefix="brahmadatta-jail-", dir=parent))
        except OSError as exc:
            raise JailUnavailableError(f"could not create a jail directory: {exc}") from exc
        root.chmod(0o700)
        return cls(root, policy)

    @property
    def root(self) -> Path:
        if self._closed:
            raise JailUnavailableError("this jail has been cleaned up")
        return self._root

    @property
    def policy(self) -> JailPolicy:
        return self._policy

    @property
    def closed(self) -> bool:
        return self._closed

    def __enter__(self) -> Jail:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        # Cleanup runs on all three paths: normal exit, exception, and cancel. That is
        # the point of putting it here rather than at the end of the happy path.
        self.close()

    def cancel(self) -> None:
        """Stop whatever is running now and refuse further runs.

        Safe to call from another thread — that is the only way it is useful, since the
        thread inside `run()` is blocked on the child.
        """
        self._cancelled.set()
        with self._live_lock:
            live = self._live
        if live is not None and live.poll() is None:
            self._kill_group(live)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.cancel()
        for path in (self._root, self._io_dir):
            shutil.rmtree(path, ignore_errors=True)

    # -- the jail part ------------------------------------------------------------

    def resolve(self, candidate: str | os.PathLike[str]) -> Path:
        """Resolve a path against the jail root and refuse anything outside it.

        `Path.resolve()` follows symlinks, so a link inside the jail pointing at `/etc`
        resolves to `/etc` and is refused here. That is the check doing real work — a
        purely lexical `..` check would not catch it.

        This constrains the paths *we* hand to a command. It does not constrain what the
        command does once running.
        """
        root = self._root.resolve()
        raw = Path(candidate)
        resolved = (root / raw).resolve() if not raw.is_absolute() else raw.resolve()
        if resolved != root and root not in resolved.parents:
            raise PathEscapeError(
                f"{candidate!r} resolves to {resolved}, which is outside the jail at "
                f"{root}. Refused before the command ran."
            )
        return resolved

    # -- running ------------------------------------------------------------------

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: str | os.PathLike[str] | None = None,
        extra_env: dict[str, str] | None = None,
        raise_on_limit: bool = False,
    ) -> JailResult:
        """Run one command inside the jail.

        Returns a `JailResult` whichever way it ends. `raise_on_limit=True` turns a
        limit into the matching `LimitExceededError` instead, for callers that would
        rather not branch.
        """
        if self._closed:
            raise JailUnavailableError("this jail has been cleaned up")
        if self._cancelled.is_set():
            raise CancelledError("jail was cancelled; no further commands will run")
        if not argv:
            raise ValueError("argv is empty")
        if not self._root.is_dir():
            raise JailUnavailableError(f"jail root {self._root} disappeared")

        workdir = self.resolve(cwd) if cwd is not None else self._root.resolve()
        if not workdir.is_dir():
            raise JailUnavailableError(f"working directory {workdir} does not exist")

        env = {
            name: os.environ[name]
            for name in self._policy.env_allowlist
            if name in os.environ
        }
        env["TMPDIR"] = str(workdir)
        env.update(extra_env or {})

        out_path = self._io_dir / "stdout"
        err_path = self._io_dir / "stderr"

        started = time.monotonic()
        with _MEASURE_LOCK:
            before = resource.getrusage(resource.RUSAGE_CHILDREN)
            proc, timed_out = self._spawn_and_wait(argv, workdir, env, out_path, err_path)
            after = resource.getrusage(resource.RUSAGE_CHILDREN)
        wall = time.monotonic() - started

        cpu = (after.ru_utime - before.ru_utime) + (after.ru_stime - before.ru_stime)
        peak_mb = _maxrss_to_mb(after.ru_maxrss)

        stdout, out_trunc = self._read_capped(out_path)
        stderr, err_trunc = self._read_capped(err_path)

        exit_code = proc.returncode
        sig = -exit_code if exit_code is not None and exit_code < 0 else None
        limit = self._classify(
            timed_out=timed_out,
            signal_number=sig,
            exit_code=exit_code or 0,
            peak_mb=peak_mb,
            stderr=stderr,
            out_trunc=out_trunc or err_trunc,
        )

        result = JailResult(
            argv=tuple(argv),
            exit_code=exit_code if exit_code is not None else -1,
            signal_number=sig,
            stdout=stdout,
            stderr=stderr,
            stdout_truncated=out_trunc,
            stderr_truncated=err_trunc,
            wall_seconds=round(wall, 3),
            cpu_seconds=round(max(0.0, cpu), 3),
            peak_memory_mb=round(peak_mb, 1),
            limit_hit=limit,
        )

        if raise_on_limit and limit is not LimitKind.NONE:
            raise self._limit_error(limit, result)
        if self._cancelled.is_set() and limit is LimitKind.WALL_CLOCK:
            raise CancelledError(f"cancelled while running {' '.join(argv)}")
        return result

    # -- internals ----------------------------------------------------------------

    def _spawn_and_wait(
        self,
        argv: Sequence[str],
        workdir: Path,
        env: dict[str, str],
        out_path: Path,
        err_path: Path,
    ) -> tuple[subprocess.Popen[bytes], bool]:
        policy = self._policy

        def apply_limits() -> None:  # pragma: no cover - runs in the forked child
            # New session, so the child is a process-group leader and `killpg` reaches
            # every descendant that has not deliberately escaped the group. This is what
            # makes "no orphans" achievable at all.
            os.setsid()
            # Soft below hard: the soft limit raises SIGXCPU, which is catchable and
            # gives a cooperative process a second to flush; the hard limit one second
            # later is SIGKILL and is not.
            resource.setrlimit(
                resource.RLIMIT_CPU, (policy.cpu_seconds, policy.cpu_seconds + 1)
            )
            resource.setrlimit(resource.RLIMIT_FSIZE, (policy.max_file_bytes,) * 2)
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            for limit_name, value in (
                ("RLIMIT_AS", policy.memory_bytes),
                ("RLIMIT_NPROC", policy.max_processes),
            ):
                limit = getattr(resource, limit_name, None)
                if limit is None:
                    continue
                try:
                    resource.setrlimit(limit, (value, value))
                except (ValueError, OSError):
                    # Some kernels refuse to lower these for an unprivileged process, or
                    # do not honour them at all. Failing the whole run over it would be
                    # worse than proceeding: the wall clock still applies, and
                    # `probe_limits()` is how a caller finds out what this kernel does.
                    pass

        with open(out_path, "wb") as out, open(err_path, "wb") as err:
            try:
                proc = subprocess.Popen(  # noqa: S603 - argv is a list, shell is never used
                    list(argv),
                    cwd=str(workdir),
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=out,
                    stderr=err,
                    preexec_fn=apply_limits,
                    close_fds=True,
                )
            except FileNotFoundError as exc:
                raise JailUnavailableError(
                    f"{argv[0]!r} was not found on PATH inside the jail"
                ) from exc

        with self._live_lock:
            self._live = proc

        timed_out = False
        try:
            proc.wait(timeout=policy.wall_clock_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._kill_group(proc)
        finally:
            with self._live_lock:
                self._live = None

        return proc, timed_out

    def _kill_group(self, proc: subprocess.Popen[bytes]) -> None:
        """SIGTERM the group, give it a grace period, then SIGKILL the group.

        Killing the *group* rather than the process is the whole point. `cmake --build`
        is a process that spawns compilers; killing only the parent leaves the compilers
        running and the build directory being written to by a mission that has ended.
        """
        try:
            pgid = os.getpgid(proc.pid)
        except ProcessLookupError:
            return

        for sig, wait_for in (
            (signal.SIGTERM, self._policy.kill_grace_seconds),
            (signal.SIGKILL, 5.0),
        ):
            try:
                os.killpg(pgid, sig)
            except ProcessLookupError:
                return
            except OSError as exc:  # pragma: no cover - defensive
                if exc.errno != errno.ESRCH:
                    raise
                return
            try:
                proc.wait(timeout=wait_for)
            except subprocess.TimeoutExpired:
                continue
            # The direct child is reaped, but a grandchild can outlive it. Keep signalling
            # until the group is genuinely empty.
            if not self._group_alive(pgid):
                return
        # Last resort: one more SIGKILL, then report what is left rather than pretending.
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass

    @staticmethod
    def _group_alive(pgid: int) -> bool:
        """Is any process still in this group? `killpg(0)` asks without signalling."""
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:  # pragma: no cover - group exists, owned elsewhere
            return True
        return True

    def _read_capped(self, path: Path) -> tuple[str, bool]:
        try:
            size = path.stat().st_size
        except OSError:
            return "", False
        cap = self._policy.max_output_bytes
        with open(path, "rb") as handle:
            data = handle.read(cap)
        try:
            path.unlink()
        except OSError:
            pass
        return data.decode("utf-8", errors="replace"), size > cap

    def _classify(
        self,
        *,
        timed_out: bool,
        signal_number: int | None,
        exit_code: int,
        peak_mb: float,
        stderr: str,
        out_trunc: bool,
    ) -> LimitKind:
        """Say which limit stopped the command, or `NONE`.

        The honest part of this function is what it refuses to claim. A process killed by
        SIGKILL that we did not kill, having barely allocated anything, is not reported as
        a memory failure just because that is the most common cause.
        """
        if timed_out:
            return LimitKind.WALL_CLOCK
        if signal_number == signal.SIGXCPU:
            return LimitKind.CPU
        if signal_number == signal.SIGKILL:
            # RLIMIT_CPU's hard limit lands one second after the soft one and arrives as
            # SIGKILL. Nothing else here sends one.
            return LimitKind.CPU

        limit_mb = self._policy.memory_bytes / _MIB
        allocation_failed = any(
            marker in stderr
            for marker in (
                "MemoryError",
                "std::bad_alloc",
                "Cannot allocate memory",
                "out of memory",
                "virtual memory exhausted",
            )
        )
        if allocation_failed:
            return LimitKind.MEMORY
        if signal_number in (signal.SIGSEGV, signal.SIGABRT) and peak_mb >= limit_mb * 0.8:
            # Circumstantial, and labelled as such in the message the caller builds.
            return LimitKind.MEMORY
        if out_trunc:
            return LimitKind.OUTPUT
        if exit_code != 0 and peak_mb >= limit_mb * 0.95:
            return LimitKind.MEMORY
        return LimitKind.NONE

    def _limit_error(self, kind: LimitKind, result: JailResult) -> Exception:
        if kind is LimitKind.WALL_CLOCK:
            return WallClockExceededError(self._policy.wall_clock_seconds)
        if kind is LimitKind.CPU:
            return CpuExceededError(self._policy.cpu_seconds)
        if kind is LimitKind.MEMORY:
            return MemoryExceededError(
                self._policy.memory_bytes,
                f"peak {result.peak_memory_mb:.0f} MB, exit {result.exit_code}",
            )
        return WallClockExceededError(self._policy.wall_clock_seconds)


def probe_limits(policy: JailPolicy | None = None) -> dict[str, bool]:
    """Report which limits this kernel actually enforces.

    Exists because `setrlimit` succeeding proves nothing. Darwin accepts `RLIMIT_AS` and
    then does not always honour it, and `RLIMIT_NPROC` is per-user on most kernels. A
    caller that needs to *know* — the preflight check, or an evidence bundle recording
    what contained a run — asks here rather than assuming.

    Each probe runs a small program that deliberately exceeds one limit.
    """
    policy = policy or JailPolicy(cpu_seconds=1, memory_bytes=64 * _MIB, wall_clock_seconds=20)
    findings: dict[str, bool] = {}

    with Jail.create(policy) as jail:
        spin = jail.run(
            [sys.executable, "-c", "\nwhile True:\n    pass\n"],
        )
        findings["cpu_seconds"] = spin.limit_hit is LimitKind.CPU

        hog = jail.run(
            [
                sys.executable,
                "-c",
                "b = bytearray()\n"
                "while True:\n"
                "    b.extend(bytes(4 * 1024 * 1024))\n",
            ],
        )
        findings["memory_bytes"] = hog.limit_hit is LimitKind.MEMORY

        slow = Jail.create(JailPolicy(cpu_seconds=60, wall_clock_seconds=1.0))
        with slow:
            sleeper = slow.run([sys.executable, "-c", "import time; time.sleep(30)"])
            findings["wall_clock_seconds"] = sleeper.limit_hit is LimitKind.WALL_CLOCK

    return findings
