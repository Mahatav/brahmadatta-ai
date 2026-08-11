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

from contracts.enums import (
    ErrorCode,
    EventType,
    MissionStage,
    MissionState,
    PatchPolicyStatus,
    PatchProvenance,
    Severity,
    Verdict,
)
from contracts.errors import (
    CandidateSetFrozenError,
    CrossMissionEvidenceError,
    InvalidStateTransitionError,
)
from contracts.schemas.evidence import ModelProvenance
from contracts.schemas.evidence import PatchCandidate as PatchCandidateSchema
from contracts.schemas.evidence import VerificationRecord as VerificationSchema
from contracts.schemas.missions import MissionPolicy
from contracts.state_machine import assert_candidate_set_open, assert_stage_can_run
from contracts.verdict import GateMatrix, derive_verdict
from missions.lifecycle import lifecycle_write
from missions.models import Mission, PatchCandidate, VerificationRecord
from orchestrator import events, repository
from orchestrator.patch_policy import evaluate_patch_policy


def record_patch_candidate(
    mission_id: UUID,
    *,
    finding_id: UUID,
    provenance: PatchProvenance,
    diff: str,
    files_changed: int | None = None,
    lines_changed: int | None = None,
    policy_status=None,
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

        mission_policy = MissionPolicy.model_validate(mission.policy or {})
        policy_decision = evaluate_patch_policy(diff, mission_policy.patch)

        # Validate against the frozen schema before touching the table, so a malformed
        # candidate is a 422 rather than a row nobody can load back.
        schema = PatchCandidateSchema(
            id=uuid.uuid4(),
            mission_id=mission.id,
            finding_id=finding_id,
            provenance=provenance,
            model=model,
            diff=diff,
            files_changed=policy_decision.files_changed,
            lines_changed=policy_decision.lines_changed,
            policy_status=policy_decision.status,
            policy_detail=policy_detail or policy_decision.detail,
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
        if policy_decision.status is not PatchPolicyStatus.ACCEPTED:
            events.emit(
                mission,
                EventType.PATCH_POLICY_EVALUATED,
                f"Patch candidate rejected by policy: {policy_decision.status}.",
                {
                    "kind": "policy_violation",
                    "code": ErrorCode.PATCH_POLICY_REJECTED,
                    "detail": schema.policy_detail,
                },
                severity=Severity.MEDIUM,
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

    Three things are checked under the mission row lock before anything is written, and
    none of them is optional:

    * **The candidate belongs to this mission** (SEC-15). Without this, D-046 freezes a
      mission's *candidate set* but not the set of candidates that can be verified
      *into* it — so a frozen mission whose only candidate was `REJECTED` reaches
      terminal `VERIFIED` by verifying a second mission's candidate into it. That
      needs no forged record and no direct database write: the row genuinely carries
      this mission's id, because the writer got to set it. Generate-until-pass with one
      extra step.
    * **An active authorization covers the VERIFY stage** (SEC-21). P0-1 says no stage
      runs without one, and a verification record is what the `VERIFY` stage produces.
    * **The mission is actually in `VERIFY`** (SEC-21). The freeze is a *side effect* of
      this function, so an unguarded call on a mission in `CREATED` permanently closes
      its candidate set before `PATCH` has run — a denial of service on the mission's
      own purpose.
    """
    now = now or timezone.now()

    with transaction.atomic():
        mission = Mission.objects.select_for_update().get(pk=mission_id)

        # SEC-15. The check the mission-binding guard in `contracts/state_machine.py`
        # cannot make for itself: that guard reads `record.mission_id`, and this is the
        # only place that column is set. A check downstream of the writer can only
        # confirm the label the writer chose.
        patch = PatchCandidate.objects.select_related(None).get(pk=patch_id)
        if patch.mission_id != mission.id:
            raise CrossMissionEvidenceError(
                f"Patch candidate {patch.id} belongs to mission {patch.mission_id}, "
                f"not {mission.id}. A candidate outside this mission's own frozen "
                f"candidate set cannot be verified into it.",
                details={
                    "mission_id": str(mission.id),
                    "patch_id": str(patch.id),
                    "patch_mission_id": str(patch.mission_id),
                },
            )

        if patch.policy_status != PatchPolicyStatus.ACCEPTED.value:
            raise InvalidStateTransitionError(
                f"Patch candidate {patch.id} was rejected by policy "
                f"({patch.policy_status}) and cannot enter verification.",
                details={
                    "mission_id": str(mission.id),
                    "patch_id": str(patch.id),
                    "policy_status": patch.policy_status,
                    "policy_detail": patch.policy_detail,
                },
            )

        # SEC-21. Authorization and stage, under the lock we already hold.
        authorization = repository.load_active_authorization(mission, now)
        assert_stage_can_run(
            MissionStage.VERIFY,
            authorization,
            now,
            repository.latest_snapshot_sha256(mission),
        )
        if mission.state_enum is not MissionState.VERIFY:
            raise InvalidStateTransitionError(
                f"A verification can only be recorded while the mission is in VERIFY; "
                f"this one is in {mission.state_enum}. Recording one now would close "
                f"the candidate set before PATCH had produced it.",
                details={
                    "mission_id": str(mission.id),
                    "current_state": str(mission.state_enum),
                    "required_state": str(MissionState.VERIFY),
                },
            )

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
        #
        # `lifecycle_write()` is claimed for exactly this one column and for the width
        # of this one statement. `verification_started_at` is the only lifecycle field
        # this module may move; `state`, `paused_from` and `verdict` belong to
        # `orchestrator.transitions.transition` and are not written here (SEC-16).
        if mission.verification_started_at is None:
            mission.verification_started_at = now
            with lifecycle_write():
                mission.save(
                    update_fields=["verification_started_at", "updated_at"]
                )

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
