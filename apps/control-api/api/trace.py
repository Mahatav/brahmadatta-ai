"""Trace-ID middleware.

"Every response includes a trace ID" — `docs/03-technical/21-api-specification.md`,
API rules. One id per request, echoed as `X-Trace-Id`, carried in every error
envelope, and stamped onto every mission event emitted while handling the request.

An inbound `X-Trace-Id` is honoured only if it is short and alphanumeric. An
attacker-controlled header ends up in log lines and in the event stream, so it is
validated rather than trusted.
"""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar

from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.http import HttpRequest, HttpResponse

TRACE_HEADER = "X-Trace-Id"
_SAFE_TRACE_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

_current_trace_id: ContextVar[str] = ContextVar("brahmadatta_trace_id", default="")


def new_trace_id() -> str:
    return uuid.uuid4().hex


def get_trace_id(request: HttpRequest | None = None) -> str:
    """Trace id for the current request, falling back to the context variable.

    Never returns an empty string: a response without a trace id is worse than one
    with a freshly-minted one, because it cannot be correlated at all.
    """
    if request is not None:
        existing = getattr(request, "trace_id", "")
        if existing:
            return existing
    return _current_trace_id.get() or new_trace_id()


def _resolve(request: HttpRequest) -> str:
    supplied = request.headers.get(TRACE_HEADER, "")
    if supplied and _SAFE_TRACE_ID.match(supplied):
        return supplied
    return new_trace_id()


class TraceIdMiddleware:
    """Sync- and async-capable, because the API runs under ASGI for SSE."""

    async_capable = True
    sync_capable = True

    def __init__(self, get_response) -> None:
        self.get_response = get_response
        if iscoroutinefunction(self.get_response):
            markcoroutinefunction(self)

    def __call__(self, request: HttpRequest):
        if iscoroutinefunction(self):
            return self.__acall__(request)

        trace_id = _resolve(request)
        request.trace_id = trace_id
        token = _current_trace_id.set(trace_id)
        try:
            response: HttpResponse = self.get_response(request)
        finally:
            _current_trace_id.reset(token)
        response[TRACE_HEADER] = trace_id
        return response

    async def __acall__(self, request: HttpRequest):
        trace_id = _resolve(request)
        request.trace_id = trace_id
        token = _current_trace_id.set(trace_id)
        try:
            response: HttpResponse = await self.get_response(request)
        finally:
            _current_trace_id.reset(token)
        response[TRACE_HEADER] = trace_id
        return response
