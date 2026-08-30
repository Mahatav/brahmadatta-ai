"""`gateway.client`'s transport-error wrapping (found live, #57 finale-rehearsal wiring).

`LiveGenerationError`'s own docstring promises "timeout, OOM, unreachable backend, bad
output" all land as `GatewayError`s. Before this fix, a `urlopen` timeout or connection
failure raised a bare `TimeoutError`/`URLError`/`OSError` instead — which is not a
`GatewayError` at all, so `orchestrator/patch_generate_executor.py::
_generate_with_ladder`'s `except GatewayError` never caught it, and the degradation
ladder's "one transport retry" never ran. These tests are the chokepoint-level proof
that every transport failure `urlopen` can raise now comes out as a `LiveGenerationError`
carrying enough detail to explain what happened, so a caller one layer up can retry it.

`test_post_json_wraps_a_truncated_real_response` (#237) is deliberately not mocked.
`http.client.IncompleteRead` is raised from deep inside `http.client`'s own
`Content-Length` bookkeeping when the socket closes early, and mocking `urlopen` itself
(as every other test in this file does) cannot reach that code path — it would only
prove this test wrapped whatever exception we told it to raise, which is circular. This
test stands up a real TCP server that sends a `Content-Length` header promising more
bytes than it delivers, then closes the connection, so `http.client` raises
`IncompleteRead` for real and the chokepoint has to catch the real thing.
"""

from __future__ import annotations

import io
import json
import socket
import threading
from contextlib import contextmanager
from typing import Any
from urllib.error import HTTPError, URLError

import pytest

from gateway.client import get_json, iter_response_lines, post_json
from gateway.errors import LiveGenerationError


def _raise(exc: Exception):
    def fake_urlopen(request, timeout):  # noqa: ANN001 - matches urlopen's call shape
        raise exc

    return fake_urlopen


def _http_error(status: int, body: dict[str, Any] | str, *, reason: str = "Internal Server Error") -> HTTPError:
    """A real `HTTPError`, `.read()`-able exactly like the one `urlopen` raises for a
    real non-2xx response — not a bare mock, so `_http_error()`/`.read()` in
    `gateway.client` exercises the real `HTTPError` object shape (#298)."""
    payload = json.dumps(body).encode("utf-8") if isinstance(body, dict) else body.encode("utf-8")
    return HTTPError("http://127.0.0.1:11434/api/chat", status, reason, None, io.BytesIO(payload))


def test_post_json_wraps_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gateway.client.urlopen", _raise(TimeoutError("timed out")))

    with pytest.raises(LiveGenerationError, match="did not respond"):
        post_json("http://127.0.0.1:11434/api/chat", {"model": "x"}, 5.0)


def test_post_json_wraps_connection_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "gateway.client.urlopen",
        _raise(ConnectionRefusedError("[Errno 111] Connection refused")),
    )

    with pytest.raises(LiveGenerationError, match="did not respond"):
        post_json("http://127.0.0.1:11434/api/chat", {"model": "x"}, 5.0)


def test_post_json_wraps_url_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gateway.client.urlopen", _raise(URLError("name resolution failed")))

    with pytest.raises(LiveGenerationError, match="did not respond"):
        post_json("http://model-host:11434/api/chat", {"model": "x"}, 5.0)


def test_get_json_wraps_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gateway.client.urlopen", _raise(TimeoutError("timed out")))

    with pytest.raises(LiveGenerationError, match="did not respond"):
        get_json("http://127.0.0.1:11434/api/tags", 5.0)


def test_iter_response_lines_wraps_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gateway.client.urlopen", _raise(TimeoutError("timed out")))

    with pytest.raises(LiveGenerationError, match="did not respond"):
        list(iter_response_lines("http://127.0.0.1:11434/api/chat", {"model": "x"}, 5.0))


def test_transport_error_detail_names_the_cause(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gateway.client.urlopen", _raise(TimeoutError("timed out")))

    with pytest.raises(LiveGenerationError) as excinfo:
        post_json("http://127.0.0.1:11434/api/chat", {"model": "x"}, 5.0)

    assert excinfo.value.details["cause"] == "TimeoutError"
    assert excinfo.value.details["timeout_sec"] == 5.0


def test_json_decode_error_is_unaffected_by_the_transport_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pre-existing "non-JSON response" path must still be its own distinct
    message, not swallowed into the generic transport-error wording above."""

    class _NotJSONResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b"not json"

    monkeypatch.setattr(
        "gateway.client.urlopen", lambda request, timeout: _NotJSONResponse()
    )

    with pytest.raises(LiveGenerationError, match="non-JSON response"):
        post_json("http://127.0.0.1:11434/api/chat", {"model": "x"}, 5.0)


def test_post_json_surfaces_the_ollama_error_body_on_http_500(monkeypatch: pytest.MonkeyPatch) -> None:
    """#298: the real, live-observed shape — Ollama answers with a real HTTP 500 and a
    JSON body naming the actual reason (a memory-capacity refusal, here). Before this
    fix `urlopen`'s `HTTPError` was already being caught (it is a `URLError`
    subclass), but the body was never read, so this collapsed to the generic
    "did not respond: HTTP Error 500: Internal Server Error" wording and the
    specific, actionable reason was discarded."""
    monkeypatch.setattr(
        "gateway.client.urlopen",
        _raise(
            _http_error(
                500,
                {"error": "model requires more system memory (8.4 GiB) than is available (7.7 GiB)"},
            )
        ),
    )

    with pytest.raises(LiveGenerationError, match="requires more system memory") as excinfo:
        post_json("http://127.0.0.1:11434/api/chat", {"model": "x"}, 5.0)

    assert excinfo.value.details["http_status"] == 500
    assert excinfo.value.details["cause"] == "HTTPError"
    assert "8.4 GiB" in excinfo.value.details["response_body"]


def test_post_json_http_error_with_non_json_body_falls_back_to_raw_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Not every backend behind this chokepoint is Ollama, and not every non-2xx body
    is JSON. A plain-text error body must still reach the caller rather than being
    reduced to the bare status line."""
    monkeypatch.setattr(
        "gateway.client.urlopen",
        _raise(_http_error(502, "upstream connect error", reason="Bad Gateway")),
    )

    with pytest.raises(LiveGenerationError, match="upstream connect error"):
        post_json("http://127.0.0.1:11434/api/chat", {"model": "x"}, 5.0)


def test_post_json_http_error_with_empty_body_falls_back_to_http_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No body at all must not blow up the error-formatting path itself — the HTTP
    reason phrase is the fallback."""
    monkeypatch.setattr(
        "gateway.client.urlopen",
        _raise(_http_error(500, "", reason="Internal Server Error")),
    )

    with pytest.raises(LiveGenerationError, match="Internal Server Error"):
        post_json("http://127.0.0.1:11434/api/chat", {"model": "x"}, 5.0)


def _drain_full_request(conn: socket.socket) -> None:
    """Read exactly the client's request off `conn`, headers and body both.

    A single `recv(65536)` is not enough: the client can write headers and body as
    separate TCP segments, and a `recv` call racing that second write only returns the
    first one. Any bytes the client already sent but this server hasn't read yet are
    left sitting in the kernel's receive queue -- and BSD sockets answer a `close()`
    against a socket with unread queued data by sending an abortive RST instead of a
    graceful FIN, which is exactly the `ConnectionResetError` (not the intended
    `IncompleteRead`) this helper exists to prevent on the client. Parsing
    `Content-Length` and reading precisely that many body bytes, rather than guessing
    at a buffer size, is what actually guarantees nothing is left unread.
    """
    buffer = b""
    while b"\r\n\r\n" not in buffer:
        chunk = conn.recv(65536)
        if not chunk:
            return
        buffer += chunk
    header_block, _, body_so_far = buffer.partition(b"\r\n\r\n")
    content_length = 0
    for line in header_block.split(b"\r\n"):
        name, _, value = line.partition(b":")
        if name.strip().lower() == b"content-length":
            content_length = int(value.strip())
            break
    remaining = content_length - len(body_so_far)
    while remaining > 0:
        chunk = conn.recv(min(65536, remaining))
        if not chunk:
            return
        remaining -= len(chunk)


@contextmanager
def _truncated_content_length_server():
    """A real TCP server that promises more body bytes than it sends, then closes.

    Sends a well-formed HTTP status line and headers declaring `Content-Length: 100`,
    writes far fewer bytes than that, then does a clean FIN close — the same shape QA
    reproduced against a real Ollama backend that dies mid-response (OOM-killed or
    force-closed). This is what makes `http.client`'s reader raise `IncompleteRead`
    instead of any of the three exception types #236 already handled: the connection
    itself succeeds, the response headers parse fine, only the body is short.
    """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    host, port = server.getsockname()

    def _serve() -> None:
        server.settimeout(5.0)
        try:
            conn, _ = server.accept()
        except OSError:
            return
        try:
            conn.settimeout(5.0)
            _drain_full_request(conn)
            response = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Length: 100\r\n"
                b"Content-Type: application/json\r\n"
                b"\r\n"
                b'{"partial": "body"'  # far short of the promised 100 bytes
            )
            conn.sendall(response)
            # Closing here still needs care even with the request fully drained above:
            # BSD sockets send an *abortive* RST instead of a graceful FIN if `close()`
            # runs while the socket has unread received data queued, or races the
            # client's own read of the bytes just sent -- confirmed flaky (~40% of
            # runs) locally without both of the following. `shutdown(SHUT_WR)` sends a
            # clean FIN as soon as the send buffer flushes, and the blocking `recv`
            # waits for the client to finish reading and close its own end (returns
            # b'' on a clean peer close) before this socket is closed for real.
            conn.shutdown(socket.SHUT_WR)
            try:
                conn.recv(1)
            except OSError:
                pass
        finally:
            conn.close()

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    try:
        yield f"http://{host}:{port}/api/chat"
    finally:
        thread.join(timeout=5.0)
        server.close()


def test_post_json_wraps_a_truncated_real_response() -> None:
    """#237: a real short-body response must raise `LiveGenerationError`, not a bare
    `http.client.IncompleteRead` — the same crash shape #236 fixed for the other three
    transport-exception types, via a different real-world trigger."""
    with _truncated_content_length_server() as url:
        with pytest.raises(LiveGenerationError, match="did not respond") as excinfo:
            post_json(url, {"model": "x"}, 5.0)

    assert excinfo.value.details["cause"] == "IncompleteRead"
