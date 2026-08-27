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
| a detached descendant cannot survive rapid, repeated fork-and-detach (SEC-38) | `test_sweep_catches_rapid_repeated_detachment` |
| `FILE_SIZE` is reported even for a target whose `SIGXFSZ` disposition is `SIG_IGN` (SEC-35) | `test_file_size_limit_is_reported_for_a_target_that_ignores_sigxfsz` |
| `FILE_SIZE` survives the target deleting its own oversized file before exiting (SEC-39, #163) | `test_file_size_limit_survives_target_deleting_its_own_evidence` |
| a stale large file left in a *shared, reused* workdir by an earlier run is not misread as this run hitting `FILE_SIZE` (SEC-40, #164) | `test_stale_file_in_shared_workdir_is_not_misclassified_as_file_size` |

**Two gaps D-056 gated `#28`'s fuzzing worker on, fixed by `#159` — not yet independently
re-verified.** Both were found by the security review of `#113`, both required an
adversarial target neither `#16`/`#17`/`#27`'s ordinary `cmake`/`ctest` invocation nor a
single-shot regression test would reach, and both are now covered by the named tests
above. **That is not the same thing as closed.** D-056 was explicit that a self-report does
not satisfy it — only `cybersecurity` independently re-attacking each one does — and `#159`
tracks that re-verification as still outstanding. Until it lands, treat `#28` as still
gated on it, not as unblocked by the strength of this fix alone:

| Gap | What was wrong | What changed |
|---|---|---|
| **SEC-38** | `_sweep_detached_descendants`'s final re-walk was anchored on this jail's own child pid, which is normally already dead (reaped) by the time the sweep runs — `_kill_group` signals and waits on it first. A walk rooted at a pid nothing claims as parent finds nothing, so any descendant a *tracked* pid forked after the pre-kill snapshot had no path back to it and was lost, deterministically, for as long as that kept happening — reproducing at the real default `kill_grace_seconds=5.0` under rapid, repeated fork-and-detach. | The walk now runs from every tracked pid each pass, not just the dead root — but killing on discovery just relocates that same race onto the newly-found pid's own next `fork()`. Closing it needed a freeze step: every pid is `SIGSTOP`ped and *confirmed* stopped before anything is killed, with the discover-then-freeze cycle run to a fixed point (nothing new turns up with everything currently tracked already frozen) before any `SIGKILL` is sent — see `_sweep_detached_descendants` and `_freeze`. `test_sweep_catches_rapid_repeated_detachment` chains many rapid fork-and-detach cycles at the real default grace period and requires zero survivors, run repeatedly, not a single detachment. |
| **SEC-35** | `_classify`'s `SIGXFSZ` branch only fires if the target actually receives and dies to that signal. CPython does not — `signal.getsignal(SIGXFSZ) is SIG_IGN` at interpreter start — so a Python target genuinely stopped by `RLIMIT_FSIZE` gets an ordinary `OSError` (`errno.EFBIG`) instead and can do anything with it, reporting `limit_hit == NONE`. Evidence-accuracy gap, not an isolation escape: the limit still stopped the process either way. | `_classify` gets the same fallback `MEMORY`'s branch already relies on for the same kind of ambiguity: a recognizable stderr marker, or (independent of anything the target says) a file on disk sized at the policy's cap — direct evidence `RLIMIT_FSIZE` actually stopped a write, gated behind `exit_code != 0` so an ordinary successful build never pays for the check. `test_file_size_limit_is_reported_for_a_target_that_ignores_sigxfsz`, verified against a real Python target, not `dd` — `dd` honours the signal, which is why the original SEC-35 test never caught this. |

**Two further residuals in that same SEC-35 fallback, found by `cybersecurity`'s independent
re-attack of `#159` (binding D-056 re-verification) and filed as `#163`/`#164`, fixed here:**

| Gap | What was wrong | What changed |
|---|---|---|
| **SEC-39 (#163)** | The on-disk half of the SEC-35 fallback only looks at the workdir *after* the command has already exited. A target that gets killed for genuinely hitting `RLIMIT_FSIZE`, but deletes or truncates its own oversized file first — a caught-signal handler, an `atexit` hook, anything that runs before the process is actually gone — leaves neither a stderr marker nor a file on disk by the time `_classify` runs, and is misclassified as a plain crash instead of `FILE_SIZE`. | `_FileSizePeakTracker` samples the workdir on an interval *while the process is still running*, in this jail's own memory, which the target has no way to reach or erase. `_classify` now takes the larger of that peak and whatever is still on disk. This narrows the race, it does not close it outright — a target that deletes faster than the poll interval can still slip through one sample window; see `_FileSizePeakTracker`'s own docstring for why an interval-based poll was judged good enough here rather than a full inotify watch. `test_file_size_limit_survives_target_deleting_its_own_evidence`. |
| **SEC-40 (#164)** | The on-disk scan looked at *any* file anywhere under the workdir, with no notion of when it was written. `workers/baseline/run.py` reuses one workdir across an entire build sequence's steps rather than a fresh one per `Jail`, so a large file left behind by an earlier, unrelated step is real, reachable evidence contamination — a later step's completely different failure gets misclassified as `FILE_SIZE` purely because of what an earlier step left lying around. | Both the peak tracker and the final on-disk check are scoped to files with `st_mtime` no older than this run's own start (`_max_file_size(..., since=...)`), with a small buffer for coarse-mtime filesystems. A stale file from a previous step, however large, is now excluded by age, not just found and blamed. `test_stale_file_in_shared_workdir_is_not_misclassified_as_file_size`. |

Anything not in the enforced-properties table above is *intended*, not enforced. In
particular this module does **not** prevent a running process from reading outside the
jail, opening a network socket, or exhausting a limit the kernel applies per-user rather
than per-process.
"""

from __future__ import annotations

import errno
import json
import logging
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

logger = logging.getLogger(__name__)

#: Reported into the evidence bundle. Mirrors `contracts.enums.IsolationMode`, as a
#: string so this package stays importable without Django.
ISOLATION_MODE = "SUBPROCESS_JAIL"

#: Resource measurement uses `RUSAGE_CHILDREN` deltas, which are process-wide. Runs are
#: serialized so a delta belongs to exactly one command. The D3 pipeline runs one command
#: at a time anyway; this makes the measurement honest rather than approximately right.
_MEASURE_LOCK = threading.Lock()

_MIB = 1024 * 1024


def _proc_children_map() -> dict[int, list[int]]:
    """Every currently-visible process on this machine, indexed by its recorded parent
    id: `{ppid: [pid, ...]}`.

    Factored out of `_proc_descendants` so a caller that needs to walk from more than
    one root — `_sweep_detached_descendants` does, see SEC-38 — can build this map once
    and reuse it, instead of re-listing all of `/proc` per root.

    Linux only (`/proc/*/stat`). Returns an empty map on any other platform or if
    `/proc` is unreadable, rather than raising — a caller that cannot do the walk needs
    to know that as "found nothing", the same shape as "there was nothing to find", not
    as a crash in a cleanup path that is often running during error handling already.
    """
    if sys.platform != "linux":
        return {}

    children: dict[int, list[int]] = {}
    try:
        entries = os.listdir("/proc")
    except OSError:
        return {}

    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        try:
            stat = Path(f"/proc/{pid}/stat").read_text()
        except OSError:
            # Gone between listdir() and read() — a race inherent to /proc, not an
            # error. It simply is not there anymore.
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
    return children


def _walk_descendants(children: dict[int, list[int]], roots: Sequence[int]) -> set[int]:
    """Breadth-first walk of `children` (as built by `_proc_children_map`) starting from
    every pid in `roots` at once.

    Multiple simultaneous roots is what makes the SEC-38 fix work: any pid already known
    to be a tracked descendant can itself have forked children of its own since the last
    time anyone looked, and those children's only path back to anything is through *that*
    pid, not through whichever process started the whole tree. Walking from one root
    only finds what is still reachable from that one pid at this exact moment — walking
    from every currently-tracked pid finds everything reachable from any of them.

    A root itself is never included in the result unless it is also reachable from a
    *different* root (harmless either way, since every root gets checked directly by the
    caller).
    """
    roots_set = set(roots)
    found: set[int] = set()
    frontier = list(roots_set)
    while frontier:
        pid = frontier.pop()
        for child in children.get(pid, ()):
            if child in found or child in roots_set:
                continue
            found.add(child)
            frontier.append(child)
    return found


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

    A single, fixed root taken once is exactly the shape that leaves SEC-38 open — see
    `_sweep_detached_descendants`, which walks from every tracked pid instead of just
    this one.
    """
    return _walk_descendants(_proc_children_map(), [root_pid])


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


def _proc_state(pid: int) -> str | None:
    """The single-character state field from `/proc/<pid>/stat` (`R`, `S`, `T` for
    stopped, `Z` for zombie, ...), or `None` if there is no such pid to read.

    Linux only, like everything else in this file that reads `/proc`.
    """
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None
    fields = stat.rpartition(")")[2].split()
    return fields[0] if fields else None


def _freeze(pids: set[int], timeout: float = 1.0) -> None:
    """`SIGSTOP` every pid in `pids` and block until each one is confirmed actually
    stopped (or gone) — not merely signalled.

    This is the piece that closes SEC-38 rather than just narrowing it. Killing a
    tracked pid the instant it is *discovered* races the pid's own next `fork()`: the
    kernel does not serialize "this process receives a fatal signal" against "this
    process is partway through creating a child", so a `SIGKILL` sent the moment a
    descendant is found can still let it complete one more fork before it dies, and that
    child's only link to anything tracked dies with it — the same invisibility as SEC-33
    and the earlier half of SEC-38, recreated one level down, no matter how tightly the
    discovery walk polls.

    `SIGSTOP` does not have that problem. A stopped process is paused, not gone: its
    process-table entry, and every child it has already forked, stay exactly as they
    were until something `SIGCONT`s it (nothing here does) or kills it outright. Once a
    pid's state is confirmed `T` (or the pid has already gone away on its own — also
    fine, there is nothing left to freeze), it provably cannot fork anything further, so
    a discovery walk run *after* every candidate is confirmed frozen cannot miss a child
    that was created before the freeze — there is no "before" left to race against.

    Best-effort per pid within `timeout`: a pid this process cannot signal (owned by
    someone else), or that exits on its own before the stop lands, is not retried —
    either way it is no longer a source of new children, which is the only property this
    function exists to guarantee before the caller moves on to killing.
    """
    for pid in pids:
        try:
            os.kill(pid, signal.SIGSTOP)
        except (ProcessLookupError, PermissionError):
            continue

    deadline = time.monotonic() + timeout
    remaining = set(pids)
    while remaining and time.monotonic() < deadline:
        remaining = {
            pid for pid in remaining if _proc_state(pid) not in (None, "T", "Z")
        }
        if remaining:
            time.sleep(0.001)


#: SEC-40 (#164): a stale file, dropped in a shared workdir by an earlier, unrelated
#: run, can be excluded from `_max_file_size`'s scan purely on age — but filesystem
#: mtime resolution is not sub-second everywhere (notably HFS+, still reachable via an
#: older macOS dev host or an unusual mount), so a same-run file written in the same
#: second the walk's `since` was captured could otherwise be excluded by a rounding
#: accident, not because it predates the run. This buffer trades a little of #164's
#: fix back for that: a leftover file modified in the second immediately before this
#: run started can still slip through, which is a far smaller, bounded window than "any
#: file of any age anywhere in the shared workdir" — the bug being fixed.
_MTIME_GRANULARITY_BUFFER_SECONDS = 1.0

#: How often `_FileSizePeakTracker` samples the workdir while a command is still
#: running. SEC-39 (#163): this is what lets the evidence survive a target deleting or
#: truncating its own oversized file before `_classify` ever gets to look at disk — the
#: peak is kept in this process's own memory, which the target has no way to reach.
#: Bounded by the same trade the rest of this module makes explicitly rather than
#: silently: tighter narrows the race further at the cost of one more `os.walk` of the
#: workdir per interval for the lifetime of every command this jail runs, not just ones
#: that hit the limit. 100ms is short enough to catch cleanup that takes any real time
#: (a signal handler doing I/O, an atexit hook) and long enough that a multi-second
#: build does not pay for a workdir walk more than a few hundred times over its life.
_FILE_SIZE_POLL_INTERVAL_SECONDS = 0.1


def _max_file_size(root: Path, *, since: float | None = None) -> int:
    """The largest regular file anywhere under `root`, or 0 if there is none.

    SEC-35's on-disk-evidence fallback (see `_classify`): when a target's `SIGXFSZ`
    disposition means the signal branch above can't be trusted, the size of whatever it
    was writing is independent, measured evidence the per-file cap was reached — not
    something a target's own reporting (or lack of it) can hide. Errors reading any one
    entry are swallowed rather than raised: a build directory can contain sockets, pipes,
    permission-denied files, or entries that vanish mid-walk, none of which should turn a
    classification helper into the reason a run's cleanup fails.

    `since`, if given, is a `time.time()`-comparable wall-clock timestamp (already
    reduced by `_MTIME_GRANULARITY_BUFFER_SECONDS`, if the caller wants that buffer):
    any file whose `st_mtime` is older than it is skipped entirely. This is SEC-40's
    (#164) fix — `workers/baseline/run.py` reuses one workdir across an entire build
    sequence, so an unrelated earlier step's leftover large file is real, reachable
    evidence contamination, not a hypothetical one, and a scan with no age filter at
    all cannot tell it apart from something the *current* run actually wrote.
    """
    largest = 0
    for dirpath, _dirnames, filenames in os.walk(root, onerror=lambda _exc: None):
        for name in filenames:
            path = Path(dirpath) / name
            try:
                if path.is_symlink():
                    continue
                stat_result = path.stat()
            except OSError:
                continue
            if since is not None and stat_result.st_mtime < since:
                continue
            if stat_result.st_size > largest:
                largest = stat_result.st_size
    return largest


class _FileSizePeakTracker:
    """Watches `workdir` while a jailed command is still running and remembers the
    largest file size ever observed there, scoped to files touched during *this* run.

    Exists to close SEC-39 (#163): `_classify`'s SEC-35 on-disk fallback only looks at
    what is left on disk *after* the command has already exited, and a target can
    defeat that by deleting or truncating its own oversized file — in a caught
    `SIGXFSZ` handler, or an exit-cleanup / `atexit` path — before `_classify` ever
    runs, leaving no stderr marker (the target was never using the default handler in
    the first place) and no file on disk either. Sampling on an interval *while the
    process is still alive* keeps a value in this process's own memory that the target
    cannot reach or erase, independent of anything still on disk by the time anyone
    looks — the same principle `peak_memory_mb` already relies on via `RUSAGE_CHILDREN`,
    applied here by direct polling since there is no equivalent kernel-tracked peak for
    file size.

    This narrows the race, it does not close it outright: a target that deletes its
    output faster than `_FILE_SIZE_POLL_INTERVAL_SECONDS` can still slip through every
    sample window. That residual gap is real, and is exactly what a full inotify-based
    watch would close instead of a fixed-interval poll — judged not worth the added
    complexity for a medium-severity, evidence-accuracy-only finding; tracked in
    #163/#164 rather than silently declared closed.
    """

    def __init__(
        self,
        workdir: Path,
        since: float,
        interval: float = _FILE_SIZE_POLL_INTERVAL_SECONDS,
    ) -> None:
        self._workdir = workdir
        self._since = since
        self._interval = interval
        self._peak = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="jail-file-size-peak-tracker", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def stop_and_get_peak(self) -> int:
        """Stop sampling and return the largest size observed, including one last
        sample taken now — after the process has already been signalled and (usually)
        reaped, so this read runs closer to the moment of death than the periodic
        sample before it, and strictly before `_classify` gets to look at anything."""
        self._stop.set()
        self._thread.join(timeout=self._interval * 4)
        self._sample()
        with self._lock:
            return self._peak

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            self._sample()

    def _sample(self) -> None:
        size = _max_file_size(self._workdir, since=self._since)
        with self._lock:
            if size > self._peak:
                self._peak = size


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

    def which(self, name: str) -> str | None:
        """Resolve a bare tool name (`"cmake"`) to the path this jail will actually
        run when handed it.

        For this subprocess jail that is exactly `shutil.which(name)`: the child runs
        on the SAME filesystem and `PATH` as the orchestrator host (see this module's
        own opening warning), so a host-resolved absolute path is a correct, valid
        argv[0] here. #181/SEC-57 added this method (and the container-backed
        equivalent, `packages.sandbox.container_runner.ContainerJailRunner.which`) so
        `adapters/cpp/toolchain.py::probe_build_tools` and `adapters/cpp/pipeline.py`
        can resolve a tool through whichever jail flavor they were actually handed,
        instead of calling `shutil.which()` themselves and silently baking in the
        assumption that a host-resolved path means anything inside a container's own,
        differently-built filesystem — see `ContainerJailRunner.which`'s own docstring
        for why that assumption is exactly the toolchain-pinning gap `toolchain.py`'s
        module docstring already names as open until "the container path" (#15) is
        wired into this call site.
        """
        return shutil.which(name)

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
        # Wall-clock, not monotonic: this is compared against `st_mtime`, which the
        # filesystem stamps in wall-clock time, not against `started` above.
        # `_MTIME_GRANULARITY_BUFFER_SECONDS` earlier absorbs coarse-mtime filesystems
        # rounding a same-run file's timestamp down below this instant — see #164.
        run_started_wall = time.time() - _MTIME_GRANULARITY_BUFFER_SECONDS
        with _MEASURE_LOCK:
            before = resource.getrusage(resource.RUSAGE_CHILDREN)
            proc, timed_out, limits_applied, peak_file_bytes = self._spawn_and_wait(
                argv, workdir, env, out_path, err_path, run_started_wall
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
            workdir=workdir,
            run_started_wall=run_started_wall,
            peak_file_bytes=peak_file_bytes,
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
        run_started_wall: float,
    ) -> tuple[subprocess.Popen[bytes], bool, dict[str, bool], int]:
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

        # SEC-39 (#163): start sampling before the process can do anything at all, so
        # a target that hits RLIMIT_FSIZE and cleans up its own evidence in well under
        # a second still has to race a peak that is already being tracked, not one
        # that starts only after `_classify` notices something is wrong.
        peak_tracker = _FileSizePeakTracker(workdir, run_started_wall)
        peak_tracker.start()

        timed_out = False
        try:
            proc.wait(timeout=policy.wall_clock_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._kill_group(proc)
        finally:
            with self._live_lock:
                self._live = None

        peak_file_bytes = peak_tracker.stop_and_get_peak()

        return proc, timed_out, limits_applied, peak_file_bytes

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

        #184: `os.killpg` can raise `PermissionError` here even though nothing about this
        jail's own privileges changed. `pgid` is snapshotted once, above, from
        `os.getpgid(proc.pid)` — but a process group id is drawn from the same small,
        reused numeric namespace as a pid, and is freed for the kernel to hand to a
        completely unrelated, differently-owned process the instant every member of the
        old group has both exited *and been reaped*. Between that snapshot and a later
        `killpg()` call in this same method (the `SIGKILL` after a `SIGTERM` that already
        finished the job, or the `else` clause's last-resort retry), that exact recycling
        can happen — `killpg`, unlike a plain `kill`, has no way to say "no such group"
        (`ESRCH`) apart from "a group by this number exists now, but you don't own it"
        (`EPERM`); both surface identically. Treating every `EPERM` here as fatal turns a
        completed, successful teardown into a spurious job failure under exactly the kind
        of timeout race this method exists to make robust to. See
        `_permission_error_is_benign_pid_reuse` for how the two cases are told apart
        rather than every `EPERM` being assumed benign.
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
                except PermissionError:
                    if not self._permission_error_is_benign_pid_reuse(proc, pgid, sig):
                        raise
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
                except ProcessLookupError:
                    pass
                except PermissionError:
                    if not self._permission_error_is_benign_pid_reuse(
                        proc, pgid, signal.SIGKILL
                    ):
                        raise
                except OSError as exc:  # pragma: no cover - defensive
                    if exc.errno != errno.ESRCH:
                        raise

        self._sweep_detached_descendants(proc.pid, known_descendants)

    @staticmethod
    def _permission_error_is_benign_pid_reuse(
        proc: subprocess.Popen[bytes], pgid: int, sig: signal.Signals
    ) -> bool:
        """Decide whether a `PermissionError` from `os.killpg(pgid, sig)` — aimed at
        `proc`'s own process group — is the pid/pgid-reuse race (#184), or a genuinely
        unexpected permission failure that must not be silently absorbed.

        The one thing still authoritative after `pgid` may have been recycled is whether
        *this jail's own tracked child* — `proc`, identified by the live `Popen` object,
        never by a bare number that can be reassigned — has already exited. `Popen.poll()`
        calls `waitpid(WNOHANG)` internally, which only ever reports on this process's own
        real child and cannot be fooled by pid or pgid reuse: the kernel never hands back
        someone else's process through our own child's wait status.

        * `proc` has already exited: this `PermissionError` cannot be about signalling
          *our* target, because there is nothing left of it to signal — the numeric group
          id was almost certainly already freed and handed to an unrelated,
          differently-owned process by the time this `killpg()` call landed. Safe to treat
          as "the group is already gone", the same outcome `ProcessLookupError` reports
          right above this call, just arriving as `EPERM` instead of `ESRCH` because
          something now sits at that number again.
        * `proc` is still running: this is not that race. Our own child is alive, and
          signalling its own group failed with `EPERM` anyway — the realistic way that
          happens is the child (or something it `exec`'d) crossing into a different
          effective privilege context, e.g. running a setuid binary. `wait()` permission
          is a fixed parent/child relationship the kernel never revokes; `kill()`
          permission is a live uid/gid check and is not immune to that change. That is a
          real, unexpected failure and must propagate, not be swallowed.

        Logs clearly either way — the whole point is that a future spurious job failure
        (or a future genuine one, now silently downgraded) is diagnosable from the log
        rather than being a mystery again.
        """
        still_running = proc.poll() is None
        if still_running:
            logger.error(
                "killpg(pgid=%s, %s) raised PermissionError while our own child "
                "pid=%s is still running; this is not the benign pid/pgid-reuse race "
                "(#184) -- treating it as a genuine, unexpected permission failure "
                "and propagating it",
                pgid, sig, proc.pid,
            )
            return False
        logger.warning(
            "killpg(pgid=%s, %s) raised PermissionError, but our own child pid=%s had "
            "already exited -- treating this as the pid/pgid-reuse race (#184): the "
            "process group id was almost certainly already recycled to an unrelated, "
            "differently-owned process by the time this signal landed. Reporting "
            "teardown for this group as complete rather than failing the job over it",
            pgid, sig, proc.pid,
        )
        return True

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

        SEC-38: `root_pid` is not a usable walk anchor here, and re-walking from it on
        every pass — which is what this loop used to do — does not help. By the time
        this method is even called, `_kill_group` has already signalled and (almost
        always) reaped `root_pid`: `proc.wait()` succeeds within the ordinary
        SIGTERM/SIGKILL sequence well before this runs. A `/proc` walk rooted at a pid
        nothing still claims as its parent finds nothing, for the rest of this method's
        lifetime — `known`, taken *before* that happened, was doing all of the real work,
        and only for pids it happened to capture directly by pid. Anything a *tracked*
        descendant forks after that snapshot — the exact shape of a target that detaches
        repeatedly rather than once — had no path back to `root_pid` and was invisible to
        the old re-walk for the sweep's entire remaining duration, not occasionally: every
        time, for every fork after the moment `root_pid` died, which in practice is
        already true beforehand almost every mission.

        Walking from `root_pid` *and* from every pid already being tracked, every pass —
        using a map of the whole process tree built once per pass (`_proc_children_map` /
        `_walk_descendants`) — closes most of that: a tracked pid that is still alive has
        a live, correct link to whatever it forks next, right up until the instant it
        exits, so re-deriving the walk's roots from the tracking set itself, not from a
        single pid that is normally already gone, lets a chain of detachments get
        followed instead of losing the thread the moment the first link in it dies.
        Nothing is ever dropped from `pending` once seen (in contrast to the old loop,
        which discarded anything not currently alive at the end of each pass): a pid that
        looks dead this instant may have forked one more child in its last moments, and
        that child's only route to discovery is a walk that still treats its parent as a
        root next pass too.

        That alone is not sufficient, and testing it caught why: it just relocates the
        race rather than closing it. Killing a tracked pid the moment it is *discovered*
        races that pid's own `fork()` — the kernel does not serialize "deliver this fatal
        signal" against "finish creating this child", so a `SIGKILL` sent the instant a
        descendant is found can still let it complete one more fork before it dies, and
        that child is lost exactly as before, just one level further down the chain. A
        tighter poll interval shrinks this window without ever closing it, because it is
        not really a polling-frequency problem — it is two independent things (the target
        forking, and us killing) that a purely periodic re-walk has no way to order.

        So this does not kill on discovery. Every pid found alive gets `SIGSTOP`ped and
        *confirmed* stopped (`_freeze`) before anything is killed — not signalled, landed:
        a stopped process cannot fork, so its process-table entry and every child it had
        already produced when the stop landed stay exactly as they are, forever, with
        nothing here ever sending it `SIGCONT`. Freezing one pid can itself surface a
        child it forked moments before the stop took effect, so the loop below treats
        "found something new" and "everything found so far is frozen" as the actual
        exit condition, not a fixed number of passes: every discovery pass first freezes
        whatever it just found and goes around again, and only once a pass finds nothing
        beyond what is already frozen is it safe to kill the batch — at that point there
        is no live, un-frozen pid left anywhere in the tracked tree that could still
        produce something new to lose. That is what actually removes the race rather than
        narrowing it: once every candidate is confirmed frozen, there is no "still
        running" left for a new fork to happen from.

        `test_sweep_catches_rapid_repeated_detachment` exercises many rapid, chained
        fork-and-detach cycles at the module's real default `kill_grace_seconds` and
        requires zero survivors across repeated runs, not merely fewer than before.
        """
        if sys.platform != "linux":
            return

        pending = set(known)
        frozen: set[int] = set()
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            children = _proc_children_map()
            pending |= _walk_descendants(children, [root_pid, *pending])
            pending.discard(root_pid)

            # Anything alive and not yet confirmed frozen might still fork something we
            # have not seen. Freeze it and go around again before considering killing
            # anything — see the docstring above for why a single freeze-then-rewalk
            # pass is not enough on its own and this has to run to a fixed point.
            to_freeze = {pid for pid in pending if pid not in frozen and _pid_running(pid)}
            if to_freeze:
                _freeze(to_freeze)
                frozen |= to_freeze
                continue

            alive = {pid for pid in pending if _pid_running(pid)}
            if not alive:
                return
            for pid in alive:
                try:
                    os.kill(pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    continue
            time.sleep(0.01)

        # One last check so a caller inspecting the outcome (a test, an evidence record)
        # sees the true state rather than an assumption that the loop above succeeded.
        children = _proc_children_map()
        pending |= _walk_descendants(children, [root_pid, *pending])
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
        workdir: Path,
        run_started_wall: float,
        peak_file_bytes: int,
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
            # RLIMIT_FSIZE's soft and hard limits are set to the same value (unlike
            # RLIMIT_CPU's staged soft-then-hard), so exceeding it always raises this
            # signal directly rather than going through an intermediate warning stage.
            # Nothing else in this process sends SIGXFSZ, so it is unambiguous — when it
            # arrives at all. See the SEC-35 fallback below for when it does not.
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

        # SEC-35 (re-opened by #159, hardened again by #163/#164): the SIGXFSZ branch
        # above only fires if the target actually dies to that signal, and nothing
        # requires that. CPython ignores SIGXFSZ by default (`signal.getsignal(SIGXFSZ)
        # is SIG_IGN` at interpreter start) — a Python target that crosses
        # RLIMIT_FSIZE gets an ordinary `OSError` (`errno.EFBIG`) at the failing
        # `write()` instead of being killed, and is free to do anything with it,
        # including nothing visible at all. This is the same ambiguity the MEMORY
        # branch above already has to live with — a limit that stopped the command
        # without the tidy, unambiguous signal this function would rather have — and it
        # gets the same answer: don't wait for a signal that might never come, look for
        # direct evidence the limit was actually hit. Three independent sources, any
        # one is enough, checked only once something already looks wrong
        # (`exit_code != 0`) so an ordinary successful build never pays for any of them:
        #   - the target's own words: CPython's default top-level handler for an
        #     uncaught EFBIG prints exactly this text to stderr on its way out, and a
        #     target that catches and reports the error itself is likely to mention the
        #     same errno;
        #   - `peak_file_bytes`, sampled by `_FileSizePeakTracker` *while the process
        #     was still alive*: this is SEC-39's (#163) fix. A target that gets killed
        #     for hitting the limit and then deletes or truncates the oversized file
        #     before this function ever runs defeats both the signal branch above and
        #     the on-disk check below — but not this, because it was recorded before
        #     the target had the chance to touch the file again;
        #   - what is actually on disk right now: RLIMIT_FSIZE stops a write at exactly
        #     the limit (soft == hard here, so there is no partial-warning stage to
        #     land short of it), so a file still sized at the policy's cap is direct,
        #     measured evidence the cap was hit. Scoped to files modified during this
        #     run (`since=run_started_wall`) rather than the whole workdir — SEC-40
        #     (#164): `workers/baseline/run.py` reuses one workdir across an entire
        #     build sequence, so an unscoped scan can misattribute a stale, unrelated
        #     large file left by an earlier step in that same sequence to a completely
        #     different failure in a later one.
        if exit_code != 0:
            file_size_reported = any(
                marker in stderr for marker in ("File too large", "Errno 27", "EFBIG")
            )
            on_disk_now = _max_file_size(workdir, since=run_started_wall)
            if (
                file_size_reported
                or peak_file_bytes >= self._policy.max_file_bytes
                or on_disk_now >= self._policy.max_file_bytes
            ):
                return LimitKind.FILE_SIZE

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
