"""The replay command behaves like the SSE contract it stands in for.

Each test starts a real server on a real port and talks to it over a real socket. There
is no mocked transport here, because the properties worth asserting — that frames arrive
one at a time rather than in a lump, that a gap is visible to the client, that
`Last-Event-ID` resumes — are all properties of the transport.

`test_frames_arrive_incrementally` is the one that matters most. It is the same property
`verify-through-nginx.sh` checks on the other side of a proxy: an SSE stream that is
buffered anywhere arrives as one block at the end, and the failure is invisible until a
panel silently renders nothing.
"""

from __future__ import annotations

import http.client
import itertools
import json
import socket
import sys
import threading
import time
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sse_replay

FIXTURE = sse_replay.DEFAULT_FIXTURE
DROPPED = {13, 14, 15}


@pytest.fixture(scope="module")
def events() -> list[dict[str, Any]]:
    return sse_replay.load_events(FIXTURE)


@pytest.fixture
def server(events: list[dict[str, Any]]) -> Iterator[tuple[str, int]]:
    """A replay server on an ephemeral port, streaming as fast as the socket allows."""
    sse_replay.ReplayHandler.events = events
    sse_replay.ReplayHandler.dropped = set(DROPPED)
    sse_replay.ReplayHandler.speed = 0.0  # no artificial delay; timing is not under test
    sse_replay.ReplayHandler.max_gap = 0.0
    sse_replay.ReplayHandler.loop = False

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), sse_replay.ReplayHandler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[0], httpd.server_address[1]
    try:
        yield str(host), int(port)
    finally:
        httpd.shutdown()
        httpd.server_close()


def read_stream(
    host: str, port: int, mission_id: str, *, last_event_id: str | None = None,
    timeout: float = 20.0,
) -> tuple[dict[str, str], list[tuple[int, str, dict[str, Any]]]]:
    """Consume the whole SSE stream. Returns headers and (sequence, type, data) frames."""
    headers = {"Accept": "text/event-stream"}
    if last_event_id:
        headers["Last-Event-ID"] = last_event_id

    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    conn.request("GET", f"/api/v1/missions/{mission_id}/events", headers=headers)
    response = conn.getresponse()
    assert response.status == 200, response.read()[:400]

    response_headers = {key.lower(): value for key, value in response.getheaders()}
    body = response.read().decode()
    conn.close()
    return response_headers, parse_frames(body)


def parse_frames(body: str) -> list[tuple[int, str, dict[str, Any]]]:
    frames: list[tuple[int, str, dict[str, Any]]] = []
    for block in body.split("\n\n"):
        lines = [line for line in block.splitlines() if line and not line.startswith(":")]
        if not lines:
            continue
        fields: dict[str, str] = {}
        for line in lines:
            key, _, value = line.partition(": ")
            fields[key] = value
        if "data" not in fields:
            continue
        frames.append((int(fields["id"]), fields["event"], json.loads(fields["data"])))
    return frames


# --- framing --------------------------------------------------------------------


def test_stream_headers_defeat_proxy_buffering(server, events) -> None:
    headers, _ = read_stream(*server, events[0]["mission_id"])
    assert headers["content-type"] == "text/event-stream"
    assert headers["x-accel-buffering"] == "no", (
        "without this nginx buffers the stream and the Command Center renders nothing"
    )
    assert "no-cache" in headers["cache-control"]
    assert headers["x-brahmadatta-fixture"] == "replay", (
        "fallback ladder §2.5: a fabricated stream must say so on the wire"
    )


def test_every_frame_carries_id_event_and_data(server, events) -> None:
    _, frames = read_stream(*server, events[0]["mission_id"])
    assert frames, "no frames arrived"
    for sequence, event_type, data in frames:
        assert data["sequence"] == sequence, "SSE id must be the event sequence"
        assert data["type"] == event_type, "SSE event name must be MissionEvent.type"
        assert data["mission_id"] == events[0]["mission_id"]


def test_stream_carries_the_whole_mission_to_a_terminal_state(server, events) -> None:
    _, frames = read_stream(*server, events[0]["mission_id"])
    assert frames[-1][2]["state"] == "VERIFIED"
    assert len(frames) == len(events) - len(DROPPED)


# --- the gap, and recovering from it --------------------------------------------


def test_live_stream_has_a_visible_gap(server, events) -> None:
    _, frames = read_stream(*server, events[0]["mission_id"])
    sequences = [sequence for sequence, _, _ in frames]
    for dropped in DROPPED:
        assert dropped not in sequences

    jumps = [b - a for a, b in itertools.pairwise(sequences) if b - a != 1]
    assert jumps, (
        "a client can only exercise reconnect-and-replay if it can see that it missed "
        "something"
    )


def test_replay_endpoint_recovers_the_dropped_window(server, events) -> None:
    host, port = server
    mission_id = events[0]["mission_id"]
    before_gap = min(DROPPED) - 1

    conn = http.client.HTTPConnection(host, port, timeout=10)
    conn.request(
        "GET",
        f"/api/v1/missions/{mission_id}/events/replay?since_sequence={before_gap}&limit=500",
    )
    response = conn.getresponse()
    assert response.status == 200
    page = json.loads(response.read())
    conn.close()

    recovered = [item["sequence"] for item in page["items"]]
    assert set(DROPPED).issubset(recovered), (
        "gap recovery that cannot return the missing events is not recovery"
    )
    assert recovered == sorted(recovered)
    assert page["items"][0]["sequence"] == before_gap + 1
    assert page["total"] == len(events) - before_gap


def test_replay_endpoint_rejects_a_bad_range(server, events) -> None:
    host, port = server
    conn = http.client.HTTPConnection(host, port, timeout=10)
    conn.request(
        "GET",
        f"/api/v1/missions/{events[0]['mission_id']}/events/replay?limit=9999",
    )
    response = conn.getresponse()
    assert response.status == 422
    body = json.loads(response.read())
    conn.close()
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_last_event_id_resumes_without_replaying_the_start(server, events) -> None:
    resume_after = 30
    _, frames = read_stream(*server, events[0]["mission_id"], last_event_id=str(resume_after))
    sequences = [sequence for sequence, _, _ in frames]
    assert sequences, "resuming produced no frames"
    assert min(sequences) > resume_after, (
        "a reconnecting client must not be sent events it already has"
    )
    assert max(sequences) == len(events)


def test_unknown_mission_is_a_404_envelope(server) -> None:
    host, port = server
    conn = http.client.HTTPConnection(host, port, timeout=10)
    conn.request("GET", "/api/v1/missions/11111111-2222-3333-4444-555555555555/events")
    response = conn.getresponse()
    assert response.status == 404
    body = json.loads(response.read())
    conn.close()
    assert body["error"]["code"] == "NOT_FOUND"
    assert "trace_id" in body


# --- the property that fails silently in production ------------------------------


def test_frames_arrive_incrementally_not_in_one_block(events) -> None:
    """Read the socket directly and prove the first frame lands long before the last.

    This is the local half of the nginx check. A buffered stream passes every other test
    in this file — the bytes all arrive, just at the end — so nothing else here would
    catch it.
    """
    sse_replay.ReplayHandler.events = events
    sse_replay.ReplayHandler.dropped = set()
    sse_replay.ReplayHandler.speed = 60.0  # ~1s of recorded time per real second
    sse_replay.ReplayHandler.max_gap = 0.25
    sse_replay.ReplayHandler.loop = False

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), sse_replay.ReplayHandler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    host, port = httpd.server_address[0], httpd.server_address[1]

    try:
        sock = socket.create_connection((host, port), timeout=20)
        sock.sendall(
            f"GET /api/v1/missions/{events[0]['mission_id']}/events HTTP/1.1\r\n"
            f"Host: {host}\r\nAccept: text/event-stream\r\n\r\n".encode()
        )

        started = time.monotonic()
        first_frame_at: float | None = None
        chunks: list[bytes] = []
        deadline = started + 15
        while time.monotonic() < deadline:
            sock.settimeout(max(0.1, deadline - time.monotonic()))
            try:
                chunk = sock.recv(65536)
            except TimeoutError:
                break
            if not chunk:
                break
            chunks.append(chunk)
            if first_frame_at is None and b"\ndata: " in b"".join(chunks):
                first_frame_at = time.monotonic() - started
            if b'"VERIFIED"' in chunk and b"end of fixture" in b"".join(chunks[-2:]):
                break
        sock.close()

        body = b"".join(chunks).decode(errors="replace")
        last_frame_at = time.monotonic() - started

        assert first_frame_at is not None, "no data frame ever arrived"
        assert first_frame_at < 1.0, (
            f"first frame took {first_frame_at:.2f}s — the stream is being buffered"
        )
        assert last_frame_at - first_frame_at > 0.3, (
            "every frame arrived at once; that is what a buffered stream looks like"
        )
        assert body.count("\ndata: ") > 10
    finally:
        httpd.shutdown()
        httpd.server_close()


# --- the §2.5 guard ---------------------------------------------------------------


def test_serving_on_a_non_loopback_address_is_refused() -> None:
    """The fallback ladder bans this fixture from a judge's screen. Making it reachable
    from another machine should take a deliberate flag, not a typo."""
    with pytest.raises(SystemExit) as excinfo:
        sse_replay.main(["--host", "0.0.0.0", "--port", "0"])
    message = str(excinfo.value)
    assert "refusing to bind" in message
    assert "10-fallback-ladder" in message


def test_check_mode_validates_without_serving() -> None:
    assert sse_replay.main(["--check"]) == 0


def test_a_fixture_with_a_gap_in_it_is_refused(tmp_path: Path, events) -> None:
    """The stored log is the server's record and must be gap-free. If someone bakes the
    gap into the file, the loader has to reject it — otherwise the fixture teaches every
    panel that `sequence` can skip."""
    broken = tmp_path / "broken.jsonl"
    kept = [event for event in events if event["sequence"] not in DROPPED]
    broken.write_text("\n".join(json.dumps(event) for event in kept), encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        sse_replay.load_events(broken)
    assert "gap-free" in str(excinfo.value)


# --- the probe has teeth ----------------------------------------------------------


def test_timing_probe_detects_a_buffered_stream(events) -> None:
    """Prove `tools/sse_timing_probe.py` can tell streaming from buffering.

    `verify-through-nginx.sh` uses that probe to assert the replay survives the proxy. A
    probe that returns PASS whatever the transport does would make that assertion
    worthless, so here it is pointed at a server that deliberately withholds every frame
    until the end — the exact failure the nginx check exists to catch — and required to
    report it.

    A note on why this is a stub and not another nginx run. On nginx 1.27, neither
    `proxy_buffering on` (even with buffers wider than the whole mission), nor
    `proxy_cache`, nor `gzip` reproduced the stall against this fixture: nginx relayed
    frames promptly in every configuration tried. The hazard the shipped config guards
    against is real and well documented, but it could not be induced on demand here, so
    the probe's sensitivity is established against a known-buffering server instead of
    against a hoped-for nginx misconfiguration.
    """
    import subprocess
    from http.server import BaseHTTPRequestHandler

    payload = [event for event in events]

    class BufferingHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: Any) -> None:
            pass

        def do_GET(self) -> None:
            body = "".join(
                f"id: {event['sequence']}\nevent: {event['type']}\n"
                f"data: {json.dumps(event, separators=(',', ':'))}\n\n"
                for event in payload
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.close_connection = True
            self.end_headers()
            # The whole point: hold everything, then emit it in one write at the end.
            time.sleep(3.0)
            self.wfile.write(body)
            self.wfile.flush()

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), BufferingHandler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    host, port = httpd.server_address[0], httpd.server_address[1]

    probe = Path(__file__).resolve().parents[1] / "tools" / "sse_timing_probe.py"
    url = f"http://{host}:{port}/api/v1/missions/{events[0]['mission_id']}/events"
    try:
        result = subprocess.run(
            [sys.executable, str(probe), url, "--expect", "buffered", "--timeout", "15"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    finally:
        httpd.shutdown()
        httpd.server_close()

    assert result.returncode == 0, (
        "the timing probe failed to notice a stream that arrived in one block:\n"
        f"{result.stdout}{result.stderr}"
    )
    assert "PASS (negative control)" in result.stdout


def test_timing_probe_passes_a_real_stream(server, events) -> None:
    """The other half: the same probe must not cry buffering at a healthy stream."""
    import subprocess

    sse_replay.ReplayHandler.speed = 40.0
    sse_replay.ReplayHandler.max_gap = 0.3
    host, port = server
    probe = Path(__file__).resolve().parents[1] / "tools" / "sse_timing_probe.py"
    url = f"http://{host}:{port}/api/v1/missions/{events[0]['mission_id']}/events"
    result = subprocess.run(
        [sys.executable, str(probe), url, "--expect", "stream", "--timeout", "15"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"{result.stdout}{result.stderr}"
    assert "PASS: frames arrived incrementally" in result.stdout
