"""Infrastructure endpoints: health, workers, sandbox teardown.

The API specification's `GET /system/gpu-leases` and
`POST /system/gpu-leases/{id}/teardown` are **not** here: rented GPU is cut entirely
(D-015). Teardown itself is still P0-14 — "applies even with zero rented GPUs" — so
it is expressed over sandboxes and the local model host, which are the compute this
build actually starts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from contracts.enums import IsolationMode
from contracts.schemas.common import StrictSchema


class DependencyStatus(StrictSchema):
    name: str = Field(max_length=100)
    reachable: bool
    detail: str = Field(
        default="",
        max_length=300,
        description="Failure class only. Never a DSN, credential, or driver message "
        "that could carry one.",
    )


class HealthResponse(StrictSchema):
    status: Literal["ok", "degraded"]
    service: str = Field(max_length=100)
    version: str = Field(max_length=40)
    app_env: str = Field(max_length=40)
    time: datetime
    dependencies: list[DependencyStatus] = Field(default_factory=list)
    trace_id: str = Field(max_length=64)


class WorkerStatus(StrictSchema):
    id: str = Field(max_length=100)
    kind: str = Field(max_length=100, description="baseline | fuzzing | patching | verification")
    healthy: bool
    busy: bool
    current_mission_id: UUID | None = None
    last_heartbeat: datetime | None = None


class WorkersResponse(StrictSchema):
    workers: list[WorkerStatus]
    checked_at: datetime


class SandboxStatus(StrictSchema):
    id: str = Field(max_length=200)
    mission_id: UUID | None = None
    runtime: Literal["podman", "docker", "subprocess-jail"]
    isolation_mode: IsolationMode = Field(
        description="Required, no default. A subprocess jail (#81) is a legitimate "
        "D3 fallback and materially weaker than a rootless container; it cannot be "
        "reported as one."
    )
    network: Literal["deny"] = Field(
        default="deny", description="Reported, and only ever this value."
    )
    running: bool
    started_at: datetime | None = None
    released_at: datetime | None = None


class SandboxListResponse(StrictSchema):
    sandboxes: list[SandboxStatus]
    checked_at: datetime


class TeardownRequest(StrictSchema):
    confirm: Literal[True] = Field(
        description="Operator-confirmed emergency teardown. Destructive and "
        "deliberate; there is no unconfirmed form."
    )
    reason: str = Field(default="", max_length=500)


class TeardownReceipt(StrictSchema):
    resource_id: str = Field(max_length=200)
    released: bool
    released_at: datetime
    detail: str = Field(default="", max_length=1000)
