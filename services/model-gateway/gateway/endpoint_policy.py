"""Which inference endpoints the gateway is allowed to open a socket to.

This is the model gateway's egress function. It is the last thing between a prompt built
from repository source and a TCP connection, and it is the layer issue #78 and SEC-02 are
about.

## What this is, and what it is not

It is **defence in depth on top of the network**, and the network is the real control.
SEC-01 closed the exploit path by topology: the process holding repository snapshots runs
on a container network with no default route, verified from inside the running container
(`infrastructure/scripts/finale-egress-evidence.sh`). This module does not repeat that
claim and does not depend on it.

It exists because the compose topology is not the only way this code runs.
`docs/04-development/31-development-setup-guide.md` documents a bare `uvicorn` on a laptop
with a full default route, and in that mode a URL validator is the *only* control. It also
exists because a control that returns the wrong answer is worse than no control: the
previous `is_local_inference_endpoint("http://metadata.google.internal/")` returned `True`,
which is a function whose name is a lie.

## The four fixes SEC-02 required, and where each one is

1. **Normalise before deciding** — `_normalise_host`. IDNA/UTS-46 encode, and reject if the
   result differs from the input in anything but case. `api。openai。com` (U+3002) and
   `api．openai．com` (U+FF0E) both normalise to `api.openai.com`, which is exactly what the
   HTTP client will do a moment later.
2. **An explicit deny list before the private check** — `_DENIED_NETWORKS`. `is_global` is
   kept afterwards as an outer allowlist but is never relied on alone; several of the worst
   addresses here (`169.254.169.254`, `fd00:ec2::254`, `100.100.100.200`, `0.0.0.0`) are
   already non-global, which is precisely why the old check waved them through.
3. **`metadata` is rejected by name** — `_METADATA_NAMES` and the leftmost-label rule.
4. **No bare-label pass** — a name is permitted only if it is `localhost`, a documented
   local alias, or explicitly listed in `MODEL_SERVICE_NAMES`. "Any name with no dots" is
   not a boundary; `http://2130706433/v1` has no dots and `inet_aton` resolves it to
   `8.8.8.8`.

## Two deliberate divergences from `contracts/model_policy.py`

Both tighten. Both are called out because they will fail existing control-API tests if the
two implementations are ever merged, and that should be a conversation, not a surprise.

- **Private DNS suffixes (`.internal`, `.local`, `.svc`, `.test`) no longer pass on the
  suffix alone.** Nobody owns those namespaces. `evil.internal`, `sneaky.svc`,
  `redirector.local` and `api.openai.com.evil.test` all passed the old check, and issue #78
  names `https://my-llm-proxy.internal/v1` as part of the finding. A host with a private
  suffix is permitted only when the operator has named it in `MODEL_SERVICE_NAMES`.
- **The reserved documentation ranges (`192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`)
  are denied.** The old module permitted them because they are not globally routable. They
  also cannot serve a model. "Not globally routable" and "inside our trust boundary" are
  different properties and only the second one is the question being asked.

## Round 3: SEC-24 and SEC-25

Two findings from the security review's round-3 gate on PR #111, both fixed here.

**SEC-24 — a 6to4/NAT64 literal was judged by its embedded address, and should never be.**
`_unwrap` reduces `2002:0a00:0001::` (6to4) or `64:ff9b::a00:1` (NAT64) to the IPv4 address
each carries, and the old code then ran that address through the *same* deny-then-allow
logic as any other address — so an embedded private or loopback address reached
`allowed-network`. That conflates two different claims: "the embedded address is private"
is not "this destination is inside our trust boundary", because reaching either literal
means a translation relay outside this policy's visibility rewrites the packet to the
embedded destination. Per RFC 3056 §2 and RFC 6052 §3.1, neither mechanism is meant to
carry a non-global address in the first place. Fix: `_unwrap` now reports *which* mechanism
produced the effective address, and a 6to4/NAT64 result is refused outright
(`translation-wrapper-non-global`) rather than handed to the allow loop — never reachable
regardless of what is embedded. `ipv4_mapped` (`::ffff:x.y.z.w`) is unaffected: that is a
notation a dual-stack socket layer uses for an address it already treats as local, not a
translation path, and it is still judged by the address it carries.

**SEC-25 — a single unbroken label of certain scripts is quadratic in `idna`.** `idna`'s
`valid_contexto()` check (required for same-script constraints on characters like
Arabic-Indic digits) is called once per codepoint in a label, each call scanning the label
— O(N) per call, O(N²) per label — and it runs *before* `idna`'s own length validation.
Reproduced through this exact call site at 99.8s-122.5s for a single ~60,000-character
label of U+0660 (ARABIC-INDIC DIGIT ZERO) on the previously pinned `idna==3.10`
(CVE-2026-45409 / PYSEC-2026-215). Two independent fixes, both required: `idna>=3.15`
(pinned to 3.18) fixes the library, and `_oversized_hostname_reason` enforces RFC 1035's
253-character / 63-per-label limits on the raw string *before* `idna.encode()` is ever
called, in both `classify()` and `normalise_service_names()` — so the guard holds even
against a future regression in `idna` itself.

## No DNS by default

`classify()` performs no network call and no name resolution, so it is safe in a system
check and deterministic in a test. Resolution is a separate, opt-in call —
`assert_resolves_inside_boundary()` — which applies the same address rules to every address
a resolver returns. The gateway runs it once before the first request of a mission; see
`gateway/service.py`.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from urllib.parse import urlsplit

import idna

from gateway.errors import ExternalInferenceBlockedError

__all__ = [
    "EndpointDecision",
    "assert_local_inference_endpoint",
    "assert_resolves_inside_boundary",
    "classify",
    "is_local_inference_endpoint",
    "normalise_service_names",
]

# --------------------------------------------------------------------------------------
# Address rules
# --------------------------------------------------------------------------------------

#: Denied before anything else, and denied even though most of these are already
#: non-global. Each entry is here because something real lives at it.
_DENIED_NETWORKS: tuple[tuple[str, str], ...] = (
    (
        "169.254.0.0/16",
        "IPv4 link-local — cloud instance metadata (169.254.169.254, and "
        "169.254.170.2 for ECS task credentials)",
    ),
    ("fe80::/10", "IPv6 link-local"),
    ("100.64.0.0/10", "CGNAT shared address space — Alibaba metadata at 100.100.100.200"),
    ("fd00:ec2::/32", "EC2 IMDS over IPv6"),
    ("0.0.0.0/32", "the unspecified IPv4 address"),
    ("::/128", "the unspecified IPv6 address"),
    ("192.0.2.0/24", "TEST-NET-1 documentation range — cannot serve a model"),
    ("198.51.100.0/24", "TEST-NET-2 documentation range — cannot serve a model"),
    ("203.0.113.0/24", "TEST-NET-3 documentation range — cannot serve a model"),
    ("224.0.0.0/4", "IPv4 multicast"),
    ("ff00::/8", "IPv6 multicast"),
    ("255.255.255.255/32", "IPv4 broadcast"),
)

_DENIED: tuple[tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, str], ...] = tuple(
    (ipaddress.ip_network(cidr), why) for cidr, why in _DENIED_NETWORKS
)

#: The only addresses that may host a model. Checked after the deny list, never instead
#: of it.
_ALLOWED_NETWORKS: tuple[str, ...] = (
    "127.0.0.0/8",  # loopback
    "::1/128",  # loopback
    "10.0.0.0/8",  # RFC 1918
    "172.16.0.0/12",  # RFC 1918
    "192.168.0.0/16",  # RFC 1918
    "fc00::/7",  # IPv6 unique-local, minus fd00:ec2::/32 which is denied above
)

_ALLOWED: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = tuple(
    ipaddress.ip_network(cidr) for cidr in _ALLOWED_NETWORKS
)

#: Prefixes that carry an IPv4 address inside an IPv6 one. Each is unwrapped and the
#: embedded IPv4 is judged by the IPv4 rules — otherwise `::ffff:169.254.169.254` reads as
#: "an IPv6 address that happens to be non-global" and `64:ff9b::808:808` reads as a
#: perfectly ordinary global IPv6 that a NAT64 gateway will deliver to 8.8.8.8.
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_NAT64_LOCAL = ipaddress.ip_network("64:ff9b:1::/48")
_SIXTOFOUR = ipaddress.ip_network("2002::/16")

# --------------------------------------------------------------------------------------
# Name rules
# --------------------------------------------------------------------------------------

#: Hostnames that are local by definition and need no operator declaration, so the
#: documented bare-`uvicorn` development flow works out of the box.
_LOCAL_NAMES: frozenset[str] = frozenset({"localhost", "host.docker.internal"})

#: Names for cloud instance metadata. Rejected by name because they are reached by name —
#: an IP deny list does not see `metadata.google.internal`.
_METADATA_NAMES: frozenset[str] = frozenset(
    {
        "metadata.google.internal",
        "metadata.goog",
        "metadata.internal",
        "metadata",
        "instance-data",
        "instance-data.ec2.internal",
    }
)

#: Suffixes an operator-declared service name is allowed to carry. A declared name must be
#: a single label (a compose service) or sit under one of these. This does not make the
#: suffix trusted — declaration does — it stops `MODEL_SERVICE_NAMES=api.openai.com.evil`
#: from being a one-line hole.
_DECLARABLE_SUFFIXES: tuple[str, ...] = (
    ".internal",
    ".local",
    ".localhost",
    ".svc",
    ".svc.cluster.local",
    ".test",
)

#: Belt and braces, exactly as in the control API: presence here is never what makes an
#: endpoint illegal — the allowlist above already excludes every public host. It sharpens
#: the error message, and it makes a declared service name that is secretly a provider
#: fail loudly.
_KNOWN_HOSTED_INFERENCE_HOSTS: tuple[str, ...] = (
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
    "api.mistral.ai",
    "api.cohere.ai",
    "api.together.xyz",
    "api.groq.com",
    "api.deepseek.com",
    "api.x.ai",
    "openrouter.ai",
    "api-inference.huggingface.co",
    "bedrock-runtime.amazonaws.com",
    "openai.azure.com",
    "api.replicate.com",
    "api.fireworks.ai",
    "api.perplexity.ai",
)

_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})

#: RFC 1035 §3.1: a domain name is at most 253 characters, and no label exceeds 63.
#: Enforced here for a second reason beyond correctness — **SEC-25**. `idna`'s ContextO
#: check (`valid_contexto()`, used for scripts like Arabic-Indic digits that carry a
#: same-script requirement) is called once per codepoint in a label, and each call scans
#: the label — O(N) per call, O(N²) per label, checked *before* `idna`'s own length
#: validation runs. A single unbroken label of the advisory's payload, U+0660 (ARABIC-INDIC
#: DIGIT ZERO) repeated ~60,000 times with no dots, measured at 99.8s-122.5s through this
#: exact call site on the pinned `idna==3.10`. `idna>=3.15` fixes the library; this guard is
#: the second, independent half — reject before the codepoint loop ever runs, so the fix
#: holds even against a future regression in the library itself. Applied to the raw string,
#: before any IDNA processing, so it costs O(N) regardless of script.
_MAX_HOSTNAME_LENGTH = 253
_MAX_LABEL_LENGTH = 63


def _oversized_hostname_reason(host: str) -> str | None:
    """None if `host` is within RFC 1035 bounds, else why it is refused.

    Splits on the literal `.` in the raw string — never on anything `idna` would produce —
    because the SEC-25 payload is exactly one label with no dots at all, and a check that
    ran IDNA processing first to find the labels would already have paid the cost this
    guard exists to avoid.
    """
    if len(host) > _MAX_HOSTNAME_LENGTH:
        return f"{len(host)} characters, exceeds the RFC 1035 limit of {_MAX_HOSTNAME_LENGTH}"
    for label in host.split("."):
        if len(label) > _MAX_LABEL_LENGTH:
            return (
                f"a label of {len(label)} characters, exceeds the RFC 1035 limit of "
                f"{_MAX_LABEL_LENGTH} per label"
            )
    return None


@dataclass(frozen=True)
class EndpointDecision:
    """Why an endpoint was allowed or refused.

    `rule` is a stable identifier so the bypass table in
    `infrastructure/scripts/testing/endpoint-policy-bypass-table.py` can show *which*
    rule caught each case, rather than a bare boolean that gives a reviewer no way to
    tell a correct answer from a lucky one.
    """

    allowed: bool
    rule: str
    reason: str
    host: str = ""

    def __bool__(self) -> bool:  # pragma: no cover - convenience only
        return self.allowed


# --------------------------------------------------------------------------------------


def normalise_service_names(names: Iterable[str]) -> frozenset[str]:
    """Validate and normalise the operator's declared service names.

    Raises `ExternalInferenceBlockedError` on a declaration that must not be honoured, so
    a bad `MODEL_SERVICE_NAMES` fails at startup rather than widening the boundary
    quietly. An allowlist is a trust decision; it should be hard to make it accidentally.
    """
    cleaned: set[str] = set()
    for raw in names:
        name = raw.strip().lower().rstrip(".")
        if not name:
            continue

        # Before IDNA touches it — SEC-25. A name this long cannot be a real service name
        # and must not reach the ContextO scan regardless.
        oversized = _oversized_hostname_reason(name)
        if oversized is not None:
            raise ExternalInferenceBlockedError(
                f"MODEL_SERVICE_NAMES contains an entry of {oversized}. Refused before "
                "IDNA processing, not after.",
                details={"entry": raw[:80] + "…" if len(raw) > 80 else raw},
            )

        try:
            encoded = idna.encode(name, uts46=True).decode("ascii")
        except (idna.IDNAError, UnicodeError) as exc:
            raise ExternalInferenceBlockedError(
                f"MODEL_SERVICE_NAMES contains {raw!r}, which is not a valid hostname: {exc}",
                details={"entry": raw},
            ) from exc
        if encoded != name:
            raise ExternalInferenceBlockedError(
                f"MODEL_SERVICE_NAMES contains {raw!r}, which normalises to {encoded!r}. "
                "Declare the normalised form so what is written is what is trusted.",
                details={"entry": raw, "normalised": encoded},
            )

        if _is_ip_literal(name) is not None or _looks_like_packed_ipv4(name):
            raise ExternalInferenceBlockedError(
                f"MODEL_SERVICE_NAMES contains {raw!r}, which is an address, not a name. "
                "Put addresses in the endpoint URL; they are judged by the network rules.",
                details={"entry": raw},
            )
        if _is_metadata_name(name):
            raise ExternalInferenceBlockedError(
                f"MODEL_SERVICE_NAMES contains {raw!r}, a cloud instance-metadata name.",
                details={"entry": raw},
            )
        if _is_known_hosted_provider(name):
            raise ExternalInferenceBlockedError(
                f"MODEL_SERVICE_NAMES contains {raw!r}, a known hosted inference provider. "
                "Repository content must never reach an external inference API.",
                details={"entry": raw},
            )
        if "." in name and not name.endswith(_DECLARABLE_SUFFIXES):
            raise ExternalInferenceBlockedError(
                f"MODEL_SERVICE_NAMES contains {raw!r}. A declared name must be a single "
                f"label (a compose service) or end in one of {', '.join(_DECLARABLE_SUFFIXES)}.",
                details={"entry": raw},
            )
        cleaned.add(name)
    return frozenset(cleaned)


def classify(url: str, *, service_names: Iterable[str] = ()) -> EndpointDecision:
    """Decide whether `url` addresses a host inside the trust boundary.

    Pure. No DNS, no sockets, no clock. `service_names` is the operator's declared
    allowlist and defaults to empty, which is the fail-closed direction.
    """
    declared = (
        service_names
        if isinstance(service_names, frozenset)
        else frozenset(n.strip().lower().rstrip(".") for n in service_names if n and n.strip())
    )

    if not url or not url.strip():
        return EndpointDecision(False, "empty", "no endpoint configured")

    try:
        parts = urlsplit(url.strip())
    except ValueError as exc:
        return EndpointDecision(False, "unparseable", f"URL does not parse: {exc}")

    if parts.scheme.lower() not in _ALLOWED_SCHEMES:
        return EndpointDecision(False, "scheme", f"scheme {parts.scheme!r} is not http or https")

    # Userinfo is rejected outright rather than ignored. `http://api.openai.com:443@evil.local/`
    # reads to a human as a request to api.openai.com and to urlsplit as a request to
    # evil.local; a setting whose meaning depends on which one is reading it has no place
    # here, and no local model server needs credentials in the URL.
    if "@" in parts.netloc:
        return EndpointDecision(
            False,
            "userinfo",
            "the endpoint carries userinfo before '@', which reads one way to a human "
            "and another to a URL parser",
        )

    try:
        raw_host = parts.hostname
    except ValueError as exc:
        return EndpointDecision(False, "unparseable-host", f"host does not parse: {exc}")
    if not raw_host:
        return EndpointDecision(False, "no-host", "the endpoint has no host")

    host = raw_host.lower().rstrip(".")
    if not host:
        return EndpointDecision(False, "no-host", "the endpoint has no host")

    # --- address literals -------------------------------------------------------------
    address = _is_ip_literal(host)
    if address is not None:
        return _classify_address(address, host)

    # --- names ------------------------------------------------------------------------
    # Before IDNA touches it — SEC-25, and checked ahead of every other name rule below,
    # not just the encode call: nothing about this host is trustworthy until it is a
    # plausible hostname at all.
    oversized = _oversized_hostname_reason(host)
    if oversized is not None:
        return EndpointDecision(
            False, "host-too-long", f"host is {oversized}. Refused before IDNA processing.", host
        )

    # Normalise before deciding. The HTTP client will do exactly this, so a decision made
    # on the un-normalised string is a decision about a different host than the one that
    # gets contacted.
    try:
        normalised = idna.encode(host, uts46=True).decode("ascii")
    except (idna.IDNAError, UnicodeError) as exc:
        return EndpointDecision(
            False, "idna-invalid", f"host is not a valid IDNA hostname: {exc}", host
        )
    if normalised != host:
        return EndpointDecision(
            False,
            "idna-mismatch",
            f"host {host!r} normalises to {normalised!r}. A hostname that changes under "
            "IDNA/UTS-46 is rejected: the client would contact the normalised form, so "
            "validating the original validates the wrong host.",
            host,
        )

    if _is_metadata_name(host):
        return EndpointDecision(False, "metadata-name", "cloud instance-metadata endpoint", host)
    if host.split(".")[0] == "metadata":
        return EndpointDecision(False, "metadata-label", "leftmost label is 'metadata'", host)
    if _is_known_hosted_provider(host):
        return EndpointDecision(
            False, "hosted-provider", "it is a known hosted inference provider", host
        )
    if _looks_like_packed_ipv4(host):
        return EndpointDecision(
            False,
            "packed-ipv4",
            f"{host!r} has no dots but the resolver reads it as a packed IPv4 address "
            "(inet_aton accepts decimal, octal and hex integers), so it is an address in "
            "disguise and usually a public one",
            host,
        )

    if host in _LOCAL_NAMES:
        return EndpointDecision(True, "local-name", "a local host by definition", host)
    if host in declared:
        return EndpointDecision(True, "declared-service", "declared in MODEL_SERVICE_NAMES", host)

    if host.endswith(_DECLARABLE_SUFFIXES):
        return EndpointDecision(
            False,
            "undeclared-private-suffix",
            f"{host!r} carries a private suffix, but nobody owns those namespaces and a "
            "suffix is not a boundary. Add it to MODEL_SERVICE_NAMES to trust it.",
            host,
        )
    if "." not in host:
        return EndpointDecision(
            False,
            "undeclared-bare-label",
            f"{host!r} is a single label that is not declared in MODEL_SERVICE_NAMES. "
            "With a DNS search domain a single label resolves to a public host.",
            host,
        )
    return EndpointDecision(
        False, "public-name", "it is not a loopback, private, or declared host", host
    )


def is_local_inference_endpoint(url: str, *, service_names: Iterable[str] = ()) -> bool:
    """True when `url` addresses a host inside the trust boundary."""
    return classify(url, service_names=service_names).allowed


def assert_local_inference_endpoint(
    setting_name: str, url: str, *, service_names: Iterable[str] = ()
) -> None:
    """Raise `ExternalInferenceBlockedError` unless `url` is inside the boundary."""
    decision = classify(url, service_names=service_names)
    if decision.allowed:
        return
    raise ExternalInferenceBlockedError(
        f"{setting_name} points at {decision.host or url!r} and {decision.reason}. "
        "Repository content must never reach an external inference API. Serve the model "
        "locally and point this at it.",
        details={"setting": setting_name, "host": decision.host, "rule": decision.rule},
    )


Resolver = Callable[[str], list[str]]


def _default_resolver(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    # sockaddr[0] is the address for both AF_INET and AF_INET6; str() is for the type
    # checker, which sees the union the stubs declare rather than what those two families
    # actually return.
    return [str(info[4][0]) for info in infos]


def assert_resolves_inside_boundary(
    setting_name: str,
    url: str,
    *,
    service_names: Iterable[str] = (),
    resolver: Resolver = _default_resolver,
) -> list[str]:
    """Resolve the endpoint's host and apply the address rules to every answer.

    This is the "and anything that resolves outward" half. `classify()` is a syntactic
    decision and cannot see that `redirector.local` answers with a public address; this
    can, at the cost of a name lookup.

    Not called from `classify()` and not called at import time. The gateway calls it once
    before the first request of a mission. `resolver` is injected so the behaviour is
    testable without a network.

    Returns the resolved addresses, so a caller can put them in the evidence record.
    """
    assert_local_inference_endpoint(setting_name, url, service_names=service_names)

    host = (urlsplit(url.strip()).hostname or "").lower().rstrip(".")
    if _is_ip_literal(host) is not None:
        return [host]

    try:
        addresses = resolver(host)
    except OSError as exc:
        raise ExternalInferenceBlockedError(
            f"{setting_name} points at {host!r}, which does not resolve: {exc}. An "
            "endpoint that cannot be resolved cannot be shown to be inside the boundary.",
            details={"setting": setting_name, "host": host},
        ) from exc

    if not addresses:
        raise ExternalInferenceBlockedError(
            f"{setting_name} points at {host!r}, which resolved to nothing.",
            details={"setting": setting_name, "host": host},
        )

    for candidate in addresses:
        address = _is_ip_literal(candidate)
        if address is None:
            raise ExternalInferenceBlockedError(
                f"{setting_name}: resolver returned {candidate!r} for {host!r}, which is "
                "not an address.",
                details={"setting": setting_name, "host": host, "address": candidate},
            )
        decision = _classify_address(address, candidate)
        if not decision.allowed:
            raise ExternalInferenceBlockedError(
                f"{setting_name} points at {host!r}, which resolves to {candidate} — "
                f"{decision.reason}. A name inside the boundary that answers with an "
                "address outside it is the boundary being crossed by DNS.",
                details={
                    "setting": setting_name,
                    "host": host,
                    "address": candidate,
                    "rule": decision.rule,
                },
            )
    return list(addresses)


# --------------------------------------------------------------------------------------
# internals
# --------------------------------------------------------------------------------------


def _is_ip_literal(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Parse `host` as an address literal, or None if it is a name.

    Strict on purpose: `ipaddress.ip_address` rejects `2130706433` and `0x7f000001`, which
    is right, because those are *names* as far as this function is concerned and get
    caught by `_looks_like_packed_ipv4` on the name path with a much clearer message.
    """
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


#: Which mechanism produced an unwrapped address, or None for "no unwrap happened".
#: The distinction is the SEC-24 fix: `ipv4-mapped` is a *notation* — `::ffff:127.0.0.1` is
#: how a dual-stack socket layer spells an IPv4 address, and no packet ever carries that
#: wrapper on the wire. `nat64` and `6to4` are *translation paths* — an IPv6 literal in
#: either range is delivered by a relay that rewrites it to the embedded IPv4 destination,
#: a hop this policy has no visibility into and does not control.
_UnwrapKind = str | None


def _unwrap(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, _UnwrapKind]:
    """Reduce an IPv6 address that carries an IPv4 one to the IPv4 address inside it.

    Returns the effective address and which mechanism did it, so the caller can tell a
    notation (safe to judge by the embedded address) from a translation path (never safe
    to judge that way — see `_classify_address`).
    """
    if address.version != 6:
        return address, None
    assert isinstance(address, ipaddress.IPv6Address)
    if address.ipv4_mapped is not None:
        return address.ipv4_mapped, "ipv4-mapped"
    if address in _NAT64 or address in _NAT64_LOCAL:
        return ipaddress.IPv4Address(int(address) & 0xFFFFFFFF), "nat64"
    if address in _SIXTOFOUR:
        return ipaddress.IPv4Address((int(address) >> 80) & 0xFFFFFFFF), "6to4"
    return address, None


#: RFC 3056 §2 requires the IPv4 address 6to4 encodes to be a global unicast address; RFC
#: 6052 §3.1 says the NAT64 well-known prefix "MUST NOT be used to represent non-global
#: IPv4 addresses" — a network that needs to translate to RFC 1918 space must use a
#: network-specific prefix instead, precisely so the well-known prefix cannot be confused
#: with a local destination. An embedded address that is *not* global is therefore not a
#: legitimate use of either mechanism — either malformed, or a deliberate attempt to make
#: an externally-routed translation path read as a private one. Refused either way,
#: regardless of what the embedded address is, unlike ipv4-mapped notation.
_TRANSLATION_WRAPPERS = frozenset({"nat64", "6to4"})


def _classify_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address, shown: str
) -> EndpointDecision:
    effective, unwrap_kind = _unwrap(address)
    wrapped = effective != address

    for network, why in _DENIED:
        if effective.version == network.version and effective in network:
            detail = f"{why} ({network})"
            if wrapped:
                detail = f"{detail}, reached via the IPv6 wrapper {shown}"
            return EndpointDecision(False, "denied-network", detail, shown)

    # The outer allowlist. Kept after the deny list, never used instead of it — most of
    # the denied addresses above are already non-global, which is how they got through.
    if effective.is_global:
        detail = "a globally routable address"
        if wrapped:
            detail = f"{detail} ({effective}) carried inside {shown}"
        return EndpointDecision(False, "global-address", detail, shown)

    # SEC-24. A 6to4 or NAT64 literal is a translation path, not a notation: the packet is
    # delivered by a relay outside this policy's visibility, which rewrites it to the
    # embedded IPv4 destination. Reaching here means the deny and global checks above did
    # not refuse the embedded address — i.e. it looks private or loopback — and per RFC
    # 3056 / RFC 6052 that is not a legitimate use of either mechanism. Refused outright,
    # never handed to the allowlist below: "the embedded address is private" is not the
    # same claim as "this destination is inside our trust boundary" when a relay sits
    # between here and it.
    if unwrap_kind in _TRANSLATION_WRAPPERS:
        return EndpointDecision(
            False,
            "translation-wrapper-non-global",
            f"{shown} is a {unwrap_kind} literal embedding {effective}, which is not a "
            f"globally routable address. {unwrap_kind} exists to reach a global IPv4 "
            "destination through a translation relay outside this policy's visibility; "
            "an embedded private or loopback address is not a legitimate use of it and "
            "is refused regardless, per RFC 3056 §2 / RFC 6052 §3.1.",
            shown,
        )

    for network in _ALLOWED:
        if effective.version == network.version and effective in network:
            return EndpointDecision(
                True, "allowed-network", f"loopback or private address ({network})", shown
            )

    return EndpointDecision(
        False,
        "unlisted-address",
        f"{effective} is not in any permitted range (loopback, RFC 1918, or IPv6 unique-local)",
        shown,
    )


def _is_metadata_name(host: str) -> bool:
    return host in _METADATA_NAMES


def _is_known_hosted_provider(host: str) -> bool:
    return any(
        host == blocked or host.endswith("." + blocked) for blocked in _KNOWN_HOSTED_INFERENCE_HOSTS
    )


def _looks_like_packed_ipv4(host: str) -> bool:
    """True when the OS resolver would read this dotless string as an IPv4 address.

    `inet_aton` accepts a bare 32-bit integer in decimal, octal or hex, so `2130706433` is
    127.0.0.1 and `134744072` is 8.8.8.8. This is the bypass QA found on top of SEC-02,
    and it is why "a bare label has no dots, so it must be a compose service" was never a
    safe inference.

    Implemented by parsing rather than by calling `inet_aton`, so it needs no network
    stack and behaves the same on every platform.
    """
    if not host or "." in host:
        return False
    lowered = host.lower()
    try:
        if lowered.startswith("0x"):
            int(lowered, 16)
        elif lowered.startswith("0") and len(lowered) > 1:
            int(lowered, 8)
        else:
            int(lowered, 10)
    except ValueError:
        return False
    return True
