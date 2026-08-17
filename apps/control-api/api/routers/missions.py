"""Mission API.

#154 wired all seven stubs this file froze at D1, split across two engineers and
sequenced (not parallel) because both touch this file: `create`/`list`/`get` and
`preflight`/`start`/`pause`/`cancel` each delegate to `missions.service`, three lines
each, matching `authorize_mission`/`create_snapshot` below — see that module's
docstring for why `preflight_mission` alone opens its own row lock and the rest do
not. The request and response schemas were real and complete from the freeze — that is
what let the Command Center be built and typed against this surface before either
half existed.

The event log was never one of the stubs: `GET .../events` (SSE) and
`GET .../events/replay` (#13) are fully implemented against the persisted
`MissionEvent` table, independent of the rest of the lifecycle.

Authorization is checked before anything else in every handler, so the 403 path is
exercised now rather than being retrofitted around working code later.
"""

from __future__ import annotations

from uuid import UUID

from django.http import HttpRequest, StreamingHttpResponse
from ninja import Query, Router, Status

from api import sse
from api.auth import OPERATOR_ROLES, READ_ROLES, require_role
from api.errors import ERROR_RESPONSES
from api.trace import get_trace_id
from authorization import service
from authorization.errors import MissionNotFoundError
from contracts.authorization import AuthorizationRecord, AuthorizationRequest
from contracts.schemas.common import Acknowledgement, ErrorEnvelope, Page
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
from missions import service as mission_service
from missions.models import Mission
from missions.models import MissionEvent as MissionEventRow  # avoid shadowing the schema

router = Router(tags=["missions"])

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
    summary = mission_service.create_mission(payload)
    return Status(201, summary)


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
    return mission_service.list_missions(limit=limit, offset=offset)


@router.get(
    "/missions/{mission_id}",
    response={200: MissionDetail, **ERROR_RESPONSES},
    summary="Mission state, stage, progress and summary counts",
    operation_id="getMission",
)
def get_mission(request: HttpRequest, mission_id: UUID):
    require_role(request, *READ_ROLES)
    return mission_service.get_mission(mission_id)


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
    return mission_service.preflight_mission(mission_id)


@router.post(
    "/missions/{mission_id}/start",
    response={202: Acknowledgement, **ERROR_RESPONSES},
    summary="Start the autonomous workflow",
    operation_id="startMission",
)
def start_mission(request: HttpRequest, mission_id: UUID, payload: StartRequest):
    require_role(request, *OPERATOR_ROLES)
    ack = mission_service.start_mission(
        mission_id, payload, trace_id=get_trace_id(request)
    )
    return Status(202, ack)


@router.post(
    "/missions/{mission_id}/pause",
    response={202: Acknowledgement, **ERROR_RESPONSES},
    summary="Pause after the current safe boundary",
    operation_id="pauseMission",
)
def pause_mission(request: HttpRequest, mission_id: UUID, payload: PauseRequest):
    require_role(request, *OPERATOR_ROLES)
    ack = mission_service.pause_mission(
        mission_id, payload, trace_id=get_trace_id(request)
    )
    return Status(202, ack)


@router.post(
    "/missions/{mission_id}/cancel",
    response={202: Acknowledgement, **ERROR_RESPONSES},
    summary="Cancel safely and release every resource",
    operation_id="cancelMission",
)
def cancel_mission(request: HttpRequest, mission_id: UUID, payload: CancelRequest):
    require_role(request, *OPERATOR_ROLES)
    ack = mission_service.cancel_mission(
        mission_id, payload, trace_id=get_trace_id(request)
    )
    return Status(202, ack)


@router.get(
    "/missions/{mission_id}/events/replay",
    response={200: Page[MissionEvent], **ERROR_RESPONSES},
    summary="Replay ordered events from a sequence number",
    description=(
        "Gap recovery for the SSE stream. `sequence` is gap-free per mission, so a "
        "client that sees a jump replays from its last known value. Reads the same "
        "persisted `MissionEvent` log the stream tails, through the same schema "
        "conversion (`api.sse.to_schema`) — there is one definition of what an event "
        "looks like, not one for the live path and a second for gap recovery."
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
    if not Mission.objects.filter(pk=mission_id).exists():
        raise MissionNotFoundError()

    query = MissionEventRow.objects.filter(
        mission_id=mission_id, sequence__gt=since_sequence
    ).order_by("sequence")
    total = query.count()
    rows = list(query[:limit])
    return Page[MissionEvent](
        items=[sse.to_schema(row) for row in rows],
        total=total,
        limit=limit,
        offset=since_sequence,
    )


@router.get(
    "/missions/{mission_id}/events",
    response={429: ErrorEnvelope, **ERROR_RESPONSES},
    summary="Ordered event stream (SSE)",
    operation_id="streamMissionEvents",
    openapi_extra=SSE_OPENAPI,
)
async def stream_events(
    request: HttpRequest,
    mission_id: UUID,
    since_sequence: int = Query(default=0, ge=0),
):
    """Server-sent events over ASGI, backed by the persisted `MissionEvent` log.

    Every ORM read runs through `sync_to_async` in `api.sse`, once per call — this
    view never holds an `asgiref` thread-pool thread between reads (CTO-C1). The
    per-mission concurrent-stream cap is enforced with `sse.acquire_slot` *before*
    `StreamingHttpResponse` is constructed, so a caller over the limit gets a real
    `429` rather than a stream that opens and immediately closes; `sse.release_slot`
    runs from the generator's `finally`, so a client disconnect (the ASGI handler
    closing this generator) frees the slot regardless of which frame it happened on.

    `Last-Event-ID` (sent automatically by a reconnecting `EventSource`) or an
    explicit `?since_sequence=` resumes from a cursor and replays every missed event
    in order before the stream goes live — see `sse.event_frames`.
    """
    require_role(request, *READ_ROLES)

    if not await sse.mission_exists(mission_id):
        raise MissionNotFoundError()

    cursor = sse.resolve_cursor(request, since_sequence)

    await sse.acquire_slot(mission_id)

    async def frames():
        try:
            async for frame in sse.event_frames(mission_id, cursor):
                yield frame
        finally:
            await sse.release_slot(mission_id)

    response = StreamingHttpResponse(frames(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache, no-transform"
    response["X-Accel-Buffering"] = "no"
    response["Connection"] = "keep-alive"
    return response
