"""Infrastructure API.

`GET /system/health` is the one endpoint on the whole surface that is implemented
rather than frozen: nginx, Docker Compose and the Astro island all need something
real to talk to on D1, and a health check that lies is worse than none.

The GPU-lease endpoints from the specification are absent — rented GPU is cut in
full (D-015). Teardown survives as P0-14 and is expressed over sandboxes.
"""

from __future__ import annotations

from datetime import datetime, timezone

from django.conf import settings
from django.db import connections
from django.http import HttpRequest
from ninja import Router, Status

from api.auth import ADMIN_ROLES, OPERATOR_ROLES, READ_ROLES, require_role
from api.errors import ERROR_RESPONSES
from api.trace import get_trace_id
from contracts.errors import NotImplementedYetError
from contracts.schemas.system import (
    DependencyStatus,
    HealthResponse,
    SandboxListResponse,
    TeardownReceipt,
    TeardownRequest,
    WorkersResponse,
)

router = Router(tags=["system"])


def _database_status() -> DependencyStatus:
    """Report reachability without ever revealing the DSN.

    Driver errors routinely quote the host, user and database name; some quote the
    password when the URL was malformed. Only the exception class name is returned.
    """
    try:
        connection = connections["default"]
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:  # noqa: BLE001 - class name only, deliberately
        return DependencyStatus(
            name="database", reachable=False, detail=type(exc).__name__
        )
    return DependencyStatus(name="database", reachable=True)


@router.get(
    "/system/health",
    auth=None,
    response={200: HealthResponse, **ERROR_RESPONSES},
    summary="Liveness and dependency reachability",
    description=(
        "Unauthenticated by design: nginx, Compose and the Astro shell probe it "
        "before any operator token exists. It returns no mission data, no "
        "configuration values and no connection strings."
    ),
    operation_id="getSystemHealth",
)
def health(request: HttpRequest):
    database = _database_status()
    return Status(200, HealthResponse(
        status="ok" if database.reachable else "degraded",
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
        app_env=settings.APP_ENV,
        time=datetime.now(timezone.utc),
        dependencies=[database],
        trace_id=get_trace_id(request),
    ))


@router.get(
    "/system/workers",
    response={200: WorkersResponse, **ERROR_RESPONSES},
    summary="Analysis worker health",
    operation_id="listWorkers",
)
def list_workers(request: HttpRequest):
    require_role(request, *READ_ROLES)
    raise NotImplementedYetError("#14 (worker queue)")


@router.get(
    "/system/sandboxes",
    response={200: SandboxListResponse, **ERROR_RESPONSES},
    summary="Live sandboxes and their isolation posture",
    description=(
        "Replaces the specification's `GET /system/gpu-leases`, which is cut with "
        "the rented GPU (D-015). Safe teardown remains P0-14 and applies to whatever "
        "compute the run actually started."
    ),
    operation_id="listSandboxes",
)
def list_sandboxes(request: HttpRequest):
    require_role(request, *READ_ROLES)
    raise NotImplementedYetError("#13 (rootless sandbox)")


@router.post(
    "/system/sandboxes/{sandbox_id}/teardown",
    response={200: TeardownReceipt, **ERROR_RESPONSES},
    summary="Operator-confirmed emergency teardown",
    operation_id="teardownSandbox",
)
def teardown_sandbox(request: HttpRequest, sandbox_id: str, payload: TeardownRequest):
    require_role(request, *(OPERATOR_ROLES + ADMIN_ROLES))
    raise NotImplementedYetError("#13 (rootless sandbox)")
