"""What the subprocess jail actually enforces.

The rule this file exists to satisfy: a property is described as enforced only when a
named test demonstrates it. Every claim in `services/sandbox/README.md` points at a test
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

from services.sandbox import (
    CancelledError,
    Jail,
    JailPolicy,
    LimitKind,
    PathEscapeError,
    probe_limits,
)
from services.sandbox.errors import (
    CpuExceededError,
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
