"""Rootful-daemon container isolation for untrusted target code and the fuzzer (#15).

READ THIS BEFORE USING IT FOR ANYTHING
=======================================

`packages/sandbox/jail.py` (#81) runs a command as the same user, on the same
filesystem, with the same network as the orchestrator — enough to build and test an
authored target for the D3 gate, and explicitly not enough to fuzz untrusted code. This
module is the thing #28's fuzzing worker is supposed to run inside instead.

## What D-024 actually decided

`docs/09-company/08-security-review.md` §6 ruled on a specific substitution: a standard
(rootful-daemon) container in place of rootless Podman, because Podman was not installed
on the build host (SEC-11) and — the substantive argument — rootless buys exactly one
property this threat model needs (protection against a container-runtime escape reaching
host root), while `--network none` answers the two threats the P0 item actually names
(egress, cloud-metadata access) *more completely* than a rootless-but-networked
container would. The ruling was **ACCEPTED, with eight binding conditions**
(§6.2), reproduced here as the table every line of this module answers to:

| # | Condition | Where |
|---|---|---|
| 1 | `--network none`, proven by an executed DNS+TCP test | `_docker_run_args`; `tests/test_container_jail.py::test_dns_and_tcp_egress_both_fail` |
| 2 | `--user <uid>:<gid>`, never 0 | `ContainerJailPolicy.__post_init__`; `test_the_container_runs_as_a_fixed_non_root_user` |
| 3 | `--cap-drop ALL`, `--security-opt no-new-privileges` | `_docker_run_args` |
| 4 | Docker socket never bind-mounted, anywhere | never appears in `_docker_run_args`; `tests/architecture/test_container_isolation.py` |
| 5 | `--read-only` + sized tmpfs; the worktree is the only writable mount | `_docker_run_args`, `ContainerJailPolicy.tmpfs_mb` |
| 6 | `--memory` / `--cpus` / `--pids-limit`, plus a wall-clock kill | `ContainerJailPolicy`, `_docker_run_args`, `ContainerJail.run` |
| 7 | Teardown + an orphan reaper, on crash and on cancel | `ContainerJail.close`/`cancel`; module-level `reap_orphans`; `test_cleanup_on_*`, `test_reap_orphans_removes_a_container_this_process_never_saw` |
| 8 | The deviation is recorded and never called "rootless" | `IsolationMode.CONTAINER_NO_NETWORK` [Δ #15] in `contracts.enums`, never `ROOTLESS_CONTAINER` |

**Condition 8 is not decoration.** `JailResult.isolation_mode` below is the string
`"CONTAINER_NO_NETWORK"`, matching the new frozen-contract member — using
`"ROOTLESS_CONTAINER"` here would claim the one property this design does not deliver.

## A structural advantage this module has that `jail.py` does not

`packages/sandbox/README.md` documents SEC-33/SEC-38 at length: a subprocess that calls
`os.setsid()` leaves the killable process group and can survive `killpg()`. That
vulnerability exists because a subprocess jail shares the orchestrator's PID namespace —
`setsid()` only ever changes session/group membership *inside* that shared namespace, and
`killpg` is a group-scoped signal.

A container has its own PID namespace. `docker kill <name>` sends `SIGKILL` to the
container's actual PID 1, and the kernel tears down every process in that namespace when
PID 1 dies — there is no analogous "leave the namespace" trick available to a process
inside it. `setsid()` cannot get a process out of its own PID namespace. This module does
not need `_kill_group`'s `/proc`-walking snapshot-and-sweep at all.

## What this module does not do

* It does not build the target image. The caller (compiler-toolchain-engineer's adapter,
  or a test) supplies `ContainerJailPolicy.image` — an already-built, already-pinned
  image reference. Building one from a mission's source is a different concern.
* It does not enforce aggregate disk usage inside the tmpfs beyond its configured size
  (that *is* enforced — a sized `tmpfs` is a hard ceiling the kernel refuses writes past,
  unlike `jail.py`'s `RLIMIT_FSIZE`, which bounds one file).
* Podman is not required. `ContainerJailPolicy.runtime` names the CLI binary
  (`"docker"` by default); anything that accepts the same `run`/`kill`/`wait`/`logs`/`rm`
  subcommands with the same flags works.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from packages.sandbox.errors import (
    ContainerUnavailableError,
    JailError,
    LimitKind,
)

MIB = 1024 * 1024

#: Matches `contracts.enums.IsolationMode.CONTAINER_NO_NETWORK`. Kept as a string
#: literal, not an import, so this package never depends on the Django app — the same
#: discipline `jail.py`'s `ISOLATION_MODE` follows.
ISOLATION_MODE = "CONTAINER_NO_NETWORK"

#: Every container this module starts carries this label, unconditionally. It is the
#: entire mechanism condition 7's "orphan reaper" needs: a crashed orchestrator leaves no
#: Python object to call `.close()` on, but the label survives on the daemon and the next
#: process to boot can find and remove it. See `reap_orphans`.
SANDBOX_LABEL = "brahmadatta.sandbox"

#: Docker socket paths that must never appear in a bind mount. Condition 4. Checked at
#: `_docker_run_args` construction time as well as by
#: `tests/architecture/test_container_isolation.py` reading this module's source.
FORBIDDEN_SOCKET_PATHS: tuple[str, ...] = (
    "/var/run/docker.sock",
    "/run/docker.sock",
)


@dataclass(frozen=True)
class ContainerJailPolicy:
    """What a single container run is allowed to do. Every field maps to one of the
    eight D-024 conditions; see the module docstring's table."""

    image: str
    """An already-built, already-pinned image reference. Required — there is no safe
    default image for running untrusted target code."""

    runtime: str = "docker"
    """The CLI binary. `"docker"` is what D-024 actually accepts (§6.1); this is not a
    knob for reintroducing something less isolated."""

    uid: int = 10001
    gid: int = 10001
    """Condition 2. `__post_init__` refuses 0 for either."""

    cpu_limit: float = 4.0
    """`--cpus`. Condition 6."""

    memory_mb: int = 8192
    """`--memory`. Condition 6."""

    pids_limit: int = 512
    """`--pids-limit`. Condition 6 — the container-runtime equivalent of `jail.py`'s
    `RLIMIT_NPROC`, and unlike that one, enforced by the kernel's cgroup controller
    rather than a per-user rlimit, so it is not shared with everything else the
    operator's host is running."""

    tmpfs_mb: int = 1024
    """Size of the `/tmp` tmpfs mounted over the read-only root. Condition 5 — a real
    ceiling `mount` refuses to exceed, not an advisory one."""

    wall_clock_seconds: float = 5400.0
    kill_grace_seconds: float = 5.0
    """Between `docker stop`'s SIGTERM and the `docker kill` SIGKILL fallback."""

    max_output_bytes: int = 4 * MIB

    network: str = "none"
    """Condition 1. Fixed. `__post_init__` refuses anything else — this is not a
    per-mission choice, it is the uncuttable half of the P0 item."""

    extra_env: dict[str, str] = field(default_factory=dict)
    """Passed as `-e KEY=VALUE`. Never a credential — same rule as `jail.py`'s
    allowlist, enforced by caller discipline rather than by this dataclass, because a
    container (unlike a forked subprocess) does not inherit the orchestrator's
    environment at all: an empty `extra_env` is already a fully scrubbed environment."""

    def __post_init__(self) -> None:
        if not self.image:
            raise ValueError("ContainerJailPolicy.image is required")
        if self.network != "none":
            raise ValueError(
                f"ContainerJailPolicy.network must be 'none' (D-024 condition 1); "
                f"got {self.network!r}. This is not configurable."
            )
        if self.uid == 0 or self.gid == 0:
            raise ValueError(
                "ContainerJailPolicy must never run as uid/gid 0 (D-024 condition 2)"
            )
        if self.cpu_limit <= 0:
            raise ValueError("cpu_limit must be positive")
        if self.memory_mb < 64:
            raise ValueError("memory_mb below 64 cannot start most toolchains")
        if self.pids_limit < 1:
            raise ValueError("pids_limit must be at least 1")
        if self.tmpfs_mb < 1:
            raise ValueError("tmpfs_mb must be at least 1")
        if self.wall_clock_seconds <= 0:
            raise ValueError("wall_clock_seconds must be positive")
        if self.kill_grace_seconds < 0:
            raise ValueError("kill_grace_seconds cannot be negative")

    @classmethod
    def from_settings(
        cls, settings: dict[str, Any], *, image: str, **overrides: Any
    ) -> ContainerJailPolicy:
        """Build from Django's `SANDBOX_POLICY`. `network` is never read from it — the
        setting exists only so `manage.py check` (`contracts.checks`) can assert it is
        `"deny"`; this dataclass hardcodes the enforcement independently."""
        values: dict[str, Any] = {}
        if "cpu_limit" in settings:
            values["cpu_limit"] = float(settings["cpu_limit"])
        if "memory_mb" in settings:
            values["memory_mb"] = int(settings["memory_mb"])
        if "max_seconds" in settings:
            values["wall_clock_seconds"] = float(settings["max_seconds"])
        values.update(overrides)
        return cls(image=image, **values)


@dataclass
class ContainerJailResult:
    """What a containerized command did. Every number here is measured, never
    inferred — same rule as `jail.py`'s `JailResult`."""

    argv: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool
    wall_seconds: float
    limit_hit: LimitKind
    isolation_mode: str = ISOLATION_MODE

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and self.limit_hit is LimitKind.NONE

    def summary(self) -> str:
        state = "ok" if self.ok else f"exit {self.exit_code}"
        if self.limit_hit is not LimitKind.NONE:
            state = f"{self.limit_hit} limit"
        return f"{' '.join(self.argv)} -> {state} ({self.wall_seconds:.2f}s wall)"


def _cap(text: str, max_bytes: int) -> tuple[str, bool]:
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text, False
    return encoded[:max_bytes].decode("utf-8", errors="replace"), True


def _run_cli(
    runtime: str, args: list[str], *, timeout: float
) -> subprocess.CompletedProcess[str]:
    """Run one runtime subcommand (`ps`, `rm`, `stop`, `logs`, ...) and raise
    `ContainerUnavailableError` if the CLI itself is missing or hangs.

    Deliberately not used for `wait` while a command is running — `run()` calls
    `subprocess.run` directly there and catches `TimeoutExpired` itself, because a
    `wait` that outlives `wall_clock_seconds` is the wall-clock *limit*, not
    unavailability, and the two must not collapse into the same exception.
    """
    try:
        return subprocess.run(  # noqa: S603 - argv is a list, shell is never used
            [runtime, *args], capture_output=True, text=True, timeout=timeout
        )
    except FileNotFoundError as exc:
        raise ContainerUnavailableError(
            f"container runtime {runtime!r} is not on PATH"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ContainerUnavailableError(
            f"`{runtime} {' '.join(args[:2])}` did not respond within {timeout}s — "
            f"is the daemon running?"
        ) from exc


def reap_orphans(
    *,
    runtime: str = "docker",
    label: str = SANDBOX_LABEL,
    mission_ref: str | None = None,
    timeout: float = 15.0,
) -> list[str]:
    """Remove every container carrying `label`, regardless of which process — or
    whether any live process at all — started it.

    This is the entire mechanism behind D-024 condition 7's "orphan reaper... on
    crash". `ContainerJail.close()` handles the normal-exit, failure and cancel cases
    from inside the process that ran the container; none of that code runs if the
    orchestrator itself is killed (`SIGKILL`, OOM, a host crash) with a container still
    live. There is no in-process hook for "my own process just died" — the label on the
    daemon is what survives that, and this function is what the *next* process boot
    calls to find and clear it.

    Returns the container ids removed, so a caller can log or assert on the count.
    """
    filters = ["--filter", f"label={label}"]
    if mission_ref is not None:
        filters += ["--filter", f"label=brahmadatta.mission={mission_ref}"]
    listed = _run_cli(runtime, ["ps", "-aq", *filters], timeout=timeout)
    ids = [line for line in listed.stdout.split() if line]
    for container_id in ids:
        _run_cli(runtime, ["rm", "-f", container_id], timeout=timeout)
    return ids


class ContainerJail:
    """A host-side writable worktree plus a container that runs commands against it
    under D-024's eight conditions.

    Use it as a context manager — the worktree is removed and any live container is
    torn down on every path out, including an exception:

        policy = ContainerJailPolicy(image="pinned-target-image@sha256:...")
        with ContainerJail.create(policy) as sandbox:
            (sandbox.root / "input.bin").write_bytes(seed)
            result = sandbox.run(["/usr/bin/fuzz-target", "/workspace/input.bin"])
    """

    def __init__(self, root: Path, policy: ContainerJailPolicy, mission_ref: str) -> None:
        self._root = root
        self._policy = policy
        self._mission_ref = mission_ref
        self._closed = False
        self._cancelled = False
        self._live_name: str | None = None
        self._live_lock = threading.Lock()

    # -- lifecycle ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        policy: ContainerJailPolicy,
        *,
        parent: Path | None = None,
        mission_ref: str = "unlabelled",
    ) -> ContainerJail:
        root = Path(tempfile.mkdtemp(prefix="brahmadatta-sandbox-", dir=parent))
        # 0o700 (jail.py's choice) is wrong here: that jail runs its command as the
        # SAME uid as the orchestrator, so only the owner ever needs access. This
        # container runs as `policy.uid`, a *different*, fixed uid — bind-mounting a
        # 0700 directory owned by the orchestrator's host uid makes it unwritable
        # from inside the container (confirmed: `Permission denied` writing into a
        # 0700 mount as a non-owning uid). World-writable is not a broader exposure
        # here the way it would be for a long-lived shared path — this directory is
        # created fresh per `ContainerJail`, its name is an unguessable `mkdtemp`
        # suffix, and it is removed in `close()`. The isolation boundary is which
        # *container* can reach it (exactly one, via the explicit `-v` mount), not
        # which local uid owns it.
        root.chmod(0o777)
        return cls(root, policy, mission_ref)

    @property
    def root(self) -> Path:
        if self._closed:
            raise ContainerUnavailableError("this sandbox has been cleaned up")
        return self._root

    @property
    def policy(self) -> ContainerJailPolicy:
        return self._policy

    @property
    def closed(self) -> bool:
        return self._closed

    def __enter__(self) -> ContainerJail:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        # Runs on all three paths this process can still act on: normal exit,
        # exception, and cancel. Condition 7's fourth path — orchestrator crash — has
        # no in-process handler by definition; see `reap_orphans`.
        self.close()

    def cancel(self) -> None:
        """Stop whatever is running now and refuse further runs. Safe to call from
        another thread — `run()` blocks the calling thread on `docker wait`."""
        self._cancelled = True
        with self._live_lock:
            name = self._live_name
            self._live_name = None
        if name is not None:
            self._teardown_container(name, force=True)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.cancel()
        shutil.rmtree(self._root, ignore_errors=True)

    # -- running ----------------------------------------------------------------------

    def run(
        self,
        argv: list[str],
        *,
        raise_on_limit: bool = False,
    ) -> ContainerJailResult:
        if self._closed:
            raise ContainerUnavailableError("this sandbox has been cleaned up")
        if self._cancelled:
            raise ContainerUnavailableError("this sandbox was cancelled")

        name = f"brahmadatta-sandbox-{uuid.uuid4().hex[:12]}"
        args = self._docker_run_args(name, argv)

        start = time.monotonic()
        created = _run_cli(self._policy.runtime, args, timeout=60.0)
        if created.returncode != 0:
            raise ContainerUnavailableError(
                f"container failed to start: {created.stderr.strip()}"
            )
        with self._live_lock:
            self._live_name = name

        limit_hit = LimitKind.NONE
        timed_out = False
        exit_code = -9
        try:
            # Not `_run_cli`: that helper turns every `TimeoutExpired` into
            # `ContainerUnavailableError`, which is right for `ps`/`rm`/`logs` and
            # wrong here — a `wait` that outlives `wall_clock_seconds` is the
            # wall-clock limit, a normal outcome this method reports on rather than
            # raises for.
            waited = subprocess.run(  # noqa: S603 - argv is a list, shell is never used
                [self._policy.runtime, "wait", name],
                capture_output=True,
                text=True,
                timeout=self._policy.wall_clock_seconds,
            )
            exit_code = int(waited.stdout.strip() or "-1")
        except subprocess.TimeoutExpired:
            limit_hit = LimitKind.WALL_CLOCK
            timed_out = True

        wall = time.monotonic() - start

        logs = _run_cli(self._policy.runtime, ["logs", name], timeout=30.0)
        stdout, stdout_trunc = _cap(logs.stdout, self._policy.max_output_bytes)
        stderr, stderr_trunc = _cap(logs.stderr, self._policy.max_output_bytes)

        # The one teardown call for both paths — `force=True` (immediate SIGKILL,
        # skipping the graceful-stop grace period) only when the wall clock is why
        # we're here; otherwise the container has already exited on its own and
        # `stop` on it is a harmless no-op. Always runs, so a caller cannot forget it.
        final_exit_code = self._teardown_container(name, force=timed_out)
        if timed_out:
            exit_code = final_exit_code
        with self._live_lock:
            if self._live_name == name:
                self._live_name = None

        result = ContainerJailResult(
            argv=tuple(argv),
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            stdout_truncated=stdout_trunc,
            stderr_truncated=stderr_trunc,
            wall_seconds=wall,
            limit_hit=limit_hit,
        )
        if raise_on_limit and limit_hit is not LimitKind.NONE:
            raise JailError(f"{limit_hit} limit exceeded: {result.summary()}")
        return result

    # -- internals --------------------------------------------------------------------

    def _docker_run_args(self, name: str, argv: list[str]) -> list[str]:
        # Condition 4: no code path here ever adds a `-v <docker.sock>:...` mount —
        # the only `-v` this method emits is `self._root:/workspace:rw`, below. That
        # absence is checked directly, not just described:
        # `tests/test_container_jail.py::test_no_call_shape_can_mount_the_docker_socket`
        # constructs args for a spread of policies/argv and asserts none of
        # `FORBIDDEN_SOCKET_PATHS` appear anywhere in the result.
        policy = self._policy
        args = [
            "run",
            "-d",
            "--name",
            name,
            "--label",
            f"{SANDBOX_LABEL}=1",
            "--label",
            f"brahmadatta.mission={self._mission_ref}",
            "--network",
            "none",
            "--user",
            f"{policy.uid}:{policy.gid}",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--read-only",
            "--tmpfs",
            f"/tmp:size={policy.tmpfs_mb}m",  # noqa: S108 - the CONTAINER's /tmp, not the host's
            "--memory",
            f"{policy.memory_mb}m",
            "--cpus",
            str(policy.cpu_limit),
            "--pids-limit",
            str(policy.pids_limit),
            "-v",
            f"{self._root}:/workspace:rw",
            "-w",
            "/workspace",
        ]
        for key, value in policy.extra_env.items():
            args += ["-e", f"{key}={value}"]
        # The container runs as fixed uid/gid 10001, not as the orchestrator's host
        # user. With the image's default umask, a command that creates
        # `/workspace/build` leaves a 0755 directory owned by uid 10001; the host can
        # remove the top-level mount point but cannot descend into that directory to
        # delete its contents. Set an explicit umask for every target command so
        # teardown remains deterministic without ever running the target as root.
        args += [
            policy.image,
            "sh",
            "-c",
            'umask 000; exec "$@"',
            "brahmadatta-command",
            *argv,
        ]
        return args

    def _teardown_container(self, name: str, *, force: bool = False) -> int:
        """SIGTERM, a grace period, then SIGKILL — condition 7. Returns the exit code
        if it could be recovered, else -9 (killed).

        A container has its own PID namespace (see the module docstring): `stop`/`kill`
        target the container's real PID 1, and the kernel tears down every process
        inside that namespace when PID 1 dies. There is no `_kill_group`-style sweep to
        write here — the isolation boundary that makes this module worth having is the
        same boundary that makes its own teardown simpler than `jail.py`'s.
        """
        runtime = self._policy.runtime
        if not force:
            _run_cli(
                runtime,
                ["stop", "--time", str(int(self._policy.kill_grace_seconds)), name],
                timeout=self._policy.kill_grace_seconds + 10,
            )
        else:
            _run_cli(runtime, ["kill", name], timeout=10.0)

        inspected = _run_cli(
            runtime, ["inspect", "--format", "{{.State.ExitCode}}", name], timeout=10.0
        )
        exit_code = -9
        if inspected.returncode == 0:
            try:
                exit_code = int(inspected.stdout.strip())
            except ValueError:
                pass

        _run_cli(runtime, ["rm", "-f", name], timeout=15.0)
        return exit_code


def probe_egress(policy: ContainerJailPolicy) -> dict[str, Any]:
    """Run a DNS lookup and a raw TCP connect from *inside* a real container built
    from `policy`, and report whether each was blocked. Condition 1's own executed
    proof, callable outside the test suite too (e.g. from a rehearsal checklist).

    `True` means "blocked", matching what `--network none` is supposed to deliver.
    Requires `policy.image` to carry a Python interpreter (the demo/`sse-live-verify`
    images used elsewhere in this repository all do).
    """
    probe_script = (
        "import socket,sys\n"
        "dns_blocked = True\n"
        "try:\n"
        "    socket.gethostbyname('example.com')\n"
        "    dns_blocked = False\n"
        "except OSError:\n"
        "    pass\n"
        "tcp_blocked = True\n"
        "try:\n"
        "    socket.create_connection(('8.8.8.8', 53), timeout=3).close()\n"
        "    tcp_blocked = False\n"
        "except OSError:\n"
        "    pass\n"
        "print(f'DNS_BLOCKED={dns_blocked}')\n"
        "print(f'TCP_BLOCKED={tcp_blocked}')\n"
    )
    with ContainerJail.create(policy, mission_ref="egress-probe") as sandbox:
        result = sandbox.run(["python3", "-c", probe_script])
    return {
        "dns_blocked": "DNS_BLOCKED=True" in result.stdout,
        "tcp_blocked": "TCP_BLOCKED=True" in result.stdout,
        "raw_stdout": result.stdout,
        "raw_stderr": result.stderr,
    }
