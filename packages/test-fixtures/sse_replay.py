"""Replay a committed mission fixture over the real SSE contract.

    python3 packages/test-fixtures/sse_replay.py

That is the whole command. It serves the pktcfg fixture on http://127.0.0.1:8971 at the
same paths, with the same framing and the same headers the control API will use, so a
Command Center panel written against it needs no change when the orchestrator (#12)
lands. Point nginx — or the Astro dev proxy — at this process instead of `control-api`
and the panel is talking to the real URL.

Routes, all matching `docs/03-technical/21-api-specification.md`:

    GET /api/v1/missions/{mission_id}/events
        Server-sent events. `id: <sequence>`, `event: <MissionEvent.type>`,
        `data: <MissionEvent as JSON>`. Honours `Last-Event-ID`, sends `: keepalive`
        comments, and sets `X-Accel-Buffering: no`.

    GET /api/v1/missions/{mission_id}/events/replay?since_sequence=N&limit=M
        `Page[MissionEvent]` — the gap-recovery endpoint. Always complete: the stored
        log has no gaps, only the live stream does.

    GET /api/v1/missions/{mission_id}
    GET /api/v1/missions
        Enough of the mission surface to render a panel header. Derived from the
        fixture, never invented.

## The dropped window

`--drop 13-15` is on by default. Those three sequences are withheld from the live stream
so a client sees `id: 12` followed by `id: 16` and has to notice. The stored fixture
itself is gap-free, because a gap is something a transport loses and never something a
server recorded — `sequence` is documented as a gap-free per-mission counter, and a
fixture that violated that would teach every panel built against it the wrong invariant.
Pass `--drop ''` to stream the log intact.

Recovery is the ordinary path: call `/events/replay?since_sequence=12`, which serves
every event from 13 on, including the withheld ones.

## This is a build tool and it never goes on screen

`docs/09-company/10-fallback-ladder.md` §2.5 bans this fixture from the finale. It is
realistic fabricated events — that is what makes it useful for building panels, and it is
exactly what makes it dangerous at hour 30 when the panels are dead and this is the
obvious thing to reach for. Streaming it in front of a judge would be decorative fake
telemetry presented as a run.

Two things enforce that here rather than leaving it to a tired operator's judgement:

*   The server binds to loopback only. Serving it on an address someone else can reach
    needs `--allow-remote`, which prints the ban and is not something you type by
    accident.
*   Every response carries `X-Brahmadatta-Fixture: replay`, and the stream opens with a
    `: FIXTURE REPLAY` comment. A panel, a proxy log, or a screen recording all show what
    this is.

## Speed

`--speed` scales the fixture's own inter-event gaps. `--speed 1` runs the mission in its
recorded ~62 seconds; `--speed 10` in about six; `--speed 0` streams as fast as the
socket accepts, which is the mode to use when a panel just needs terminal state. Gaps are
capped by `--max-gap` so a long recorded pause does not stall an interactive session.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
DEFAULT_FIXTURE = HERE / "missions" / "mission-pktcfg-001.events.jsonl"

EVENTS_RE = re.compile(r"^/api/v1/missions/(?P<mission_id>[^/]+)/events/?$")
REPLAY_RE = re.compile(r"^/api/v1/missions/(?P<mission_id>[^/]+)/events/replay/?$")
MISSION_RE = re.compile(r"^/api/v1/missions/(?P<mission_id>[^/]+)/?$")
MISSIONS_RE = re.compile(r"^/api/v1/missions/?$")


def load_events(path: Path) -> list[dict[str, Any]]:
    events = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not events:
        raise SystemExit(f"{path} contains no events")

    sequences = [event["sequence"] for event in events]
    if sequences != list(range(1, len(events) + 1)):
        raise SystemExit(
            f"{path} is not a gap-free log. `sequence` is a gap-free per-mission counter; "
            f"the gap belongs in the stream (--drop), not in the fixture."
        )
    return events


def parse_drop(spec: str) -> set[int]:
    """`13-15,22` -> {13, 14, 15, 22}. Empty string -> nothing dropped."""
    dropped: set[int] = set()
    for chunk in (part.strip() for part in spec.split(",")):
        if not chunk:
            continue
        if "-" in chunk:
            low, _, high = chunk.partition("-")
            dropped.update(range(int(low), int(high) + 1))
        else:
            dropped.add(int(chunk))
    return dropped


def mission_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive a mission header from the event log. Nothing here is invented — every
    field is read back out of the events themselves."""
    last = events[-1]
    counts = {
        "findings": sum(1 for e in events if e["payload"]["kind"] == "finding"),
        "reproducers": sum(1 for e in events if e["payload"]["kind"] == "reproducer"),
        "patches": sum(1 for e in events if e["payload"]["kind"] == "patch_candidate"),
        "verifications": sum(1 for e in events if e["payload"]["kind"] == "verification"),
    }
    verdict = next(
        (
            e["payload"]["summary"]
            for e in reversed(events)
            if e["payload"]["kind"] == "mission_verdict"
        ),
        None,
    )
    return {
        "mission_id": last["mission_id"],
        "state": last["state"],
        "posture": next(
            e["payload"]["posture"]
            for e in reversed(events)
            if e["payload"]["kind"] == "state_changed"
        ),
        "started_at": events[0]["timestamp"],
        "updated_at": last["timestamp"],
        "counts": counts,
        "verdict_summary": verdict,
        "event_count": len(events),
        "source": "packages/test-fixtures — replayed fixture, not a live mission",
    }


class ReplayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # injected by serve()
    events: ClassVar[list[dict[str, Any]]] = []
    dropped: ClassVar[set[int]] = set()
    speed: float = 4.0
    max_gap: float = 2.0
    keepalive: float = 15.0
    loop: bool = False

    server_version = "brahmadatta-fixture-replay"
    sys_version = ""

    # -- helpers -----------------------------------------------------------------

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write(f"[replay] {self.address_string()} {fmt % args}\n")

    def _json(self, status: int, body: dict[str, Any]) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Trace-Id", "fixture-replay")
        self.send_header("X-Brahmadatta-Fixture", "replay")
        self.end_headers()
        self.wfile.write(payload)

    def _error(self, status: int, code: str, message: str) -> None:
        self._json(
            status,
            {
                "error": {"code": code, "message": message, "details": {}},
                "trace_id": "fixture-replay",
            },
        )

    # -- routing -----------------------------------------------------------------

    def do_GET(self) -> None:
        url = urlparse(self.path)
        query = parse_qs(url.query)

        if match := EVENTS_RE.match(url.path):
            self.stream_events(match.group("mission_id"))
            return
        if match := REPLAY_RE.match(url.path):
            self.replay_page(match.group("mission_id"), query)
            return
        if match := MISSION_RE.match(url.path):
            self.mission_detail(match.group("mission_id"))
            return
        if MISSIONS_RE.match(url.path):
            summary = mission_summary(self.events)
            self._json(200, {"items": [summary], "total": 1, "limit": 50, "offset": 0})
            return

        self._error(404, "NOT_FOUND", f"No route for {url.path}")

    def _wrong_mission(self, mission_id: str) -> bool:
        actual = self.events[0]["mission_id"]
        if mission_id == actual:
            return False
        self._error(
            404,
            "NOT_FOUND",
            f"This replay serves mission {actual}; {mission_id} is not in the fixture.",
        )
        return True

    def mission_detail(self, mission_id: str) -> None:
        if self._wrong_mission(mission_id):
            return
        self._json(200, mission_summary(self.events))

    def replay_page(self, mission_id: str, query: dict[str, list[str]]) -> None:
        if self._wrong_mission(mission_id):
            return
        try:
            since = int(query.get("since_sequence", ["0"])[0])
            limit = int(query.get("limit", ["200"])[0])
        except ValueError:
            self._error(422, "VALIDATION_ERROR", "since_sequence and limit must be integers")
            return
        if since < 0 or not (1 <= limit <= 500):
            self._error(422, "VALIDATION_ERROR", "since_sequence >= 0, 1 <= limit <= 500")
            return

        # The stored log is complete. Gap recovery has to return the events the live
        # stream withheld, or it is not recovery.
        matching = [event for event in self.events if event["sequence"] > since]
        self._json(
            200,
            {
                "items": matching[:limit],
                "total": len(matching),
                "limit": limit,
                "offset": since,
            },
        )

    # -- the stream ---------------------------------------------------------------

    def stream_events(self, mission_id: str) -> None:
        if self._wrong_mission(mission_id):
            return

        last_event_id = self.headers.get("Last-Event-ID")
        try:
            resume_after = int(last_event_id) if last_event_id else 0
        except ValueError:
            resume_after = 0

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache, no-transform")
        # Belt and braces with nginx's `proxy_buffering off`. Without one of the two the
        # whole stream arrives in a lump at the end, silently. See
        # infrastructure/compose/nginx/includes/sse.conf.
        self.send_header("X-Accel-Buffering", "no")
        # An SSE body has no Content-Length. It is terminated by the connection closing,
        # which is what `close_connection` below arranges. The alternative — chunked
        # transfer encoding — would be equally valid but adds a framing layer nginx is
        # told to strip anyway (`chunked_transfer_encoding off` in includes/sse.conf).
        # Without one of the two a client blocks forever waiting for a body length that
        # never comes, which is how this was found.
        self.send_header("Connection", "close")
        self.close_connection = True
        # Fallback ladder §2.5: this stream is fabricated and must never be shown to a
        # judge. Say so on the wire, so a proxy log or a screen recording carries it too.
        self.send_header("X-Brahmadatta-Fixture", "replay")
        self.end_headers()

        try:
            self.wfile.write(
                b": FIXTURE REPLAY - fabricated events, build tool only, never on screen\n\n"
            )
            self.wfile.flush()
            if resume_after:
                self.wfile.write(
                    f": resuming after Last-Event-ID {resume_after}\n\n".encode()
                )
                self.wfile.flush()

            while True:
                self._stream_once(resume_after)
                if not self.loop:
                    break
                resume_after = 0
                time.sleep(1.0)

            self.wfile.write(b": end of fixture\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            self.log_message("client disconnected")

    def _stream_once(self, resume_after: int) -> None:
        previous_ts: float | None = None
        last_write = time.monotonic()

        for event in self.events:
            sequence = event["sequence"]
            timestamp = self._epoch(event["timestamp"])

            gap = 0.0 if previous_ts is None else max(0.0, timestamp - previous_ts)
            previous_ts = timestamp
            if self.speed > 0:
                delay = min(gap / self.speed, self.max_gap)
                # Keep the connection warm across a long recorded pause. A dead TCP path
                # has to be detectable long before nginx's proxy_read_timeout fires.
                while delay > 0:
                    step = min(delay, self.keepalive)
                    time.sleep(step)
                    delay -= step
                    if time.monotonic() - last_write >= self.keepalive:
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
                        last_write = time.monotonic()

            if sequence <= resume_after or sequence in self.dropped:
                continue

            frame = (
                f"id: {sequence}\n"
                f"event: {event['type']}\n"
                f"data: {json.dumps(event, separators=(',', ':'))}\n\n"
            )
            self.wfile.write(frame.encode())
            self.wfile.flush()
            last_write = time.monotonic()

    @staticmethod
    def _epoch(iso: str) -> float:
        from datetime import datetime

        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


LOOPBACK = {"127.0.0.1", "::1", "localhost"}

FIXTURE_BAN = (
    "docs/09-company/10-fallback-ladder.md §2.5: the #71 fixture is a build tool. It is "
    "fabricated telemetry and must never be streamed in front of a judge."
)


def serve(args: argparse.Namespace) -> int:
    if args.host not in LOOPBACK and not args.allow_remote:
        raise SystemExit(
            f"refusing to bind {args.host}: this replay serves fabricated mission "
            f"events.\n{FIXTURE_BAN}\nIf you genuinely need it reachable from another "
            f"host on the dev network, pass --allow-remote."
        )

    events = load_events(args.fixture)
    dropped = parse_drop(args.drop)

    ReplayHandler.events = events
    ReplayHandler.dropped = dropped
    ReplayHandler.speed = args.speed
    ReplayHandler.max_gap = args.max_gap
    ReplayHandler.loop = args.loop

    mission_id = events[0]["mission_id"]
    httpd = ThreadingHTTPServer((args.host, args.port), ReplayHandler)
    httpd.daemon_threads = True
    host, port = httpd.server_address[0], httpd.server_address[1]

    base = f"http://{host}:{port}/api/v1/missions/{mission_id}"
    print(f"fixture      {args.fixture}")  # noqa: T201 - operator-facing tool
    print(f"events       {len(events)} (sequences 1..{len(events)})")  # noqa: T201
    print(f"withheld     {sorted(dropped) or 'none'}")  # noqa: T201
    print(f"speed        {args.speed}x (max gap {args.max_gap}s)")  # noqa: T201
    print(f"stream       {base}/events")  # noqa: T201
    print(f"gap recovery {base}/events/replay?since_sequence=N")  # noqa: T201
    print(f"\nBUILD TOOL - {FIXTURE_BAN}")  # noqa: T201
    print("ctrl-c to stop")  # noqa: T201

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")  # noqa: T201
    finally:
        httpd.shutdown()
        httpd.server_close()
    return 0


def check(args: argparse.Namespace) -> int:
    events = load_events(args.fixture)
    print(f"ok: {args.fixture} holds {len(events)} gap-free events")  # noqa: T201
    print(f"    mission {events[0]['mission_id']}")  # noqa: T201
    print(f"    terminal state {events[-1]['state']}")  # noqa: T201
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sse_replay",
        description="Replay a committed mission fixture over the real SSE contract.",
    )
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8971)
    parser.add_argument(
        "--speed",
        type=float,
        default=4.0,
        help="Multiplier on the fixture's own timing. 0 streams as fast as possible.",
    )
    parser.add_argument(
        "--max-gap",
        type=float,
        default=2.0,
        help="Cap on any single inter-event pause, in seconds.",
    )
    parser.add_argument(
        "--drop",
        default="13-15",
        help="Sequences to withhold from the live stream so a client must reconnect and "
        "replay. Pass '' to stream the log intact.",
    )
    parser.add_argument("--loop", action="store_true", help="Restart when the fixture ends.")
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Bind a non-loopback address. Read the fallback ladder §2.5 first.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate the fixture's shape and exit without serving.",
    )
    args = parser.parse_args(argv)

    if not args.fixture.is_file():
        raise SystemExit(f"fixture not found: {args.fixture}")
    return check(args) if args.check else serve(args)


if __name__ == "__main__":
    raise SystemExit(main())
