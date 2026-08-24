"""Issue #82: replay serves from a transcript, through the same path as live generation.

The acceptance criteria this module covers, in the issue's order:

- serves from a recorded transcript through the **same** code path and schema — the two
  `test_replay_and_live_produce_...` tests
- transcripts stored by SHA-256 with capture timestamp, model artifact hash, prompt version
  and schema version — `test_transcript_records_everything_the_issue_names`
- the replay provenance triple travels together — `test_replayed_provenance_carries_...`

The honesty criteria are in `test_provenance_labelling.py`; "never a silent fallback" is in
`test_no_silent_fallback.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from gateway.backends import LiveSource, RecordingSource, ReplaySource
from gateway.errors import TranscriptError, TranscriptNotFoundError
from gateway.provenance import ResponseSource
from gateway.schemas import RESPONSE_SCHEMA_VERSION, GenerationRequest, PatchCandidate
from gateway.service import ModelGateway, build_gateway
from gateway.settings import GatewayMode, GatewaySettings
from gateway.tests.conftest import FAKE_ARTIFACT_SHA, FakeLiveBackend
from gateway.transcripts import CaptureKind, Transcript, TranscriptStore, capture


def test_replay_serves_the_recorded_candidate(
    replay_settings: GatewaySettings, request_: GenerationRequest, recorded: str
) -> None:
    gateway = build_gateway(replay_settings)
    response = gateway.generate(request_)

    assert response.candidate.diff == FakeLiveBackend().candidate.diff
    assert response.provenance.source is ResponseSource.RECORDED_TRANSCRIPT
    assert response.provenance.transcript_sha256 == recorded


def test_replay_and_live_produce_the_same_response_type_and_schema(
    store: TranscriptStore,
    replay_settings: GatewaySettings,
    live_settings: GatewaySettings,
    request_: GenerationRequest,
    recorded: str,
) -> None:
    """The "same code path and schema" criterion, asserted on the objects themselves.

    Both responses are `GatewayResponse`, both carry a validated `PatchCandidate`, and the
    two candidates are field-for-field identical — because the transcript recorded the one
    the live backend produced. The *only* difference between the two objects is the
    provenance, which is the entire design intent.
    """
    replayed = build_gateway(replay_settings).generate(request_)
    live = build_gateway(live_settings, live_backend=FakeLiveBackend()).generate(request_)

    assert type(replayed) is type(live)
    assert type(replayed.candidate) is type(live.candidate)
    assert replayed.candidate.model_dump() == live.candidate.model_dump()

    differing = {
        field
        for field in replayed.provenance.model_dump()
        if getattr(replayed.provenance, field) != getattr(live.provenance, field)
    }
    assert differing == {
        "source",
        "generated_at",
        "replayed_from_transcript",
        "captured_at",
        "transcript_sha256",
    }, (
        "replay and live must differ only in where the response came from. Any other "
        f"difference means the two paths have drifted: {sorted(differing)}"
    )


def test_replay_goes_through_the_same_validation(
    store: TranscriptStore, replay_settings: GatewaySettings, request_: GenerationRequest
) -> None:
    """A transcript is not trusted because it is on disk.

    Written straight to the file so the store's own writer cannot launder it: the response
    inside carries an empty diff, which `PatchCandidate` forbids. Replay must reject it for
    the same reason live generation would.
    """
    store.root.mkdir(parents=True, exist_ok=True)
    (store.root / ("c" * 64 + ".json")).write_text(
        '{"envelope_version": "transcript/1", "capture_kind": "LIVE_GENERATION", '
        '"captured_at": "2026-08-06T21:45:00Z", "request_fingerprint": "' + "a" * 64 + '", '
        '"prompt_sha256": "' + "a" * 64 + '", "prompt_version": "patch-prompt/3", '
        '"response_schema_version": "patch-candidate/1", "model_name": "x", '
        '"model_revision": "", "model_artifact_sha256": "' + "b" * 64 + '", '
        '"served_from": "", "response": {"diff": "", "rationale": "", '
        '"touched_files": [], "confidence": null}, "wall_time_ms": 0, '
        '"output_tokens": null, "note": ""}',
        encoding="utf-8",
    )
    with pytest.raises(TranscriptError, match="not a valid transcript"):
        build_gateway(replay_settings).generate(request_)


def test_a_malformed_transcript_error_never_carries_a_raw_value_or_a_secret_shaped_key(
    store: TranscriptStore, replay_settings: GatewaySettings, request_: GenerationRequest
) -> None:
    """#258: `TranscriptStore._read`'s `ValidationError` branch used to embed
    `str(exc)` verbatim in the raised `TranscriptError` message — which carries every
    failing field's actual value (pydantic's own `input_value=...` rendering) and,
    for a forbidden-extra-field rejection, the extra field's own key name. That
    message reaches `transcripts_cli.py`'s stdout (an operator-facing dev tool).

    Written straight to the file, same as `test_replay_goes_through_the_same_
    validation` above, so the store's own writer cannot launder it: a secret-shaped
    `confidence` value (wrong type — triggers a real `ValidationError` whose `input`
    is that value) and a forbidden extra field whose *key name* is secret-shaped.
    """
    secret_value = "sk-live-SUPER-SECRET-should-never-reach-an-exception-message-abc123"
    secret_key = "sk-live-SOME-SECRET-999"

    store.root.mkdir(parents=True, exist_ok=True)
    (store.root / ("c" * 64 + ".json")).write_text(
        '{"envelope_version": "transcript/1", "capture_kind": "LIVE_GENERATION", '
        '"captured_at": "2026-08-06T21:45:00Z", "request_fingerprint": "' + "a" * 64 + '", '
        '"prompt_sha256": "' + "a" * 64 + '", "prompt_version": "patch-prompt/3", '
        '"response_schema_version": "patch-candidate/1", "model_name": "x", '
        '"model_revision": "", "model_artifact_sha256": "' + "b" * 64 + '", '
        '"served_from": "", "response": {"diff": "ok", "rationale": "", '
        '"touched_files": [], "confidence": "' + secret_value + '", '
        '"' + secret_key + '": "y"}, "wall_time_ms": 0, '
        '"output_tokens": null, "note": ""}',
        encoding="utf-8",
    )
    with pytest.raises(TranscriptError) as excinfo:
        build_gateway(replay_settings).generate(request_)

    message = str(excinfo.value)
    assert secret_value not in message
    assert secret_key not in message

    # still diagnostically useful: which field, which kind of mismatch.
    assert "confidence" in message
    assert "<redacted secret-shaped segment>" in message


# --------------------------------------------------------------------------------------
# Storage: everything issue #82 names, by name
# --------------------------------------------------------------------------------------


def test_transcript_records_everything_the_issue_names(
    store: TranscriptStore, recorded: str, recorded_at: datetime
) -> None:
    transcript = store.load(recorded)

    assert (store.root / f"{recorded}.json").is_file(), "stored by SHA-256, as the filename"
    assert transcript.captured_at == recorded_at, "capture timestamp"
    assert transcript.model_artifact_sha256 == FAKE_ARTIFACT_SHA, "model artifact hash"
    assert transcript.prompt_version == "patch-prompt/3", "prompt version"
    assert transcript.response_schema_version == RESPONSE_SCHEMA_VERSION, "schema version"


def test_a_transcript_that_does_not_hash_to_its_own_name_is_refused(
    store: TranscriptStore, recorded: str
) -> None:
    path = store.root / f"{recorded}.json"
    original = path.read_text(encoding="utf-8")
    tampered = original.replace("Off-by-one", "A different rationale entirely")
    assert tampered != original, "precondition: the edit actually changed the file"
    path.write_text(tampered, encoding="utf-8")

    with pytest.raises(TranscriptError, match="does not hash to its own name"):
        store.load(recorded)


def test_capture_is_idempotent(
    store: TranscriptStore, request_: GenerationRequest, recorded: str, recorded_at: datetime
) -> None:
    again = store.save(
        capture(
            request_,
            FakeLiveBackend().candidate,
            model_name="fake-code-model",
            model_revision="test",
            model_artifact_sha256=FAKE_ARTIFACT_SHA,
            served_from="http://127.0.0.1:8080/v1",
            captured_at=recorded_at,
            wall_time_ms=4200,
            output_tokens=128,
            note="D5 rehearsal, attempt 3 of 10",
        )
    )
    assert again == recorded
    assert len(store.paths()) == 1


def test_a_naive_capture_timestamp_is_normalised_to_utc(
    store: TranscriptStore, request_: GenerationRequest
) -> None:
    """A date that renders to a judge must not depend on the capture machine's locale."""
    digest = store.save(
        capture(
            request_,
            FakeLiveBackend().candidate,
            model_name="m",
            model_artifact_sha256=FAKE_ARTIFACT_SHA,
            captured_at=datetime(2026, 8, 6, 21, 45),
        )
    )
    loaded = store.load(digest).captured_at
    assert loaded.utcoffset() == UTC.utcoffset(None)
    assert loaded == datetime(2026, 8, 6, 21, 45, tzinfo=UTC)


# --------------------------------------------------------------------------------------
# Lookup
# --------------------------------------------------------------------------------------


def test_a_different_prompt_does_not_match_a_recorded_transcript(
    replay_settings: GatewaySettings, recorded: str
) -> None:
    other = GenerationRequest(
        mission_id="m-0001",
        prompt="Something else entirely.",
        prompt_version="patch-prompt/3",
    )
    with pytest.raises(TranscriptNotFoundError):
        build_gateway(replay_settings).generate(other)


def test_a_transcript_is_findable_from_a_mission_that_did_not_exist_when_it_was_captured(
    replay_settings: GatewaySettings, request_: GenerationRequest, recorded: str
) -> None:
    """The fingerprint excludes `mission_id` on purpose — D5 captures, D7 replays."""
    later = request_.model_copy(update={"mission_id": "m-9999"})
    assert build_gateway(replay_settings).generate(later).provenance.transcript_sha256 == recorded


def test_a_schema_version_mismatch_is_refused_rather_than_decoded(
    store: TranscriptStore, replay_settings: GatewaySettings, request_: GenerationRequest
) -> None:
    """Rung 3's third trigger in the fallback ladder, as a distinguishable error."""
    store.save(
        capture(
            request_,
            FakeLiveBackend().candidate,
            model_name="m",
            model_artifact_sha256=FAKE_ARTIFACT_SHA,
            captured_at=datetime(2026, 8, 6, tzinfo=UTC),
        ).model_copy(update={"response_schema_version": "patch-candidate/0"})
    )
    with pytest.raises(TranscriptError, match="response schema"):
        build_gateway(replay_settings).generate(request_)


def test_two_transcripts_for_one_request_are_refused_rather_than_picked_between(
    store: TranscriptStore, replay_settings: GatewaySettings, request_: GenerationRequest
) -> None:
    for confidence in (0.4, 0.9):
        store.save(
            capture(
                request_,
                PatchCandidate(diff="--- a\n+++ b\n", confidence=confidence),
                model_name="m",
                model_artifact_sha256=FAKE_ARTIFACT_SHA,
                captured_at=datetime(2026, 8, 6, tzinfo=UTC),
            )
        )
    with pytest.raises(TranscriptError, match="Ambiguous replay is refused"):
        build_gateway(replay_settings).generate(request_)


# --------------------------------------------------------------------------------------
# A hand-written transcript is not a recording
# --------------------------------------------------------------------------------------


def test_a_synthetic_fixture_cannot_be_served_as_model_output(
    store: TranscriptStore, replay_settings: GatewaySettings, request_: GenerationRequest
) -> None:
    """#82: "a transcript nobody recorded is not a fallback", as a check."""
    store.save(
        capture(
            request_,
            FakeLiveBackend().candidate,
            model_name="m",
            model_artifact_sha256=FAKE_ARTIFACT_SHA,
            captured_at=datetime(2026, 8, 6, tzinfo=UTC),
            capture_kind=CaptureKind.SYNTHETIC_FIXTURE,
        )
    )
    with pytest.raises(TranscriptError, match="SYNTHETIC_FIXTURE"):
        build_gateway(replay_settings).generate(request_)


def test_synthetic_fixtures_load_only_when_explicitly_allowed(
    store: TranscriptStore, request_: GenerationRequest, tmp_path: Path
) -> None:
    digest = store.save(
        capture(
            request_,
            FakeLiveBackend().candidate,
            model_name="m",
            model_artifact_sha256=FAKE_ARTIFACT_SHA,
            captured_at=datetime(2026, 8, 6, tzinfo=UTC),
            capture_kind=CaptureKind.SYNTHETIC_FIXTURE,
        )
    )
    permissive = TranscriptStore(store.root, allow_synthetic=True)
    assert permissive.load(digest).capture_kind is CaptureKind.SYNTHETIC_FIXTURE


# --------------------------------------------------------------------------------------
# Capture happens on the live path, so there is something to replay later
# --------------------------------------------------------------------------------------


def test_live_generation_records_a_transcript(
    store: TranscriptStore, live_settings: GatewaySettings, request_: GenerationRequest
) -> None:
    """#82's last criterion: capture on D5/D6 from real runs, without a separate step."""
    assert store.paths() == []
    gateway = build_gateway(live_settings, live_backend=FakeLiveBackend())
    live = gateway.generate(request_)

    assert len(store.paths()) == 1
    transcript = next(iter(store))
    assert transcript.capture_kind is CaptureKind.LIVE_GENERATION
    assert transcript.response.diff == live.candidate.diff
    assert transcript.model_artifact_sha256 == FAKE_ARTIFACT_SHA

    # ...and the recorded transcript is immediately replayable, which is the property that
    # makes D5 capture useful on D7 rather than a file nobody tried to read.
    replayed = ModelGateway(
        GatewaySettings(mode=GatewayMode.REPLAY, transcript_root=store.root).validate(),
        ReplaySource(store),
    ).generate(request_)
    assert replayed.candidate.model_dump() == live.candidate.model_dump()


def test_a_capture_failure_does_not_lose_the_live_response(
    store: TranscriptStore, request_: GenerationRequest
) -> None:
    """The response was real. Losing it because the disk is full would be the wrong trade."""
    seen: list[Exception] = []

    class Broken(TranscriptStore):
        def save(self, transcript: Transcript) -> str:
            raise OSError("read-only file system")

    source = RecordingSource(
        LiveSource(FakeLiveBackend()),
        Broken(store.root),
        on_capture_error=seen.append,
    )
    result = source.produce(request_)

    assert result.candidate.diff
    assert len(seen) == 1, "the failure is reported, never silent"
