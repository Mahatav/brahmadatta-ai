"""Measure whether an SSE endpoint streams or buffers. Stdlib only.

    python3 sse_timing_probe.py URL --expect stream
    python3 sse_timing_probe.py URL --expect buffered

A buffered stream is not a broken stream. Every byte arrives, the JSON parses, the frame
count is right — it all just lands at once, at the end. So the only thing that
distinguishes the two is *when* the bytes show up, and that is what this measures:

    time_to_first_frame   how long before the first `data:` line appears
    spread                first frame to last frame

Streaming looks like a small time-to-first-frame and a spread covering most of the run.
Buffered looks like a time-to-first-frame equal to the whole run and a spread near zero.

`--expect buffered` exists so the negative control in `verify-through-nginx.sh` can prove
this probe actually detects the failure it claims to detect. A check that passes whatever
nginx does is worth nothing.
"""

from __future__ import annotations

import argparse
import socket
import ssl
import sys
import time
from urllib.parse import urlparse


def probe(url: str, timeout: float) -> dict[str, float]:
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path + (f"?{parsed.query}" if parsed.query else "")

    started = time.monotonic()
    sock: socket.socket = socket.create_connection((host, port), timeout=timeout)
    if parsed.scheme == "https":
        context = ssl.create_default_context()
        # The dev stack uses a self-signed certificate; this probe measures timing, not
        # trust. It never sends credentials and never reads anything but the fixture.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        sock = context.wrap_socket(sock, server_hostname=host)

    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {parsed.netloc}\r\n"
        f"Accept: text/event-stream\r\n"
        f"Connection: close\r\n\r\n"
    )
    sock.sendall(request.encode())

    buffer = b""
    frames = 0
    first_frame: float | None = None
    last_frame = 0.0
    deadline = started + timeout

    while time.monotonic() < deadline:
        sock.settimeout(max(0.1, deadline - time.monotonic()))
        try:
            chunk = sock.recv(65536)
        except (TimeoutError, socket.timeout):
            break
        if not chunk:
            break
        now = time.monotonic() - started
        buffer += chunk
        new_frames = buffer.count(b"\ndata: ")
        if new_frames > frames:
            frames = new_frames
            if first_frame is None:
                first_frame = now
            last_frame = now
    sock.close()

    return {
        "frames": float(frames),
        "time_to_first_frame": -1.0 if first_frame is None else round(first_frame, 3),
        "last_frame": round(last_frame, 3),
        "spread": 0.0 if first_frame is None else round(last_frame - first_frame, 3),
        "total": round(time.monotonic() - started, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--expect", choices=["stream", "buffered"], default="stream")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--min-frames", type=int, default=10, help="Fewer than this means nothing streamed."
    )
    parser.add_argument(
        "--first-frame-budget",
        type=float,
        default=2.0,
        help="A streaming endpoint must produce its first frame inside this.",
    )
    args = parser.parse_args()

    result = probe(args.url, args.timeout)
    print(  # noqa: T201 - this is the tool's whole output
        f"frames={int(result['frames'])} "
        f"first={result['time_to_first_frame']}s "
        f"last={result['last_frame']}s "
        f"spread={result['spread']}s "
        f"total={result['total']}s"
    )

    if result["frames"] < args.min_frames:
        print(f"FAIL: only {int(result['frames'])} frames arrived")  # noqa: T201
        return 2

    streaming = (
        0 <= result["time_to_first_frame"] <= args.first_frame_budget
        and result["spread"] > 0.3
    )

    if args.expect == "stream":
        if streaming:
            print("PASS: frames arrived incrementally")  # noqa: T201
            return 0
        print(  # noqa: T201
            "FAIL: the stream is buffered — every frame arrived at once. "
            "Check proxy_buffering, proxy_cache and gzip on the SSE location."
        )
        return 1

    if not streaming:
        print("PASS (negative control): buffering detected, as expected")  # noqa: T201
        return 0
    print(  # noqa: T201
        "FAIL (negative control): frames streamed even with buffering on. "
        "This probe cannot detect the failure it exists to detect."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
