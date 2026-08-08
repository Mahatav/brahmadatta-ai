"""Subprocess jail — the D3 isolation fallback (#81), not the container path (#15).

**State this plainly wherever it is reported, because it is materially weaker than the
rootless container it stands in for.** `contracts.enums.IsolationMode` exists precisely so
the weaker path is inexpressible as the stronger one (D-041), and
`SubstitutionKind.SUBPROCESS_JAIL_ISOLATION` exists so a run that used it says so in the
evidence bundle.

What this jail does
-------------------

* **No shell.** Fixed ``argv`` lists, ``shell=False``, no string interpolation into a
  command line. A target-controlled filename cannot become a command.
* **Working-directory jail.** Every path the caller hands in is ``resolve()``-d and
  rejected if it lands outside :attr:`Jail.root`. Symlinks are resolved *before* the
  check, so a symlink out of the tree is caught rather than followed.
* **Scrubbed environment.** Allowlist, not denylist. The child sees ``PATH`` and a handful
  of locale/temp variables rooted inside the jail — not the operator's environment, not
  credentials that happen to be exported in the shell that started the mission.
* **Resource limits.** ``RLIMIT_CPU``, ``RLIMIT_FSIZE``, ``RLIMIT_NOFILE``,
  ``RLIMIT_CORE=0``, and where the platform supports it ``RLIMIT_AS`` and ``RLIMIT_NPROC``.
  Which ones actually took effect is recorded in :attr:`JailResult.limits_applied` rather
  than assumed — see "what it does not protect against" below.
* **Hard wall-clock timeout.** The child gets its own session (``start_new_session=True``),
  so on timeout the whole *process group* is signalled — ``SIGTERM``, a grace period, then
  ``SIGKILL``. A build that forks a compiler and hangs does not survive as an orphan
  burning the competition clock.
* **Bounded output.** stdout and stderr go to files under the jail, and only a head/tail
  window is read back into memory. A target that prints a gigabyte cannot exhaust the
  worker's RAM, and the full log is still on disk as an artifact.

What it does NOT protect against
--------------------------------

This list is the point of the module docstring. Do not let it drift.

1. **Network access.** Nothing here blocks egress. On Linux that needs a network
   namespace; on macOS it needs a privileged filter. A target's build script can reach the
   internet. Container isolation (#15) is what closes this, and D-028 puts the egress
   control on the worker's network topology, not here.
2. **Filesystem reads outside the jail.** The *cwd* is jailed and paths the adapter passes
   are jailed. The child process itself is not chrooted and can ``open("/etc/passwd")``.
   Writes are only constrained by ordinary user permissions.
3. **A hostile target.** ``RLIMIT_NPROC`` is per-user, not per-process-tree, so on a shared
   account a fork bomb degrades the host before it hits the limit. There is no seccomp
   filter, no user namespace, no capability drop.
4. **``RLIMIT_AS`` on macOS.** Setting it reliably breaks unrelated allocators, so it is
   skipped on Darwin. Memory is therefore *unbounded* there, and
   :attr:`JailResult.limits_applied` will not list ``RLIMIT_AS``. Check the field; do not
   assume the limit.
5. **Reproducibility.** Host toolchains are whatever the host has. Pinning is a container
   property (see `adapters/cpp/toolchain.py`), and this path cannot deliver it.

Therefore: **fuzzing untrusted code on top of this jail is not sanctioned.** #15 is
required before D4 fuzzing, and no output of this module may be described as containerised.
"""

from __future__ import annotations

import os
import resource
import signal
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .errors import JailEscape

__all__ = [
    "ISOLATION_MODE",
    "ISOLATION_UNPROTECTED_AGAINST",
    "Jail",
    "JailLimits",
    "JailResult",
]

#: Mirrors `contracts.enums.IsolationMode.SUBPROCESS_JAIL`. Duplicated as a plain string
#: rather than imported so this package never pulls Django into a worker process; the
#: values are asserted equal by
#: `adapters/cpp/tests/test_contract_conformance.py::test_isolation_mode_matches_contract`.
ISOLATION_MODE = "SUBPROCESS_JAIL"

#: Machine-readable form of the "does not protect against" list above, so an evidence
#: report can carry the caveats instead of a reader being expected to have read this file.
ISOLATION_UNPROTECTED_AGAINST: tuple[str, ...] = (
    "network egress from the target's build and test processes",
    "filesystem reads outside the jail root",
    "a hostile target: no seccomp, no user namespace, no capability drop",
    "memory exhaustion on Darwin, where RLIMIT_AS is deliberately not applied",
    "toolchain reproducibility: the host toolchain is whatever the host has",
)

_GRACE_SECONDS = 5.0

#: Environment the child is allowed to inherit. Everything else is dropped.
_ENV_ALLOWLIST = ("PATH",)


@dataclass(frozen=True, slots=True)
class JailLimits:
    """Resource ceilings. Defaults are sized for a small CMake project, not a kernel."""

    wall_clock_seconds: float = 900.0
    cpu_seconds: int = 900
    address_space_bytes: int = 4 * 1024**3
    file_size_bytes: int = 512 * 1024**2
    max_processes: int = 512
    open_files: int = 4096
    #: How much of each stream is read back into memory. The full log stays on disk.
    max_captured_bytes: int = 4 * 1024**2

    def __post_init__(self) -> None:
        if self.wall_clock_seconds <= 0:
            raise ValueError(
                "wall_clock_seconds must be positive: a jail with no timeout is not a jail"
            )
        if self.max_captured_bytes <= 0:
            raise ValueError("max_captured_bytes must be positive")


@dataclass(frozen=True, slots=True)
class JailResult:
    """Everything a caller needs to build a `StepFailure` without re-reading the log."""

    argv: tuple[str, ...]
    cwd: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool
    stdout_path: str
    stderr_path: str
    stdout_truncated: bool
    stderr_truncated: bool
    #: RLIMIT_* names that were actually set in the child. Read it; do not assume.
    limits_applied: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


def _read_bounded(path: Path, limit: int) -> tuple[str, bool]:
    """Read at most ``limit`` bytes, keeping the head and the tail.

    The head carries the command echo and the first error; the tail carries the summary
    line the build system prints last. The middle of a long log is the part nobody reads.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return "", False
    with path.open("rb") as handle:
        if size <= limit:
            return handle.read().decode("utf-8", errors="replace"), False
        half = limit // 2
        head = handle.read(half)
        handle.seek(size - half)
        tail = handle.read(half)
    dropped = size - 2 * half
    marker = f"\n\n... [{dropped} bytes elided by the jail's output cap] ...\n\n".encode()
    return (head + marker + tail).decode("utf-8", errors="replace"), True


def _apply_limits(limits: JailLimits) -> None:
    """Runs in the forked child, between ``fork`` and ``exec``.

    Anything that raises here kills the child before it execs, which is the safe direction:
    a limit that could not be set means the command does not run.
    """
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (limits.cpu_seconds, limits.cpu_seconds))
    resource.setrlimit(resource.RLIMIT_FSIZE, (limits.file_size_bytes, limits.file_size_bytes))
    resource.setrlimit(resource.RLIMIT_NOFILE, (limits.open_files, limits.open_files))
    if sys.platform != "darwin":
        resource.setrlimit(
            resource.RLIMIT_AS, (limits.address_space_bytes, limits.address_space_bytes)
        )
        if hasattr(resource, "RLIMIT_NPROC"):
            resource.setrlimit(resource.RLIMIT_NPROC, (limits.max_processes, limits.max_processes))


def _limit_names() -> tuple[str, ...]:
    """The limits `_apply_limits` will actually set on this platform."""
    names = ["RLIMIT_CORE", "RLIMIT_CPU", "RLIMIT_FSIZE", "RLIMIT_NOFILE"]
    if sys.platform != "darwin":
        names.append("RLIMIT_AS")
        if hasattr(resource, "RLIMIT_NPROC"):
            names.append("RLIMIT_NPROC")
    return tuple(names)


class Jail:
    """A working directory that commands are confined to, plus the limits they run under.

    Construct one per mission workspace. :meth:`run` is the only way to execute anything in
    this package — nothing else in `adapters/cpp` calls `subprocess` directly, which is
    what makes "every build ran jailed" checkable by grep rather than by review.
    """

    def __init__(self, root: Path | str, limits: JailLimits | None = None) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise JailEscape(f"jail root does not exist or is not a directory: {self.root}")
        self.limits = limits or JailLimits()
        self.log_dir = self.root / ".brahmadatta" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._home = self.root / ".brahmadatta" / "home"
        self._tmp = self.root / ".brahmadatta" / "tmp"
        for directory in (self._home, self._tmp):
            directory.mkdir(parents=True, exist_ok=True)

    # -- path jail ---------------------------------------------------------------

    def contains(self, path: Path | str) -> bool:
        """Whether ``path`` resolves inside the jail root. Symlinks resolved first."""
        try:
            resolved = Path(path).resolve()
        except OSError:
            return False
        return resolved == self.root or self.root in resolved.parents

    def resolve_inside(self, path: Path | str) -> Path:
        """Resolve ``path``, or raise :class:`JailEscape` if it escapes the root.

        Called on every path before it reaches an argv. Demonstrated by
        `test_jail.py::test_a_symlink_out_of_the_jail_is_rejected`.
        """
        resolved = Path(path).resolve()
        if not self.contains(resolved):
            raise JailEscape(
                f"path escapes the jail\n  path: {path}\n  resolves to: {resolved}\n  jail root: {self.root}"
            )
        return resolved

    def child_env(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        """Allowlisted environment for the child, with HOME and TMPDIR inside the jail."""
        env = {name: os.environ[name] for name in _ENV_ALLOWLIST if name in os.environ}
        env.setdefault("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
        env.update(
            {
                "HOME": str(self._home),
                "TMPDIR": str(self._tmp),
                "TEMP": str(self._tmp),
                "TMP": str(self._tmp),
                "LANG": "C",
                "LC_ALL": "C",
                "TERM": "dumb",
                # Deterministic, machine-readable build output.
                "CLICOLOR": "0",
                "NO_COLOR": "1",
            }
        )
        if extra:
            env.update(extra)
        return env

    # -- execution ---------------------------------------------------------------

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | str | None = None,
        env: Mapping[str, str] | None = None,
        label: str = "run",
        timeout_seconds: float | None = None,
    ) -> JailResult:
        """Run ``argv`` inside the jail. Never raises on a non-zero exit — that is the
        caller's judgement to make — but always raises on a jail escape.
        """
        if not argv:
            raise ValueError("argv must not be empty")
        if any(not isinstance(part, str) for part in argv):
            raise TypeError("argv must be a sequence of str; no implicit stringification")

        work_dir = self.resolve_inside(cwd) if cwd is not None else self.root
        if not work_dir.is_dir():
            raise JailEscape(f"working directory does not exist inside the jail: {work_dir}")

        stamp = f"{label}-{time.strftime('%Y%m%dT%H%M%S')}-{os.getpid()}"
        stdout_path = self.log_dir / f"{stamp}.out"
        stderr_path = self.log_dir / f"{stamp}.err"
        wall = self.limits.wall_clock_seconds if timeout_seconds is None else timeout_seconds

        limits = self.limits
        started = time.monotonic()
        timed_out = False

        with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
            process = subprocess.Popen(  # noqa: S603 - fixed argv, shell=False, jailed cwd
                list(argv),
                cwd=str(work_dir),
                env=self.child_env(env),
                stdout=out,
                stderr=err,
                stdin=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,
                preexec_fn=lambda: _apply_limits(limits),
            )
            try:
                exit_code = process.wait(timeout=wall)
            except subprocess.TimeoutExpired:
                timed_out = True
                exit_code = _terminate_group(process)

        duration = time.monotonic() - started
        stdout, stdout_truncated = _read_bounded(stdout_path, limits.max_captured_bytes)
        stderr, stderr_truncated = _read_bounded(stderr_path, limits.max_captured_bytes)

        return JailResult(
            argv=tuple(argv),
            cwd=str(work_dir),
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
            timed_out=timed_out,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            limits_applied=_limit_names(),
        )


def _terminate_group(process: subprocess.Popen[bytes]) -> int:
    """SIGTERM the child's whole process group, then SIGKILL what survives.

    ``start_new_session=True`` made the child a session leader, so its pid is its process
    group id and every compiler it forked is in that group. Signalling the group rather
    than the pid is what stops a hung `make` leaving `cc` processes behind.
    """
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(os.getpgid(process.pid), sig)
        except (ProcessLookupError, PermissionError):
            break
        try:
            return process.wait(timeout=_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            continue
    try:
        return process.wait(timeout=_GRACE_SECONDS)
    except subprocess.TimeoutExpired:  # pragma: no cover - the kernel ignored SIGKILL
        return -int(signal.SIGKILL)
