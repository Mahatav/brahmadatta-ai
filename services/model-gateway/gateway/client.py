"""The model gateway's single HTTP egress chokepoint.

Endpoint allowlisting and DNS-boundary checks happen before callers reach this module.
Keeping the socket-opening code here gives the D5 gateway review one place to audit and
one AST guard to enforce.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any
from urllib.request import Request, urlopen

from gateway.errors import LiveGenerationError


def post_json(
    url: str,
    payload: dict[str, Any],
    timeout_sec: float,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    request = _json_request(url, payload, bearer_token=bearer_token)
    with urlopen(request, timeout=timeout_sec) as response:  # noqa: S310
        body = response.read().decode("utf-8", errors="replace")
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        raise LiveGenerationError(
            "local model endpoint returned a non-JSON response.",
            details={"response_preview": body[:500]},
        ) from exc
    if not isinstance(decoded, dict):
        raise LiveGenerationError("local model endpoint returned a JSON value that is not an object.")
    return decoded


def get_json(url: str, timeout_sec: float, *, bearer_token: str | None = None) -> dict[str, Any]:
    headers = _auth_headers(bearer_token)
    request = Request(url, headers=headers, method="GET")  # noqa: S310 - endpoint policy is enforced first.
    with urlopen(request, timeout=timeout_sec) as response:  # noqa: S310
        body = response.read().decode("utf-8", errors="replace")
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        raise LiveGenerationError(
            "local model endpoint returned a non-JSON response.",
            details={"response_preview": body[:500]},
        ) from exc
    if not isinstance(decoded, dict):
        raise LiveGenerationError("local model endpoint returned a JSON value that is not an object.")
    return decoded


def iter_response_lines(
    url: str,
    payload: dict[str, Any],
    timeout_sec: float,
    *,
    bearer_token: str | None = None,
) -> Iterator[str]:
    request = _json_request(url, payload, bearer_token=bearer_token)
    with urlopen(request, timeout=timeout_sec) as response:  # noqa: S310
        for raw_line in response:
            yield raw_line.decode("utf-8", errors="replace").strip()


def _auth_headers(bearer_token: str | None) -> dict[str, str]:
    """`Authorization: Bearer <token>`, only when a token is actually configured.

    D-075 / SEC-50: `model-host`'s nginx sidecar is the only caller that ever demands
    this header today, and it demands it unconditionally — an empty/unset
    `bearer_token` here means the caller did not configure one, which is a legitimate
    state for every OTHER local-inference target this client talks to (e.g. a bare
    `ollama serve` on loopback, which has no auth of any kind to send). Sending no
    header rather than `Authorization: Bearer ` (empty) keeps a caller that never
    configured a token indistinguishable from one that never had a reason to.
    """
    if not bearer_token:
        return {}
    return {"Authorization": f"Bearer {bearer_token}"}


def _json_request(
    url: str,
    payload: dict[str, Any],
    *,
    bearer_token: str | None = None,
) -> Request:
    headers = {"Content-Type": "application/json", **_auth_headers(bearer_token)}
    return Request(  # noqa: S310 - endpoint policy is enforced before this chokepoint.
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
