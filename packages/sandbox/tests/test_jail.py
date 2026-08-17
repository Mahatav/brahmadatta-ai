"""What the subprocess jail actually enforces.

The rule this file exists to satisfy: a property is described as enforced only when a
named test demonstrates it. Every claim in `packages/sandbox/README.md` points at a test
here. Where a property could not be demonstrated on this platform, the test says so out
loud with `skipif` and a reason, rather than being quietly dropped.

Nothing here is mocked. Every test starts a real process and observes what the kernel
does to it.
"""

from __future__ import annotations

import os
import signal
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from packages.sandbox import (
    CancelledError,
    Jail,
    JailPolicy,
    LimitKind,
    PathEscapeError,
    probe_limits,
)
from packages.sandbox.errors import (
    CpuExceededError,
    FileSizeExceededError,
    JailUnavailableError,
    WallClockExceededError,
)

IS_DARWIN = sys.platform == "darwin"
MIB = 1024 * 1024


@pytest.fixture
def jail():
    with Jail.create(JailPolicy(cpu_seconds=20, wall_clock_seconds=30)) as j:
        yield j


def python(code: str) -> list[str]:
    return [sys.executable, "-c", textwrap.dedent(code)]


# --- the working-directory jail ---------------------------------------------------


def test_command_runs_in_the_jail_root(jail) -> None:
    result = jail.run(python("import os; print(os.getcwd())"))
    assert result.ok, result.summary()
    assert Path(result.stdout.strip()).resolve() == jail.root.resolve()


def test_path_outside_the_jail_is_refused(jail) -> None:
    for outside in ("/etc", "/etc/passwd", "..", "../..", "/tmp"):
        with pytest.raises(PathEscapeError) as excinfo:
            jail.resolve(outside)
        assert "outside the jail" in str(excinfo.value)


def test_a_path_inside_the_jail_is_allowed(jail) -> None:
    (jail.root / "build").mkdir()
    assert jail.resolve("build") == (jail.root / "build").resolve()
    assert jail.resolve(jail.root / "build") == (jail.root / "build").resolve()


def test_symlink_escape_is_refused(jail) -> None:
    """The check that earns its place. A lexical `..` test would pass this link."""
    link = jail.root / "escape"
    link.symlink_to("/etc")
    with pytest.raises(PathEscapeError) as excinfo:
        jail.resolve("escape")
    assert "/etc" in str(excinfo.value)


def test_running_with_a_cwd_outside_the_jail_is_refused(jail) -> None:
    with pytest.raises(PathEscapeError):
        jail.run(["/bin/echo", "hello"], cwd="/etc")


# --- limits -----------------------------------------------------------------------


def test_cpu_limit_stops_a_spinner() -> None:
    """A busy loop with a 1s CPU budget is stopped, and reported as CPU rather than as
    a mysterious signal."""
    policy = JailPolicy(cpu_seconds=1, wall_clock_seconds=60)
    with Jail.create(policy) as jail:
        started = time.monotonic()
        result = jail.run(python("while True: pass"))
        elapsed = time.monotonic() - started

    assert result.limit_hit is LimitKind.CPU, result.summary()
    assert not result.ok
    assert elapsed < 30, "the CPU limit must stop it long before the wall clock would"
    assert result.cpu_seconds >= 0.5, f"expected real CPU burn, got {result.cpu_seconds}"


def test_cpu_limit_can_be_raised_as_a_specific_error() -> None:
    with Jail.create(JailPolicy(cpu_seconds=1, wall_clock_seconds=60)) as jail:
        with pytest.raises(CpuExceededError) as excinfo:
            jail.run(python("while True: pass"), raise_on_limit=True)
    assert excinfo.value.kind is LimitKind.CPU
    assert "CPU budget" in str(excinfo.value)


@pytest.mark.skipif(
    IS_DARWIN,
    reason=(
        "RLIMIT_AS is not enforced on Darwin: setrlimit is refused and the child reports "
        "an unlimited address space, so a 64 MiB cap allowed a 900 MB allocation. "
        "Measured, not assumed - see probe_limits(). Linux is the platform the finale "
        "runs on and this asserts there."
    ),
)
def test_memory_limit_stops_an_allocator() -> None:
    policy = JailPolicy(cpu_seconds=30, memory_bytes=64 * MIB, wall_clock_seconds=60)
    with Jail.create(policy) as jail:
        result = jail.run(
            python(
                """
                b = bytearray()
                while len(b) < 900 * 1024 * 1024:
                    b.extend(bytes(4 * 1024 * 1024))
                print("allocated", len(b))
                """
            )
        )
    assert result.limit_hit is LimitKind.MEMORY, result.summary()
    assert "allocated" not in result.stdout
    # D-054: the per-run record has to agree with what was just observed to happen.
    # `setrlimit` succeeding is what let the allocator get stopped at all.
    assert result.limits_applied.get("memory_bytes") is True, result.limits_applied


# --- D-054: limits_applied is measured per run, never guessed from the platform ---


def test_limits_applied_is_a_real_per_run_measurement(jail) -> None:
    """The field exists precisely because a name is not a measurement (D-054). Every
    key is populated from the real outcome of a `setrlimit()` call made in this run's
    own child process, carried back across the fork boundary — not computed from
    `sys.platform` before any such call is attempted.
    """
    result = jail.run(["/bin/echo", "hello"])
    assert result.ok, result.summary()
    assert set(result.limits_applied) == {"memory_bytes", "max_processes"}
    assert all(isinstance(value, bool) for value in result.limits_applied.values())


@pytest.mark.skipif(
    not IS_DARWIN,
    reason="this is the Darwin-specific half of the memory_bytes measurement; Linux is "
    "covered by test_memory_limit_stops_an_allocator asserting the same field",
)
def test_limits_applied_matches_measured_darwin_behaviour(jail) -> None:
    """Pin the actual value observed on this platform, so a future macOS release that
    starts honouring RLIMIT_AS is discovered by a failing assertion — not silently, and
    not by trusting a comment that could go stale the day it changes."""
    result = jail.run(["/bin/echo", "hello"])
    assert result.limits_applied["memory_bytes"] is False, (
        "if this is now True, Darwin has started enforcing RLIMIT_AS: remove the skip "
        "on test_memory_limit_stops_an_allocator and update the README's platform table"
    )


def test_limits_applied_agrees_with_probe_limits_on_memory(jail) -> None:
    """Two independent measurements of the same kernel property — one per-run
    (`limits_applied`, from a real `setrlimit()` call), one a standalone diagnostic
    (`probe_limits()`, from actually exceeding the limit and observing the result).
    They ask different questions ("did the call succeed" vs "did behaviour change") but
    on this kernel they had better agree, or one of them is measuring the wrong thing.
    """
    result = jail.run(["/bin/echo", "hello"])
    findings = probe_limits()
    assert result.limits_applied["memory_bytes"] == findings["memory_bytes"]


def test_limits_applied_survives_a_command_that_is_immediately_killed() -> None:
    """The measurement is taken before the wall-clock timeout can possibly fire — a
    command that gets killed the instant it starts must still report what its own
    setrlimit calls did, because those ran before the kill, not after."""
    policy = JailPolicy(cpu_seconds=60, wall_clock_seconds=0.2, kill_grace_seconds=0.2)
    with Jail.create(policy) as jail:
        result = jail.run(python("import time; time.sleep(30)"))
    assert result.limit_hit is LimitKind.WALL_CLOCK
    assert set(result.limits_applied) == {"memory_bytes", "max_processes"}


def test_probe_limits_reports_what_this_kernel_does() -> None:
    """`probe_limits()` is how a caller finds out, rather than trusting a README."""
    findings = probe_limits()
    assert findings["cpu_seconds"] is True
    assert findings["wall_clock_seconds"] is True
    if IS_DARWIN:
        assert findings["memory_bytes"] is False, (
            "if Darwin has started honouring RLIMIT_AS, the skip on "
            "test_memory_limit_stops_an_allocator should be removed"
        )
    else:
        assert findings["memory_bytes"] is True


def test_wall_clock_timeout_is_reported_not_hung() -> None:
    policy = JailPolicy(cpu_seconds=60, wall_clock_seconds=1.0, kill_grace_seconds=0.5)
    with Jail.create(policy) as jail:
        started = time.monotonic()
        result = jail.run(python("import time; time.sleep(300)"))
        elapsed = time.monotonic() - started

    assert result.limit_hit is LimitKind.WALL_CLOCK, result.summary()
    assert elapsed < 10, f"the timeout did not fire promptly ({elapsed:.1f}s)"


def test_wall_clock_can_be_raised_as_a_specific_error() -> None:
    policy = JailPolicy(cpu_seconds=60, wall_clock_seconds=1.0, kill_grace_seconds=0.5)
    with Jail.create(policy) as jail:
        with pytest.raises(WallClockExceededError) as excinfo:
            jail.run(python("import time; time.sleep(300)"), raise_on_limit=True)
    assert excinfo.value.kind is LimitKind.WALL_CLOCK


def test_output_is_capped(jail) -> None:
    with Jail.create(JailPolicy(max_output_bytes=4096, wall_clock_seconds=30)) as j:
        result = j.run(python("print('x' * 200000)"))
    assert result.stdout_truncated
    assert len(result.stdout) <= 4096


def test_file_size_limit_is_reported_as_file_size_not_none(jail) -> None:
    """SEC-35 (cybersecurity review of #113, Medium). `LimitKind.FILE_SIZE` was defined
    and never produced: `_classify` had no branch for `SIGXFSZ`, the signal
    `RLIMIT_FSIZE` delivers, so a run genuinely stopped by the per-file limit reported
    `limit_hit == NONE` — indistinguishable from an unrelated failure, and silently wrong
    for exactly the property this field exists to name.

    Unlike `RLIMIT_AS`, `RLIMIT_FSIZE` is reliably enforced on both platforms this
    project runs on — no Darwin skip needed here.
    """
    policy = JailPolicy(cpu_seconds=10, wall_clock_seconds=15, max_file_bytes=1 * MIB)
    with Jail.create(policy) as jail_:
        result = jail_.run(
            ["/bin/dd", "if=/dev/zero", "of=toolarge.bin", "bs=1M", "count=50"]
        )
    assert result.limit_hit is LimitKind.FILE_SIZE, result.summary()
    assert result.signal_number == signal.SIGXFSZ


def test_file_size_limit_can_be_raised_as_a_specific_error() -> None:
    policy = JailPolicy(cpu_seconds=10, wall_clock_seconds=15, max_file_bytes=1 * MIB)
    with Jail.create(policy) as jail_:
        with pytest.raises(FileSizeExceededError) as excinfo:
            jail_.run(
                ["/bin/dd", "if=/dev/zero", "of=toolarge.bin", "bs=1M", "count=50"],
                raise_on_limit=True,
            )
    assert excinfo.value.kind is LimitKind.FILE_SIZE
    assert "per-file limit" in str(excinfo.value)


def test_file_size_limit_is_reported_for_a_target_that_ignores_sigxfsz(jail) -> None:
    """SEC-35, residual gap (cybersecurity review of #113, re-opened by #159).

    `_classify`'s `SIGXFSZ` branch only fires if the target actually receives and dies
    to that signal. CPython does not: `signal.getsignal(signal.SIGXFSZ) is SIG_IGN` at
    interpreter start (confirmed below), so a write that crosses `RLIMIT_FSIZE` fails at
    the syscall with `EFBIG` and surfaces to Python as an ordinary `OSError` — the
    process is free to do anything with that, including nothing recognizable at all.
    The original SEC-35 test used `/bin/dd`, which *does* honour the signal, which is
    exactly why it never caught this — the acceptance criteria for #159 call that out
    by name and require a real Python target instead.

    This mirrors an uncaught, naive target: no try/except, just the default CPython
    traceback that already prints "OSError: [Errno 27] File too large" to stderr on
    the way to a nonzero exit.
    """
    policy = JailPolicy(cpu_seconds=10, wall_clock_seconds=15, max_file_bytes=1 * MIB)
    with Jail.create(policy) as jail_:
        result = jail_.run(
            python(
                """
                import signal
                assert signal.getsignal(signal.SIGXFSZ) is signal.SIG_IGN, (
                    "this test assumes CPython's default SIGXFSZ disposition; if that "
                    "assumption is now false the test needs to be revisited"
                )
                with open("toolarge.bin", "wb") as fh:
                    for _ in range(50):
                        fh.write(b"x" * (1024 * 1024))
                        fh.flush()
                print("wrote past the limit without being stopped")
                """
            )
        )
    assert result.exit_code != 0, result.summary()
    assert result.signal_number is None, (
        "the whole point: no signal reaches a target that ignores SIGXFSZ"
    )
    assert "wrote past the limit" not in result.stdout
    assert result.limit_hit is LimitKind.FILE_SIZE, result.summary()


def test_file_size_limit_bounds_one_file_not_aggregate_usage(jail) -> None:
    """SEC-36 (cybersecurity review of #113, Low). The docstring on `max_file_bytes`
    said this stops "a pathological build product filling the disk" — an overclaim.
    `RLIMIT_FSIZE` bounds the size any *single* file may grow to; several files that
    each stay under the limit are not caught by it, or by anything else this jail
    enforces. This test is the demonstration the corrected docstring points at.
    """
    policy = JailPolicy(cpu_seconds=10, wall_clock_seconds=15, max_file_bytes=2 * MIB)
    with Jail.create(policy) as jail_:
        result = jail_.run(
            python(
                """
                for i in range(20):
                    with open(f"file-{i}.bin", "wb") as fh:
                        fh.write(b"x" * 1024 * 1024)  # 1 MiB, under the 2 MiB cap
                print("wrote 20 files, 20 MiB total, no single file over the limit")
                """
            )
        )
    assert result.ok, result.summary()
    assert result.limit_hit is LimitKind.NONE
    assert "wrote 20 files" in result.stdout


# --- no orphans -------------------------------------------------------------------


def test_timeout_kills_grandchildren_leaving_no_orphans(tmp_path: Path) -> None:
    """The property `cmake --build` makes non-negotiable.

    A build is a process that spawns compilers. Killing only the direct child leaves the
    compilers running and writing into a build directory belonging to a mission that has
    already ended. So: start a parent that spawns three long-lived grandchildren, record
    their pids, let the wall clock fire, and require every one of them to be gone.
    """
    pidfile = tmp_path / "pids"
    policy = JailPolicy(cpu_seconds=60, wall_clock_seconds=2.0, kill_grace_seconds=0.5)

    with Jail.create(policy) as jail:
        result = jail.run(
            python(
                f"""
                import subprocess, sys, time
                kids = [
                    subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
                    for _ in range(3)
                ]
                with open({str(pidfile)!r}, "w") as fh:
                    fh.write("\\n".join(str(k.pid) for k in kids))
                    fh.flush()
                time.sleep(600)
                """
            )
        )

    assert result.limit_hit is LimitKind.WALL_CLOCK, result.summary()

    for _ in range(50):
        if pidfile.exists() and pidfile.read_text().strip():
            break
        time.sleep(0.1)
    pids = [int(line) for line in pidfile.read_text().split() if line.strip()]
    assert len(pids) == 3, f"the test did not manage to spawn grandchildren: {pids}"

    deadline = time.monotonic() + 10
    survivors: list[int] = []
    while time.monotonic() < deadline:
        survivors = [pid for pid in pids if _alive(pid)]
        if not survivors:
            break
        time.sleep(0.2)

    assert not survivors, (
        f"grandchildren {survivors} outlived the mission. Killing the process group is "
        f"the only thing standing between a timeout and a machine full of orphaned "
        f"compilers."
    )


@pytest.mark.skipif(
    sys.platform != "linux",
    reason="the SEC-33 sweep is Linux-only (/proc-based); see _proc_descendants in jail.py",
)
def test_timeout_kills_a_grandchild_that_detaches_via_setsid(tmp_path: Path) -> None:
    """SEC-33 (cybersecurity review of #113, HIGH). `killpg()` only reaches processes
    still in the child's process group. A process that calls `os.setsid()` — deliberately
    to survive its parent, or as a side effect of a daemonizing library a fuzz target
    links against — starts a new session and process group and is invisible to
    `killpg()` from that instant, while remaining this process's descendant in every
    other sense the kernel tracks.

    Reproduced directly before the fix: the ordinary-grandchild test above passed while
    this one failed — the detached process was confirmed alive, still running, after
    full teardown. This is the test that would have caught it, and the reason the CTO's
    D-053 ruling — which cited "no orphans" as the decisive reason this implementation
    won — is now backed by a claim that covers the case a hostile or merely
    poorly-behaved target can actually reach for, not only the cooperative one.
    """
    pidfile = tmp_path / "detached-pid"
    policy = JailPolicy(cpu_seconds=60, wall_clock_seconds=2.0, kill_grace_seconds=0.5)

    with Jail.create(policy) as jail:
        result = jail.run(
            python(
                f"""
                import os, sys, time
                pid = os.fork()
                if pid == 0:
                    os.setsid()  # detach into a brand new session and process group
                    with open({str(pidfile)!r}, "w") as fh:
                        fh.write(str(os.getpid()))
                        fh.flush()
                    time.sleep(600)
                    sys.exit(0)
                time.sleep(600)
                """
            )
        )

    assert result.limit_hit is LimitKind.WALL_CLOCK, result.summary()

    for _ in range(50):
        if pidfile.exists() and pidfile.read_text().strip():
            break
        time.sleep(0.1)
    detached_pid = int(pidfile.read_text().strip())

    deadline = time.monotonic() + 10
    still_alive = True
    while time.monotonic() < deadline:
        still_alive = _alive(detached_pid)
        if not still_alive:
            break
        time.sleep(0.2)

    assert not still_alive, (
        f"the detached descendant (pid {detached_pid}) outlived the mission by escaping "
        f"the process group. killpg() was never going to reach it; only a parent-id-based "
        f"sweep, independent of process group membership, can."
    )


@pytest.mark.skipif(
    sys.platform != "linux",
    reason="the SEC-38 sweep is Linux-only (/proc-based); see _proc_descendants in jail.py",
)
def test_sweep_catches_rapid_repeated_detachment(tmp_path: Path) -> None:
    """SEC-38 (cybersecurity review of #113, MEDIUM, re-opened by #159).

    `_sweep_detached_descendants`'s single-detachment case (the test above) was never
    the gap. The gap is a descendant that keeps forking new, independently-detached
    descendants of its own *after* the pre-kill snapshot (`known`) was taken — the
    final sweep's own re-walk of `/proc` is anchored on this jail's own child pid
    (`root_pid`), and that pid is normally already dead and reaped by the time the
    sweep runs (`_kill_group` kills and reaps the direct child before ever calling
    this), so a plain `_proc_descendants(root_pid)` walk finds nothing new for the
    entire sweep — only pids already captured in `known` by literal pid membership
    ever get cleaned up. Anything forked by a still-alive detached descendant *after*
    the snapshot has no path back to `root_pid` and is invisible to that walk,
    deterministically, for as long as it keeps happening.

    This is the review's own stated bar for a sufficient regression test: not a single
    detachment, but many descendants forking and detaching in quick succession, spanning
    the real kill window (`kill_grace_seconds` left at its actual default, 5.0 — not
    tightened to make the race easier to hit). A `driver` process detaches immediately,
    then spends 4 real seconds forking a new, separately-detached leaf roughly every
    20ms; the jail's 1.5s wall clock guarantees the pre-kill snapshot lands in the
    middle of that window, so leaves born after it are forking *while the sweep is
    actively running*, not before it starts.
    """
    assert JailPolicy().kill_grace_seconds == 5.0, (
        "this test is required to reproduce at the module's real default, not an "
        "artificially tightened value"
    )
    pid_dir = tmp_path / "leaves"
    pid_dir.mkdir()
    policy = JailPolicy(cpu_seconds=60, wall_clock_seconds=1.5, max_processes=1024)

    with Jail.create(policy) as jail:
        result = jail.run(
            python(
                f"""
                import os, time

                pid_dir = {str(pid_dir)!r}

                driver = os.fork()
                if driver == 0:
                    os.setsid()
                    end = time.monotonic() + 4.0
                    i = 0
                    while time.monotonic() < end:
                        i += 1
                        leaf = os.fork()
                        if leaf == 0:
                            os.setsid()
                            path = os.path.join(pid_dir, f"leaf-{{i}}-{{os.getpid()}}")
                            with open(path, "w") as fh:
                                fh.write(str(os.getpid()))
                                fh.flush()
                            time.sleep(600)
                            os._exit(0)
                        try:
                            os.waitpid(leaf, os.WNOHANG)
                        except ChildProcessError:
                            pass
                        time.sleep(0.02)
                    os._exit(0)
                time.sleep(600)
                """
            )
        )

    assert result.limit_hit is LimitKind.WALL_CLOCK, result.summary()

    deadline = time.monotonic() + 6.0
    leaf_files: list[Path] = []
    while time.monotonic() < deadline:
        leaf_files = list(pid_dir.iterdir())
        if len(leaf_files) >= 40:
            break
        time.sleep(0.1)
    leaf_pids = [int(p.read_text().strip()) for p in leaf_files]
    assert len(leaf_pids) >= 40, (
        f"the fork loop only produced {len(leaf_pids)} leaves before the jail returned; "
        f"not enough to trust this as a real exercise of rapid repeated detachment"
    )

    deadline = time.monotonic() + 10
    survivors = list(leaf_pids)
    while time.monotonic() < deadline:
        survivors = [pid for pid in leaf_pids if _alive(pid)]
        if not survivors:
            break
        time.sleep(0.2)

    assert not survivors, (
        f"{len(survivors)}/{len(leaf_pids)} rapidly-detached descendants outlived the "
        f"mission (SEC-38) — the sweep must catch all of them, not just the ones "
        f"present at the pre-kill snapshot: {sorted(survivors)}"
    )


def _alive(pid: int) -> bool:
    """Is this pid still running and not a zombie?"""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    if sys.platform == "linux":
        try:
            status = Path(f"/proc/{pid}/stat").read_text()
        except OSError:
            return False
        return not status.rpartition(")")[2].strip().startswith("Z")
    return True


# --- cleanup ----------------------------------------------------------------------


def test_cleanup_on_success() -> None:
    jail = Jail.create(JailPolicy(wall_clock_seconds=30))
    root = jail.root
    with jail:
        assert jail.run(["/bin/echo", "fine"]).ok
    assert not root.exists()
    assert jail.closed


def test_cleanup_on_failure() -> None:
    jail = Jail.create(JailPolicy(wall_clock_seconds=30))
    root = jail.root
    with pytest.raises(RuntimeError):
        with jail:
            jail.run(["/bin/sh", "-c", "exit 3"])
            raise RuntimeError("the caller blew up mid-mission")
    assert not root.exists(), "cleanup must run when the caller raises"


def test_cleanup_on_cancel() -> None:
    jail = Jail.create(JailPolicy(wall_clock_seconds=30))
    root = jail.root
    with jail:
        jail.cancel()
    assert not root.exists()


def test_cancel_stops_a_running_command_from_another_thread() -> None:
    policy = JailPolicy(cpu_seconds=60, wall_clock_seconds=120, kill_grace_seconds=0.5)
    jail = Jail.create(policy)
    root = jail.root
    started = time.monotonic()

    def cancel_soon() -> None:
        time.sleep(1.0)
        jail.cancel()

    threading.Thread(target=cancel_soon, daemon=True).start()
    with jail:
        result = jail.run(python("import time; time.sleep(300)"))
    elapsed = time.monotonic() - started

    assert elapsed < 30, f"cancel did not take effect ({elapsed:.1f}s)"
    assert result.signal_number in (signal.SIGTERM, signal.SIGKILL), result.summary()
    assert not root.exists(), "cancel must clean up too"


def test_a_cancelled_jail_refuses_further_commands() -> None:
    with Jail.create(JailPolicy(wall_clock_seconds=30)) as jail:
        jail.cancel()
        with pytest.raises(CancelledError):
            jail.run(["/bin/echo", "no"])


def test_a_closed_jail_refuses_further_commands() -> None:
    jail = Jail.create(JailPolicy(wall_clock_seconds=30))
    jail.close()
    with pytest.raises(JailUnavailableError):
        jail.run(["/bin/echo", "no"])


# --- environment ------------------------------------------------------------------


def test_environment_is_scrubbed_to_the_allowlist(jail, monkeypatch) -> None:
    monkeypatch.setenv("CONTROL_API_OPERATOR_TOKEN", "a-real-looking-secret-value")
    monkeypatch.setenv("DJANGO_SECRET_KEY", "another-secret")
    result = jail.run(python("import os; print('\\n'.join(sorted(os.environ)))"))
    names = set(result.stdout.split())

    assert "CONTROL_API_OPERATOR_TOKEN" not in names
    assert "DJANGO_SECRET_KEY" not in names
    assert "PATH" in names, "a build needs a compiler on PATH"


def test_tmpdir_points_inside_the_jail(jail) -> None:
    result = jail.run(python("import os; print(os.environ['TMPDIR'])"))
    assert Path(result.stdout.strip()).resolve() == jail.root.resolve()


# --- policy -----------------------------------------------------------------------


def test_policy_maps_the_django_sandbox_settings() -> None:
    policy = JailPolicy.from_settings(
        {
            "runtime": "podman",
            "network": "deny",
            "cpu_limit": 4,
            "memory_mb": 8192,
            "max_seconds": 5400,
        }
    )
    assert policy.wall_clock_seconds == 5400
    assert policy.memory_bytes == 8192 * MIB
    assert policy.cpu_seconds == 4 * 5400


def test_policy_rejects_nonsense() -> None:
    for bad in (
        {"cpu_seconds": 0},
        {"memory_bytes": 1024},
        {"wall_clock_seconds": 0},
        {"max_output_bytes": 8},
    ):
        with pytest.raises(ValueError):
            JailPolicy(**bad)


def test_result_reports_the_isolation_mode_honestly(jail) -> None:
    result = jail.run(["/bin/echo", "hello"])
    assert result.isolation_mode == "SUBPROCESS_JAIL", (
        "a subprocess jail must never be recordable as the container path"
    )
