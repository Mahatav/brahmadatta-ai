"""Model routing policy: no hosted third-party inference API, ever.

Hard product rule from `CLAUDE.md` and every security document in the pack:
repository content is never sent to an external inference API. This module decides,
without a network call and without DNS, whether a configured inference endpoint sits
inside the trust boundary.

The rule is allowlist-shaped, not denylist-shaped: an endpoint is permitted only if
its host is demonstrably local or private. A denylist of known providers is applied
*as well*, so a familiar hostname produces a clearer error message — but removing an
entry from it cannot make an external endpoint legal.

`contracts.checks` runs this over settings as a Django system check, so a bad value
fails `manage.py check`, `runserver` and ASGI startup. It is not possible to boot the
control API with an inference endpoint pointing at a hosted provider.

`contracts/` has no Django dependency and never will (see this package's own
`README`/module docstrings and `tests/architecture/test_import_direction.py`, which
imports every module here in a bare interpreter with no `django` installed). So
`MODEL_SERVICE_NAMES` — the one piece of this policy that is deployment
configuration rather than a fixed rule — arrives as an explicit parameter, never
read from `django.conf.settings` in this file. `contracts.checks`, which already
depends on Django, is the one place that bridges the two.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from urllib.parse import urlparse

import idna

from contracts.errors import ExternalInferenceBlockedError

#: Suffixes that denote a private/internal name. `.local` and `.internal` are the
#: conventions used by the environment-variables guide; the rest are container and
#: cluster DNS.
_PRIVATE_SUFFIXES: tuple[str, ...] = (
    ".internal",
    ".local",
    ".localhost",
    ".svc",
    ".svc.cluster.local",
    ".test",
)

_LOCAL_NAMES: frozenset[str] = frozenset({"localhost", "host.docker.internal"})

_DENIED_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in (
        "169.254.0.0/16",
        "fe80::/10",
        "100.64.0.0/10",
        "fd00:ec2::/32",
        "0.0.0.0/32",
        "::/128",
    )
)

_METADATA_NAMES: frozenset[str] = frozenset(
    {"metadata.google.internal", "metadata.internal"}
)

#: Belt and braces. Presence here is never what makes an endpoint illegal — the
#: allowlist above already excludes every public host. This only sharpens the error.
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
)


def _host_is_private_ip(host: str) -> bool | None:
    """True/False if `host` is an IP literal, None if it is a name.

    Cloud metadata/link-local/CGNAT ranges are denied before the outer non-global
    allowlist. IPv4-mapped IPv6 is judged by its embedded IPv4 address.
    """
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return None
    policy_address = getattr(address, "ipv4_mapped", None) or address
    if any(
        policy_address.version == network.version and policy_address in network
        for network in _DENIED_NETWORKS
    ):
        return False
    return not policy_address.is_global


def _normalize_service_names(service_names: Iterable[str]) -> frozenset[str]:
    return frozenset(
        str(name).strip().lower() for name in service_names if str(name).strip()
    )


def is_local_inference_endpoint(
    url: str, *, service_names: Iterable[str] = ()
) -> bool:
    """True when `url` addresses a host inside the trust boundary.

    `service_names` is the deployment's `MODEL_SERVICE_NAMES` allowlist (compose
    service names a bare DNS label is trusted to name) — the caller's
    responsibility to supply, per the module docstring. Defaults to empty, which is
    the fail-closed behaviour: no bare label is trusted unless explicitly named.
    """
    if not url:
        return False

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False

    raw_host = (parsed.hostname or "").rstrip(".")
    if not raw_host:
        return False
    ip_verdict = _host_is_private_ip(raw_host)
    if ip_verdict is not None:
        return ip_verdict
    try:
        host = idna.encode(raw_host, uts46=True).decode("ascii")
    except (idna.IDNAError, UnicodeError):
        return False
    if host.lower() != raw_host.lower():
        return False
    host = host.lower()
    if not host:
        return False

    if host.split(".", 1)[0] == "metadata" or host in _METADATA_NAMES:
        return False

    if any(host == blocked or host.endswith("." + blocked) for blocked in _KNOWN_HOSTED_INFERENCE_HOSTS):
        return False

    if host in _LOCAL_NAMES:
        return True
    if host.endswith(_PRIVATE_SUFFIXES):
        return True
    # Bare DNS labels are trusted only when deployment configuration names them.
    return "." not in host and host in _normalize_service_names(service_names)


def assert_local_inference_endpoint(
    setting_name: str, url: str, *, service_names: Iterable[str] = ()
) -> None:
    """Raise `ExternalInferenceBlockedError` unless `url` is inside the boundary."""
    if is_local_inference_endpoint(url, service_names=service_names):
        return

    host = (urlparse(url).hostname or "").lower()
    known = any(
        host == blocked or host.endswith("." + blocked)
        for blocked in _KNOWN_HOSTED_INFERENCE_HOSTS
    )
    reason = (
        "it is a known hosted inference provider"
        if known
        else "it is not a loopback, private, or internal host"
    )
    raise ExternalInferenceBlockedError(
        f"{setting_name} points at {host or url!r} and {reason}. Repository content "
        f"must never reach an external inference API. Serve the model locally and "
        f"point this at it.",
        details={"setting": setting_name, "host": host},
    )
