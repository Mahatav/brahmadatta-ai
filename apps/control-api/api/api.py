"""The single `NinjaAPI` instance.

Mounted at `/api/v1/` by `config.urls`. Its OpenAPI dump is committed to
`packages/schemas/openapi.json` and is the source the Astro client generates its
TypeScript types from — see `packages/schemas/README.md`.
"""

from __future__ import annotations

from ninja import NinjaAPI

from api.auth import BearerTokenAuth
from api.errors import register_exception_handlers
from api.routers.evidence import router as evidence_router
from api.routers.missions import router as missions_router
from api.routers.system import router as system_router

DESCRIPTION = """
Control API for Brahmadatta AI — an authorized, defensive Cyber-Reasoning System.

**Contract status.** Frozen at D1 (issues #6, #9). Every endpoint except
`GET /system/health` returns `501 NOT_IMPLEMENTED` with the standard error envelope;
the request and response schemas are final and are what the Command Center types
against.

**Rules the schemas enforce rather than describe.**

* A verdict is derived only from the deterministic gate matrix. Model confidence is
  recorded on `ModelProvenance` for display and cannot reach the derivation; a
  `VerificationRecord` whose verdict does not follow from its gates cannot be
  serialized.
* No mission stage runs without an active authorization record.
* Sandbox network policy is typed `"deny"` and has no other permitted value.
* No inference endpoint may address a hosted third party; that is validated at
  startup by a Django system check.

**Errors.** Every non-2xx response is an `ErrorEnvelope` carrying a code from the
frozen vocabulary and the request's trace id, which is also returned as `X-Trace-Id`.
""".strip()

api = NinjaAPI(
    title="Brahmadatta AI Control API",
    version="0.1.0",
    description=DESCRIPTION,
    auth=BearerTokenAuth(),
    urls_namespace="control-api",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

register_exception_handlers(api)

api.add_router("", missions_router)
api.add_router("", evidence_router)
api.add_router("", system_router)
