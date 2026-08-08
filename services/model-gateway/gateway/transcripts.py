"""Recorded model transcripts: written by SHA-256, read back only if they still hash.

A transcript is one captured (request, response) pair plus everything needed to say what
produced it. Issue #82 requires four of those things by name — capture timestamp, model
artifact hash, prompt version, schema version — because a fallback whose provenance cannot
be stated is a fallback that cannot honestly be used.

## Content addressing, and what it does and does not prove

The file name is the SHA-256 of the canonical JSON of the record *without* its own digest
field. `load()` recomputes it and refuses a mismatch. That makes a transcript
**tamper-evident**, not tamper-proof: anyone who can edit the file can recompute the name.
It is worth having anyway — it catches a truncated write, a hand-edit, and a
copy-paste-into-the-wrong-file, which are the realistic failures on day six — but the
wording in the evidence report must stay "digest recorded", never "signed". That is D-025's
correction (a hash is not a signature) applied here before someone has to make it again.

## Two capture kinds, because the difference is a claim

`CaptureKind.LIVE_GENERATION` — recorded from a model that actually ran. This is the only
kind that supports "model output recorded <date>, replayed".

`CaptureKind.SYNTHETIC_FIXTURE` — written by a human to exercise the code path. Refused at
load time unless `allow_synthetic_transcripts` is explicitly on, and the tests are the only
place that turns it on. Issue #82's last acceptance criterion is "capture the transcripts
on D5/D6 from real runs; a transcript nobody recorded is not a fallback" — this is that
sentence made into a check, so the fallback cannot quietly become a hand-written patch
wearing a model's provenance.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from gateway.errors import TranscriptError, TranscriptNotFoundError
from gateway.schemas import (
    RESPONSE_SCHEMA_VERSION,
    GenerationRequest,
    PatchCandidate,
    canonical_bytes,
    sha256_of,
)

__all__ = [
    "TRANSCRIPT_ENVELOPE_VERSION",
    "CaptureKind",
    "Transcript",
    "TranscriptStore",
]

#: The envelope, not the payload. Bumped when `Transcript`'s own shape changes.
TRANSCRIPT_ENVELOPE_VERSION = "transcript/1"


class CaptureKind(StrEnum):
    LIVE_GENERATION = "LIVE_GENERATION"
    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"


class Transcript(BaseModel):
    """One recorded exchange.

    `request_fingerprint` is `GenerationRequest.fingerprint()` — the lookup key. It
    excludes the mission id so a transcript captured on D5 is findable from a mission that
    did not exist when it was recorded, and includes everything that would change what a
    model produced, so a transcript cannot be served for a prompt it never answered.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    envelope_version: str = Field(default=TRANSCRIPT_ENVELOPE_VERSION, max_length=50)
    capture_kind: CaptureKind

    #: When the model actually ran. Timezone-aware, normalised to UTC on construction —
    #: this date is rendered to a judge and a naive datetime renders as whatever the
    #: machine felt like.
    captured_at: datetime

    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_version: str = Field(max_length=100)
    response_schema_version: str = Field(max_length=100)

    model_name: str = Field(max_length=200)
    model_revision: str = Field(default="", max_length=200)
    #: Digest of the quantized weight file the response came from. Without it "the model
    #: that produced this" is a name, and a name is not an artifact.
    model_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    served_from: str = Field(default="", max_length=200)

    response: PatchCandidate
    wall_time_ms: int = Field(default=0, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)

    #: Free-form operator note: which run this came from, what was being tested.
    note: str = Field(default="", max_length=1000)

    def digest(self) -> str:
        """SHA-256 over the canonical JSON of this record. The file name."""
        return sha256_of(self.model_dump(mode="json"))

    def to_bytes(self) -> bytes:
        return canonical_bytes(self.model_dump(mode="json"))


def _utc(value: datetime) -> datetime:
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC)


class TranscriptStore:
    """A directory of transcripts, addressed by digest and indexed by request.

    Reads are lazy and uncached: the store is small (tens of files at most), the D6 path
    is not latency-bound, and an uncached read means a transcript dropped into the
    directory five minutes before the finale is visible without a restart.
    """

    def __init__(self, root: Path, *, allow_synthetic: bool = False) -> None:
        self.root = Path(root)
        self.allow_synthetic = allow_synthetic

    # -- writing ------------------------------------------------------------------------

    def save(self, transcript: Transcript) -> str:
        """Write a transcript under its own digest. Returns the digest.

        Atomic: written to a temporary file in the same directory and renamed, so a
        transcript is never half-visible. Re-saving identical content is a no-op, which
        makes capture idempotent.
        """
        normalised = transcript.model_copy(update={"captured_at": _utc(transcript.captured_at)})
        digest = normalised.digest()
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / f"{digest}.json"
        if target.exists():
            return digest

        payload = json.dumps(
            normalised.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False
        )
        handle, tmp_name = tempfile.mkstemp(dir=str(self.root), suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(payload + "\n")
            os.replace(tmp_name, target)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
        return digest

    # -- reading ------------------------------------------------------------------------

    def paths(self) -> list[Path]:
        if not self.root.is_dir():
            return []
        return sorted(p for p in self.root.glob("*.json") if p.is_file())

    def load(self, digest: str) -> Transcript:
        """Load one transcript by digest, verifying the digest and the capture kind."""
        path = self.root / f"{digest}.json"
        if not path.is_file():
            raise TranscriptNotFoundError(
                f"no transcript {digest} in {self.root}", details={"digest": digest}
            )
        return self._read(path)

    def __iter__(self) -> Iterator[Transcript]:
        for path in self.paths():
            yield self._read(path)

    def find(self, request: GenerationRequest) -> Transcript:
        """The transcript recorded for this exact request.

        Raises `TranscriptNotFoundError` when there is none. In replay mode that is fatal
        and is *not* answered by generating live — the operator chose a mode.
        """
        fingerprint = request.fingerprint()
        matches = [t for t in self if t.request_fingerprint == fingerprint]
        if not matches:
            raise TranscriptNotFoundError(
                f"no recorded transcript for this request (fingerprint {fingerprint}). "
                f"{len(self.paths())} transcript(s) present in {self.root}. Replay mode "
                "does not fall back to live generation; capture the transcript or switch "
                "the mode deliberately.",
                details={"fingerprint": fingerprint, "root": str(self.root)},
            )
        if len(matches) > 1:
            # Two different recorded answers to the same prompt is a real situation (the
            # model was run twice) and picking one silently would make the gateway
            # non-deterministic in the one place determinism is the entire point.
            digests = sorted(t.digest() for t in matches)
            raise TranscriptError(
                f"{len(matches)} transcripts match this request: {', '.join(digests)}. "
                "Ambiguous replay is refused; keep one and archive the rest.",
                details={"fingerprint": fingerprint, "digests": digests},
            )

        transcript = matches[0]
        if transcript.response_schema_version != request.response_schema_version:
            raise TranscriptError(
                f"transcript {transcript.digest()} was captured under response schema "
                f"{transcript.response_schema_version!r} but this request expects "
                f"{request.response_schema_version!r}. Re-capture it; decoding an old "
                "transcript with new code is a silent data bug.",
                details={"digest": transcript.digest()},
            )
        return transcript

    def _read(self, path: Path) -> Transcript:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TranscriptError(f"{path.name} is not readable JSON: {exc}") from exc
        try:
            transcript = Transcript.model_validate(raw)
        except ValidationError as exc:
            raise TranscriptError(f"{path.name} is not a valid transcript: {exc}") from exc

        if transcript.envelope_version != TRANSCRIPT_ENVELOPE_VERSION:
            raise TranscriptError(
                f"{path.name} uses envelope {transcript.envelope_version!r}, this build "
                f"reads {TRANSCRIPT_ENVELOPE_VERSION!r}."
            )

        expected = path.stem
        actual = transcript.digest()
        if actual != expected:
            raise TranscriptError(
                f"{path.name} does not hash to its own name (content digest {actual}). "
                "The file has been edited or truncated since capture. A transcript that "
                "does not match its digest is not evidence of anything.",
                details={"path": str(path), "expected": expected, "actual": actual},
            )

        if transcript.capture_kind is CaptureKind.SYNTHETIC_FIXTURE and not self.allow_synthetic:
            raise TranscriptError(
                f"{path.name} is a SYNTHETIC_FIXTURE — written by hand, not captured from "
                "a model run. It cannot be served as model output. Set "
                "MODEL_ALLOW_SYNTHETIC_TRANSCRIPTS=1 only in tests.",
                details={"path": str(path)},
            )
        return transcript


def capture(
    request: GenerationRequest,
    response: PatchCandidate,
    *,
    model_name: str,
    model_artifact_sha256: str,
    captured_at: datetime,
    model_revision: str = "",
    served_from: str = "",
    wall_time_ms: int = 0,
    output_tokens: int | None = None,
    note: str = "",
    capture_kind: CaptureKind = CaptureKind.LIVE_GENERATION,
) -> Transcript:
    """Build a `Transcript` from a request and the response a model gave to it.

    `capture_kind` defaults to `LIVE_GENERATION` because the only caller that should reach
    this function is a live run; a hand-written fixture has to say so, which is the
    direction that makes the wrong thing loud.
    """
    return Transcript(
        capture_kind=capture_kind,
        captured_at=_utc(captured_at),
        request_fingerprint=request.fingerprint(),
        prompt_sha256=request.prompt_sha256,
        prompt_version=request.prompt_version,
        response_schema_version=request.response_schema_version or RESPONSE_SCHEMA_VERSION,
        model_name=model_name,
        model_revision=model_revision,
        model_artifact_sha256=model_artifact_sha256,
        served_from=served_from,
        response=response,
        wall_time_ms=wall_time_ms,
        output_tokens=output_tokens,
        note=note,
    )
