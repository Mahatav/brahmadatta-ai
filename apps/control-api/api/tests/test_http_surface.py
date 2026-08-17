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


# --- SEC-05 (#96): the docs/openapi routes only exist when API_DOCS_ENABLED is True ----


def test_docs_urls_are_off_when_the_flag_is_off():
    from api.api import docs_urls

    assert docs_urls(False) == (None, None)


def test_docs_urls_are_on_when_the_flag_is_on():
    from api.api import docs_urls

    assert docs_urls(True) == ("/docs", "/openapi.json")


@pytest.mark.django_db
def test_docs_and_openapi_are_reachable_under_the_test_profile(client: Client):
    """The test/development profiles default API_DOCS_ENABLED to True — this is the
    control for the finale-only gate: the routes exist and answer 200 unauthenticated
    when the flag is on, so SEC-05's fix is that the finale profile turns it off, not
    that these routes were unreachable in every profile."""
    assert client.get("/api/v1/openapi.json").status_code == 200
    assert client.get("/api/v1/docs").status_code == 200


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


def test_a_body_over_djangos_memory_limit_is_413_not_500(client: Client):
    """SEC-38: nginx may admit a large body that Django must still reject safely."""
    response = client.generic(
        "POST",
        f"/api/v1/missions/{MISSION_ID}/snapshot",
        data=b"{}",
        content_type="application/json",
        CONTENT_LENGTH=settings.DATA_UPLOAD_MAX_MEMORY_SIZE + 1,
        **bearer(OPERATOR),
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["trace_id"]


@pytest.mark.django_db
def test_authenticated_read_of_a_missing_mission_is_404_not_a_stub(client: Client):
    """#154: `GET /missions/{id}` is real now. `MISSION_ID` is never created by any
    test in this module, so the only honest answer is 404 — reaching the real
    NOT_FOUND path (rather than the old 501 stub) is what this asserts."""
    response = client.get(f"/api/v1/missions/{MISSION_ID}", **bearer(OPERATOR))
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"


# --- authorization ---------------------------------------------------------------


@pytest.mark.django_db
def test_reviewer_may_read(client: Client):
    """A reviewer reaches the same real NOT_FOUND path an operator does — role alone
    gates access to the read, per `require_role(request, *READ_ROLES)`."""
    response = client.get(f"/api/v1/missions/{MISSION_ID}", **bearer(REVIEWER))
    assert response.status_code == 404


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


@pytest.mark.django_db(transaction=True)
async def test_event_stream_is_an_unbuffered_event_stream():
    """Exercised through the async client, because the stream is an ASGI view.

    The deeper SSE behaviours (replay ordering, reconnect, heartbeat, the
    concurrent-stream cap) have their own tests in `test_event_stream.py`. This one
    is the HTTP-surface contract: right status, right content type, the header that
    keeps nginx from buffering it, and real incremental delivery.
    """
    from asgiref.sync import sync_to_async

    from contracts.enums import LanguageAdapter
    from missions.models import Mission

    mission = await sync_to_async(Mission.objects.create)(
        name="pktcfg",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    response = await AsyncClient().get(
        f"/api/v1/missions/{mission.id}/events",
        headers={"authorization": f"Bearer {OPERATOR}"},
    )
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "text/event-stream"
    # nginx buffers proxied responses by default, which silently breaks SSE.
    assert response.headers["X-Accel-Buffering"] == "no"

    it = response.streaming_content.__aiter__()
    first = await it.__anext__()
    assert first == b": brahmadatta stream open\n\n"
    await response._iterator.aclose()


def test_event_stream_requires_a_token(client: Client):
    response = client.get(f"/api/v1/missions/{MISSION_ID}/events")
    assert response.status_code == 401


@pytest.mark.django_db
def test_event_stream_404s_for_a_mission_that_does_not_exist(client: Client):
    response = client.get(
        f"/api/v1/missions/{MISSION_ID}/events", **bearer(OPERATOR)
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.django_db
def test_events_replay_requires_a_token(client: Client):
    response = client.get(f"/api/v1/missions/{MISSION_ID}/events/replay")
    assert response.status_code == 401


@pytest.mark.django_db
def test_events_replay_404s_for_a_mission_that_does_not_exist(client: Client):
    response = client.get(
        f"/api/v1/missions/{MISSION_ID}/events/replay", **bearer(OPERATOR)
    )
    assert response.status_code == 404


# --- docs ------------------------------------------------------------------------


def test_openapi_document_is_served(client: Client):
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "Brahmadatta AI Control API"


def test_docs_page_is_served(client: Client):
    response = client.get("/api/v1/docs")
    assert response.status_code == 200
