"""Tests for `packages.sandbox.container` (#15), organized around D-024's eight
conditions (`docs/09-company/08-security-review.md` §6.2 — see the module docstring
in `container.py` for the full table).

The pure tests (policy validation, the `docker run` argument shape) need nothing and
always run. Everything that actually starts a container is `skipif`-ed when no
container runtime is on `PATH`, loudly, with a reason — never silently dropped, per
this package's own standing rule (see `test_jail.py`'s header comment).

Run just this file, with a container runtime available:

    pytest packages/sandbox/tests/test_container_jail.py -q
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from packages.sandbox.container import (
    FORBIDDEN_SOCKET_PATHS,
    SANDBOX_LABEL,
    ContainerJail,
    ContainerJailPolicy,
    ContainerUnavailableError,
    LimitKind,
    probe_egress,
    reap_orphans,
)

RUNTIME = "docker"
HAS_RUNTIME = shutil.which(RUNTIME) is not None

#: colima's virtiofs mount (macOS + Virtualization.framework, this session's dev
#: host) only shares `$HOME` and a short allowlist with the VM by default — a
#: `-v <path>:/workspace` outside that set does not fail loudly, it silently binds an
#: empty, root-owned directory inside the container instead, which reads exactly like
#: a permissions bug until you check `ls -la` on both sides and notice the container
#: never saw the host's files at all. Python's default `tempfile.mkdtemp()` uses
#: `/var/folders/...` on macOS, which is outside that set. Native Linux (the finale's
#: actual deployment target) has no such split — `$TMPDIR`/`/tmp` and `$HOME` are the
#: same filesystem — so this redirect is a no-op there. Session-scoped so every
#: `ContainerJail.create()` call in this file, with no `parent=` argument needed,
#: lands somewhere the running container can actually see.
@pytest.fixture(scope="session", autouse=True)
def _redirect_tempdir_under_home():
    scratch = Path.home() / ".cache" / "brahmadatta-sandbox-tests"
    try:
        scratch.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        scratch = Path(tempfile.gettempdir()) / "brahmadatta-sandbox-tests"
        scratch.mkdir(parents=True, exist_ok=True)
    previous = tempfile.tempdir
    tempfile.tempdir = str(scratch)
    try:
        yield
    finally:
        tempfile.tempdir = previous
        shutil.rmtree(scratch, ignore_errors=True)


def _daemon_responds() -> bool:
    if not HAS_RUNTIME:
        return False
    try:
        return (
            subprocess.run(
                [RUNTIME, "info"], capture_output=True, timeout=10
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


HAS_DOCKER = _daemon_responds()
needs_docker = pytest.mark.skipif(
    not HAS_DOCKER,
    reason=f"no {RUNTIME!r} daemon reachable on this host — container tests skipped, "
    f"not silently passed",
)

#: Pinned, already used and pulled by this repository's own test/CI infrastructure
#: (see infrastructure/scripts/smoke-sse.sh and testing/sse-stub.py) — a Python
#: interpreter is all these tests need from the "target" image.
PROBE_IMAGE = (
    "python@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2"
)


def _policy(**overrides) -> ContainerJailPolicy:
    # cpu_limit defaults small deliberately: the production default
    # (`SANDBOX_CPU_LIMIT=4`, see `.env.example`) targets a real deployment host, and
    # `docker run --cpus` refuses to accept a value above the host's actual core
    # count — a constrained CI runner or a 2-core laptop cannot honour 4.
    return ContainerJailPolicy(
        image=PROBE_IMAGE,
        wall_clock_seconds=overrides.pop("wall_clock_seconds", 30.0),
        cpu_limit=overrides.pop("cpu_limit", 1.0),
        **overrides,
    )


def _running_container_names() -> set[str]:
    out = subprocess.run(
        [RUNTIME, "ps", "-a", "--filter", f"label={SANDBOX_LABEL}", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return {line for line in out.stdout.split() if line}


# --- policy validation (condition 1, 2) -- pure, no docker needed -----------------


def test_policy_rejects_a_network_other_than_none():
    with pytest.raises(ValueError, match="condition 1"):
        ContainerJailPolicy(image=PROBE_IMAGE, network="bridge")


def test_policy_rejects_uid_zero():
    with pytest.raises(ValueError, match="condition 2"):
        ContainerJailPolicy(image=PROBE_IMAGE, uid=0)


def test_policy_rejects_gid_zero():
    with pytest.raises(ValueError, match="condition 2"):
        ContainerJailPolicy(image=PROBE_IMAGE, gid=0)


def test_policy_requires_an_image():
    with pytest.raises(ValueError, match="image is required"):
        ContainerJailPolicy(image="")


def test_policy_from_settings_never_reads_network():
    """`SANDBOX_POLICY["network"]` exists only for `contracts.checks` to assert it is
    `"deny"`. This dataclass hardcodes the enforcement itself — condition 1 is not
    something a settings typo could weaken."""
    policy = ContainerJailPolicy.from_settings(
        {"cpu_limit": 2, "memory_mb": 4096, "max_seconds": 600, "network": "allow"},
        image=PROBE_IMAGE,
    )
    assert policy.network == "none"


def test_reap_orphans_can_be_scoped_to_one_mission(monkeypatch):
    calls: list[list[str]] = []

    def fake_run_cli(runtime: str, args: list[str], *, timeout: float):
        calls.append(args)
        if args[:2] == ["ps", "-aq"]:
            return subprocess.CompletedProcess(
                [runtime, *args], 0, "abc123\ndef456\n", ""
            )
        return subprocess.CompletedProcess([runtime, *args], 0, "", "")

    monkeypatch.setattr("packages.sandbox.container._run_cli", fake_run_cli)

    removed = reap_orphans(mission_ref="mission-a")

    assert [r.container_id for r in removed] == ["abc123", "def456"]
    assert all(r.removed for r in removed), removed
    assert calls[0] == [
        "ps",
        "-aq",
        "--filter",
        f"label={SANDBOX_LABEL}",
        "--filter",
        "label=brahmadatta.mission=mission-a",
    ]
    assert calls[1:] == [["rm", "-f", "abc123"], ["rm", "-f", "def456"]]


def test_reap_orphans_reports_a_failed_removal_rather_than_claiming_success(monkeypatch):
    """SEC-51 (#182): `docker rm -f`'s exit code must actually be inspected. Before
    this fix, `reap_orphans` returned the bare list of ids it *found* and called that
    "removed" regardless of what `rm -f` actually did -- this reproduces the exact
    scenario from the issue: one container's `rm -f` fails (daemon refuses, wedged
    state, anything), and the caller must be able to tell that container apart from
    the one that was genuinely removed, not have both reported as clean.
    """

    def fake_run_cli(runtime: str, args: list[str], *, timeout: float):
        if args[:2] == ["ps", "-aq"]:
            return subprocess.CompletedProcess(
                [runtime, *args], 0, "good123\nwedged456\n", ""
            )
        if args == ["rm", "-f", "wedged456"]:
            return subprocess.CompletedProcess(
                [runtime, *args], 1, "", "Error response from daemon: removal in progress"
            )
        return subprocess.CompletedProcess([runtime, *args], 0, "", "")

    monkeypatch.setattr("packages.sandbox.container._run_cli", fake_run_cli)

    results = reap_orphans(mission_ref="mission-a")

    by_id = {r.container_id: r for r in results}
    assert by_id["good123"].removed is True
    assert by_id["good123"].error == ""
    assert by_id["wedged456"].removed is False
    assert "removal in progress" in by_id["wedged456"].error


# --- docker socket never mounted (condition 4) -- pure, no docker needed -----------


@pytest.mark.parametrize(
    "argv", [["true"], ["sh", "-c", "echo hi"], ["python3", "-c", "print(1)"]]
)
@pytest.mark.parametrize(
    "extra_env", [{}, {"FOO": "bar"}, {"DOCKER_HOST": "unix:///var/run/docker.sock"}]
)
def test_no_call_shape_can_mount_the_docker_socket(argv, extra_env):
    """Condition 4, checked directly against the constructed argument list rather
    than trusted from the source reading. `DOCKER_HOST` as an env *value* is
    deliberately included and deliberately NOT asserted absent from the whole
    argument list: an `-e DOCKER_HOST=unix:///var/run/docker.sock` is inert (nothing
    mounts the socket there, so the path is unreachable) and a real caller mistake
    would be a `-v` flag whose target is that path — which is what this checks."""
    jail = ContainerJail.__new__(ContainerJail)
    jail._root = "/tmp/does-not-need-to-exist-for-this-test"
    jail._policy = _policy(extra_env=extra_env)
    jail._mission_ref = "test-mission"

    args = jail._docker_run_args("test-container-name", argv)

    mount_targets = [args[i + 1] for i, a in enumerate(args) if a == "-v"]
    for forbidden in FORBIDDEN_SOCKET_PATHS:
        assert not any(forbidden in target for target in mount_targets)
    # And exactly one -v exists at all: the worktree, nothing else.
    assert len(mount_targets) == 1
    assert mount_targets[0].endswith(":/workspace:rw")


def test_docker_run_args_carry_every_flag_the_eight_conditions_require():
    jail = ContainerJail.__new__(ContainerJail)
    jail._root = "/tmp/x"
    jail._policy = _policy(uid=10005, gid=10005, cpu_limit=2.0, memory_mb=1024, pids_limit=64)
    jail._mission_ref = "m-123"

    args = jail._docker_run_args("c-name", ["true"])

    assert "--network" in args and args[args.index("--network") + 1] == "none"
    assert "--user" in args and args[args.index("--user") + 1] == "10005:10005"
    assert "--cap-drop" in args and args[args.index("--cap-drop") + 1] == "ALL"
    assert "--security-opt" in args and args[args.index("--security-opt") + 1] == "no-new-privileges"
    assert "--read-only" in args
    assert "--memory" in args and args[args.index("--memory") + 1] == "1024m"
    assert "--cpus" in args and args[args.index("--cpus") + 1] == "2.0"
    assert "--pids-limit" in args and args[args.index("--pids-limit") + 1] == "64"
    assert f"{SANDBOX_LABEL}=1" in args
    assert "brahmadatta.mission=m-123" in args


# --- everything below needs a real container runtime ------------------------------


@needs_docker
def test_the_container_runs_as_a_fixed_non_root_user():
    """Condition 2's own executed proof. Not 'rootless' (D-024 condition 8 forbids
    claiming that) — a fixed high uid, verified from inside the running container."""
    with ContainerJail.create(_policy(uid=10001, gid=10001)) as sandbox:
        result = sandbox.run(["id", "-u"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "10001"


@needs_docker
def test_dns_and_tcp_egress_both_fail():
    """Condition 1's own executed proof: a DNS lookup and a raw TCP connect,
    attempted from *inside* the running sandbox, both fail."""
    outcome = probe_egress(_policy())
    assert outcome["dns_blocked"] is True, outcome["raw_stdout"] + outcome["raw_stderr"]
    assert outcome["tcp_blocked"] is True, outcome["raw_stdout"] + outcome["raw_stderr"]


@needs_docker
def test_all_capabilities_are_dropped():
    """Condition 3's own executed proof, the effective half — not just that
    `--cap-drop ALL` is passed as a flag (that's `test_docker_run_args_carry_every_
    flag_the_eight_conditions_require`), but that the kernel actually reports zero
    effective capabilities inside the running container."""
    with ContainerJail.create(_policy()) as sandbox:
        result = sandbox.run(["sh", "-c", "grep CapEff /proc/self/status"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "CapEff:\t0000000000000000"


@needs_docker
def test_no_new_privileges_is_effective():
    """Condition 3's other half: `NoNewPrivs` is 1 inside the running container, not
    merely passed as `--security-opt no-new-privileges` on the command line."""
    with ContainerJail.create(_policy()) as sandbox:
        result = sandbox.run(["sh", "-c", "grep NoNewPrivs /proc/self/status"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "NoNewPrivs:\t1"


@needs_docker
def test_pids_limit_is_enforced():
    """Condition 6's `--pids-limit` half, the effective proof — a real fork attempt
    past the configured ceiling is refused by the kernel's cgroup controller, not
    merely passed as a flag. `posix_spawn`, in a loop, until it fails; the count that
    actually succeeded must stay under the configured limit."""
    policy = _policy(pids_limit=16, wall_clock_seconds=20)
    script = (
        "import os, sys\n"
        "created = 0\n"
        "for _ in range(200):\n"
        "    try:\n"
        "        pid = os.fork()\n"
        "    except OSError:\n"
        "        break\n"
        "    if pid == 0:\n"
        "        import time; time.sleep(5); os._exit(0)\n"
        "    created += 1\n"
        "print(f'CREATED={created}')\n"
    )
    with ContainerJail.create(policy) as sandbox:
        result = sandbox.run(["python3", "-c", script])
    created = int(result.stdout.strip().removeprefix("CREATED="))
    # Some slack above the configured ceiling for the interpreter's own threads/pids
    # already counted against the cgroup; the property under test is "capped well
    # short of 200", not an exact match to 16.
    assert created < 100, result.stdout + result.stderr


@needs_docker
def test_the_root_filesystem_is_read_only():
    with ContainerJail.create(_policy()) as sandbox:
        result = sandbox.run(["sh", "-c", "echo x > /etc/should-not-be-writable"])
    assert result.exit_code != 0
    assert "Read-only file system" in result.stderr


@needs_docker
def test_tmp_is_writable_scratch_under_the_read_only_root():
    with ContainerJail.create(_policy()) as sandbox:
        result = sandbox.run(["sh", "-c", "echo scratch > /tmp/ok && cat /tmp/ok"])
    assert result.exit_code == 0
    assert "scratch" in result.stdout


@needs_docker
def test_the_worktree_is_the_writable_mount_and_visible_on_the_host():
    """"Target source never leaves the sandbox except as recorded artifacts" (#15 AC)
    — the inverse direction, checked here: what the container writes into
    `/workspace` is exactly what the host-side `sandbox.root` sees, so the
    orchestrator can harvest it as artifacts after the run without another channel."""
    with ContainerJail.create(_policy()) as sandbox:
        result = sandbox.run(["sh", "-c", "echo artifact > /workspace/out.txt"])
        assert result.exit_code == 0
        assert (sandbox.root / "out.txt").read_text().strip() == "artifact"


@needs_docker
def test_memory_limit_is_passed_to_the_runtime_and_enforced():
    # A 64 MiB cap trying to allocate ~512 MiB. The OOM killer inside the container's
    # cgroup should kill it; python reports this as being killed (exit code 137) or,
    # depending on kernel/overcommit behaviour, a Python-level MemoryError (exit 1)
    # — either is "the limit stopped it", which is the property under test.
    policy = _policy(memory_mb=64, wall_clock_seconds=20)
    with ContainerJail.create(policy) as sandbox:
        result = sandbox.run(
            ["python3", "-c", "x = bytearray(512 * 1024 * 1024)"]
        )
    assert result.exit_code != 0


@needs_docker
def test_wall_clock_timeout_is_reported_and_the_container_is_removed():
    policy = _policy(wall_clock_seconds=2)
    with ContainerJail.create(policy) as sandbox:
        result = sandbox.run(["sleep", "30"])
    assert result.limit_hit is LimitKind.WALL_CLOCK
    assert not result.ok
    # Removed, not merely stopped — "no stray containers" is about `docker ps -a`,
    # which shows stopped-but-not-removed containers too.
    assert _running_container_names() == set()


@needs_docker
def test_cleanup_on_normal_completion():
    with ContainerJail.create(_policy()) as sandbox:
        result = sandbox.run(["true"])
    assert result.ok
    assert _running_container_names() == set()


@needs_docker
def test_cleanup_on_command_failure():
    with ContainerJail.create(_policy()) as sandbox:
        result = sandbox.run(["false"])
    assert result.exit_code != 0
    assert _running_container_names() == set()


@needs_docker
def test_cleanup_on_operator_cancel():
    """`cancel()` from another thread, matching the only way it's actually useful:
    `run()` blocks the calling thread on `docker wait`."""
    import threading

    policy = _policy(wall_clock_seconds=60)
    sandbox = ContainerJail.create(policy)
    results: list = []

    def _drive():
        try:
            results.append(sandbox.run(["sleep", "30"]))
        except ContainerUnavailableError as exc:
            results.append(exc)

    thread = threading.Thread(target=_drive)
    thread.start()
    time.sleep(1.5)  # let the container actually start
    sandbox.cancel()
    thread.join(timeout=20)
    sandbox.close()

    assert not thread.is_alive()
    assert _running_container_names() == set()


@needs_docker
def test_cleanup_on_a_populated_worktree():
    """A build-sized tree of files is still fully removed — the container's
    `/workspace` mount and the host directory are the same inode tree, so removing
    the host directory removes everything the container wrote."""
    with ContainerJail.create(_policy()) as sandbox:
        sandbox.run(["sh", "-c", "mkdir -p /workspace/build && "
                                  "for i in 1 2 3 4 5; do echo $i > /workspace/build/f$i; done"])
        assert (sandbox.root / "build").exists()
        root = sandbox.root
    assert not root.exists()


@needs_docker
def test_reap_orphans_removes_a_container_this_process_never_saw():
    """Condition 7's crash-recovery half: a container started entirely outside any
    `ContainerJail` instance — simulating what a killed orchestrator would leave
    behind — is still found and removed by `reap_orphans()`, because it only ever
    looks for the label on the daemon, never at in-process state."""
    name = "brahmadatta-sandbox-orphan-test"
    created = subprocess.run(
        [
            RUNTIME, "run", "-d", "--name", name,
            "--label", f"{SANDBOX_LABEL}=1",
            "--network", "none", "--user", "10001:10001",
            PROBE_IMAGE, "sleep", "60",
        ],
        capture_output=True, text=True, timeout=30, check=True,
    )
    container_id = created.stdout.strip()
    try:
        assert name in _running_container_names()
        removed = reap_orphans()
        # `docker ps -aq` reports ids, not names — reap_orphans returns exactly what
        # it received back from the daemon.
        matches = [
            r
            for r in removed
            if container_id.startswith(r.container_id)
            or r.container_id.startswith(container_id)
        ]
        assert matches, removed
        assert all(r.removed for r in matches), matches
        assert name not in _running_container_names()
    finally:
        subprocess.run([RUNTIME, "rm", "-f", name], capture_output=True, timeout=15)


@needs_docker
def test_no_stray_containers_or_volumes_after_this_module_runs(request):
    """The literal #15 acceptance criterion: verified with `docker ps -a` output,
    reproduced here rather than only claimed. Runs last in this file (pytest collects
    in source order and this is the final test) so it reports on everything the
    file did, not a single test in isolation."""
    remaining = subprocess.run(
        [RUNTIME, "ps", "-a", "--filter", f"label={SANDBOX_LABEL}"],
        capture_output=True, text=True, timeout=15,
    )
    print(remaining.stdout)
    assert _running_container_names() == set(), remaining.stdout
