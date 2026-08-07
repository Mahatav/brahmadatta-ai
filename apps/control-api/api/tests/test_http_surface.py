"""The HTTP surface: auth, roles, error envelope, trace id, health, SSE framing."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from django.conf import settings
from django.test import AsyncClient, Client

OPERATOR = settings.CONTROL_API_TOKENS["operator"]
REVIEWER = settings.CONTROL_API_TOKENS["reviewer"]
MISSION_ID = uuid4()


def bearer(token: str) -> dict[str, str]:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.fixture
def client() -> Client:
    return Client()


# --- health ---------------------------------------------------------------------


@pytest.mark.django_db
def test_health_is_reachable_without_a_token(client: Client):
    response = client.get("/api/v1/system/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "brahmadatta-control-api"
    assert body["status"] in {"ok", "degraded"}
    assert body["dependencies"][0]["name"] == "database"
    assert body["trace_id"]


@pytest.mark.django_db
def test_health_never_reveals_the_database_dsn(client: Client):
    body = client.get("/api/v1/system/health").content.decode()
    for leak in ("postgresql://", "password", "PASSWORD", settings.SECRET_KEY):
        assert leak not in body


@pytest.mark.django_db
def test_every_response_carries_a_trace_id_header(client: Client):
    response = client.get("/api/v1/system/health")
    assert response.headers["X-Trace-Id"]


@pytest.mark.django_db
def test_a_supplied_trace_id_is_echoed_when_it_is_safe(client: Client):
    response = client.get(
        "/api/v1/system/health", headers={"x-trace-id": "abc123def456"}
    )
    assert response.headers["X-Trace-Id"] == "abc123def456"


@pytest.mark.django_db
def test_a_hostile_trace_id_is_replaced(client: Client):
    response = client.get(
        "/api/v1/system/health",
        headers={"x-trace-id": "<script>alert(1)</script>"},
    )
    assert response.headers["X-Trace-Id"] != "<script>alert(1)</script>"


# --- authentication --------------------------------------------------------------


def test_missing_token_is_rejected(client: Client):
    response = client.get(f"/api/v1/missions/{MISSION_ID}")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "UNAUTHENTICATED"
    assert body["trace_id"]


def test_wrong_token_is_rejected(client: Client):
    response = client.get(
        f"/api/v1/missions/{MISSION_ID}", **bearer("not-the-right-token" + "x" * 20)
    )
    assert response.status_code == 401


def test_authenticated_read_reaches_the_stub(client: Client):
    response = client.get(f"/api/v1/missions/{MISSION_ID}", **bearer(OPERATOR))
    assert response.status_code == 501
    body = response.json()
    assert body["error"]["code"] == "NOT_IMPLEMENTED"
    assert body["error"]["details"]["tracked_by"]


# --- authorization ---------------------------------------------------------------


def test_reviewer_may_read(client: Client):
    response = client.get(f"/api/v1/missions/{MISSION_ID}", **bearer(REVIEWER))
    assert response.status_code == 501


def test_reviewer_may_not_start_a_mission(client: Client):
    """Authorization is checked before business logic, so this is 403 and not 501."""
    response = client.post(
        f"/api/v1/missions/{MISSION_ID}/start",
        data=json.dumps({"confirm_authorized": True}),
        content_type="application/json",
        **bearer(REVIEWER),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_reviewer_may_not_cancel_a_mission(client: Client):
    response = client.post(
        f"/api/v1/missions/{MISSION_ID}/cancel",
        data=json.dumps({"confirm": True, "reason": "test"}),
        content_type="application/json",
        **bearer(REVIEWER),
    )
    assert response.status_code == 403


# --- validation ------------------------------------------------------------------


def test_unknown_request_fields_are_rejected(client: Client):
    response = client.post(
        "/api/v1/missions",
        data=json.dumps(
            {
                "name": "demo",
                "repository_ref": "file:///demo/targets/parser-lib",
                "adapter": "C_CMAKE_CTEST",
                "surprise": True,
            }
        ),
        content_type="application/json",
        **bearer(OPERATOR),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_an_egress_enabled_sandbox_cannot_be_requested(client: Client):
    """SandboxPolicy.network is Literal['deny']; the API has no other vocabulary."""
    response = client.post(
        "/api/v1/missions",
        data=json.dumps(
            {
                "name": "demo",
                "repository_ref": "file:///demo/targets/parser-lib",
                "adapter": "C_CMAKE_CTEST",
                "policy": {"sandbox": {"network": "allow"}},
            }
        ),
        content_type="application/json",
        **bearer(OPERATOR),
    )
    assert response.status_code == 422


def test_start_without_explicit_confirmation_is_rejected(client: Client):
    response = client.post(
        f"/api/v1/missions/{MISSION_ID}/start",
        data=json.dumps({"confirm_authorized": False}),
        content_type="application/json",
        **bearer(OPERATOR),
    )
    assert response.status_code == 422


def test_a_malformed_mission_id_is_rejected(client: Client):
    response = client.get("/api/v1/missions/not-a-uuid", **bearer(OPERATOR))
    assert response.status_code == 422


# --- SSE -------------------------------------------------------------------------


async def test_event_stream_is_an_unbuffered_event_stream():
    """Exercised through the async client, because the stream is an ASGI view."""
    response = await AsyncClient().get(
        f"/api/v1/missions/{MISSION_ID}/events",
        headers={"authorization": f"Bearer {OPERATOR}"},
    )
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "text/event-stream"
    # nginx buffers proxied responses by default, which silently breaks SSE.
    assert response.headers["X-Accel-Buffering"] == "no"
    chunks = [chunk async for chunk in response.streaming_content]
    # More than one chunk: the response really is streamed, not assembled and sent.
    assert len(chunks) >= 3
    body = b"".join(chunks).decode()
    assert body.startswith(": brahmadatta stream open")
    assert "event: contract.not_implemented" in body
    payload = json.loads(body.split("data: ", 1)[1].strip())
    assert payload["error"]["code"] == "NOT_IMPLEMENTED"


def test_event_stream_requires_a_token(client: Client):
    response = client.get(f"/api/v1/missions/{MISSION_ID}/events")
    assert response.status_code == 401


# --- docs ------------------------------------------------------------------------


def test_openapi_document_is_served(client: Client):
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "Brahmadatta AI Control API"


def test_docs_page_is_served(client: Client):
    response = client.get("/api/v1/docs")
    assert response.status_code == 200
