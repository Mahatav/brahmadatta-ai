"""Where a `PatchCandidate` physically comes from.

Two implementations of one protocol, and the protocol is the reason issue #82's "same code
path" criterion is a structural property rather than a promise: `ModelGateway` calls
`produce()` and then does the identical validation, provenance construction and labelling
regardless of which object answered.

`UnavailableLiveBackend` remains the default because the gateway must not invent a live
model when the operator has not configured one. D5 adds `gateway.ollama.OllamaCodeLlamaBackend`
as the local CodeLlama implementation; callers still pass it explicitly so "live inference"
is a configured claim, not a default.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from gateway.errors import LiveBackendUnavailableError, OperatorCandidateError
from gateway.provenance import ResponseProvenance, ResponseSource
from gateway.schemas import GenerationRequest, PatchCandidate
from gateway.transcripts import CaptureKind, TranscriptStore, capture

__all__ = [
    "BackendResult",
    "GenerationSource",
    "LiveSource",
    "OperatorSuppliedSource",
    "RecordingSource",
    "ReplaySource",
    "UnavailableLiveBackend",
]


@dataclass(frozen=True)
class BackendResult:
    """What a backend returns before the gateway attaches provenance."""

    candidate: PatchCandidate
    provenance: ResponseProvenance
    wall_time_ms: int = 0
    output_tokens: int | None = None


@runtime_checkable
class GenerationSource(Protocol):
    """The seam. `ModelGateway` knows nothing else about how a response is produced."""

    name: str

    def produce(self, request: GenerationRequest) -> BackendResult: ...


@runtime_checkable
class LiveBackend(Protocol):
    """A served model. Issues #35/#36 provide a real one; nothing here does."""

    #: Digest of the weight file being served. Recorded into every transcript, so a
    #: replayed response can name the artifact that produced it.
    model_name: str
    model_revision: str
    model_artifact_sha256: str
    served_from: str

    def generate(self, request: GenerationRequest) -> tuple[PatchCandidate, int, int | None]: ...


class UnavailableLiveBackend:
    """Default live backend: refuses, loudly, until a real backend is configured."""

    model_name = ""
    model_revision = ""
    model_artifact_sha256 = ""
    served_from = ""

    def generate(self, request: GenerationRequest) -> tuple[PatchCandidate, int, int | None]:
        raise LiveBackendUnavailableError(
            "no live model backend is wired into this build. Live CPU generation is "
            "available only when the operator supplies a backend such as the D5 Ollama "
            "CodeLlama backend. This is not a generation failure — nothing was attempted.",
            details={"mission_prompt_sha256": request.prompt_sha256},
        )


Clock = Callable[[], datetime]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class LiveSource:
    """Live inference. Produces a response and the provenance that goes with it."""

    name = "live"

    def __init__(self, backend: LiveBackend, *, clock: Clock = _utcnow) -> None:
        self.backend = backend
        self.clock = clock

    def produce(self, request: GenerationRequest) -> BackendResult:
        started = self.clock()
        candidate, wall_time_ms, output_tokens = self.backend.generate(request)
        provenance = ResponseProvenance(
            source=ResponseSource.LIVE_INFERENCE,
            model_name=self.backend.model_name,
            model_revision=self.backend.model_revision,
            model_artifact_sha256=self.backend.model_artifact_sha256 or None,
            served_from=self.backend.served_from,
            prompt_version=request.prompt_version,
            prompt_sha256=request.prompt_sha256,
            response_schema_version=request.response_schema_version,
            context_bytes=len(request.prompt.encode("utf-8")),
            confidence=candidate.confidence,
            generated_at=started,
        )
        return BackendResult(candidate, provenance, wall_time_ms, output_tokens)


class RecordingSource:
    """A live source that writes every successful response to the transcript store.

    Issue #82's last acceptance criterion is *"capture the transcripts on D5/D6 from real
    runs; a transcript nobody recorded is not a fallback."* Capture is therefore a wrapper
    that is on by default in live mode rather than a separate operator step someone has to
    remember at 2am on day six.

    A capture failure does not fail the mission — the response was real and the operator
    wants it. It is reported through `on_capture_error` so it cannot be silent either.
    """

    name = "live+recording"

    def __init__(
        self,
        inner: LiveSource,
        store: TranscriptStore,
        *,
        note: str = "",
        on_capture_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self.inner = inner
        self.store = store
        self.note = note
        self.on_capture_error = on_capture_error

    def produce(self, request: GenerationRequest) -> BackendResult:
        result = self.inner.produce(request)
        try:
            self.store.save(
                capture(
                    request,
                    result.candidate,
                    model_name=result.provenance.model_name,
                    model_revision=result.provenance.model_revision,
                    model_artifact_sha256=result.provenance.model_artifact_sha256 or "",
                    served_from=result.provenance.served_from,
                    captured_at=result.provenance.generated_at or _utcnow(),
                    wall_time_ms=result.wall_time_ms,
                    output_tokens=result.output_tokens,
                    note=self.note,
                    capture_kind=CaptureKind.LIVE_GENERATION,
                )
            )
        except Exception as exc:
            if self.on_capture_error is None:
                raise
            self.on_capture_error(exc)
        return result


class ReplaySource:
    """A recorded transcript, served through the same seam as a live one."""

    name = "replay"

    def __init__(self, store: TranscriptStore, *, clock: Clock = _utcnow) -> None:
        self.store = store
        self.clock = clock

    def produce(self, request: GenerationRequest) -> BackendResult:
        transcript = self.store.find(request)
        provenance = ResponseProvenance(
            source=ResponseSource.RECORDED_TRANSCRIPT,
            model_name=transcript.model_name,
            model_revision=transcript.model_revision,
            model_artifact_sha256=transcript.model_artifact_sha256,
            served_from=transcript.served_from,
            prompt_version=transcript.prompt_version,
            prompt_sha256=transcript.prompt_sha256,
            response_schema_version=transcript.response_schema_version,
            context_bytes=len(request.prompt.encode("utf-8")),
            confidence=transcript.response.confidence,
            # The replay happened now; the model ran on `captured_at`. Keeping both is
            # what lets the report say "recorded <date>, replayed" and mean it.
            generated_at=self.clock(),
            # A locator an operator can open, beside the digest that verifies it. The
            # control API's field is `str | None` and its presence is what every renderer
            # keys on, so it carries the file name rather than a bare `True`.
            replayed_from_transcript=f"{transcript.digest()}.json",
            captured_at=transcript.captured_at,
            transcript_sha256=transcript.digest(),
        )
        return BackendResult(
            transcript.response,
            provenance,
            # The recorded wall time is the model's, and reporting it as this mission's
            # latency would be a fabricated measurement. Replay took no measurable time.
            wall_time_ms=0,
            output_tokens=transcript.output_tokens,
        )


class OperatorSuppliedSource:
    """Rung 3 of the fallback ladder: a diff a person wrote.

    It goes through the gateway rather than around it for one reason — the labelling. The
    ladder's §4 forbids "model-generated" for an operator-supplied candidate, and the
    cheapest way to make that hold is for every candidate the system handles to acquire its
    provenance from the same place. A path that bypasses the gateway is a path where the
    label is somebody's discipline again.

    No model fields are populated, because none apply. `confidence` stays `None`: a human
    did not emit a self-reported probability, and inventing one would be exactly the
    "two invented strings" BUG-008 is about.
    """

    name = "operator-supplied"

    def __init__(self, diff_path: Path, *, rationale: str = "") -> None:
        self.diff_path = Path(diff_path)
        self.rationale = rationale

    def produce(self, request: GenerationRequest) -> BackendResult:
        try:
            diff = self.diff_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise OperatorCandidateError(
                f"cannot read the operator candidate diff at {self.diff_path}: {exc}",
                details={"path": str(self.diff_path)},
            ) from exc
        if not diff.strip():
            raise OperatorCandidateError(
                f"{self.diff_path} is empty; there is no candidate to supply.",
                details={"path": str(self.diff_path)},
            )

        candidate = PatchCandidate(
            diff=diff,
            rationale=self.rationale,
            touched_files=_touched_files(diff),
            confidence=None,
        )
        provenance = ResponseProvenance(
            source=ResponseSource.OPERATOR_SUPPLIED,
            prompt_version=request.prompt_version,
            prompt_sha256=request.prompt_sha256,
            response_schema_version=request.response_schema_version,
            context_bytes=len(request.prompt.encode("utf-8")),
            generated_at=_utcnow(),
        )
        return BackendResult(candidate, provenance, wall_time_ms=0, output_tokens=None)


def _touched_files(diff: str) -> tuple[str, ...]:
    """File paths named on the `+++ b/...` lines of a unified diff.

    Best effort and used for display only. Patch policy re-derives the file set from the
    diff itself — this is not, and must not become, the input to a policy decision.
    """
    seen: list[str] = []
    for line in diff.splitlines():
        if line.startswith("+++ ") and not line.startswith("+++ /dev/null"):
            path = line[4:].strip().split("\t")[0]
            if path.startswith("b/"):
                path = path[2:]
            if path and path not in seen:
                seen.append(path)
    return tuple(seen)
