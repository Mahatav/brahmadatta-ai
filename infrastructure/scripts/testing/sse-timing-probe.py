#!/usr/bin/env python3
"""Measure the ARRIVAL SCHEDULE of an SSE stream, over a pinned HTTP version.

Companion to sse-client.py, not a replacement. sse-client.py answers "does the
Command Center see events". This answers "when exactly did each byte hit the wire, and
over which transport", which is what #114 needed and what sse-client.py cannot express:

  - it pins HTTP/1.1 via ALPN. This is the whole point. The nginx SSE stall is
    HTTP/1.1-only — over h2, `proxy_buffering on` streams perfectly — and curl
    negotiates h2 by default over TLS. A probe that does not pin the version will report
    that a broken config is fine. Measured numbers in
    docs/06-operations/73-sse-buffering-measurements.md.
  - it reads from a raw TLS socket rather than urllib, so nothing between nginx and the
    assertion can add buffering of its own.
  - it can sit through an arbitrarily long idle gap, which is what testing
    proxy_read_timeout requires. urllib's socket timeout aborts on the first gap.
  - it reports WHEN the peer closed, so "nginx dropped the connection at 5.4s" is an
    observation rather than an inference.

Modes, all of which must be able to fail:

  --expect streaming   >= MIN_FRAMES frames, first within FIRST_DEADLINE, spread over
                       at least MIN_SPREAD seconds
  --expect stalled     the opposite: the frames did not arrive on schedule
  --expect survives-idle
                       the connection was still open after the idle gap and frames
                       resumed afterwards
  --expect dropped-by-idle
                       the peer closed the connection during the idle gap, no later than
                       --drop-before seconds

Usage:
    sse-timing-probe.py https://127.0.0.1:18443/api/... --expect streaming
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import ssl
import sys
import time
from urllib.parse import urlsplit

MIN_FRAMES = 3
MIN_SPREAD = 0.6
FIRST_DEADLINE = 3.0

DATA_LINE = re.compile(rb"(?:^|\n)data: ")


def read_stream(url: str, duration: float, recv_bytes: int) -> dict:
    parts = urlsplit(url)
    host = parts.hostname or "127.0.0.1"
    port = parts.port or (443 if parts.scheme == "https" else 80)
    path = parts.path + (f"?{parts.query}" if parts.query else "")

    # Dev TLS material is self-signed on purpose and this probe is only ever pointed at
    # 127.0.0.1 by smoke-sse.sh. It never talks to anything off the machine.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    # THE line that makes this probe meaningful. Do not remove it to "let it negotiate".
    ctx.set_alpn_protocols(["http/1.1"])

    arrivals: list[float] = []
    buf = b""
    total = 0
    error = None
    closed_at = None
    negotiated = None

    try:
        raw = socket.create_connection((host, port), timeout=5)
        raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock = ctx.wrap_socket(raw, server_hostname="localhost")
        negotiated = sock.selected_alpn_protocol()
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "Accept: text/event-stream\r\n"
            "Accept-Encoding: gzip\r\n"
            "Connection: keep-alive\r\n\r\n"
        ).encode()
        started = time.monotonic()
        sock.sendall(request)
        sock.settimeout(0.25)
        deadline = started + duration
        while time.monotonic() < deadline:
            try:
                data = sock.recv(recv_bytes)
            except (socket.timeout, ssl.SSLWantReadError):
                # An idle gap is the normal state of an SSE stream between mission
                # phases. Keep waiting until the overall budget is spent.
                #
                # socket.timeout is NOT an alias of TimeoutError before Python 3.10.
                # Catching TimeoutError alone turns every idle gap into an abort and
                # makes a healthy stream look stalled — that bug produced a false
                # positive during the #114 investigation before it was caught.
                continue
            except OSError as exc:
                error = repr(exc)
                closed_at = time.monotonic() - started
                break
            if not data:
                closed_at = time.monotonic() - started
                break
            now = time.monotonic() - started
            total += len(data)
            buf += data
            for _ in DATA_LINE.findall(data):
                arrivals.append(now)
        sock.close()
    except Exception as exc:  # noqa: BLE001 — any failure to read the stream is a result
        error = repr(exc)

    head = buf.split(b"\r\n\r\n", 1)[0].decode("latin-1", "replace") if buf else ""
    status = head.splitlines()[0] if head else ""
    encoding = ""
    for line in head.splitlines()[1:]:
        if line.lower().startswith("content-encoding:"):
            encoding = line.split(":", 1)[1].strip()

    first = arrivals[0] if arrivals else None
    spread = (arrivals[-1] - arrivals[0]) if len(arrivals) >= 2 else 0.0
    return {
        "alpn": negotiated,
        "status": status,
        "content_encoding": encoding,
        "frames": len(arrivals),
        "arrivals": [round(a, 3) for a in arrivals],
        "first_frame_s": round(first, 3) if first is not None else None,
        "spread_s": round(spread, 3),
        "bytes": total,
        "closed_at_s": round(closed_at, 3) if closed_at is not None else None,
        "error": error,
        "streaming": bool(
            len(arrivals) >= MIN_FRAMES
            and spread >= MIN_SPREAD
            and (first if first is not None else 1e9) <= FIRST_DEADLINE
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument(
        "--expect",
        choices=("streaming", "stalled", "survives-idle", "dropped-by-idle"),
        default="streaming",
    )
    ap.add_argument("--duration", type=float, default=9.0)
    ap.add_argument("--recv-bytes", type=int, default=65536)
    ap.add_argument(
        "--idle-starts-at",
        type=float,
        default=None,
        help="seconds into the stream at which the upstream goes silent; required by the "
        "idle modes so 'survived the gap' can be asserted rather than assumed",
    )
    ap.add_argument(
        "--drop-before",
        type=float,
        default=None,
        help="dropped-by-idle fails if the peer had not closed by this many seconds",
    )
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    r = read_stream(args.url, args.duration, args.recv_bytes)

    if args.json:
        print(json.dumps(r, indent=2))
    else:
        print(f"  alpn={r['alpn']}  {r['status'] or '(no status line)'}")
        for a in r["arrivals"][:6]:
            print(f"  +{a:7.3f}s  data:")
        if len(r["arrivals"]) > 6:
            print(f"  ... {len(r['arrivals']) - 6} more, last at +{r['arrivals'][-1]:.3f}s")
        print(
            f"  frames={r['frames']} first={r['first_frame_s']} spread={r['spread_s']}s "
            f"bytes={r['bytes']} encoding={r['content_encoding'] or '-'} "
            f"closed_at={r['closed_at_s']} error={r['error']}"
        )

    if args.expect == "streaming":
        ok = r["streaming"]
        why = (
            f"expected incremental delivery: >={MIN_FRAMES} frames, first within "
            f"{FIRST_DEADLINE}s, spread >={MIN_SPREAD}s"
        )
    elif args.expect == "stalled":
        ok = not r["streaming"]
        why = "expected the stream NOT to arrive on schedule"
    elif args.expect == "survives-idle":
        if args.idle_starts_at is None:
            print("  --idle-starts-at is required for --expect survives-idle")
            return 2
        # Frames must have arrived on BOTH sides of the gap: anything else means the
        # connection did not actually survive it.
        after = [a for a in r["arrivals"] if a > args.idle_starts_at]
        before = [a for a in r["arrivals"] if a <= args.idle_starts_at]
        ok = bool(before and after and r["error"] is None)
        why = (
            f"expected frames before AND after the idle gap at {args.idle_starts_at}s "
            f"(saw {len(before)} before, {len(after)} after)"
        )
    else:  # dropped-by-idle
        if args.drop_before is None:
            print("  --drop-before is required for --expect dropped-by-idle")
            return 2
        ok = r["closed_at_s"] is not None and r["closed_at_s"] <= args.drop_before
        why = (
            f"expected the peer to close the connection within {args.drop_before}s "
            f"(closed_at={r['closed_at_s']})"
        )

    print(f"  {'PASS' if ok else 'FAIL'} ({args.expect}) — {why}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
