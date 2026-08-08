"""The gateway's request and response schemas.

Craft rule 1 for this seat: every model call is schema-constrained. Pydantic in, validated
JSON out, checked before anything downstream sees it. A malformed response is retried or
escalated, never parsed hopefully.

The important structural property for issue #82 is that **replay and live share these
types**. There is no `ReplayResponse`. A recorded transcript is decoded into
`PatchCandidate` and validated by the same model, with the same schema version check, as a
response that arrived from a socket — so "the replay path" cannot drift into accepting
something the live path would have rejected, and a downstream consumer cannot tell the two
apart *structurally*. It can only tell them apart by the provenance, which is the point.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from gateway.provenance import ResponseProvenance

__all__ = [
    "RESPONSE_SCHEMA_VERSION",
    "GatewayResponse",
    "GenerationRequest",
    "PatchCandidate",
    "canonical_bytes",
    "sha256_of",
]

#: Bumped when `PatchCandidate` changes shape. A transcript records the version it was
#: captured under and `TranscriptStore` refuses to serve one captured under a different
#: version — an old transcript decoded by new code is a silent data bug, and this is a
#: fallback that has to work on the day it is needed.
RESPONSE_SCHEMA_VERSION = "patch-candidate/1"


def canonical_bytes(payload: Any) -> bytes:
    """Deterministic JSON encoding, so a digest of the same content is the same digest.

    Sorted keys, no insignificant whitespace, UTF-8, `ensure_ascii=False`. Everything the
    gateway hashes goes through here so that a hash computed on one machine matches one
    computed on another — which is the whole value of storing transcripts by SHA-256.
    """
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")


def sha256_of(payload: Any) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


class GenerationRequest(BaseModel):
    """What the patching worker asks the gateway for.

    `prompt` is the assembled, already-redacted context. The gateway does not build it and
    does not redact it — redaction happens where the repository snapshot is, before this
    object exists. That boundary is stated here because "redact before you prompt" is a
    rule for this seat and it is *not* implemented in this module; see the README's
    "What this does not do".
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    mission_id: str = Field(max_length=100)
    prompt: str
    prompt_version: str = Field(max_length=100)
    response_schema_version: str = Field(default=RESPONSE_SCHEMA_VERSION, max_length=100)
    target_language: str = Field(default="c", max_length=20)
    max_output_tokens: int = Field(default=1024, ge=1, le=32768)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    seed: int | None = None

    @property
    def prompt_sha256(self) -> str:
        return hashlib.sha256(self.prompt.encode("utf-8")).hexdigest()

    def fingerprint(self) -> str:
        """The transcript lookup key.

        Deliberately excludes `mission_id`: a transcript captured on D5 has to be findable
        from a mission that did not exist yet. Includes everything that changes what a
        model would produce, so a transcript cannot be served for a prompt it was not a
        response to.
        """
        return sha256_of(
            {
                "prompt_sha256": self.prompt_sha256,
                "prompt_version": self.prompt_version,
                "response_schema_version": self.response_schema_version,
                "target_language": self.target_language,
                "max_output_tokens": self.max_output_tokens,
                "temperature": self.temperature,
                "seed": self.seed,
            }
        )


class PatchCandidate(BaseModel):
    """The structured output the model is constrained to produce.

    `confidence` is recordable and displayable and is an input to nothing. There is no
    branch on it anywhere in this package — not a threshold, not a sort, not a retry
    condition — and that absence is asserted by
    `gateway/tests/test_confidence_is_display_only.py` rather than left to review
    attention.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    diff: str = Field(min_length=1)
    rationale: str = Field(default="", max_length=4000)
    touched_files: tuple[str, ...] = ()
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class GatewayResponse(BaseModel):
    """A patch candidate plus the provenance that must travel with it.

    They are one object on purpose. A candidate that can be passed around without its
    provenance is a candidate that will eventually be rendered without it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate: PatchCandidate
    provenance: ResponseProvenance
    wall_time_ms: int = Field(default=0, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
