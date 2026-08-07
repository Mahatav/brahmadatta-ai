#!/usr/bin/env python3
"""Read an SSE stream and assert that the frames actually arrive incrementally.

The point of this client is timing, not content. A buffered proxy still delivers every
byte eventually; what it destroys is the *arrival schedule*. So the assertion is: at least
MIN_EVENTS frames must arrive, spread over at least MIN_SPREAD seconds, with the first one
arriving within FIRST_BYTE_DEADLINE seconds.

If nginx is buffering, the first frame does not appear until the upstream response ends —
which for a real mission event stream is never. The failure mode this catches is the one
described at the top of infrastructure/compose/nginx/includes/sse.conf.

Usage:
    sse-client.py URL [--expect-streaming | --expect-buffered]

--expect-buffered inverts the assertion and is used by smoke-sse.sh to demonstrate that
the test can actually fail, i.e. that a green result means something.
"""

from __future__ import annotations

import argparse
import ssl
import sys
import time
import urllib.request

MIN_EVENTS = 3
MIN_SPREAD = 0.6
FIRST_BYTE_DEADLINE = 3.0
READ_WINDOW = 6.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument(
        "--expect",
        choices=("streaming", "buffered"),
        default="streaming",
        help="streaming = frames must arrive incrementally (the correct config)",
    )
    args = ap.parse_args()

    # Dev TLS material is self-signed on purpose; this client is only ever pointed at
    # localhost by smoke-sse.sh. It never talks to anything outside the machine.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    started = time.monotonic()
    arrivals: list[tuple[float, str]] = []

    # S310: the URL comes from smoke-sse.sh and is always https://127.0.0.1:<port>. This
    # client is a test harness and never fetches anything it was not handed on the command
    # line by a script in this repository.
    req = urllib.request.Request(args.url, headers={"Accept": "text/event-stream"})  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=READ_WINDOW, context=ctx) as resp:  # noqa: S310
            print(f"  HTTP {resp.status}  content-type={resp.headers.get('Content-Type')}")
            deadline = started + READ_WINDOW
            while time.monotonic() < deadline and len(arrivals) < 8:
                line = resp.fp.readline()
                if not line:
                    break
                text = line.decode("utf-8", "replace").rstrip("\n")
                if text.startswith("data:"):
                    elapsed = time.monotonic() - started
                    arrivals.append((elapsed, text[:72]))
                    print(f"  +{elapsed:6.3f}s  {text[:72]}")
    except Exception as exc:  # any failure to read the stream is a test failure
        print(f"  transport error after {time.monotonic() - started:.3f}s: {exc!r}")

    spread = (arrivals[-1][0] - arrivals[0][0]) if len(arrivals) >= 2 else 0.0
    first = arrivals[0][0] if arrivals else float("inf")

    streamed = len(arrivals) >= MIN_EVENTS and spread >= MIN_SPREAD and first <= FIRST_BYTE_DEADLINE

    print(
        f"  frames={len(arrivals)} first={first:.3f}s spread={spread:.3f}s "
        f"-> {'STREAMING' if streamed else 'NOT STREAMING'}"
    )

    want_streaming = args.expect == "streaming"
    if streamed == want_streaming:
        print(f"  PASS (expected {args.expect})")
        return 0
    print(f"  FAIL (expected {args.expect})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
