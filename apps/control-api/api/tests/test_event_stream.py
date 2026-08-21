"""Server-sent events end to end (#13): replay ordering, reconnect, heartbeat, the
concurrent-stream cap, and `/events/replay` gap recovery.

Every test here drives the real ASGI view (`api.routers.missions.stream_events`)
through `django.test.AsyncClient`, not a mock of it — the property under test is
"what actually leaves the process," and a mocked generator cannot prove that.

**Why `@pytest.mark.django_db(transaction=True)` and not the default `django_db`.**
The view reads through `asgiref.sync.sync_to_async`, which runs each query on a
worker thread. The default `django_db` fixture wraps a test in one atomic
transaction on the *test's* connection; a different thread cannot see uncommitted
rows inside that transaction (and, on the in-memory SQLite this suite uses, a second
thread does not even share the same `:memory:` database). `transaction=True` uses
real commits instead, which is what makes cross-thread visibility — the exact thing
CTO-C1 asks this view to do correctly — actually exercised rather than incidentally
passing because everything ran on one thread.

**Why tests close what they open.** `StreamingHttpResponse.streaming_content` is a
*property*: reading it returns a fresh wrapper around the response's real generator
(`response._iterator`) each time, so closing the wrapper does not close the
generator underneath it. A real ASGI disconnect closes `_iterator` directly, after
already having pulled at least one frame from it — a fresh, never-started generator
does not run its `finally` block when closed (Python does not enter a generator's
body just to close it). Tests that check slot release therefore pull one frame
before closing, matching what the ASGI handler actually does.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from asgiref.sync import sync_to_async
from django.conf import settings
from django.test import AsyncClient, Client, override_settings

from contracts.enums import (
    EventStatus,
    EventType,
    LanguageAdapter,
    MissionStage,
    MissionState,
    Severity,
)
from missions.models import Mission, MissionEvent

OPERATOR = settings.CONTROL_API_TOKENS["operator"]
TRACE = "test-trace-0000000000000000"


def bearer(token: str) -> dict[str, str]:
    """For `django.test.Client`, which reads auth from WSGI-style `**extra` kwargs."""
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def auth_header(token: str, **more: str) -> dict[str, dict[str, str]]:
    """For `django.test.AsyncClient`, which takes a `headers=` dict instead."""
    return {"headers": {"authorization": f"Bearer {token}", **more}}


async def _create_mission() -> Mission:
    return await sync_to_async(Mission.objects.create)(
        name="pktcfg",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )


async def _emit(mission: Mission, sequence: int) -> MissionEvent:
    def _write() -> MissionEvent:
        return MissionEvent.objects.create(
            mission=mission,
            sequence=sequence,
            timestamp=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
            type=EventType.LOG.value,
            stage=MissionStage.BASELINE.value,
            state=MissionState.BASELINE.value,
            status=EventStatus.RUNNING.value,
            severity=Severity.INFO.value,
            message=f"event {sequence}",
            payload={"kind": "log", "text": f"line {sequence}"},
            evidence_refs=[],
            metrics={},
            trace_id=TRACE,
        )

    return await sync_to_async(_write)()


async def _collect(streaming_content, count: int, *, timeout_seconds: float = 5.0) -> bytes:
    """The first `count` frames, or raise `asyncio.TimeoutError` well before CI's own
    timeout would — a hang here means the stream never produced what was expected,
    not that it needs more patience."""
    import asyncio

    frames: list[bytes] = []
    it = streaming_content.__aiter__()

    async def _pull() -> None:
        async for chunk in it:
            frames.append(chunk)
            if len(frames) >= count:
                return

    await asyncio.wait_for(_pull(), timeout=timeout_seconds)
    return b"".join(frames)


# --- replay ordering and persistence ---------------------------------------------


@pytest.mark.django_db(transaction=True)
async def test_stream_replays_persisted_events_in_order_before_going_live():
    mission = await _create_mission()
    await _emit(mission, 1)
    await _emit(mission, 2)
    await _emit(mission, 3)

    response = await AsyncClient().get(
        f"/api/v1/missions/{mission.id}/events", **auth_header(OPERATOR)
    )
    assert response.status_code == 200
    body = (await _collect(response.streaming_content, 4)).decode()
    await response._iterator.aclose()

    assert body.index("id: 1") < body.index("id: 2") < body.index("id: 3")
    assert '"sequence":1' in body
    assert '"sequence":2' in body
    assert '"sequence":3' in body


@pytest.mark.django_db(transaction=True)
async def test_stream_survives_a_fresh_process_reading_the_same_rows():
    """"Events persist and survive restart" (#13 AC).

    There is no in-process cache of event *content* anywhere in `api.sse` — only a
    concurrent-stream *counter*, which is connection accounting, not data. Every
    frame comes from one `SELECT` against `MissionEvent`. This test proves that by
    closing every open database connection (the closest a single test process can
    get to "the process restarted") between writing the events and reading them
    back over a brand-new connection, then streaming from a mission object it never
    held a reference to across the gap.
    """
    from django.db import connections

    mission = await _create_mission()
    await _emit(mission, 1)
    await _emit(mission, 2)
    mission_id = mission.id

    await sync_to_async(connections.close_all)()

    response = await AsyncClient().get(
        f"/api/v1/missions/{mission_id}/events", **auth_header(OPERATOR)
    )
    assert response.status_code == 200
    body = (await _collect(response.streaming_content, 3)).decode()
    await response._iterator.aclose()

    assert "id: 1" in body
    assert "id: 2" in body


# --- reconnect with Last-Event-ID --------------------------------------------------


@pytest.mark.django_db(transaction=True)
async def test_reconnect_with_last_event_id_replays_only_missed_events_in_order():
    mission = await _create_mission()
    await _emit(mission, 1)
    await _emit(mission, 2)
    await _emit(mission, 3)

    response = await AsyncClient().get(
        f"/api/v1/missions/{mission.id}/events",
        **auth_header(OPERATOR, **{"Last-Event-ID": "1"}),
    )
    body = (await _collect(response.streaming_content, 3)).decode()
    await response._iterator.aclose()

    assert "id: 1\n" not in body
    assert body.index("id: 2") < body.index("id: 3")


@pytest.mark.django_db(transaction=True)
async def test_since_sequence_query_param_does_the_same_thing_for_non_browser_clients():
    mission = await _create_mission()
    await _emit(mission, 1)
    await _emit(mission, 2)

    response = await AsyncClient().get(
        f"/api/v1/missions/{mission.id}/events?since_sequence=1", **auth_header(OPERATOR)
    )
    body = (await _collect(response.streaming_content, 2)).decode()
    await response._iterator.aclose()

    assert "id: 1\n" not in body
    assert "id: 2" in body


# --- heartbeat ----------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
async def test_an_idle_stream_emits_heartbeats_instead_of_going_silent():
    mission = await _create_mission()
    await _emit(mission, 1)

    with override_settings(
        SSE_HEARTBEAT_INTERVAL_SECONDS=0.15, SSE_POLL_INTERVAL_SECONDS=0.05
    ):
        response = await AsyncClient().get(
            f"/api/v1/missions/{mission.id}/events?since_sequence=1", **auth_header(OPERATOR)
        )
        body = (
            await _collect(response.streaming_content, 3, timeout_seconds=3.0)
        ).decode()
        await response._iterator.aclose()

    assert body.count(": heartbeat") >= 2


# --- concurrent-stream cap (CTO-C1) --------------------------------------------------


@pytest.mark.django_db(transaction=True)
async def test_a_mission_over_the_concurrent_stream_cap_gets_429_not_a_stream():
    mission = await _create_mission()

    with override_settings(SSE_MAX_STREAMS_PER_MISSION=1):
        first = await AsyncClient().get(
            f"/api/v1/missions/{mission.id}/events", **auth_header(OPERATOR)
        )
        assert first.status_code == 200

        second = await AsyncClient().get(
            f"/api/v1/missions/{mission.id}/events", **auth_header(OPERATOR)
        )
        assert second.status_code == 429
        assert second.json()["error"]["code"] == "CONFLICT"

        await first._iterator.aclose()


@pytest.mark.django_db(transaction=True)
async def test_the_slot_frees_when_the_client_disconnects():
    mission = await _create_mission()

    with override_settings(SSE_MAX_STREAMS_PER_MISSION=1):
        first = await AsyncClient().get(
            f"/api/v1/missions/{mission.id}/events", **auth_header(OPERATOR)
        )
        assert first.status_code == 200
        # Prime the generator the way a real ASGI send-loop would (see module
        # docstring), then close it the way a real disconnect does.
        await first._iterator.__anext__()
        await first._iterator.aclose()

        second = await AsyncClient().get(
            f"/api/v1/missions/{mission.id}/events", **auth_header(OPERATOR)
        )
        assert second.status_code == 200
        await second._iterator.aclose()


@pytest.mark.django_db(transaction=True)
async def test_the_cap_is_per_mission_not_global():
    mission_a = await _create_mission()
    mission_b = await _create_mission()

    with override_settings(SSE_MAX_STREAMS_PER_MISSION=1):
        a = await AsyncClient().get(
            f"/api/v1/missions/{mission_a.id}/events", **auth_header(OPERATOR)
        )
        b = await AsyncClient().get(
            f"/api/v1/missions/{mission_b.id}/events", **auth_header(OPERATOR)
        )
        assert a.status_code == 200
        assert b.status_code == 200
        await a._iterator.aclose()
        await b._iterator.aclose()


# --- /events/replay -------------------------------------------------------------


@pytest.mark.django_db
def test_replay_endpoint_returns_events_after_the_cursor_in_order():
    mission = Mission.objects.create(
        name="pktcfg",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    for seq in (1, 2, 3):
        MissionEvent.objects.create(
            mission=mission,
            sequence=seq,
            timestamp=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
            type=EventType.LOG.value,
            stage=MissionStage.BASELINE.value,
            state=MissionState.BASELINE.value,
            status=EventStatus.RUNNING.value,
            severity=Severity.INFO.value,
            message=f"event {seq}",
            payload={"kind": "log", "text": f"line {seq}"},
            evidence_refs=[],
            metrics={},
            trace_id=TRACE,
        )

    response = Client().get(
        f"/api/v1/missions/{mission.id}/events/replay?since_sequence=1",
        **bearer(OPERATOR),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [item["sequence"] for item in body["items"]] == [2, 3]


@pytest.mark.django_db
def test_replay_endpoint_paginates_with_limit():
    mission = Mission.objects.create(
        name="pktcfg",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    for seq in range(1, 6):
        MissionEvent.objects.create(
            mission=mission,
            sequence=seq,
            timestamp=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
            type=EventType.LOG.value,
            stage=MissionStage.BASELINE.value,
            state=MissionState.BASELINE.value,
            status=EventStatus.RUNNING.value,
            severity=Severity.INFO.value,
            message=f"event {seq}",
            payload={"kind": "log", "text": f"line {seq}"},
            evidence_refs=[],
            metrics={},
            trace_id=TRACE,
        )

    response = Client().get(
        f"/api/v1/missions/{mission.id}/events/replay?since_sequence=0&limit=2",
        **bearer(OPERATOR),
    )
    body = response.json()
    assert body["total"] == 5
    assert body["limit"] == 2
    assert [item["sequence"] for item in body["items"]] == [1, 2]


# --- D-116 regression: triage_stub events and malformed-row resilience -------------
#
# `orchestrator.queue._emit_triage_stub_events` has emitted real `MissionEvent` rows
# with `payload={"kind": "triage_stub"}` for every mission's mandatory TRIAGE stage
# since months before this schema variant existed. `contracts.schemas.envelope.
# MissionEventSchema`'s payload union had no matching tag, so `api.sse.to_schema`
# raised `pydantic.ValidationError` on every such row — crashing the live SSE stream
# (`GET .../events`) mid-connection and 500ing the REST replay endpoint
# (`GET .../events/replay`) outright. These tests reproduce that failure against the
# *unpatched* strict path (`api.sse.to_schema`, still strict by design) and then
# prove both real HTTP-reachable paths survive it end to end.


async def _emit_triage_stub(mission: Mission, sequence: int) -> MissionEvent:
    """The exact row shape `orchestrator.queue._emit_triage_stub_events` writes."""

    def _write() -> MissionEvent:
        return MissionEvent.objects.create(
            mission=mission,
            sequence=sequence,
            timestamp=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
            type=EventType.STAGE_COMPLETED.value,
            stage=MissionStage.ANALYZE.value,
            state=MissionState.TRIAGE.value,
            status=EventStatus.SUCCEEDED.value,
            severity=Severity.INFO.value,
            message="TRIAGE completed",
            payload={"kind": "triage_stub"},
            evidence_refs=[],
            metrics={},
            trace_id=TRACE,
        )

    return await sync_to_async(_write)()


@pytest.mark.django_db
def test_triage_stub_row_now_validates_through_the_strict_schema_path():
    """D-116's actual root-cause fix: `TriageStubPayload` is a real, recognized
    variant now, so the strict conversion function (`api.sse.to_schema`, used by
    tests/tooling that want a hard failure on genuine drift) accepts the real
    orchestrator payload rather than raising."""
    from api import sse

    mission = Mission.objects.create(
        name="pktcfg",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    row = MissionEvent.objects.create(
        mission=mission,
        sequence=1,
        timestamp=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
        type=EventType.STAGE_COMPLETED.value,
        stage=MissionStage.ANALYZE.value,
        state=MissionState.TRIAGE.value,
        status=EventStatus.SUCCEEDED.value,
        severity=Severity.INFO.value,
        message="TRIAGE completed",
        payload={"kind": "triage_stub"},
        evidence_refs=[],
        metrics={},
        trace_id=TRACE,
    )

    schema = sse.to_schema(row)
    assert schema.payload.kind == "triage_stub"


@pytest.mark.django_db(transaction=True)
async def test_sse_stream_survives_a_real_triage_stub_event_without_dying():
    """Reproduces D-116's SSE crash (`ERR_HTTP2_PROTOCOL_ERROR` client-side, a
    `ValidationError` raised mid-generator server-side) against real `_emit`-shaped
    rows, with a real triage_stub event sandwiched between two ordinary ones. Before
    the schema fix this would abort the whole generator on the middle row; after it,
    all three frames stream through in order, live."""
    mission = await _create_mission()
    await _emit(mission, 1)
    await _emit_triage_stub(mission, 2)
    await _emit(mission, 3)

    response = await AsyncClient().get(
        f"/api/v1/missions/{mission.id}/events", **auth_header(OPERATOR)
    )
    assert response.status_code == 200
    body = (await _collect(response.streaming_content, 4)).decode()
    await response._iterator.aclose()

    assert body.index("id: 1") < body.index("id: 2") < body.index("id: 3")
    assert '"sequence":2' in body
    assert '"kind":"triage_stub"' in body


@pytest.mark.django_db
def test_replay_endpoint_survives_a_real_triage_stub_event_without_500ing():
    """Reproduces D-116's REST replay crash (a real 500 `INTERNAL_ERROR`, confirmed
    live via `docker logs` + `trace_id` correlation) against a real triage_stub row,
    then confirms it returns 200 with the event correctly typed."""
    mission = Mission.objects.create(
        name="pktcfg",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    MissionEvent.objects.create(
        mission=mission,
        sequence=1,
        timestamp=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
        type=EventType.STAGE_COMPLETED.value,
        stage=MissionStage.ANALYZE.value,
        state=MissionState.TRIAGE.value,
        status=EventStatus.SUCCEEDED.value,
        severity=Severity.INFO.value,
        message="TRIAGE completed",
        payload={"kind": "triage_stub"},
        evidence_refs=[],
        metrics={},
        trace_id=TRACE,
    )

    response = Client().get(
        f"/api/v1/missions/{mission.id}/events/replay?since_sequence=0",
        **bearer(OPERATOR),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["payload"]["kind"] for item in body["items"]] == ["triage_stub"]


# --- defense in depth: a genuinely malformed row must not sink the whole mission ---


async def _emit_malformed(mission: Mission, sequence: int) -> MissionEvent:
    """A row with a `kind` no `EventPayload` variant recognizes — simulates the
    *next* orchestrator/schema drift, the class of bug `triage_stub` was. Bypasses
    Django's own model-level validation (there is none on `payload`, a plain JSON
    field) exactly the way a real bug in the orchestrator would: it writes something
    the schema was never told about."""

    def _write() -> MissionEvent:
        return MissionEvent.objects.create(
            mission=mission,
            sequence=sequence,
            timestamp=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
            type=EventType.LOG.value,
            stage=MissionStage.BASELINE.value,
            state=MissionState.BASELINE.value,
            status=EventStatus.RUNNING.value,
            severity=Severity.INFO.value,
            message="from a future, not-yet-modeled event kind",
            payload={"kind": "some_future_kind_nobody_added_a_schema_for"},
            evidence_refs=[],
            metrics={},
            trace_id=TRACE,
        )

    return await sync_to_async(_write)()


@pytest.mark.django_db
def test_to_schema_still_raises_on_a_genuinely_unrecognized_kind():
    """The strict path (`api.sse.to_schema`) must keep raising — this is what proves
    the resilience below is a deliberate skip-and-log, not a permissive catch-all
    that would hide real future schema drift the same way `triage_stub` hid this
    one."""
    from pydantic import ValidationError

    from api import sse

    mission = Mission.objects.create(
        name="pktcfg",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    row = MissionEvent.objects.create(
        mission=mission,
        sequence=1,
        timestamp=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
        type=EventType.LOG.value,
        stage=MissionStage.BASELINE.value,
        state=MissionState.BASELINE.value,
        status=EventStatus.RUNNING.value,
        severity=Severity.INFO.value,
        message="from a future, not-yet-modeled event kind",
        payload={"kind": "some_future_kind_nobody_added_a_schema_for"},
        evidence_refs=[],
        metrics={},
        trace_id=TRACE,
    )

    with pytest.raises(ValidationError):
        sse.to_schema(row)


@pytest.mark.django_db(transaction=True)
async def test_sse_stream_skips_one_malformed_row_and_keeps_serving_the_rest():
    """Defense in depth (D-116 recommendation (b)/(c)): a single malformed row must
    not take down the whole connection. The good events on either side of it still
    stream through, in order; the malformed one is silently absent from the frames
    but does not stall the cursor (a real follow-up drift like this one must not
    freeze the poll loop forever re-fetching the same bad row)."""
    mission = await _create_mission()
    await _emit(mission, 1)
    await _emit_malformed(mission, 2)
    await _emit(mission, 3)

    response = await AsyncClient().get(
        f"/api/v1/missions/{mission.id}/events", **auth_header(OPERATOR)
    )
    assert response.status_code == 200
    body = (await _collect(response.streaming_content, 3)).decode()
    await response._iterator.aclose()

    assert "id: 1" in body
    assert "id: 2" not in body  # the malformed row: skipped, not crashed on
    assert "id: 3" in body
    assert body.index("id: 1") < body.index("id: 3")


@pytest.mark.django_db
def test_replay_endpoint_skips_one_malformed_row_instead_of_500ing():
    mission = Mission.objects.create(
        name="pktcfg",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    for seq, payload in (
        (1, {"kind": "log", "text": "line 1"}),
        (2, {"kind": "some_future_kind_nobody_added_a_schema_for"}),
        (3, {"kind": "log", "text": "line 3"}),
    ):
        MissionEvent.objects.create(
            mission=mission,
            sequence=seq,
            timestamp=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
            type=EventType.LOG.value,
            stage=MissionStage.BASELINE.value,
            state=MissionState.BASELINE.value,
            status=EventStatus.RUNNING.value,
            severity=Severity.INFO.value,
            message=f"event {seq}",
            payload=payload,
            evidence_refs=[],
            metrics={},
            trace_id=TRACE,
        )

    response = Client().get(
        f"/api/v1/missions/{mission.id}/events/replay?since_sequence=0",
        **bearer(OPERATOR),
    )

    assert response.status_code == 200
    body = response.json()
    # `total` still counts every row in range (accurate about what exists);
    # `items` holds only the ones that could actually be served.
    assert body["total"] == 3
    assert [item["sequence"] for item in body["items"]] == [1, 3]
