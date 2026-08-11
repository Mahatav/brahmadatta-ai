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
live in `packages/sandbox/tests/test_jail.py`:

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
| `limits_applied` is measured per run, not guessed from the platform (D-054) | `test_limits_applied_is_a_real_per_run_measurement` |

**Two open gaps, ruled on and gated rather than silently accepted (D-056).** Both require an
adversarial target and are not reachable through `#16`/`#17`/`#27`'s ordinary `cmake`/`ctest`
invocation — they are why this module cannot be pointed at `#28`'s fuzzing worker until both
close:

| Gap | Condition to trigger it | Tracking |
|---|---|---|
| **SEC-38** — a detached descendant can survive `_sweep_detached_descendants` under rapid, repeated fork-and-detach (~1-in-10 to 1-in-15 in testing), reproducing at the real default `kill_grace_seconds=5.0`. The final sweep's re-walk is anchored on this jail's own child pid, which is already dead by the time of that walk, so a descendant reparenting between two poll iterations can go briefly invisible. | A target that forks and `setsid()`s repeatedly near the kill window — the exact pattern a hostile or malformed fuzz target can produce, not ordinary build/test behaviour. | `#28`'s Definition of Done. A single-detachment test is not sufficient re-verification for this — the regression test must exercise *rapid, repeated* detachment. |
| **SEC-35** — `_classify`'s `SIGXFSZ` branch does not fire for a target that ignores or handles that signal. CPython does so by default (`signal.getsignal(SIGXFSZ) == SIG_IGN` at interpreter start), so a Python-based target genuinely stopped by `RLIMIT_FSIZE` reports `limit_hit == NONE` instead. The jail still stops the process — this is an evidence-accuracy gap, not an isolation escape. | A Python-based (or any `SIGXFSZ`-ignoring) target actually hitting `max_file_bytes`. | `#28`'s Definition of Done. The fix needs the same stderr/on-disk-size fallback `MEMORY`'s branch already uses, verified against a Python target, not `dd`. |

**No caller may point this jail at generated or fuzzer-derived input before both close.**

Anything not in that table is *intended*, not enforced. In particular this module does
**not** prevent a running process from reading outside the jail, opening a network
socket, or exhausting a limit the kernel applies per-user rather than per-process.
"""

from __future__ import annotations

import errno
import json
import os
import resource
import select
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

from packages.sandbox.errors import (
    CancelledError,
    CpuExceededError,
    FileSizeExceededError,
    JailUnavailableError,
    LimitKind,
    MemoryExceededError,
    PathEscapeError,
    WallClockExceededError,
)
from packages.sandbox.policy import JailPolicy

#: Reported into the evidence bundle. Mirrors `contracts.enums.IsolationMode`, as a
#: string so this package stays importable without Django.
ISOLATION_MODE = "SUBPROCESS_JAIL"

#: Resource measurement uses `RUSAGE_CHILDREN` deltas, which are process-wide. Runs are
#: serialized so a delta belongs to exactly one command. The D3 pipeline runs one command
#: at a time anyway; this makes the measurement honest rather than approximately right.
_MEASURE_LOCK = threading.Lock()

_MIB = 1024 * 1024


def _proc_descendants(root_pid: int) -> set[int]:
    """Every process still descended from `root_pid`, found by walking `/proc`'s
    parent-id links rather than by process group or session membership.

    This is what makes the SEC-33 fix work: `os.setsid()` gives a process a new process
    group and session, escaping `killpg()`, but it cannot and does not change the
    process's parent id — that is fixed by the kernel at fork time. Walking by ppid finds
    a detached process anyway.

    Linux only (`/proc/*/stat`). Returns an empty set on any other platform or if `/proc`
    is unreadable, rather than raising — a caller that cannot do the sweep needs to know
    that as "found nothing", the same shape as "there was nothing to find", not as a
    crash in a cleanup path that is often running during error handling already.

    Does not catch a process that double-forks to reparent itself under init — that
    changes the parent id itself, not just the group, and is a harder problem this
    function does not claim to solve. See `packages/sandbox/README.md`.
    """
    if sys.platform != "linux":
        return set()

    children: dict[int, list[int]] = {}
    try:
        entries = os.listdir("/proc")
    except OSError:
        return set()

    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        try:
            stat = Path(f"/proc/{pid}/stat").read_text()
        except OSError:
            # Gone between listdir() and read() — a race inherent to /proc, not an
            # error. It simply is not a descendant anymore.
            continue
        # `comm` (the second field) is wrapped in parens and can itself contain spaces
        # or parens, so the reliable split point is the *last* ')' in the line, not the
        # first whitespace. Everything after it is space-separated, and ppid is field 4
        # overall, i.e. the second field after that split.
        after_comm = stat.rpartition(")")[2].split()
        if len(after_comm) < 2:
            continue
        try:
            ppid = int(after_comm[1])
        except ValueError:
            continue
        children.setdefault(ppid, []).append(pid)

    found: set[int] = set()
    frontier = [root_pid]
    while frontier:
        pid = frontier.pop()
        for child in children.get(pid, ()):
            if child not in found:
                found.add(child)
                frontier.append(child)
    return found


def _pid_running(pid: int) -> bool:
    """Is this pid still doing something — running, not exited-but-unreaped?

    A zombie (`/proc/<pid>/stat` state `Z`) has already terminated; the entry left
    behind is bookkeeping for whichever process now owns it to collect with
    `waitpid()`. `_sweep_detached_descendants` only ever reaches a pid after this jail's
    own direct child — its original parent — is already dead, so whatever it reparented
    to (the pid namespace's init, or an ancestor with `PR_SET_CHILD_SUBREAPER` set) is
    not this jail and never was. SIGKILL already reached a zombie; it holds no CPU, no
    memory beyond the process-table slot itself, and does nothing further. Reporting one
    as a surviving orphan would be reporting a property this code cannot affect and does
    not need to — see `packages/sandbox/README.md` for the residual "zombie slot, not a
    running process" gap this leaves, and why it is not the same failure as SEC-33.

    Falls back to a plain existence check off Linux, or if `/proc` cannot be read, which
    is the more conservative answer where the zombie/running distinction is unavailable.
    """
    if sys.platform == "linux":
        try:
            stat = Path(f"/proc/{pid}/stat").read_text()
        except OSError:
            return False  # no /proc entry at all: not a zombie, just gone
        state = stat.rpartition(")")[2].split()
        if state and state[0] == "Z":
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # pragma: no cover - exists, owned elsewhere
        return True
    return True


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
    limits_applied: dict[str, bool] = field(default_factory=dict)
    """Which resource limits actually took effect in *this* run — `{"memory_bytes":
    True, "max_processes": False}` and so on. Measured, not inferred: the child records
    the real outcome of each `setrlimit()` call before it execs, and that outcome is
    carried back across the fork boundary on the same pipe the exit status already
    crosses (D-054). Never derived from the platform name — a locked-down CI runner can
    refuse a limit for reasons that have nothing to do with the OS, and a name is not a
    measurement.

    Empty means the measurement itself could not be recovered (the child never reached
    that point), not that nothing was applied. `probe_limits()` is the pre-flight,
    ahead-of-any-mission version of the same question; this is the per-run,
    after-the-fact record — they answer different questions and both are worth having.
    """
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
            proc, timed_out, limits_applied = self._spawn_and_wait(
                argv, workdir, env, out_path, err_path
            )
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
            limits_applied=limits_applied,
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
    ) -> tuple[subprocess.Popen[bytes], bool, dict[str, bool]]:
        policy = self._policy

        # D-054: report which limits actually took effect in *this* run, from the real
        # outcome of each setrlimit() call — never from the platform name. `preexec_fn`
        # runs in the forked child, after fork() but before exec(), and exec() replaces
        # the process image, so nothing computed here survives past this function
        # returning except what is written out before that happens. This pipe is the
        # only channel, and it is created before the fork so both ends exist on both
        # sides of it.
        limits_r, limits_w = os.pipe()
        os.set_inheritable(limits_w, True)

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

            applied: dict[str, bool] = {}
            for limit_name, key, value in (
                ("RLIMIT_AS", "memory_bytes", policy.memory_bytes),
                ("RLIMIT_NPROC", "max_processes", policy.max_processes),
            ):
                limit = getattr(resource, limit_name, None)
                if limit is None:
                    applied[key] = False
                    continue
                try:
                    resource.setrlimit(limit, (value, value))
                    applied[key] = True
                except (ValueError, OSError):
                    # Some kernels refuse to lower these for an unprivileged process, or
                    # do not honour them at all. Failing the whole run over it would be
                    # worse than proceeding: the wall clock still applies regardless, and
                    # this is exactly the outcome `applied` exists to report honestly —
                    # rather than assuming it from `sys.platform`, which is the mistake
                    # this field exists to not repeat.
                    applied[key] = False

            try:
                os.write(limits_w, json.dumps(applied).encode())
            finally:
                os.close(limits_w)

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
                    pass_fds=(limits_w,),
                )
            except FileNotFoundError as exc:
                os.close(limits_r)
                os.close(limits_w)
                raise JailUnavailableError(
                    f"{argv[0]!r} was not found on PATH inside the jail"
                ) from exc
            except BaseException:
                os.close(limits_r)
                os.close(limits_w)
                raise

        # Our own copy of the write end has to close too, or a read below can block
        # waiting for an EOF that only arrives once every writer has closed — and the
        # parent process holds one whether or not the child ever gets to write.
        os.close(limits_w)
        limits_applied = self._read_limits_applied(limits_r)

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

        return proc, timed_out, limits_applied

    @staticmethod
    def _read_limits_applied(read_fd: int) -> dict[str, bool]:
        """Read the child's real `setrlimit` outcome back across the fork boundary.

        By the time `Popen()` returns to the caller, the child has already run
        `apply_limits()` and either exec'd or failed to — `subprocess` itself uses an
        internal pipe to confirm exactly that before returning control to the parent, so
        the write on the child's side has already happened. This still bounds the read
        with a short deadline rather than trusting that guarantee unconditionally: a
        malformed protocol on this end must never be able to hang a build.
        """
        try:
            ready, _, _ = select.select([read_fd], [], [], 2.0)
            if not ready:
                return {}
            chunks = []
            while True:
                ready, _, _ = select.select([read_fd], [], [], 0.5)
                if not ready:
                    break
                chunk = os.read(read_fd, 65536)
                if not chunk:
                    break
                chunks.append(chunk)
            raw = b"".join(chunks)
            if not raw:
                return {}
            parsed = json.loads(raw.decode())
            if not isinstance(parsed, dict):
                return {}
            return {str(k): bool(v) for k, v in parsed.items()}
        except (OSError, ValueError):
            return {}
        finally:
            os.close(read_fd)

    def _kill_group(self, proc: subprocess.Popen[bytes]) -> None:
        """SIGTERM the group, give it a grace period, SIGKILL the group — then sweep
        for descendants that detached from the group entirely (SEC-33).

        Killing the *group* rather than the process is most of the point. `cmake --build`
        is a process that spawns compilers; killing only the parent leaves the compilers
        running and the build directory being written to by a mission that has ended.

        It is not the whole point, and treating it as such was a real gap. A process that
        calls `os.setsid()` — deliberately, to survive its parent, or as an incidental
        side effect of a daemonizing library a fuzz target links against — starts a *new*
        session and process group and becomes invisible to `killpg()` from that instant.
        This was found by review, reproduced directly (a detached grandchild confirmed
        alive after full teardown), and is exactly the shape a hostile or just
        poorly-behaved target can take — which is the whole reason this method exists.

        The fix does not need process groups at all: `setsid()` changes the process
        group and session id, but it does not and cannot change the parent process id —
        that is fixed at fork time by the kernel. So after the group-based kill, a second
        sweep walks `/proc` by parent id, finds every descendant of `proc.pid` regardless
        of which group or session it has put itself in, and kills each one directly.

        This sweep is Linux-only. That is where it is tested and where it matters — #81
        exists for the D3 gate, which runs on the finale's Linux stack, not for a
        developer's Mac. On another platform this call is the group-kill only, and that
        gap is documented here and in the README rather than silently narrowed.

        Ordering matters and cost a debugging pass to get right: the snapshot below has
        to happen *before* the group is killed, not after. Once the direct child dies and
        is reaped, a detached grandchild's parent-id link — the only thing the sweep has
        to go on — is gone too: the kernel reparents it to init (or whatever subreaper
        owns this pid namespace) the moment its recorded parent exits, and at that point
        walking `/proc` for descendants of `proc.pid` finds nothing, because there no
        longer are any. Snapshotting first, while the tree is still intact, is what makes
        the sweep able to find a process the group-kill was never going to reach anyway.
        """
        known_descendants = _proc_descendants(proc.pid)

        try:
            pgid = os.getpgid(proc.pid)
        except ProcessLookupError:
            pgid = None

        if pgid is not None:
            for sig, wait_for in (
                (signal.SIGTERM, self._policy.kill_grace_seconds),
                (signal.SIGKILL, 5.0),
            ):
                try:
                    os.killpg(pgid, sig)
                except ProcessLookupError:
                    break
                except OSError as exc:  # pragma: no cover - defensive
                    if exc.errno != errno.ESRCH:
                        raise
                    break
                try:
                    proc.wait(timeout=wait_for)
                except subprocess.TimeoutExpired:
                    continue
                if not self._group_alive(pgid):
                    break
            else:
                # Last resort inside the group: one more SIGKILL before moving on to the
                # sweep below, rather than giving up on the ordinary case.
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass

        self._sweep_detached_descendants(proc.pid, known_descendants)

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

    def _sweep_detached_descendants(self, root_pid: int, known: set[int]) -> None:
        """Kill every process still descended from `root_pid`, independent of process
        group or session. See `_kill_group` for why this exists (SEC-33) and why `known`
        — a snapshot taken before the group was touched — is required rather than
        optional: a fresh `/proc` walk *after* the direct child is dead finds nothing,
        because a detached descendant has by then reparented away from `root_pid`.

        Two sources are combined on every pass, not just `known`: a currently-linked walk
        also runs, to catch anything that forked *after* the snapshot was taken (during
        the grace period, for instance) and is still attached to `root_pid` at that
        moment. Between the two, a straggler has to actively evade both a point-in-time
        snapshot and continuous re-observation to survive — which is a materially
        different claim than "was in the process group when we checked".
        """
        if sys.platform != "linux":
            return

        pending = set(known)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            pending |= _proc_descendants(root_pid)
            pending.discard(root_pid)
            alive = {pid for pid in pending if _pid_running(pid)}
            if not alive:
                return
            for pid in alive:
                try:
                    os.kill(pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    continue
            pending = alive
            time.sleep(0.1)

        # One last check so a caller inspecting the outcome (a test, an evidence record)
        # sees the true state rather than an assumption that the loop above succeeded.
        pending |= _proc_descendants(root_pid)
        remaining = {pid for pid in pending if pid != root_pid and _pid_running(pid)}
        if remaining:  # pragma: no cover - only reachable if SIGKILL itself is refused
            raise JailUnavailableError(
                f"could not clear detached descendant(s) {sorted(remaining)} of pid "
                f"{root_pid} after the timeout sweep; refusing to report a clean "
                f"teardown that did not happen"
            )

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
        if signal_number == signal.SIGXFSZ:
            # SEC-35: RLIMIT_FSIZE's soft and hard limits are set to the same value
            # (unlike RLIMIT_CPU's staged soft-then-hard), so exceeding it always raises
            # this signal directly rather than going through an intermediate warning
            # stage. Nothing else in this process sends SIGXFSZ, so it is unambiguous.
            return LimitKind.FILE_SIZE
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
        if kind is LimitKind.FILE_SIZE:
            return FileSizeExceededError(self._policy.max_file_bytes)
        # LimitKind.OUTPUT has no dedicated exception type: it is not a resource the
        # command was stopped from consuming, it is our own cap on what we kept from
        # what it already produced — the command itself may have run to completion.
        # `raise_on_limit` on an OUTPUT-classified result falls back here rather than
        # inventing a claim ("timed out") that would be actively wrong.
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
