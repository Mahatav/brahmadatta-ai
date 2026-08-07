"""The authorization record.

P0-1 and the safety boundary in every security document: Brahmadatta runs against
*authorized* repositories only. The record below is the artifact that proves it, and
`contracts.state_machine` refuses to run any stage without one.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ninja import Schema
from pydantic import ConfigDict, Field


class AuthorizationRecord(Schema):
    """An operator's declaration of authority over a target repository.

    Immutable once written. Revocation is a new field, not an edit — the audit trail
    in the evidence bundle has to show that authority existed at the moment each
    stage ran.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    mission_id: UUID
    statement: str = Field(
        min_length=20,
        max_length=4000,
        description="Operator's declaration of authority and scope. Reproduced "
        "verbatim in the evidence bundle.",
    )
    granted_by: str = Field(
        min_length=1, max_length=200, description="Named human accountable for the claim."
    )
    granted_at: datetime
    expires_at: datetime = Field(
        description="Hard expiry. A stage starting after this instant is refused."
    )
    revoked_at: datetime | None = None
    repository_ref: str = Field(
        min_length=1,
        max_length=500,
        description="Repository the authority covers: URL or uploaded archive name.",
    )
    snapshot_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
        description="Bound snapshot digest. Once set, the authorization covers this "
        "snapshot and no other.",
    )
    evidence_ref: str | None = Field(
        default=None,
        max_length=500,
        description="Artifact pointer to the signed authorization document, if one exists.",
    )


class AuthorizationRequest(Schema):
    """Operator input. The server owns ids and timestamps; the client cannot set
    `granted_at`, so an expired authority cannot be back-dated into validity."""

    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=20, max_length=4000)
    granted_by: str = Field(min_length=1, max_length=200)
    repository_ref: str = Field(min_length=1, max_length=500)
    valid_for_minutes: int = Field(
        default=240,
        ge=1,
        le=1440,
        description="Lifetime of the authority, capped at 24 hours.",
    )


def is_active(record: AuthorizationRecord | None, now: datetime) -> bool:
    """True only for a record that exists, is unrevoked, and has not expired."""
    if record is None:
        return False
    if record.revoked_at is not None and record.revoked_at <= now:
        return False
    return record.expires_at > now


def covers_snapshot(record: AuthorizationRecord, snapshot_sha256: str | None) -> bool:
    """True when the record's snapshot binding permits work on this snapshot.

    An unbound record covers the first snapshot it sees; a bound record covers only
    that digest, so swapping the archive after authorization does not inherit it.
    """
    if record.snapshot_sha256 is None:
        return True
    return record.snapshot_sha256 == snapshot_sha256
