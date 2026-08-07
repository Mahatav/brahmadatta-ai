"""The Docker socket must never be bind-mounted into any container, and nothing may run
privileged.

Why this is a test and not a convention. The plan called for rootless Podman for the target
sandbox; Podman is not installed on the build host, so the security review accepted
`--network none` plus a non-root user as a substitute. The thing that substitution loses is
rootless's guarantee that a container escape lands you as an unprivileged user rather than
as root on the host. **Never mounting the Docker socket is what most nearly recovers that.**

A container with `/var/run/docker.sock` mounted has root on the host. Not "close to root",
not "root in a namespace" — it can start a new container with `--privileged -v /:/host` and
read or write anything. For a product whose entire job is running attacker-controlled code
from an authorized target repository, that is the whole game. It is also the single most
common thing a developer adds at 2am to make a build step work, which is exactly why it
needs an assertion rather than a note in a README.

The same applies to `privileged: true`, host namespaces, and the capabilities that make a
namespace boundary decorative. `docs/03-technical/23-security-plan.md` lists all of them as
controls: "no privileged mode, host mounts, Docker socket, or cloud metadata."

Two layers, because they fail differently: a structural scan of the compose files, and a
plain text scan of every tracked file, which catches a `docker run -v /var/run/docker.sock`
in a shell script that no YAML parser would ever look at.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_DIR = REPO_ROOT / "infrastructure" / "compose"
COMPOSE_FILES = sorted(COMPOSE_DIR.glob("docker-compose*.yml"))

FORBIDDEN_MOUNT_SOURCES = (
    "/var/run/docker.sock",
    "/run/docker.sock",
    "docker.sock",
    "/var/run/podman/podman.sock",
)

# Capabilities that hand back what dropping root was supposed to take away.
FORBIDDEN_CAPS = {"SYS_ADMIN", "SYS_PTRACE", "SYS_MODULE", "SYS_RAWIO", "NET_ADMIN", "ALL"}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _services(path: Path) -> dict[str, dict]:
    return {k: v for k, v in (_load(path).get("services") or {}).items() if isinstance(v, dict)}


def test_compose_files_exist() -> None:
    """Guards every other test in this file against passing because it found nothing."""
    assert COMPOSE_FILES, f"no compose files found under {COMPOSE_DIR}"


@pytest.mark.parametrize("compose_file", COMPOSE_FILES, ids=lambda p: p.name)
def test_no_container_mounts_a_container_runtime_socket(compose_file: Path) -> None:
    offenders: list[str] = []
    for name, svc in _services(compose_file).items():
        for mount in svc.get("volumes") or []:
            source = mount.split(":")[0] if isinstance(mount, str) else str(mount.get("source", ""))
            for forbidden in FORBIDDEN_MOUNT_SOURCES:
                if forbidden in source:
                    offenders.append(f"{name}: {mount}")

    assert not offenders, (
        f"{compose_file.name} mounts a container runtime socket:\n"
        + "\n".join(f"  - {line}" for line in offenders)
        + "\n\nA container with the Docker socket has root on the host. Never mount it. "
        "If a service needs to start containers, it needs a broker with an allow-list, "
        "not the socket."
    )


@pytest.mark.parametrize("compose_file", COMPOSE_FILES, ids=lambda p: p.name)
def test_no_container_mounts_the_host_root_or_run(compose_file: Path) -> None:
    offenders: list[str] = []
    for name, svc in _services(compose_file).items():
        for mount in svc.get("volumes") or []:
            source = mount.split(":")[0] if isinstance(mount, str) else str(mount.get("source", ""))
            if source in ("/", "/var/run", "/run", "/proc", "/sys", "/etc", "/dev"):
                offenders.append(f"{name}: {mount}")
    assert not offenders, f"{compose_file.name} bind-mounts a host system path:\n" + "\n".join(
        f"  - {line}" for line in offenders
    )


@pytest.mark.parametrize("compose_file", COMPOSE_FILES, ids=lambda p: p.name)
def test_nothing_runs_privileged_or_in_a_host_namespace(compose_file: Path) -> None:
    offenders: list[str] = []
    for name, svc in _services(compose_file).items():
        if svc.get("privileged"):
            offenders.append(f"{name}: privileged: true")
        for key in ("network_mode", "pid", "ipc", "userns_mode", "cgroup"):
            value = svc.get(key)
            if isinstance(value, str) and value.startswith("host"):
                offenders.append(f"{name}: {key}: {value}")
        for cap in svc.get("cap_add") or []:
            if str(cap).upper().removeprefix("CAP_") in FORBIDDEN_CAPS:
                offenders.append(f"{name}: cap_add: {cap}")
    assert not offenders, (
        f"{compose_file.name} weakens container isolation:\n"
        + "\n".join(f"  - {line}" for line in offenders)
        + "\n\nSee docs/03-technical/23-security-plan.md: no privileged mode, host mounts, "
        "Docker socket, or cloud metadata."
    )


def test_no_tracked_file_mounts_the_docker_socket() -> None:
    """Text-level scan of everything git tracks.

    Catches what the YAML scan structurally cannot: a `docker run -v
    /var/run/docker.sock:...` inside a shell script, a Dockerfile, a CI workflow, or a
    helper somebody adds next week. Lines that merely *name* the socket in prose — this
    file, the security plan, a decision record — are not matches, because the pattern
    requires it to appear as a bind mount.
    """
    # Fixed argv, no shell.
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.split("\0")

    offenders: list[str] = []
    for rel in tracked:
        if not rel or rel == str(Path(__file__).relative_to(REPO_ROOT)):
            continue
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            # A bind mount, not a mention: `- /var/run/docker.sock:` or `-v /run/docker.sock:`
            if "docker.sock:" in stripped and not stripped.startswith("#"):
                offenders.append(f"{rel}:{lineno}: {stripped[:100]}")

    assert not offenders, "a tracked file bind-mounts the container runtime socket:\n" + "\n".join(
        f"  - {line}" for line in offenders
    )
