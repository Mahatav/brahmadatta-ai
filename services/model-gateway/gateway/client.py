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


def post_json(url: str, payload: dict[str, Any], timeout_sec: float) -> dict[str, Any]:
    request = _json_request(url, payload)
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


def get_json(url: str, timeout_sec: float) -> dict[str, Any]:
    request = Request(url, method="GET")  # noqa: S310 - endpoint policy is enforced first.
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


def iter_response_lines(url: str, payload: dict[str, Any], timeout_sec: float) -> Iterator[str]:
    request = _json_request(url, payload)
    with urlopen(request, timeout=timeout_sec) as response:  # noqa: S310
        for raw_line in response:
            yield raw_line.decode("utf-8", errors="replace").strip()


def _json_request(url: str, payload: dict[str, Any]) -> Request:
    return Request(  # noqa: S310 - endpoint policy is enforced before this chokepoint.
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
