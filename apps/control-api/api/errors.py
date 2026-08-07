"""One error envelope for every failure path.

Registered on the `NinjaAPI` instance in `api.api`. Nothing is swallowed: unexpected
exceptions are logged with the trace id and answered with a generic 500 that carries
no internal detail, so the browser learns the trace id and the operator reads the
server log.
"""

from __future__ import annotations

import logging
from typing import Any

from django.http import Http404, HttpRequest, HttpResponse
from ninja.errors import AuthenticationError, HttpError
from ninja.errors import ValidationError as NinjaValidationError

from api.trace import get_trace_id
from contracts.enums import ErrorCode
from contracts.errors import ContractError
from contracts.schemas.common import ErrorEnvelope

logger = logging.getLogger("brahmadatta.api")

#: Response schemas attached to every operation, so the OpenAPI dump documents the
#: failure shapes and the generated TypeScript types cover them.
ERROR_RESPONSES: dict[int, Any] = {
    400: ErrorEnvelope,
    401: ErrorEnvelope,
    403: ErrorEnvelope,
    404: ErrorEnvelope,
    409: ErrorEnvelope,
    422: ErrorEnvelope,
    501: ErrorEnvelope,
}


def envelope(
    request: HttpRequest,
    code: ErrorCode,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "error": {"code": str(code), "message": message, "details": details or {}},
        "trace_id": get_trace_id(request),
    }


def register_exception_handlers(api) -> None:
    """Attach handlers to a `NinjaAPI`. Called once, from `api.api`."""

    @api.exception_handler(ContractError)
    def _contract_error(request: HttpRequest, exc: ContractError) -> HttpResponse:
        logger.info(
            "contract error trace_id=%s code=%s status=%s",
            get_trace_id(request),
            exc.code,
            exc.http_status,
        )
        return api.create_response(
            request,
            envelope(request, exc.code, exc.message, exc.details),
            status=exc.http_status,
        )

    @api.exception_handler(NinjaValidationError)
    def _validation_error(
        request: HttpRequest, exc: NinjaValidationError
    ) -> HttpResponse:
        return api.create_response(
            request,
            envelope(
                request,
                ErrorCode.VALIDATION_ERROR,
                "Request failed validation.",
                {"errors": exc.errors},
            ),
            status=422,
        )

    @api.exception_handler(AuthenticationError)
    def _authentication_error(
        request: HttpRequest, exc: AuthenticationError
    ) -> HttpResponse:
        return api.create_response(
            request,
            envelope(
                request,
                ErrorCode.UNAUTHENTICATED,
                "A valid operator bearer token is required.",
            ),
            status=401,
        )

    @api.exception_handler(Http404)
    def _not_found(request: HttpRequest, exc: Http404) -> HttpResponse:
        return api.create_response(
            request,
            envelope(request, ErrorCode.NOT_FOUND, "Resource not found."),
            status=404,
        )

    @api.exception_handler(HttpError)
    def _http_error(request: HttpRequest, exc: HttpError) -> HttpResponse:
        return api.create_response(
            request,
            envelope(request, ErrorCode.INTERNAL_ERROR, str(exc)),
            status=exc.status_code,
        )

    @api.exception_handler(Exception)
    def _unhandled(request: HttpRequest, exc: Exception) -> HttpResponse:
        # Logged in full, returned as nothing. The trace id is the bridge.
        logger.exception("unhandled error trace_id=%s", get_trace_id(request))
        return api.create_response(
            request,
            envelope(
                request,
                ErrorCode.INTERNAL_ERROR,
                "Internal error. Quote the trace id when reporting this.",
            ),
            status=500,
        )
