"""Shared building blocks: the error envelope, pagination, artifact references.

Every schema in the contract forbids unknown fields. That is deliberate and it is
what makes the contract load-bearing: a field the backend starts sending that the
frontend has not regenerated types for is a validation failure on our side, and a
field the frontend sends that the backend does not know about is a 422. Contract
drift surfaces as a build or test failure instead of a silently-ignored key.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from ninja import Schema
from pydantic import ConfigDict, Field

from contracts.enums import ErrorCode

T = TypeVar("T")


class StrictSchema(Schema):
    """Base for every contract schema. Unknown fields are an error, not a shrug."""

    model_config = ConfigDict(extra="forbid")


class ErrorDetail(StrictSchema):
    code: ErrorCode
    message: str = Field(
        description="User-safe explanation. Never contains secrets, credentials, "
        "raw target output, or unsanitized source."
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured, sanitized context for the UI: allowed transitions, "
        "field errors, the issue tracking an unimplemented stub.",
    )


class ErrorEnvelope(StrictSchema):
    """The single error shape every non-2xx response uses."""

    error: ErrorDetail
    trace_id: str = Field(
        description="Correlates this failure with the server logs and the mission "
        "event stream. Also returned as the X-Trace-Id header."
    )


class Page(StrictSchema, Generic[T]):
    """Offset pagination. Small result sets by design — one mission at a time."""

    items: list[T]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=500)
    offset: int = Field(ge=0)


class ArtifactRef(StrictSchema):
    """Pointer to an artifact in the encrypted store.

    The URI is opaque and is never a browser-resolvable link. The UI exchanges it for
    a signed, short-lived URL through the evidence endpoints — raw archives and
    unsanitized logs never reach the browser directly
    (`docs/03-technical/21-api-specification.md`, API rules).
    """

    uri: str = Field(max_length=500, description="artifact://<mission>/<kind>/<id>")
    kind: str = Field(max_length=64)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    size_bytes: int | None = Field(default=None, ge=0)


class ResourceUsage(StrictSchema):
    """Measured, never estimated. Displayed in the Core's resource rail and written
    into the evidence bundle (P0-14)."""

    cpu_seconds: float = Field(ge=0)
    peak_memory_mb: float = Field(ge=0)
    wall_seconds: float = Field(ge=0)
    sandbox_count: int = Field(ge=0)
    gpu_seconds: float = Field(
        default=0.0,
        ge=0,
        description="Zero for the seven-day build: rented GPU is cut (D-015). The "
        "field stays so an evidence bundle keeps one shape across versions.",
    )


class Acknowledgement(StrictSchema):
    """Response to an accepted command that does its work asynchronously."""

    mission_id: str
    accepted: bool
    trace_id: str
    message: str = Field(default="", max_length=500)
