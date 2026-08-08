"""Jail isolation properties, each demonstrated by running something and checking the
consequence — never asserted from reading the source."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from adapters.cpp.errors import JailEscape
from adapters.cpp.jail import Jail, JailLimits


@pytest.fixture
def jail(tmp_path: Path) -> Jail:
    root = tmp_path / "jail-root"
    root.mkdir()
    return Jail(root)


def test_a_command_inside_the_jail_runs_normally(jail: Jail) -> None:
    result = jail.run(["/bin/echo", "hello"])
    assert result.ok
    assert "hello" in result.stdout


def test_cwd_outside_the_jail_is_rejected(jail: Jail) -> None:
    """Injected violation: ask the jail to run a command with a cwd outside its root.
    Demonstrates the working-directory jail rather than assuming it from the code."""
    with pytest.raises(JailEscape):
        jail.run(["/bin/echo", "hi"], cwd="/tmp")


def test_a_symlink_out_of_the_jail_is_rejected(jail: Jail, tmp_path: Path) -> None:
    """Injected violation: a path that is nominally under the jail root but resolves
    (via a symlink) to somewhere else entirely. `contains`/`resolve_inside` must catch
    this, not just a string-prefix check on the unresolved path."""
    outside = tmp_path / "outside"
    outside.mkdir()
    sneaky = jail.root / "sneaky"
    sneaky.symlink_to(outside)
    assert jail.contains(sneaky) is False
    with pytest.raises(JailEscape):
        jail.resolve_inside(sneaky / "whatever")


def test_a_path_inside_the_jail_is_accepted(jail: Jail) -> None:
    inside = jail.root / "subdir"
    inside.mkdir()
    assert jail.contains(inside) is True
    assert jail.resolve_inside(inside) == inside.resolve()


def test_environment_is_scrubbed_to_an_allowlist(jail: Jail, monkeypatch: pytest.MonkeyPatch) -> None:
    """Injected violation: put a secret-shaped variable in the parent process's
    environment and confirm the child does not inherit it."""
    monkeypatch.setenv("SUPER_SECRET_TOKEN", "should-not-leak-into-the-child")
    result = jail.run(["/usr/bin/env"])
    assert result.ok
    assert "SUPER_SECRET_TOKEN" not in result.stdout


def test_home_and_tmpdir_are_jailed(jail: Jail) -> None:
    result = jail.run(["/bin/sh", "-c", "echo $HOME; echo $TMPDIR"])
    assert result.ok
    lines = [line for line in result.stdout.splitlines() if line]
    for line in lines:
        assert jail.contains(Path(line)), f"{line} escapes the jail root {jail.root}"


def test_a_hung_process_is_killed_on_timeout(jail: Jail) -> None:
    """A child that traps SIGTERM must still die — via SIGKILL — inside the grace
    period, and the whole run must not exceed the configured wall clock by more than
    that grace period."""
    started = time.monotonic()
    result = jail.run(
        ["/bin/sh", "-c", 'trap "" TERM; sleep 30'],
        label="hang",
        timeout_seconds=1.0,
    )
    elapsed = time.monotonic() - started
    assert result.timed_out is True
    assert elapsed < 15, "the jail did not enforce its timeout within a reasonable grace period"


def test_a_forked_child_process_is_killed_too(jail: Jail) -> None:
    """The timeout must signal the whole process group, not just the direct child —
    otherwise a `make` that forked a compiler leaves the compiler running as an orphan."""
    marker = jail.root / "child-still-running"
    script = (
        f'(trap "" TERM; sleep 20; touch {marker}) & wait'
    )
    result = jail.run(["/bin/sh", "-c", script], label="fork-hang", timeout_seconds=1.0)
    assert result.timed_out is True
    time.sleep(2.0)
    assert not marker.exists(), "the forked grandchild survived the jail's timeout"


def test_output_is_captured_and_bounded(tmp_path: Path) -> None:
    limits = JailLimits(max_captured_bytes=1024)
    root = tmp_path / "bounded-jail"
    root.mkdir()
    jail = Jail(root, limits=limits)
    result = jail.run(["/bin/sh", "-c", "yes x | head -c 200000"])
    assert result.ok
    assert result.stdout_truncated is True
    assert len(result.stdout) < 200000
    # The full output is still on disk, even though the in-memory copy was capped.
    assert Path(result.stdout_path).stat().st_size >= 200000


def test_rlimit_as_is_not_applied_on_darwin(jail: Jail) -> None:
    """Pins the documented gap rather than letting it drift: `RLIMIT_AS` must be absent
    from `limits_applied` on macOS specifically, because setting it there is known to
    break unrelated allocators (see the module docstring in `adapters/cpp/jail.py`)."""
    import sys

    result = jail.run(["/bin/echo", "hi"])
    if sys.platform == "darwin":
        assert "RLIMIT_AS" not in result.limits_applied
    else:
        assert "RLIMIT_AS" in result.limits_applied
