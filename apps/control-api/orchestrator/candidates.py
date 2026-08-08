"""Recording patch candidates and verification runs — and freezing the set (D-046).

## The failure this file exists to prevent

*"Add one more candidate and re-verify."* Repeated, that is generate-until-pass: run
candidates through the gates until one comes out `VERIFIED`, then present it. It needs
**no transition-table change**, so it is the one failure mode in this system that
leaves no diff for a reviewer to object to. The state machine cannot see it, because
nothing about it is an illegal transition.

## Where it is closed

`Mission.verification_started_at`. Set when the first `VerificationRecord` is written;
`record_patch_candidate` refuses once it is set. Both run under `SELECT … FOR UPDATE`
on the mission row, so two concurrent writers cannot interleave a candidate insert
between the check and the first verification write.

`contracts.state_machine.assert_candidate_set_open` states the same rule in the file a
developer reads before writing the insert. It is called below, but it is not the
enforcement — a caller handed an empty list learns nothing from it (same reasoning as
D-045). The column is the mechanism.

The named test the CTO asked for is
`orchestrator/tests/test_candidate_freeze.py::test_cannot_add_candidate_after_verification_starts`.
"""

from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from contracts.enums import EventType, PatchProvenance, Severity, Verdict
from contracts.errors import CandidateSetFrozenError
from contracts.schemas.evidence import ModelProvenance
from contracts.schemas.evidence import PatchCandidate as PatchCandidateSchema
from contracts.schemas.evidence import VerificationRecord as VerificationSchema
from contracts.state_machine import assert_candidate_set_open
from contracts.verdict import GateMatrix, derive_verdict
from missions.models import Mission, PatchCandidate, VerificationRecord
from orchestrator import events, repository


def record_patch_candidate(
    mission_id: UUID,
    *,
    finding_id: UUID,
    provenance: PatchProvenance,
    diff: str,
    files_changed: int,
    lines_changed: int,
    policy_status,
    trace_id: str,
    model: ModelProvenance | None = None,
    policy_detail: str = "",
    rationale: str = "",
    now=None,
) -> PatchCandidate:
    """Persist one candidate, or refuse because the set is frozen.

    Refuses with `CandidateSetFrozenError` (HTTP 409) once verification has started.
    """
    now = now or timezone.now()

    with transaction.atomic():
        mission = Mission.objects.select_for_update().get(pk=mission_id)

        # The enforcement. State, in the store, read under the lock. Both halves are
        # checked because they can disagree: the column is the mechanism, and the
        # record count is the thing the column is a summary of. A mission with either
        # one set is frozen.
        if mission.verification_started_at is not None:
            raise CandidateSetFrozenError(
                "Verification has already started for this mission; the candidate set "
                "is closed.",
                details={
                    "mission_id": str(mission.id),
                    "verification_started_at": (
                        mission.verification_started_at.isoformat()
                    ),
                },
            )
        assert_candidate_set_open(repository.load_verifications(mission.id))

        # Validate against the frozen schema before touching the table, so a malformed
        # candidate is a 422 rather than a row nobody can load back.
        schema = PatchCandidateSchema(
            id=uuid.uuid4(),
            mission_id=mission.id,
            finding_id=finding_id,
            provenance=provenance,
            model=model,
            diff=diff,
            files_changed=files_changed,
            lines_changed=lines_changed,
            policy_status=policy_status,
            policy_detail=policy_detail,
            rationale=rationale,
            created_at=now,
        )

        row = PatchCandidate.objects.create(
            id=schema.id,
            mission=mission,
            finding_id=finding_id,
            provenance=str(schema.provenance),
            model_provenance=(
                schema.model.model_dump(mode="json") if schema.model else None
            ),
            diff=schema.diff,
            files_changed=schema.files_changed,
            lines_changed=schema.lines_changed,
            policy_status=str(schema.policy_status),
            policy_detail=schema.policy_detail,
            rationale=schema.rationale,
            created_at=schema.created_at,
        )

        events.emit(
            mission,
            EventType.PATCH_CANDIDATE_RECORDED,
            f"Patch candidate recorded ({schema.provenance}).",
            {"kind": "patch_candidate", "patch": schema.model_dump(mode="json")},
            trace_id=trace_id,
            timestamp=now,
        )

    return row


def record_verification(
    mission_id: UUID,
    *,
    patch_id: UUID,
    gates: GateMatrix,
    started_at,
    finished_at,
    trace_id: str,
    worktree_sha256: str | None = None,
    resource_usage: dict[str, Any] | None = None,
    now=None,
) -> VerificationRecord:
    """Persist one verification run and close the candidate set.

    The verdict is **not** a parameter. It is derived from `gates` by `derive_verdict`
    and nothing else — there is no argument a caller could pass to influence it, which
    is the same shape the contract uses (`derive_verdict` takes one argument).
    """
    now = now or timezone.now()

    with transaction.atomic():
        mission = Mission.objects.select_for_update().get(pk=mission_id)

        verdict = derive_verdict(gates)

        schema = VerificationSchema(
            id=uuid.uuid4(),
            mission_id=mission.id,
            patch_id=patch_id,
            gates=gates,
            verdict=verdict,
            started_at=started_at,
            finished_at=finished_at,
            worktree_sha256=worktree_sha256,
            resource_usage=resource_usage,
        )

        row = VerificationRecord.objects.create(
            id=schema.id,
            mission=mission,
            patch_id=patch_id,
            gates=schema.gates.model_dump(mode="json"),
            verdict=str(schema.verdict),
            started_at=schema.started_at,
            finished_at=schema.finished_at,
            worktree_sha256=schema.worktree_sha256,
            resource_usage=(
                schema.resource_usage.model_dump(mode="json")
                if schema.resource_usage
                else None
            ),
        )

        # D-046: the freeze goes on with the first record, under the same lock.
        if mission.verification_started_at is None:
            mission.verification_started_at = now
            mission.save(update_fields=["verification_started_at", "updated_at"])

        events.emit(
            mission,
            EventType.VERIFICATION_RECORDED,
            f"Verification complete: {verdict}.",
            {"kind": "verification", "verification": schema.model_dump(mode="json")},
            trace_id=trace_id,
            severity=(
                Severity.INFO if verdict is Verdict.VERIFIED else Severity.MEDIUM
            ),
            timestamp=now,
        )

    return row
