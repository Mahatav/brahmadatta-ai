"""Server-sent events for the mission event log (#13).

`GET /missions/{id}/events` is the UI's only source of live truth, and the two ways
it is easy to get wrong are both named in `docs/09-company/12-condition-register.md`
§1.1 C1:

1. **Holding an `asgiref` sync-thread pool thread for the connection's life.** A sync
   generator that reads the ORM directly does exactly that — the thread never comes
   back until the browser tab closes. Three viewers and a couple of reloads exhaust
   the pool, and the failure is silent: the *next* request that needs a thread (any
   ordinary view) just hangs with nothing in any log. Every read below goes through
   `sync_to_async`, once per call, so the thread is returned the moment the query
   finishes.
2. **No cap.** Nothing stops a client from opening the same stream a hundred times.
   `_acquire_slot` enforces `settings.SSE_MAX_STREAMS_PER_MISSION` before the response
   is created at all — so the caller gets a real `429`, not a stream that immediately
   closes.

There is no message broker (D-019/D-024: no Redis, one supervised ASGI process for
the control API). So "live" means polling `MissionEvent` on an interval — a plain
`SELECT ... WHERE sequence > :cursor ORDER BY sequence`, cheap against the
`(mission, sequence)` index `missions.models.MissionEvent` already carries. Reconnect
and gap-recovery are the same code path as the live tail: both start from a cursor
and read forward, which is what makes "replay missed events in order" true by
construction rather than by a second implementation that has to agree with the first.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import HttpRequest
from pydantic import ValidationError

from contracts.errors import TooManyConcurrentStreamsError
from contracts.schemas.envelope import MissionEvent as MissionEventSchema
from missions.models import Mission, MissionEvent
from orchestrator.redaction import redact_loc

logger = logging.getLogger("api.sse")

#: Process-local concurrent-stream accounting, keyed by mission id. Deliberately not
#: a database row: it tracks *this process's* open ASGI connections, and there is
#: exactly one control-api process per D-019/D-024. A multi-worker deployment would
#: need a shared counter; that is not this deployment.
_active_streams: dict[UUID, int] = defaultdict(int)
_streams_guard = asyncio.Lock()

#: SSE preamble comment, sent once so a client (and a human running curl) can tell
#: the connection opened before the first real event arrives.
_STREAM_OPEN = b": brahmadatta stream open\n\n"
_HEARTBEAT = b": heartbeat\n\n"


def _max_streams() -> int:
    return getattr(settings, "SSE_MAX_STREAMS_PER_MISSION", 4)


def _poll_interval() -> float:
    return getattr(settings, "SSE_POLL_INTERVAL_SECONDS", 0.5)


def _heartbeat_interval() -> float:
    return getattr(settings, "SSE_HEARTBEAT_INTERVAL_SECONDS", 15.0)


async def mission_exists(mission_id: UUID) -> bool:
    return await sync_to_async(Mission.objects.filter(pk=mission_id).exists)()


async def acquire_slot(mission_id: UUID) -> None:
    """Reserve one of this mission's `SSE_MAX_STREAMS_PER_MISSION` slots.

    Raises `TooManyConcurrentStreamsError` (429) rather than opening the stream and
    closing it immediately — the caller gets a real error to retry against, and
    `StreamingHttpResponse` is never constructed with a status the body can't change.
    Call `release_slot` exactly once for every successful call, from a `finally`.
    """
    async with _streams_guard:
        if _active_streams[mission_id] >= _max_streams():
            raise TooManyConcurrentStreamsError(
                details={
                    "mission_id": str(mission_id),
                    "limit": _max_streams(),
                }
            )
        _active_streams[mission_id] += 1


async def release_slot(mission_id: UUID) -> None:
    async with _streams_guard:
        remaining = _active_streams.get(mission_id, 0) - 1
        if remaining <= 0:
            _active_streams.pop(mission_id, None)
        else:
            _active_streams[mission_id] = remaining


def resolve_cursor(request: HttpRequest, since_sequence: int) -> int:
    """The sequence to resume after: the larger of `Last-Event-ID` and the explicit
    `since_sequence` query parameter.

    A reconnecting `EventSource` sends `Last-Event-ID` automatically — that is the
    whole mechanism the SSE spec gives a client for "where I left off," and it is the
    header the browser sets, not one JavaScript in this codebase has to manage. The
    query parameter exists so a non-browser client (`sse-client.py`, a test, an
    operator's `curl`) can ask for the same thing explicitly.
    """
    header = request.headers.get("Last-Event-ID")
    if header:
        try:
            return max(int(header), since_sequence)
        except ValueError:
            pass
    return since_sequence


@sync_to_async
def _events_after(mission_id: UUID, cursor: int, limit: int) -> list[MissionEvent]:
    """One SELECT, fully materialized before the thread is returned.

    `list(...)` inside the `sync_to_async`-wrapped call is deliberate: a lazy
    queryset handed back to the async side would evaluate its query the next time it
    is touched, which is exactly the "hold a thread across an await" failure this
    module exists to avoid.
    """
    return list(
        MissionEvent.objects.filter(mission_id=mission_id, sequence__gt=cursor)
        .order_by("sequence")[:limit]
    )


def to_schema(row: MissionEvent) -> MissionEventSchema:
    """Strict conversion: raises `pydantic.ValidationError` if `row.payload` does not
    match any `EventPayload` variant (D-116's original failure mode, before
    `TriageStubPayload` existed). Kept strict and raising — rather than swallowing
    here — because this is also the function contract/unit tests use to prove a given
    payload shape *is* invalid; `safe_to_schema` below is the tolerant wrapper the two
    real serving paths (`format_frame`/`event_frames`, `replay_events`) actually use.
    """
    return MissionEventSchema(
        id=row.id,
        mission_id=row.mission_id,
        sequence=row.sequence,
        timestamp=row.timestamp,
        type=row.type,
        stage=row.stage,
        state=row.state,
        status=row.status,
        severity=row.severity,
        message=row.message,
        payload=row.payload,
        evidence_refs=row.evidence_refs,
        metrics=row.metrics,
        trace_id=row.trace_id,
    )


def safe_to_schema(row: MissionEvent) -> MissionEventSchema | None:
    """`to_schema`, tolerant of a single malformed row (D-116).

    A future event `kind` written by the orchestrator without a matching
    `EventPayload` variant — the exact class of bug `triage_stub` was — must not take
    down an entire mission's live stream or replay page. Logs the failure (row id,
    mission, sequence, trace_id — no payload contents, since a malformed payload is
    exactly the thing not to trust well-formedness of for a log line) and returns
    `None` so the caller can skip just this one row and keep serving the rest.

    #229: deliberately `logger.error(..., exc_info=False)`, never `logger.exception`
    or anything that formats `exc`/`exc.errors()` wholesale. Pydantic's own
    `ValidationError.__str__`/`__repr__` — which is exactly what `logger.exception`'s
    traceback rendering calls — embeds each failing field's actual value as
    `input_value=...`; `exc.errors()` carries the same value under the `"input"` key
    of every entry. Either one, logged raw, is the malformed payload's contents
    leaking into server logs anyway, contradicting the promise this docstring already
    made before #229 (D-113's defense-in-depth landed the try/except; the logging
    call inside it never actually delivered on the comment). `errors(include_url=
    False)`'s `"loc"`/`"type"` keys are the shape of the failure — which field, which
    kind of mismatch — with no value in them, which is what "no payload contents"
    was always supposed to mean.

    #258: `loc` itself can still leak. A forbidden-extra-field failure's `loc` ends in
    the extra field's own *key name* (`StrictSchema`'s `extra="forbid"`), and a payload
    can make that key name secret-shaped (`{"sk-live-...": "y"}` → `loc=("payload",
    "log", "sk-live-...")`) without needing a secret-shaped *value* at all — a narrower
    channel than #229 closed (attacker-controlled key vs. value). `orchestrator.
    redaction.redact_loc` — the same secret-keyword vocabulary `_SECRET_LINE_RE`
    already uses for `GateResult.detail`/sanitizer-report redaction, applied to a bare
    `loc` segment rather than a whole line — replaces just the secret-shaped segment(s),
    keeping the rest of `loc` (which field, which position) as useful as before.
    """
    try:
        return to_schema(row)
    except ValidationError as exc:
        error_shape = [
            {"loc": redact_loc(e["loc"]), "type": e["type"]}
            for e in exc.errors(include_url=False)
        ]
        logger.error(
            "Skipping malformed MissionEvent id=%s mission_id=%s sequence=%s "
            "trace_id=%s — payload failed EventPayload schema validation "
            "(error_shape=%s; payload contents deliberately omitted).",
            row.id,
            row.mission_id,
            row.sequence,
            row.trace_id,
            error_shape,
            exc_info=False,
        )
        return None


def format_frame(row: MissionEvent) -> bytes | None:
    """`id: <sequence>` / `event: <type>` / `data: <MissionEvent JSON>`, or `None` if
    this row is malformed and must be skipped (see `safe_to_schema`).

    Serialized through the frozen `MissionEvent` schema, not the Django row directly,
    so a frame can never carry a shape the contract — and therefore the generated
    TypeScript — does not already describe.
    """
    schema = safe_to_schema(row)
    if schema is None:
        return None
    data = schema.model_dump_json()
    return f"id: {row.sequence}\nevent: {row.type}\ndata: {data}\n\n".encode()


def event_dict_for_test(row: MissionEvent) -> dict[str, Any]:
    """`format_frame`'s payload as a dict, for assertions. Not used by the view.
    Deliberately uses the strict `to_schema` (not `safe_to_schema`): a test asserting
    on this helper wants a real `ValidationError` if the fixture it built is invalid,
    not a silently-`None` result."""
    return json.loads(to_schema(row).model_dump_json())


async def event_frames(mission_id: UUID, cursor: int) -> AsyncIterator[bytes]:
    """Replay-then-tail. The only two states this loop is ever in: catching up on
    persisted rows, or waiting on the next poll — reconnect and "stay live" are the
    same code, so there is no second path that can disagree with the first about
    ordering.

    Runs until the client disconnects, at which point the ASGI handler closes this
    generator (`GeneratorExit` at the suspended `yield`) or the ASGI receive loop's
    disconnect check ends it. Either way the slot release in the caller's `finally`
    still runs, so a heartbeat write that fails because the peer is gone frees the
    slot immediately rather than after the next database poll.

    A single malformed row (`format_frame` returning `None`, see `safe_to_schema`,
    D-116) is skipped, not raised — one bad row must not abort the whole connection.
    The cursor still advances past it either way, so the poll loop does not spin
    forever re-fetching the same unserializable row.
    """
    yield _STREAM_OPEN
    last_activity = time.monotonic()
    while True:
        rows = await _events_after(mission_id, cursor, limit=200)
        if rows:
            for row in rows:
                frame = format_frame(row)
                cursor = row.sequence
                if frame is not None:
                    yield frame
            last_activity = time.monotonic()
        else:
            now = time.monotonic()
            if now - last_activity >= _heartbeat_interval():
                yield _HEARTBEAT
                last_activity = now
        await asyncio.sleep(_poll_interval())
