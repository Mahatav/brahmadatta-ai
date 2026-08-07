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
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

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

    `is_global` is the discriminator, and it is the strict one: an address is
    permitted only when it is *not* globally routable. That covers loopback, RFC 1918
    space, link-local, and the reserved documentation/benchmark ranges — none of which
    can carry traffic to a hosted provider.
    """
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return None
    return not address.is_global


def is_local_inference_endpoint(url: str) -> bool:
    """True when `url` addresses a host inside the trust boundary."""
    if not url:
        return False

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False

    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        return False

    if any(host == blocked or host.endswith("." + blocked) for blocked in _KNOWN_HOSTED_INFERENCE_HOSTS):
        return False

    ip_verdict = _host_is_private_ip(host)
    if ip_verdict is not None:
        return ip_verdict

    if host in _LOCAL_NAMES:
        return True
    if host.endswith(_PRIVATE_SUFFIXES):
        return True
    # A bare label with no dots is a container/compose service name on a private
    # network (e.g. `small-model`). Anything with a public-looking domain is not.
    return "." not in host


def assert_local_inference_endpoint(setting_name: str, url: str) -> None:
    """Raise `ExternalInferenceBlockedError` unless `url` is inside the boundary."""
    if is_local_inference_endpoint(url):
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
