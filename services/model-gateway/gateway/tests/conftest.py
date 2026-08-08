"""Fixtures shared by the replay tests.

`FakeLiveBackend` is a stand-in for a served model and is the only thing in this package
that produces a `PatchCandidate` without reading a file. It is emphatically **not** a
model: no model has been served in this repository, and every test that uses this fixture
is testing the gateway's plumbing, not a model's output. Issues #35/#36 provide the real
one.

The diff it returns is the real bounds fix from `demo/repositories/pktcfg` so that a replay
run produces something a verification gate could plausibly be pointed at, rather than a
placeholder that would have to be swapped before anything downstream is exercised.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from gateway.schemas import GenerationRequest, PatchCandidate
from gateway.settings import GatewayMode, GatewaySettings
from gateway.transcripts import CaptureKind, Transcript, TranscriptStore, capture

FAKE_ARTIFACT_SHA = "b" * 64

SAMPLE_DIFF = """--- a/src/parse.c
+++ b/src/parse.c
@@ -118,7 +118,7 @@
-    while (cursor < end) {
+    while (cursor + 1 < end) {
"""


class FakeLiveBackend:
    """A scripted stand-in for a served model. Not a model."""

    model_name = "fake-code-model"
    model_revision = "test"
    model_artifact_sha256 = FAKE_ARTIFACT_SHA
    served_from = "http://127.0.0.1:8080/v1"

    def __init__(self, candidate: PatchCandidate | None = None) -> None:
        self.candidate = candidate or PatchCandidate(
            diff=SAMPLE_DIFF,
            rationale="Off-by-one on the terminating byte.",
            touched_files=("src/parse.c",),
            confidence=0.61,
        )
        self.calls = 0

    def generate(self, request: GenerationRequest) -> tuple[PatchCandidate, int, int | None]:
        self.calls += 1
        return self.candidate, 4200, 128


class ExplodingLiveBackend:
    """A served model that times out. Used to prove replay is not a silent fallback."""

    model_name = "fake-code-model"
    model_revision = "test"
    model_artifact_sha256 = FAKE_ARTIFACT_SHA
    served_from = "http://127.0.0.1:8080/v1"

    def __init__(self, error: Exception) -> None:
        self.error = error

    def generate(self, request: GenerationRequest) -> tuple[PatchCandidate, int, int | None]:
        raise self.error


class SpyingStore(TranscriptStore):
    """A store that records every read, so "was this consulted?" is answerable."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.reads: list[str] = []

    def find(self, request: GenerationRequest) -> Transcript:
        self.reads.append(request.fingerprint())
        return super().find(request)

    def paths(self) -> list[Path]:
        self.reads.append("paths")
        return super().paths()


@pytest.fixture
def request_() -> GenerationRequest:
    return GenerationRequest(
        mission_id="m-0001",
        prompt="Fix the off-by-one in pktcfg_parse_entry.",
        prompt_version="patch-prompt/3",
    )


@pytest.fixture
def store(tmp_path: Path) -> TranscriptStore:
    return TranscriptStore(tmp_path / "transcripts")


@pytest.fixture
def recorded_at() -> datetime:
    return datetime(2026, 8, 6, 21, 45, tzinfo=UTC)


@pytest.fixture
def recorded(store: TranscriptStore, request_: GenerationRequest, recorded_at: datetime) -> str:
    """One transcript in the store, captured as if from a live run."""
    return store.save(
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
            capture_kind=CaptureKind.LIVE_GENERATION,
        )
    )


@pytest.fixture
def replay_settings(store: TranscriptStore) -> GatewaySettings:
    return GatewaySettings(mode=GatewayMode.REPLAY, transcript_root=store.root).validate()


@pytest.fixture
def live_settings(store: TranscriptStore) -> GatewaySettings:
    return GatewaySettings(
        mode=GatewayMode.LIVE,
        endpoint="http://127.0.0.1:8080/v1",
        transcript_root=store.root,
        resolve_endpoint=False,
    ).validate()
