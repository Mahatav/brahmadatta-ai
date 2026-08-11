"""#37 — deterministic patch policy before verification."""

from __future__ import annotations

import pytest

from contracts.enums import (
    EventType,
    MissionState,
    PatchPolicyStatus,
    PatchProvenance,
)
from contracts.errors import InvalidStateTransitionError
from contracts.schemas.missions import PatchPolicy
from missions.models import MissionEvent
from orchestrator import candidates, transitions
from orchestrator.patch_policy import evaluate_patch_policy
from orchestrator.tests.conftest import (
    CANDIDATE_A,
    CANDIDATE_B,
    NOW,
    TRACE,
    gate_matrix,
    walk_to,
)

pytestmark = pytest.mark.django_db(transaction=True)


def _record(mission, finding, diff: str):
    return candidates.record_patch_candidate(
        mission.id,
        finding_id=finding.id,
        provenance=PatchProvenance.OPERATOR_SUPPLIED,
        diff=diff,
        files_changed=999,
        lines_changed=999,
        policy_status=PatchPolicyStatus.REJECTED_MALFORMED_DIFF,
        trace_id=TRACE,
        now=NOW,
    )


def test_committed_demo_candidates_are_accepted_by_policy(mission, finding):
    walk_to(mission, MissionState.PATCH)

    candidate_a = _record(mission, finding, CANDIDATE_A.read_text())
    candidate_b = _record(mission, finding, CANDIDATE_B.read_text())

    assert candidate_a.policy_status == PatchPolicyStatus.ACCEPTED.value
    assert candidate_a.files_changed == 1
    assert candidate_a.lines_changed == 7
    assert "allowed_paths=src/decode.c" in candidate_a.policy_detail
    assert candidate_b.policy_status == PatchPolicyStatus.ACCEPTED.value
    assert candidate_b.lines_changed == 6


def test_path_allowlist_violation_is_named_before_verification(mission, finding):
    walk_to(mission, MissionState.PATCH)
    diff = CANDIDATE_A.read_text().replace("src/decode.c", "CMakeLists.txt")

    candidate = _record(mission, finding, diff)

    assert candidate.policy_status == PatchPolicyStatus.REJECTED_PATH_NOT_ALLOWED.value
    assert "path not allowed: CMakeLists.txt" in candidate.policy_detail
    assert _policy_events(mission)[0].payload["detail"] == candidate.policy_detail


def test_too_many_files_violation_is_named(mission, finding):
    walk_to(mission, MissionState.PATCH)
    diff = (
        CANDIDATE_A.read_text()
        + "\n"
        + CANDIDATE_A.read_text().replace("src/decode.c", "src/config.c")
    )

    candidate = _record(mission, finding, diff)

    assert candidate.policy_status == PatchPolicyStatus.REJECTED_TOO_MANY_FILES.value
    assert "too many files changed" in candidate.policy_detail


def test_too_many_lines_violation_is_named(mission, finding):
    walk_to(mission, MissionState.PATCH)
    mission.policy["patch"]["max_lines_changed"] = 3
    mission.save(update_fields=["policy"])

    candidate = _record(mission, finding, CANDIDATE_A.read_text())

    assert candidate.policy_status == PatchPolicyStatus.REJECTED_TOO_MANY_LINES.value
    assert "lines=7/3" in candidate.policy_detail


def test_malformed_diff_violation_is_named(mission, finding):
    walk_to(mission, MissionState.PATCH)

    candidate = _record(mission, finding, "not a unified diff")

    assert candidate.policy_status == PatchPolicyStatus.REJECTED_MALFORMED_DIFF.value
    assert "malformed unified diff" in candidate.policy_detail


def test_policy_rejected_candidate_cannot_be_verified(mission, finding):
    walk_to(mission, MissionState.PATCH)
    candidate = _record(
        mission,
        finding,
        CANDIDATE_A.read_text().replace("src/decode.c", "CMakeLists.txt"),
    )
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)

    with pytest.raises(InvalidStateTransitionError) as excinfo:
        candidates.record_verification(
            mission.id,
            patch_id=candidate.id,
            gates=gate_matrix(),
            started_at=NOW,
            finished_at=NOW,
            trace_id=TRACE,
            now=NOW,
        )

    assert candidate.policy_status in str(excinfo.value)


def test_empty_allowlist_is_not_a_silent_pass():
    decision = evaluate_patch_policy(
        CANDIDATE_A.read_text(),
        PatchPolicy(allowed_paths=[], max_files_changed=1, max_lines_changed=40),
    )

    assert decision.status is PatchPolicyStatus.REJECTED_PATH_NOT_ALLOWED
    assert "allowed_paths=<none>" in decision.detail


def _policy_events(mission):
    return list(
        MissionEvent.objects.filter(
            mission=mission,
            type=EventType.PATCH_POLICY_EVALUATED.value,
        ).order_by("sequence")
    )
