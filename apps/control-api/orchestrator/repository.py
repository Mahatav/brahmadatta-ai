"""Loading persisted records back into the frozen contract schemas.

Everything the orchestrator reasons about is a pydantic model from `contracts/`, not a
Django instance. That is deliberate: `VerificationRecord` re-derives its verdict from
its gate matrix in a validator, so a row whose stored verdict disagrees with its stored
gates **cannot be loaded**, let alone used to justify a transition. The re-derivation
runs on every read, not only on write.

These functions are the only sanctioned way to get verification records into
`contracts.state_machine.assert_verdict_is_evidenced`. See the comment at that call
site in `orchestrator.transitions`.
"""

from __future__ import annotations

from uuid import UUID

from django.utils import timezone

from contracts.authorization import AuthorizationRecord, is_active
from contracts.schemas.evidence import VerificationRecord as VerificationSchema
from missions.models import Mission, VerificationRecord


def load_verifications(mission_id: UUID) -> list[VerificationSchema]:
    """Every verification record this mission has, as contract schemas.

    Ordered and complete by construction: the query is `mission_id=<this mission>` with
    no filter, no slice and no `exclude`. That is the property the verdict guard cannot
    check for itself — see `contracts.state_machine`'s module docstring.
    """
    rows = VerificationRecord.objects.filter(mission_id=mission_id).order_by(
        "started_at", "id"
    )
    return [_to_schema(row) for row in rows]


def _to_schema(row: VerificationRecord) -> VerificationSchema:
    return VerificationSchema(
        id=row.id,
        mission_id=row.mission_id,
        patch_id=row.patch_id,
        gates=row.gates,
        verdict=row.verdict,
        started_at=row.started_at,
        finished_at=row.finished_at,
        worktree_sha256=row.worktree_sha256,
        resource_usage=row.resource_usage,
    )


def load_active_authorization(
    mission: Mission, now=None
) -> AuthorizationRecord | None:
    """The mission's active authorization, or `None`.

    `None` is a refusal, not a skip: `assert_transition` treats a missing record as "no
    stage may run". Returning the newest *active* one rather than the newest one full
    stop means a revoked record cannot be resurrected by adding a second.
    """
    now = now or timezone.now()
    for row in mission.authorizations.order_by("-granted_at"):
        record = AuthorizationRecord(
            id=row.id,
            mission_id=row.mission_id,
            statement=row.statement,
            granted_by=row.granted_by,
            granted_at=row.granted_at,
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
            repository_ref=row.repository_ref,
            snapshot_sha256=row.snapshot_sha256,
            evidence_ref=row.evidence_ref,
        )
        if is_active(record, now):
            return record
    return None


def latest_snapshot_sha256(mission: Mission) -> str | None:
    row = mission.snapshots.order_by("-created_at").first()
    return row.archive_sha256 if row else None
