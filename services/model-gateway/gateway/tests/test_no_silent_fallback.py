"""Replay is an operator choice. It is never reached by failing.

Issue #82: *"Replay mode is an explicit operator choice, never a silent fallback on
timeout."* The fallback ladder §2.3 explains why that is worth defending rather than
working around — a system that quietly degrades to replay under load can present a recorded
response as live inference without anybody choosing to.

The assertions here are about a *negative*: that a code path does not exist. The spy store
is how a negative is tested — it fails if it is read at all, so "the transcript store was
not consulted" is checked rather than inferred from a passing exception.
"""

from __future__ import annotations

import inspect

import pytest

from gateway.errors import (
    GatewayConfigurationError,
    LiveBackendUnavailableError,
    LiveGenerationError,
    TranscriptNotFoundError,
)
from gateway.schemas import GenerationRequest
from gateway.service import ModelGateway, build_gateway
from gateway.settings import GatewayMode, GatewaySettings, from_environment
from gateway.tests.conftest import ExplodingLiveBackend, FakeLiveBackend, SpyingStore
from gateway.transcripts import TranscriptStore


@pytest.mark.parametrize(
    "failure",
    [
        TimeoutError("model did not respond in 120s"),
        MemoryError("llama_decode: out of memory"),
        ConnectionRefusedError("[Errno 111] Connection refused"),
    ],
    ids=["timeout", "oom", "unreachable"],
)
def test_a_live_failure_raises_and_never_reaches_for_a_transcript(
    live_settings: GatewaySettings,
    request_: GenerationRequest,
    recorded: str,
    failure: Exception,
) -> None:
    """The store is fully populated and answers this exact request. It is still not read."""
    spy = SpyingStore(live_settings.transcript_root)
    assert spy.paths() and spy.reads == ["paths"], "precondition: a matching transcript exists"
    spy.reads.clear()

    gateway = build_gateway(live_settings, live_backend=ExplodingLiveBackend(failure))
    with pytest.raises(type(failure)):
        gateway.generate(request_)

    assert spy.reads == [], (
        "live generation failed and something read the transcript store. A fallback that "
        "nobody chose is how a replayed response ends up presented as live inference."
    )


def test_the_absence_of_a_live_backend_is_its_own_error(
    live_settings: GatewaySettings, request_: GenerationRequest, recorded: str
) -> None:
    """ "No backend was configured" must not read as "the model tried and failed"."""
    with pytest.raises(LiveBackendUnavailableError) as caught:
        build_gateway(live_settings).generate(request_)
    assert "nothing was attempted" in str(caught.value)
    assert isinstance(caught.value, LiveGenerationError)


def test_build_gateway_binds_one_source_and_does_not_reconsider(
    live_settings: GatewaySettings, replay_settings: GatewaySettings
) -> None:
    """Structural: the mode selects a source once, and nothing re-reads it per request."""
    live = build_gateway(live_settings)
    replay = build_gateway(replay_settings)

    assert live.source.name == "live+recording"
    assert replay.source.name == "replay"

    body = inspect.getsource(ModelGateway.generate)
    assert "ReplaySource" not in body and "except" not in body, (
        "ModelGateway.generate must contain no exception handler and no reference to a "
        "second source. A `try live / except: replay` here is the silent fallback."
    )


def test_live_endpoint_boundary_is_asserted_on_every_generation(
    live_settings: GatewaySettings,
    request_: GenerationRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = GatewaySettings(
        mode=live_settings.mode,
        endpoint=live_settings.endpoint,
        transcript_root=live_settings.transcript_root,
        resolve_endpoint=True,
    ).validate()
    calls: list[str] = []

    def fake_boundary_check(setting_name: str, endpoint: str, *, service_names: object) -> list[str]:
        calls.append(f"{setting_name}:{endpoint}:{service_names}")
        return ["127.0.0.1"]

    monkeypatch.setattr("gateway.service.assert_resolves_inside_boundary", fake_boundary_check)

    gateway = build_gateway(settings, live_backend=FakeLiveBackend())
    gateway.generate(request_)
    gateway.generate(request_)

    assert calls == [
        "MODEL_ENDPOINT:http://127.0.0.1:8080/v1:frozenset()",
        "MODEL_ENDPOINT:http://127.0.0.1:8080/v1:frozenset()",
    ]


def test_replay_mode_must_be_asked_for_by_name() -> None:
    """An unset mode is an error, not a default. D-049 Part 1."""
    with pytest.raises(GatewayConfigurationError, match="has no default"):
        from_environment({})

    with pytest.raises(GatewayConfigurationError):
        from_environment({"MODEL_GATEWAY_MODE": "whatever"})

    assert from_environment({"MODEL_GATEWAY_MODE": "replay"}).mode is GatewayMode.REPLAY


def test_switching_to_replay_is_a_configuration_change_not_a_runtime_one(
    replay_settings: GatewaySettings,
) -> None:
    """`GatewaySettings` is frozen, so nothing can flip the mode mid-mission."""
    with pytest.raises(Exception):  # noqa: B017 - pydantic/dataclass both raise here
        replay_settings.mode = GatewayMode.LIVE  # type: ignore[misc]


def test_replay_with_no_transcript_fails_rather_than_generating(
    replay_settings: GatewaySettings, request_: GenerationRequest
) -> None:
    """The mirror of the rule: replay does not quietly become live either."""
    empty = TranscriptStore(replay_settings.transcript_root)
    assert empty.paths() == []

    with pytest.raises(TranscriptNotFoundError, match="does not fall back to live"):
        build_gateway(replay_settings).generate(request_)
