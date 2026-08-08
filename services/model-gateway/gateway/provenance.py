"""Where a response came from, and the only place in this package that says so in words.

## The honesty constraint, mechanically

A replayed response is legitimate. Presenting it as inference happening in front of a
judge is not. That is D-008's rule for operator-supplied patches applied to the model
itself, and issue #82 makes it the point of the feature rather than a footnote on it.

Three things make it hold here rather than merely intending it:

1. **One chokepoint.** Every provenance sentence this package produces comes out of
   `describe()`. `gateway/tests/test_provenance_chokepoint.py` scans the package source and
   fails if provenance wording appears in any other module, so a second renderer cannot be
   added without the test noticing.

2. **The fallback branch is the humble one.** `describe()` claims live inference only when
   every field that would evidence it is present. Anything else — a missing timestamp, an
   empty `served_from`, a half-filled record — renders as *not attested*, which is an
   understatement rather than an overclaim. This is D-049 Part 1: a default is a claim the
   system makes on your behalf when you say nothing, so the silence has to point downward.

3. **`source` has no default.** `ResponseProvenance` cannot be constructed without stating
   where the response came from.

## The wording

The strings are fixed because they are quoted in issue #82's acceptance criteria and in
`docs/09-company/10-fallback-ladder.md` §1 (the patch rungs) and §4 ("sentences we do not
say"), and they end up on a screen a judge reads:

    replayed   "model output recorded 2026-08-06, replayed"
    operator   "operator-supplied candidate"
    live       "model-generated (live inference 2026-08-07)"
    unattested "model output, provenance not attested — not presented as live inference"

The ladder's three patch rungs are these first three, and they come out of one function so
that the bundle cannot disagree with the narration —
`gateway/tests/test_fallback_ladder_wording.py` reads the strings back out of the ladder
document itself, so editing one without the other fails.

`render_for_evidence()` is the same claim in a sentence, for the Markdown report.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "ProvenanceClaim",
    "ResponseProvenance",
    "ResponseSource",
    "describe",
    "render_for_evidence",
    "render_for_ui",
]


class ResponseSource(StrEnum):
    """How this response was produced. Set by the gateway from the active source object.

    The three values are the fallback ladder's three patch rungs: live inference, #82
    replay, and the D-008 operator-supplied candidate.
    """

    LIVE_INFERENCE = "LIVE_INFERENCE"
    RECORDED_TRANSCRIPT = "RECORDED_TRANSCRIPT"
    OPERATOR_SUPPLIED = "OPERATOR_SUPPLIED"


class ProvenanceClaim(StrEnum):
    """What the system is entitled to say about a response.

    Distinct from `ResponseSource`: the source is what happened, the claim is what we can
    demonstrate. `NOT_ATTESTED` is the case where a response says it was live and cannot
    show it — and the rule is that we then do not say it was.
    """

    LIVE_INFERENCE = "LIVE_INFERENCE"
    REPLAYED_TRANSCRIPT = "REPLAYED_TRANSCRIPT"
    OPERATOR_SUPPLIED = "OPERATOR_SUPPLIED"
    NOT_ATTESTED = "NOT_ATTESTED"


class ResponseProvenance(BaseModel):
    """Provenance for one gateway response.

    Field names in the replay block are the control API's, deliberately:
    `contracts.schemas.evidence.ModelProvenance` on `main` carries
    `replayed_from_transcript`, `captured_at` and `transcript_sha256` with an all-or-nothing
    validator. `to_contract_dict()` produces exactly that shape. The two models are not
    shared by import — the ASGI process must not import this package, which
    `tests/architecture/test_import_direction.py` enforces — so they are kept aligned by
    name and by `gateway/tests/test_contract_alignment.py`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # No default. The gateway must state this.
    source: ResponseSource

    model_name: str = Field(default="", max_length=200)
    model_revision: str = Field(default="", max_length=200)
    model_artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    served_from: str = Field(default="", max_length=200)
    prompt_version: str = Field(default="", max_length=100)
    prompt_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    response_schema_version: str = Field(default="", max_length=100)
    context_bytes: int = Field(default=0, ge=0)

    #: DISPLAY ONLY. Never an input to a gate, a verdict, or an escalation. The gateway
    #: has no branch on this value and `gateway/tests/test_confidence_is_display_only.py`
    #: is the assertion, not this comment.
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    #: When this response was produced by this process. For a replayed response this is
    #: the replay time, not the capture time — `captured_at` is the capture time.
    generated_at: datetime | None = None

    # --- replay block, all three together or none of them ------------------------------
    replayed_from_transcript: str | None = Field(default=None, max_length=500)
    captured_at: datetime | None = None
    transcript_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _replay_block_is_all_or_nothing(self) -> ResponseProvenance:
        block = (self.replayed_from_transcript, self.captured_at, self.transcript_sha256)
        if any(v is not None for v in block) and not all(v is not None for v in block):
            raise ValueError(
                "replayed_from_transcript, captured_at and transcript_sha256 are set "
                "together or not at all — a partially-declared replay cannot be "
                "distinguished from a live generation."
            )
        if self.source is ResponseSource.RECORDED_TRANSCRIPT and not all(
            v is not None for v in block
        ):
            raise ValueError(
                "source=RECORDED_TRANSCRIPT requires replayed_from_transcript, "
                "captured_at and transcript_sha256. A replayed response that cannot say "
                "which transcript it came from is indistinguishable from a live one, "
                "which is the exact substitution issue #82 exists to prevent."
            )
        if self.source is ResponseSource.OPERATOR_SUPPLIED and any(v is not None for v in block):
            raise ValueError(
                "source=OPERATOR_SUPPLIED cannot carry replay fields. A candidate is "
                "either a recorded model response or something a person wrote; a record "
                "claiming both describes nothing that happened."
            )
        return self

    @property
    def is_replayed(self) -> bool:
        return self.replayed_from_transcript is not None

    def contract_patch_provenance(self) -> str:
        """The value the control API's `PatchProvenance` field must carry.

        `MODEL_GENERATED` covers live and replayed, which is the CTO's shape for D-020:
        the replay block inside `ModelProvenance` is what distinguishes them, not this
        enum. An operator-supplied candidate is not model-generated in any mode and
        `gateway/tests/test_fallback_ladder_wording.py` asserts it never renders as one.
        """
        if self.source is ResponseSource.OPERATOR_SUPPLIED:
            return "OPERATOR_SUPPLIED"
        return "MODEL_GENERATED"

    def to_contract_dict(self) -> dict[str, object]:
        """The subset the control API's `ModelProvenance` accepts.

        Every replay key is present in the returned mapping, explicitly, including when it
        is `None`. That is deliberate and it is a mitigation, not a style choice: the
        contract's replay fields default to the *stronger* claim (BUG-007, D-049 Part 1,
        still open on #6), so a gateway that omitted a key would be relying on a default
        that points at "live". Emitting all three every time means a gateway-produced
        record never depends on that default in either direction.

        `confidence` is carried because the contract carries it, and for the same reason:
        recorded so the evidence bundle shows what the model claimed alongside what the
        tools proved.
        """
        return {
            "model_name": self.model_name,
            "model_revision": self.model_revision,
            "served_from": self.served_from,
            "prompt_sha256": self.prompt_sha256,
            "context_bytes": self.context_bytes,
            "confidence": self.confidence,
            "replayed_from_transcript": self.replayed_from_transcript,
            "captured_at": self.captured_at,
            "transcript_sha256": self.transcript_sha256,
        }


def claim_for(provenance: ResponseProvenance) -> ProvenanceClaim:
    """What we are entitled to say about this response.

    The live branch is the narrow one and it is checked positively. Every other shape
    falls through to a weaker claim, so a field somebody forgot to set produces an
    understatement.
    """
    if provenance.source is ResponseSource.OPERATOR_SUPPLIED:
        return ProvenanceClaim.OPERATOR_SUPPLIED
    if provenance.is_replayed:
        return ProvenanceClaim.REPLAYED_TRANSCRIPT

    live = (
        provenance.source is ResponseSource.LIVE_INFERENCE
        and bool(provenance.served_from)
        and bool(provenance.model_name)
        and provenance.generated_at is not None
    )
    return ProvenanceClaim.LIVE_INFERENCE if live else ProvenanceClaim.NOT_ATTESTED


def _as_date(value: datetime | None) -> str:
    if value is None:
        return "date unknown"
    moment = value if value.tzinfo else value.replace(tzinfo=UTC)
    return moment.astimezone(UTC).date().isoformat()


def describe(provenance: ResponseProvenance) -> str:
    """The one sentence fragment this package uses to label a response.

    Everything that renders provenance — UI payload, evidence report, structured log —
    goes through here. See the module docstring for why that is a test and not a habit.
    """
    claim = claim_for(provenance)
    if claim is ProvenanceClaim.OPERATOR_SUPPLIED:
        return "operator-supplied candidate"
    if claim is ProvenanceClaim.REPLAYED_TRANSCRIPT:
        return f"model output recorded {_as_date(provenance.captured_at)}, replayed"
    if claim is ProvenanceClaim.LIVE_INFERENCE:
        return f"model-generated (live inference {_as_date(provenance.generated_at)})"
    return "model output, provenance not attested — not presented as live inference"


def render_for_ui(provenance: ResponseProvenance) -> dict[str, object]:
    """The provenance payload a Command Center panel renders.

    `label` is the whole sentence; the panel prints it as given. The structured fields are
    beside it so the operator can check the claim rather than take it — the transcript
    digest in particular, which is what makes "recorded, replayed" verifiable instead of
    merely stated.
    """
    claim = claim_for(provenance)
    return {
        "label": describe(provenance),
        "claim": claim.value,
        "is_replayed": provenance.is_replayed,
        "captured_at": provenance.captured_at.isoformat() if provenance.captured_at else None,
        "transcript_sha256": provenance.transcript_sha256,
        "model_name": provenance.model_name or None,
        "model_artifact_sha256": provenance.model_artifact_sha256,
        "served_from": provenance.served_from or None,
        "prompt_version": provenance.prompt_version or None,
        "confidence": provenance.confidence,
        "confidence_note": (
            "Displayed, not trusted. The model's self-reported score is not an input to "
            "any gate or verdict."
        ),
    }


def render_for_evidence(provenance: ResponseProvenance) -> str:
    """The Markdown line the exported evidence report carries.

    Same claim as the UI, in a sentence, because the two must not be able to drift —
    `gateway/tests/test_provenance_labelling.py` asserts the UI label appears verbatim
    inside this string.
    """
    label = describe(provenance)
    claim = claim_for(provenance)

    if claim is ProvenanceClaim.OPERATOR_SUPPLIED:
        return (
            f"**Provenance:** {label}. A person wrote this diff; no model produced it. The "
            "policy and verification gates below ran against it unchanged, which is the "
            "part that carries the claim."
        )
    if claim is ProvenanceClaim.REPLAYED_TRANSCRIPT:
        return (
            f"**Provenance:** {label}. This patch candidate was served from a transcript "
            f"captured on {_as_date(provenance.captured_at)} "
            f"(`sha256:{provenance.transcript_sha256}`), not generated during this "
            "mission. The verification gates below ran against it in this mission, "
            "unchanged."
        )
    if claim is ProvenanceClaim.LIVE_INFERENCE:
        return f"**Provenance:** {label}. Served by `{provenance.served_from}` during this mission."
    return (
        f"**Provenance:** {label}. The record is incomplete, so no claim is made that "
        "this response was generated live."
    )
