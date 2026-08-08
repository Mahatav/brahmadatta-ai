"""Mission API.

Every operation below is contract-frozen and returns 501 until the orchestrator lands
(issue #12). The request and response schemas are real and complete — that is the
point of the freeze: the Command Center can be built and typed against this surface
today, and the pipeline fills it in behind.

Authorization is checked before anything else in every handler, so the 403 path is
exercised now rather than being retrofitted around working code later.
"""

from __future__ import annotations

import asyncio
import json
from uuid import UUID

from django.http import HttpRequest, StreamingHttpResponse
from ninja import Query, Router, Status

from api.auth import OPERATOR_ROLES, READ_ROLES, require_role
from api.errors import ERROR_RESPONSES, envelope
from api.trace import get_trace_id
from authorization import service
from contracts.authorization import AuthorizationRecord, AuthorizationRequest
from contracts.enums import ErrorCode
from contracts.errors import NotImplementedYetError
from contracts.schemas.common import Acknowledgement, Page
from contracts.schemas.envelope import MissionEvent
from contracts.schemas.missions import (
    CancelRequest,
    MissionCreateRequest,
    MissionDetail,
    MissionSummary,
    PauseRequest,
    PreflightReport,
    SnapshotRecord,
    SnapshotRequest,
    StartRequest,
)

router = Router(tags=["missions"])

ORCHESTRATOR_ISSUE = "#12 (orchestrator state machine)"
EVIDENCE_ISSUE = "#20 (evidence database)"

#: OpenAPI description of the SSE response. django-ninja cannot express a
#: `text/event-stream` body through `response=`, so it is declared explicitly and
#: deep-merged into the operation.
SSE_OPENAPI = {
    "responses": {
        "200": {
            "description": (
                "Ordered mission event stream. Each frame is `id: <sequence>`, "
                "`event: <MissionEvent.type>`, `data: <MissionEvent as JSON>`. "
                "Reconnect with `Last-Event-ID`, or replay through "
                "`/missions/{mission_id}/events/replay`."
            ),
            "content": {
                "text/event-stream": {
                    "schema": {"$ref": "#/components/schemas/MissionEvent"}
                }
            },
        }
    }
}


@router.post(
    "/missions",
    response={201: MissionSummary, **ERROR_RESPONSES},
    summary="Create a mission draft",
    operation_id="createMission",
)
def create_mission(request: HttpRequest, payload: MissionCreateRequest):
    require_role(request, *OPERATOR_ROLES)
    raise NotImplementedYetError(ORCHESTRATOR_ISSUE)


@router.get(
    "/missions",
    response={200: Page[MissionSummary], **ERROR_RESPONSES},
    summary="List missions",
    operation_id="listMissions",
)
def list_missions(
    request: HttpRequest,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    require_role(request, *READ_ROLES)
    raise NotImplementedYetError(ORCHESTRATOR_ISSUE)


@router.get(
    "/missions/{mission_id}",
    response={200: MissionDetail, **ERROR_RESPONSES},
    summary="Mission state, stage, progress and summary counts",
    operation_id="getMission",
)
def get_mission(request: HttpRequest, mission_id: UUID):
    require_role(request, *READ_ROLES)
    raise NotImplementedYetError(ORCHESTRATOR_ISSUE)


@router.post(
    "/missions/{mission_id}/authorize",
    response={201: AuthorizationRecord, **ERROR_RESPONSES},
    summary="Record the authorization that every later stage depends on",
    description=(
        "P0-1. Until this record exists, no stage may run: `contracts.state_machine` "
        "refuses every transition past CREATED without an active record. The record "
        "is immutable and is reproduced in the evidence bundle."
    ),
    operation_id="authorizeMission",
)
def authorize_mission(
    request: HttpRequest, mission_id: UUID, payload: AuthorizationRequest
):
    require_role(request, *OPERATOR_ROLES)
    record = service.authorize_mission(
        mission_id, payload, trace_id=get_trace_id(request)
    )
    return Status(201, record)


@router.post(
    "/missions/{mission_id}/snapshot",
    response={201: SnapshotRecord, **ERROR_RESPONSES},
    summary="Ingest an immutable repository snapshot",
    operation_id="createMissionSnapshot",
)
def create_snapshot(request: HttpRequest, mission_id: UUID, payload: SnapshotRequest):
    require_role(request, *OPERATOR_ROLES)
    record = service.create_mission_snapshot(
        mission_id, payload, trace_id=get_trace_id(request)
    )
    return Status(201, record)


@router.post(
    "/missions/{mission_id}/preflight",
    response={200: PreflightReport, **ERROR_RESPONSES},
    summary="Validate authorization, commands, adapter and limits",
    operation_id="preflightMission",
)
def preflight_mission(request: HttpRequest, mission_id: UUID):
    require_role(request, *OPERATOR_ROLES)
    raise NotImplementedYetError(ORCHESTRATOR_ISSUE)


@router.post(
    "/missions/{mission_id}/start",
    response={202: Acknowledgement, **ERROR_RESPONSES},
    summary="Start the autonomous workflow",
    operation_id="startMission",
)
def start_mission(request: HttpRequest, mission_id: UUID, payload: StartRequest):
    require_role(request, *OPERATOR_ROLES)
    raise NotImplementedYetError(ORCHESTRATOR_ISSUE)


@router.post(
    "/missions/{mission_id}/pause",
    response={202: Acknowledgement, **ERROR_RESPONSES},
    summary="Pause after the current safe boundary",
    operation_id="pauseMission",
)
def pause_mission(request: HttpRequest, mission_id: UUID, payload: PauseRequest):
    require_role(request, *OPERATOR_ROLES)
    raise NotImplementedYetError(ORCHESTRATOR_ISSUE)


@router.post(
    "/missions/{mission_id}/cancel",
    response={202: Acknowledgement, **ERROR_RESPONSES},
    summary="Cancel safely and release every resource",
    operation_id="cancelMission",
)
def cancel_mission(request: HttpRequest, mission_id: UUID, payload: CancelRequest):
    require_role(request, *OPERATOR_ROLES)
    raise NotImplementedYetError(ORCHESTRATOR_ISSUE)


@router.get(
    "/missions/{mission_id}/events/replay",
    response={200: Page[MissionEvent], **ERROR_RESPONSES},
    summary="Replay ordered events from a sequence number",
    description=(
        "Gap recovery for the SSE stream. `sequence` is gap-free per mission, so a "
        "client that sees a jump replays from its last known value."
    ),
    operation_id="replayMissionEvents",
)
def replay_events(
    request: HttpRequest,
    mission_id: UUID,
    since_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
):
    require_role(request, *READ_ROLES)
    raise NotImplementedYetError(EVIDENCE_ISSUE)


@router.get(
    "/missions/{mission_id}/events",
    response=ERROR_RESPONSES,
    summary="Ordered event stream (SSE)",
    operation_id="streamMissionEvents",
    openapi_extra=SSE_OPENAPI,
)
async def stream_events(request: HttpRequest, mission_id: UUID):
    """Server-sent events over ASGI.

    The transport is real and running today; the mission events are not, because the
    orchestrator that emits them does not exist yet. Rather than fabricate telemetry
    — which the product rules forbid outright — this emits the stream preamble, two
    heartbeat comments, and one terminal `contract.not_implemented` frame carrying the
    standard error envelope, then closes.

    That is enough to prove the thing most likely to break silently: nginx buffers
    proxied responses by default, and a buffered SSE stream arrives as one lump at the
    end. `X-Accel-Buffering: no` is set here as well as `proxy_buffering off` in the
    nginx config (issue #10) — belt and braces, because this failure is invisible
    until the demo.
    """
    require_role(request, *READ_ROLES)

    body = envelope(
        request,
        ErrorCode.NOT_IMPLEMENTED,
        f"Mission event stream is contract-frozen but not implemented yet; "
        f"tracked by {ORCHESTRATOR_ISSUE}.",
        {"mission_id": str(mission_id), "tracked_by": ORCHESTRATOR_ISSUE},
    )

    async def frames():
        yield b": brahmadatta stream open\n\n"
        for _ in range(2):
            await asyncio.sleep(0.25)
            yield b": heartbeat\n\n"
        payload = json.dumps(body, separators=(",", ":")).encode()
        yield b"event: contract.not_implemented\ndata: " + payload + b"\n\n"

    response = StreamingHttpResponse(frames(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache, no-transform"
    response["X-Accel-Buffering"] = "no"
    response["Connection"] = "keep-alive"
    return response
