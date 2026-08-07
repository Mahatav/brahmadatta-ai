#!/usr/bin/env python3
"""Minimal SSE upstream used only to test the nginx ingress.

This is NOT the control API. It exists so that the proxy's streaming behaviour can be
tested before Django exists, and so it can keep being tested afterwards without booting
the whole stack. infrastructure/scripts/smoke-sse.sh drives it.

It speaks raw HTTP/1.1 chunked rather than using http.server, because http.server's
BaseHTTPRequestHandler buffers in ways that would muddy the thing under test: we want any
observed stalling to be nginx's, not Python's.

It deliberately does NOT send `X-Accel-Buffering: no` by default. That header would let
nginx disable buffering on its own, which would mask a missing `proxy_buffering off` in
the committed config — the exact bug this test exists to catch. Set SSE_STUB_ACCEL=no to
turn it on when testing the belt-and-braces path.
"""

from __future__ import annotations

import json
import os
import socketserver
import sys
import threading
import time

PORT = int(os.environ.get("SSE_STUB_PORT", "8000"))
EVENTS = int(os.environ.get("SSE_STUB_EVENTS", "10"))
INTERVAL = float(os.environ.get("SSE_STUB_INTERVAL", "0.4"))
SEND_ACCEL_HEADER = os.environ.get("SSE_STUB_ACCEL", "") == "no"


def chunk(payload: bytes) -> bytes:
    return b"%x\r\n%s\r\n" % (len(payload), payload)


class Handler(socketserver.StreamRequestHandler):
    timeout = 30

    def handle(self) -> None:
        request_line = self.rfile.readline(65536).decode("latin-1").strip()
        while True:
            line = self.rfile.readline(65536)
            if line in (b"\r\n", b"\n", b""):
                break

        parts = request_line.split(" ")
        path = parts[1] if len(parts) > 1 else "/"

        if "/events" not in path:
            body = json.dumps({"ok": True, "path": path, "stub": "sse-stub"}).encode()
            self.wfile.write(
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/json\r\n"
                b"Content-Length: %d\r\n"
                b"X-Trace-Id: sse-stub\r\n"
                b"Connection: close\r\n\r\n" % len(body)
            )
            self.wfile.write(body)
            self.wfile.flush()
            return

        headers = [
            b"HTTP/1.1 200 OK",
            b"Content-Type: text/event-stream",
            b"Cache-Control: no-cache",
            b"Transfer-Encoding: chunked",
            b"X-Trace-Id: sse-stub",
            b"Connection: keep-alive",
        ]
        if SEND_ACCEL_HEADER:
            headers.append(b"X-Accel-Buffering: no")
        self.wfile.write(b"\r\n".join(headers) + b"\r\n\r\n")
        self.wfile.flush()

        try:
            for seq in range(1, EVENTS + 1):
                payload = json.dumps(
                    {
                        "mission_id": "00000000-0000-0000-0000-000000000000",
                        "sequence": seq,
                        "timestamp": time.time(),
                        "phase": "SMOKE",
                        "status": "RUNNING",
                        "severity": "INFO",
                        "message": f"smoke event {seq}",
                    }
                )
                frame = f"event: mission\ndata: {payload}\n\n".encode()
                self.wfile.write(chunk(frame))
                self.wfile.flush()
                time.sleep(INTERVAL)
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (TimeoutError, BrokenPipeError, ConnectionResetError):
            pass


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    disable_nagle_algorithm = True


def main() -> int:
    # S104: binding all interfaces is required — this stub is reached from the nginx
    # container over a docker network, and it only ever runs inside smoke-sse.sh, which
    # publishes no host port for it.
    with Server(("0.0.0.0", PORT), Handler) as srv:  # noqa: S104
        print(
            f"sse-stub listening on :{PORT} "
            f"(events={EVENTS} interval={INTERVAL}s accel_header={SEND_ACCEL_HEADER})",
            flush=True,
        )
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    sys.exit(main())
