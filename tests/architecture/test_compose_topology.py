"""Egress denial is a property of the compose topology, not of a URL validator.

SEC-01 was Critical: the control-api container — the process that holds the repository
snapshot and assembles model prompts — could reach `api.openai.com`. The reviewer connected
and OpenAI answered. The fix was topology: only nginx sits on a routable network, and
everything else sits on networks declared `internal: true`.

The live proof of that is `infrastructure/scripts/finale-egress-evidence.sh`, which starts the
stack and attempts real outbound connections. It is the right test and it is too expensive to
run on every PR — Docker-in-CI is a real cost, and the CTO cut D1's CI to two jobs.

So this file is the cheap guard that runs every time instead. It reads the compose files as
data and asserts the topology that makes the expensive test pass. It cannot prove egress is
denied. It can prove nobody quietly reattached a container to the routable network, which is
the regression that would otherwise land silently and take the product's central claim with it.

Written after the security re-verification observed that the approved claim was "one careless
commit from false, with nothing failing".
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

COMPOSE_DIR = Path(__file__).resolve().parents[2] / "infrastructure" / "compose"

DEV = COMPOSE_DIR / "docker-compose.yml"
FINALE = COMPOSE_DIR / "docker-compose.finale.yml"

# nginx is the ingress and is routable by design — that is what it is for.
INGRESS = {"nginx"}

# Reviewed exception, development profile only. `command-center-deps` is a short-lived
# `npm ci` that exits before the dev server starts and never holds repository content.
# It is encoded here as an allowlist rather than left to drift, which is the whole point:
# an exception nobody wrote down becomes an exception nobody notices.
DEV_ROUTABLE_EXCEPTIONS = {"command-center-deps"}

# Services that must never be routable in any profile. These are the ones that hold
# repository content, assemble prompts, or hold credentials.
MUST_NEVER_BE_ROUTABLE = {"control-api", "worker", "db", "redis"}

SNAPSHOT_BODY_LIMIT_MIB = 512
SNAPSHOT_TMPFS_MIN_MIB = 640


def _load(path: Path) -> dict:
    if not path.exists():
        pytest.skip(f"{path.name} does not exist yet")
    return yaml.safe_load(path.read_text()) or {}


def _routable_networks(doc: dict) -> set[str]:
    """Networks a container can reach the internet through.

    A compose network is egress-capable unless it is declared `internal: true`.
    Absent means routable — the insecure default is the silent one, which is why
    this asserts on the declaration rather than trusting omission.
    """
    return {
        name
        for name, cfg in (doc.get("networks") or {}).items()
        if not (cfg or {}).get("internal") is True
    }


def _services_on_routable(doc: dict) -> set[str]:
    routable = _routable_networks(doc)
    out = set()
    for service, cfg in (doc.get("services") or {}).items():
        attached = cfg.get("networks") or []
        names = attached.keys() if isinstance(attached, dict) else attached
        if routable.intersection(names):
            out.add(service)
    return out


def _tmpfs_size_mib(service: dict, mountpoint: str = "/tmp") -> int:
    prefix = f"{mountpoint}:size="
    matches = [entry for entry in service.get("tmpfs") or [] if entry.startswith(prefix)]
    assert len(matches) == 1, f"expected one sized {mountpoint} tmpfs, found {matches}"
    value = matches[0].removeprefix(prefix)
    assert value.endswith("m"), f"tmpfs size must be explicit MiB, got {value}"
    return int(value.removesuffix("m"))


@pytest.mark.parametrize("path", [DEV, FINALE], ids=["dev", "finale"])
def test_every_network_declares_its_intent(path: Path) -> None:
    """No network may be left implicitly routable.

    `internal: true` or an explicit comment-free declaration — either way the value is
    present. A network that simply omits the key is routable, and reads as if nobody decided.
    """
    doc = _load(path)
    networks = doc.get("networks") or {}
    assert networks, f"{path.name} declares no networks at all"

    undeclared = [
        name
        for name, cfg in networks.items()
        if "internal" not in (cfg or {})
    ]
    # The ingress network is the one that is meant to be routable.
    undeclared = [n for n in undeclared if n != "external"]
    assert not undeclared, (
        f"{path.name}: networks {sorted(undeclared)} do not declare `internal`. "
        "Absent means routable. Say so on purpose or set `internal: true`."
    )


def test_finale_exposes_only_the_ingress() -> None:
    """The competition profile. Nothing but nginx may reach the internet."""
    doc = _load(FINALE)
    routable = _services_on_routable(doc)
    assert routable == INGRESS, (
        f"finale profile: expected only {sorted(INGRESS)} on a routable network, "
        f"found {sorted(routable)}. This is SEC-01. The process holding repository "
        "content must not be able to reach an external inference API."
    )


def test_dev_exposes_only_the_ingress_and_reviewed_exceptions() -> None:
    doc = _load(DEV)
    routable = _services_on_routable(doc)
    allowed = INGRESS | DEV_ROUTABLE_EXCEPTIONS
    unexpected = routable - allowed
    assert not unexpected, (
        f"development profile: {sorted(unexpected)} are on a routable network. "
        f"Only {sorted(allowed)} are allowed, and every exception is a reviewed one — "
        "add it to DEV_ROUTABLE_EXCEPTIONS with a reason, or take it off the network."
    )


@pytest.mark.parametrize("path", [DEV, FINALE], ids=["dev", "finale"])
def test_content_holding_services_are_never_routable(path: Path) -> None:
    """The rule that does not bend, in either profile.

    These services hold the repository snapshot, assemble prompts, or hold credentials.
    No exception list reaches them.
    """
    doc = _load(path)
    routable = _services_on_routable(doc)
    declared = set((doc.get("services") or {}).keys())
    violations = routable & MUST_NEVER_BE_ROUTABLE & declared
    assert not violations, (
        f"{path.name}: {sorted(violations)} are on a routable network. "
        "These hold repository content or credentials and must never be."
    )


@pytest.mark.parametrize("path", [DEV, FINALE], ids=["dev", "finale"])
@pytest.mark.parametrize("service_name", ["nginx", "control-api"])
def test_snapshot_buffer_tmpfs_exceeds_the_body_limit(
    path: Path, service_name: str
) -> None:
    """SEC-38: a legal snapshot body must fit with bounded scratch headroom."""
    service = (_load(path).get("services") or {}).get(service_name) or {}
    size_mib = _tmpfs_size_mib(service)
    assert size_mib >= SNAPSHOT_TMPFS_MIN_MIB, (
        f"{path.name} {service_name} /tmp is {size_mib} MiB; the "
        f"{SNAPSHOT_BODY_LIMIT_MIB} MiB snapshot ceiling requires at least "
        f"{SNAPSHOT_TMPFS_MIN_MIB} MiB including buffering overhead"
    )


def test_snapshot_buffer_tmpfs_is_identical_across_profiles() -> None:
    sizes = {
        (path.name, service_name): _tmpfs_size_mib(
            (_load(path).get("services") or {}).get(service_name) or {}
        )
        for path in (DEV, FINALE)
        for service_name in ("nginx", "control-api")
    }
    assert len(set(sizes.values())) == 1, f"snapshot tmpfs sizing drifted: {sizes}"


def test_the_finale_profile_has_no_source_mounts_into_control_api() -> None:
    """A bind mount is an egress path of a different kind.

    The finale is a standalone file rather than an overlay precisely because an overlay
    cannot *delete* a bind mount (D-032). This asserts the reason that decision was made
    still holds.
    """
    doc = _load(FINALE)
    control_api = (doc.get("services") or {}).get("control-api") or {}
    mounts = control_api.get("volumes") or []
    source_mounts = [
        m for m in mounts
        if isinstance(m, str) and (m.startswith(".") or m.startswith("/") or m.startswith("$"))
    ]
    assert not source_mounts, (
        f"finale profile mounts host paths into control-api: {source_mounts}. "
        "The finale image is the artifact; a source mount makes what runs on stage "
        "different from what was tested."
    )
