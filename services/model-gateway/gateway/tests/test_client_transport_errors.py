"""`gateway.client`'s transport-error wrapping (found live, #57 finale-rehearsal wiring).

`LiveGenerationError`'s own docstring promises "timeout, OOM, unreachable backend, bad
output" all land as `GatewayError`s. Before this fix, a `urlopen` timeout or connection
failure raised a bare `TimeoutError`/`URLError`/`OSError` instead — which is not a
`GatewayError` at all, so `orchestrator/patch_generate_executor.py::
_generate_with_ladder`'s `except GatewayError` never caught it, and the degradation
ladder's "one transport retry" never ran. These tests are the chokepoint-level proof
that every transport failure `urlopen` can raise now comes out as a `LiveGenerationError`
carrying enough detail to explain what happened, so a caller one layer up can retry it.
"""

from __future__ import annotations

from urllib.error import URLError

import pytest

from gateway.client import get_json, iter_response_lines, post_json
from gateway.errors import LiveGenerationError


def _raise(exc: Exception):
    def fake_urlopen(request, timeout):  # noqa: ANN001 - matches urlopen's call shape
        raise exc

    return fake_urlopen


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
