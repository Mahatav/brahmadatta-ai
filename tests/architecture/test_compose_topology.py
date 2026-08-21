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

# Reviewed exception, development profile only (D-073's Postgres-reachability follow-up):
# `db` publishes 127.0.0.1:${POSTGRES_PORT:-5432} so `fuzz-worker`, a bare-metal host
# process with no route onto the `backend` network, can reach it. Loopback-only, and
# `docker-compose.finale.yml` deliberately does NOT carry this — see that decision's
# own text on why the finale profile is left alone. `_host_port_bindings` below checks
# the exception is actually loopback-bound, not just present by name.
DEV_HOST_PORT_EXCEPTIONS = {"db"}

# Services that must never be routable in any profile. These are the ones that hold
# repository content, assemble prompts, or hold credentials.
#
# model-host-auth (D-075) holds MODEL_HOST_BEARER_TOKEN and is not expected to ever
# gain its own `networks:` entry (it joins model-host's namespace via `network_mode`
# instead, asserted separately by test_model_host_auth_sidecar_shares_model_hosts_
# namespace) — listed here too as a defence-in-depth net in case someone later adds a
# `networks:` block alongside removing `network_mode`.
MUST_NEVER_BE_ROUTABLE = {"control-api", "worker", "db", "redis", "model-host", "model-host-auth"}

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
        if (cfg or {}).get("internal") is not True
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


def _host_port_bindings(cfg: dict) -> list[str]:
    """Raw `ports:` entries for one service, as compose's short syntax strings.

    Only the short `"HOST_IP:HOST_PORT:CONTAINER_PORT"` form is used anywhere in these
    compose files (checked directly), so this does not handle the long mapping form —
    it would need extending, not silently passing, if that ever changes.
    """
    return [str(p) for p in (cfg or {}).get("ports") or []]


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


def test_finale_stage_origin_is_loopback_http_only() -> None:
    """Issue #92: the stage browser must not hit a TLS warning on localhost.

    #230: the HOST side of this port is now `${NGINX_FINALE_HTTP_PORT:-8080}`, not a
    bare literal — a linked worktree's finale-up.sh assigns a distinct host port so two
    worktrees' nginx containers do not collide trying to bind the same one. The
    CONTAINER side stays a literal `8080` always (nginx's own `listen` directive, see
    test_finale_localhost_ingress.py), which is what this test actually cares about:
    loopback-scoped, exactly one mapping, plaintext only. It no longer pins the host
    port's literal value, only its shape and default.
    """
    doc = _load(FINALE)
    nginx = (doc.get("services") or {}).get("nginx") or {}
    ports = nginx.get("ports") or []
    volumes = nginx.get("volumes") or []

    assert ports == ["127.0.0.1:${NGINX_FINALE_HTTP_PORT:-8080}:8080"]
    assert not any("8443" in str(port) for port in ports)
    assert not any("certs" in str(volume) for volume in volumes)


def test_dev_db_port_is_published_on_loopback_only() -> None:
    """D-073: the dev profile's `db` publishes a host port so the bare-metal
    `fuzz-worker` process (infrastructure/scripts/run-fuzz-worker.sh) can reach
    Postgres from outside the compose network at all — `db` itself stays off any
    routable network (`test_content_holding_services_are_never_routable` covers
    that). This asserts the *host* side of that publish never widens past loopback —
    a `"5432:5432"` or `0.0.0.0:...` edit here would make Postgres reachable from
    anything else on the operator's network, not just this host's own processes.
    """
    doc = _load(DEV)
    db = (doc.get("services") or {}).get("db") or {}
    ports = db.get("ports") or []

    assert ports, "db has no published port; if D-073's fuzz-worker fix was reverted, update this test too"
    for port in ports:
        assert str(port).startswith("127.0.0.1:"), (
            f"db port {port!r} is not loopback-scoped. Every published port in this "
            "compose family binds 127.0.0.1 only — see nginx's own ports for the "
            "existing pattern this must match."
        )


def test_finale_db_publishes_no_port() -> None:
    """The finale profile's own header comment states "no port is published except
    through nginx" as an explicit invariant (item 6 of its documented differences
    from the dev profile). D-073 needed a bare-metal Postgres connection for
    fuzz-worker and deliberately did NOT extend the dev fix to this file — that is
    an open decision for CTO/devops-engineer plus a `cybersecurity` review, not
    made silently. This test is the tripwire: if `db` ever gains a `ports:` entry
    here without that decision being recorded, this fails instead of the invariant
    quietly eroding.
    """
    doc = _load(FINALE)
    db = (doc.get("services") or {}).get("db") or {}
    assert not db.get("ports"), (
        "docker-compose.finale.yml's db service now publishes a port. That is a "
        "deliberate, reviewed exception to this file's own stated invariant ('no "
        "port is published except through nginx') or it is a regression — which one "
        "must be recorded in .project/decisions.md (see the D-073 follow-up entry) "
        "before this assertion is relaxed."
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
def test_only_the_ingress_publishes_a_host_port(path: Path) -> None:
    """QA gap found reviewing PR #201 (D-075/SEC-50): every test above this one guards
    `networks:`/`internal:` membership, but `ports:` (a host-port publish) is a
    completely separate Compose mechanism that bypasses Docker network membership
    entirely — a `ports:` entry on `model-host` or `model-host-auth` would make Ollama
    (or its bearer-token gate) reachable from anything with LAN/host access, no Docker
    daemon access required at all, which is a *lower* bar for an attacker than the
    SEC-50 PoC this file's D-075 tests were written to guard against.

    Verified live during PR #201 QA: injecting `ports: ["11434:11434"]` into
    `model-host-auth` in this file left every existing test in this module green and
    `docker compose config --quiet` silent — nothing here would have caught it.

    docker-compose.yml's own header comment on the `nginx` service already states the
    invariant this enforces: "the single published surface: nothing else maps a host
    port." This was previously true by convention only, unchecked by any test.

    `db` (dev profile only) is a reviewed exception, not a hole this test missed —
    D-073's Postgres-reachability follow-up publishes it for `fuzz-worker`, but only
    loopback-bound. The allowlist alone would not have caught the `model-host-auth`
    PoC above if it degenerated into "any published port is fine once one exception
    exists", so this also asserts every allowed publish is actually `127.0.0.1:...`,
    not `0.0.0.0` or unbound.
    """
    doc = _load(path)
    services = doc.get("services") or {}
    published = {name for name, cfg in services.items() if (cfg or {}).get("ports")}
    allowed = INGRESS | (DEV_HOST_PORT_EXCEPTIONS if path is DEV else set())
    assert published == allowed, (
        f"{path.name}: {sorted(published)} publish a host port via `ports:`. "
        f"Only {sorted(allowed)} may — a `ports:` entry on any other service exposes "
        "it to the host/LAN directly, bypassing every `internal: true` network "
        "boundary this file otherwise enforces. See D-075/SEC-50 in "
        ".project/decisions.md."
    )
    for name in published - INGRESS:
        bindings = _host_port_bindings(services[name])
        not_loopback = [b for b in bindings if not b.startswith("127.0.0.1:")]
        assert not not_loopback, (
            f"{path.name}: {name}'s host-port exception is only reviewed as "
            f"loopback-only, but publishes {not_loopback} — LAN-reachable is a "
            "different, unreviewed exposure. See D-073 in .project/decisions.md."
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


@pytest.mark.parametrize("path", [DEV, FINALE], ids=["dev", "finale"])
def test_model_host_is_internal_only_and_memory_capped(path: Path) -> None:
    doc = _load(path)
    model_host = (doc.get("services") or {}).get("model-host")
    assert model_host is not None, f"{path.name} has no model-host service"
    assert model_host.get("profiles") == ["model"]
    assert model_host.get("mem_limit"), f"{path.name} model-host has no hard mem_limit"
    assert model_host.get("networks") == ["backend"]
    assert "external" not in model_host.get("networks", [])
    assert "ollama/ollama@sha256:" in model_host.get("image", "")


# ----------------------------------------------------------------------------------------
# D-075 / SEC-50 — cybersecurity's review of PR #197 proved that `internal: true` on
# `backend` does not stop a NEW container, created by anything holding Docker daemon access
# (which `fuzz-worker` is irreducibly granted under D-073), from joining `backend` directly
# and reaching a `0.0.0.0`-bound `model-host` at L3/L4 with zero credential. The fix is
# topology PLUS a secret the transport itself demands, not topology alone — these tests
# guard both halves so a future edit cannot quietly widen Ollama's bind back to every
# interface, or drop the sidecar that is the only thing standing between `backend` and it.
# See .project/decisions.md's D-075 for the full ruling and the live verification this
# was proven against (docker compose up, real curl probes with/without the token, and a
# direct-connect attempt against Ollama's own internal port from an adversary-joined
# container — all recorded in the PR, not just asserted here).
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("path", [DEV, FINALE], ids=["dev", "finale"])
def test_model_host_never_binds_a_non_loopback_interface(path: Path) -> None:
    """The other half of SEC-50's fix: `OLLAMA_HOST` must never be `0.0.0.0` (or any
    other non-loopback address) again. `0.0.0.0:11434` is exactly the bind cybersecurity's
    PoC reached from a container that had only just joined `backend` — loopback-only,
    inside Ollama's own network namespace, is what makes that PoC's connection attempt
    fail closed regardless of which network the namespace's owning container sits on.
    """
    doc = _load(path)
    model_host = (doc.get("services") or {}).get("model-host") or {}
    ollama_host = (model_host.get("environment") or {}).get("OLLAMA_HOST", "")
    assert ollama_host, f"{path.name} model-host has no OLLAMA_HOST set"
    assert ollama_host.startswith("127.0.0.1:"), (
        f"{path.name} model-host OLLAMA_HOST={ollama_host!r} is not loopback-only. "
        "This is SEC-50: a 0.0.0.0 (or any other non-loopback) bind here is directly "
        "reachable by any container that joins `backend`, however it got there — "
        "`internal: true` does not stop a NEW container from joining. See D-075."
    )


@pytest.mark.parametrize("path", [DEV, FINALE], ids=["dev", "finale"])
def test_model_host_auth_sidecar_shares_model_hosts_namespace(path: Path) -> None:
    """`network_mode: "service:model-host"`, not a second, independent `backend`
    membership — that is what makes this sidecar the ONLY thing that can still reach
    Ollama's now loopback-only bind: it runs *inside* the one namespace where that
    loopback is visible, rather than routing to it over `backend` the way every other
    container (including an adversary's, per SEC-50's own PoC) would have to.
    """
    doc = _load(path)
    sidecar = (doc.get("services") or {}).get("model-host-auth")
    assert sidecar is not None, f"{path.name} has no model-host-auth service"
    assert sidecar.get("profiles") == ["model"]
    assert sidecar.get("network_mode") == "service:model-host", (
        f"{path.name} model-host-auth must join model-host's network namespace "
        "directly, not attach to `backend` as an independent member."
    )
    # Compose itself refuses `network_mode: service:x` together with `networks:` — this
    # is the cheap assertion that nobody "fixed" a lint complaint by adding one back.
    assert "networks" not in sidecar, (
        f"{path.name} model-host-auth declares its own `networks:` as well as "
        "`network_mode: service:model-host` — these are mutually exclusive in "
        "practice; Compose will refuse this at 'docker compose config' time."
    )
    assert "nginxinc/nginx-unprivileged@sha256:" in sidecar.get("image", "")
    assert sidecar.get("depends_on", {}).get("model-host", {}).get("condition") == (
        "service_healthy"
    )
    assert sidecar.get("read_only") is True
    assert sidecar.get("cap_drop") == ["ALL"]


def test_model_host_auth_requires_a_real_token_in_finale() -> None:
    """Same `:?`-guard convention this file already uses for POSTGRES_PASSWORD/
    REDIS_PASSWORD — the finale stack must refuse to start `--profile model` at all
    without a real MODEL_HOST_BEARER_TOKEN, rather than silently running the sidecar
    with an empty/guessable check.
    """
    doc = _load(FINALE)
    sidecar = (doc.get("services") or {}).get("model-host-auth") or {}
    token_expr = (sidecar.get("environment") or {}).get("MODEL_HOST_BEARER_TOKEN", "")
    assert ":?" in token_expr, (
        f"docker-compose.finale.yml model-host-auth's MODEL_HOST_BEARER_TOKEN is "
        f"{token_expr!r}, not `:?`-guarded. The finale stack must not be able to start "
        "`--profile model` with an unset/empty bearer token."
    )


def test_model_host_auth_template_fails_closed_unconditionally() -> None:
    """The nginx conf template itself, not just the compose wiring: every request
    without the exact `Authorization: Bearer <token>` header must be rejected before
    `proxy_pass` is ever reached, in both profiles — there is deliberately no
    "skip the check when the token is blank" branch (see the template's own header
    comment for why that would defeat the fix in dev specifically).
    """
    template_path = (
        COMPOSE_DIR / "nginx" / "model-host-auth" / "templates" / "model-host-auth.conf.template"
    )
    assert template_path.is_file(), f"{template_path} is missing"
    text = template_path.read_text(encoding="utf-8")

    assert "MODEL_HOST_BEARER_TOKEN" in text
    assert "return 401" in text
    assert "proxy_pass http://127.0.0.1:11435" in text, (
        "the sidecar must proxy to Ollama's own internal loopback port (11435, not "
        "11434 — this server block itself binds 11434 on the shared namespace's "
        "backend-visible interface, and a wildcard bind there would collide with an "
        "exact 127.0.0.1:11434 bind in the same namespace at the kernel level)."
    )
    # The check must run before proxy_pass, in the same location block, or a caller
    # could reach Ollama by hitting a location this check does not cover. Searches for
    # the DIRECTIVE, not just the string "proxy_pass" — this file's own prose comments
    # mention proxy_pass by name earlier, and a naive substring search would find those
    # instead of the actual directive below the check.
    check_index = text.index("return 401")
    proxy_index = text.index("proxy_pass http://")
    assert check_index < proxy_index, (
        "the bearer-token check must appear before proxy_pass in the template, so a "
        "request is rejected before it is ever forwarded to Ollama."
    )


def test_model_host_bearer_token_is_declared_only_in_the_compose_env_example() -> None:
    """D-075's own reasoning: `infrastructure/scripts/run-fuzz-worker.sh` (D-073's
    bare-metal fuzz-worker process) sources `apps/control-api/.env` WHOLESALE
    (`set -a; source .env; set +a`) when it needs DATABASE_URL. A var declared in
    `apps/control-api/.env.example` would land in fuzz-worker's process environment
    even though its code never reads it — fuzz-worker must never receive this token,
    full stop, and the cheapest way to guarantee that is to never declare it where
    that sourcing reaches. It belongs only in the repository-root, compose-only
    `.env.example`, which that script never touches.
    """
    repo_root = COMPOSE_DIR.parents[1]
    root_env_example = repo_root / ".env.example"
    control_api_env_example = repo_root / "apps" / "control-api" / ".env.example"

    assert root_env_example.is_file()
    assert "MODEL_HOST_BEARER_TOKEN" in root_env_example.read_text(encoding="utf-8")

    if control_api_env_example.is_file():
        assert "MODEL_HOST_BEARER_TOKEN=" not in control_api_env_example.read_text(
            encoding="utf-8"
        ), (
            "apps/control-api/.env.example declares MODEL_HOST_BEARER_TOKEN. "
            "infrastructure/scripts/run-fuzz-worker.sh sources this exact file "
            "wholesale for the bare-metal fuzz-worker process (D-073) — declaring the "
            "token here hands fuzz-worker ambient access to it even though its code "
            "never reads it. See D-075 in .project/decisions.md and this file's own "
            "comment on the point."
        )


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
