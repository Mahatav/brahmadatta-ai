"""The model gateway's single HTTP egress chokepoint.

Endpoint allowlisting and DNS-boundary checks happen before callers reach this module.
Keeping the socket-opening code here gives the D5 gateway review one place to audit and
one AST guard to enforce.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from gateway.errors import LiveGenerationError

#: `urlopen(..., timeout=...)` raises a bare `TimeoutError` on expiry (an alias of the
#: old `socket.timeout` since Python 3.10) and `URLError`/`OSError` for everything else
#: transport-shaped — connection refused, DNS failure inside the boundary, a reset
#: connection. None of these are `GatewayError` subclasses on their own, which matters:
#: `orchestrator/patch_generate_executor.py::_generate_with_ladder` only retries
#: `GatewayError`, exactly per `LiveGenerationError`'s own docstring ("Live generation
#: failed — timeout, OOM, unreachable backend, bad output"). Before this fix that
#: promise was not kept for the timeout/unreachable cases: a slow or unreachable local
#: model raised a raw `TimeoutError`/`URLError` straight through this chokepoint,
#: past the ladder's `except GatewayError` entirely, and crashed the whole
#: `PATCH_GENERATE` job instead of being recorded as one failed attempt and retried.
#: Found live: #57 finale-rehearsal wiring, CPU-only `codellama:7b-instruct` cold model
#: load (~186s) plus generation exceeded `OllamaCodeLlamaBackend`'s 300s per-call
#: `timeout_sec` on the very first attempt.
_TRANSPORT_EXCEPTIONS: tuple[type[Exception], ...] = (TimeoutError, URLError, OSError)


def post_json(
    url: str,
    payload: dict[str, Any],
    timeout_sec: float,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    request = _json_request(url, payload, bearer_token=bearer_token)
    try:
        with urlopen(request, timeout=timeout_sec) as response:  # noqa: S310
            body = response.read().decode("utf-8", errors="replace")
    except _TRANSPORT_EXCEPTIONS as exc:
        raise _transport_error(url, timeout_sec, exc) from exc
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
    try:
        with urlopen(request, timeout=timeout_sec) as response:  # noqa: S310
            body = response.read().decode("utf-8", errors="replace")
    except _TRANSPORT_EXCEPTIONS as exc:
        raise _transport_error(url, timeout_sec, exc) from exc
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
    try:
        with urlopen(request, timeout=timeout_sec) as response:  # noqa: S310
            for raw_line in response:
                yield raw_line.decode("utf-8", errors="replace").strip()
    except _TRANSPORT_EXCEPTIONS as exc:
        raise _transport_error(url, timeout_sec, exc) from exc


def _transport_error(url: str, timeout_sec: float, exc: Exception) -> LiveGenerationError:
    if isinstance(exc, TimeoutError):
        reason = f"timed out after {timeout_sec:.0f}s"
    else:
        reason = str(exc) or type(exc).__name__
    return LiveGenerationError(
        f"local model endpoint at {url!r} did not respond: {reason}.",
        details={"url": url, "timeout_sec": timeout_sec, "cause": type(exc).__name__},
    )


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
