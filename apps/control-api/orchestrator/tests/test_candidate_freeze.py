"""D-046 — the candidate set freezes when VERIFY begins.

The CTO named the test in this file. It is here rather than in `contracts/tests/`
because the enforcement is a column, not a function: `Mission.verification_started_at`,
read under the mission row lock. A contract-level test could only exercise the
*statement* of the rule, and the statement is not what stops anyone.
"""

from __future__ import annotations

import pytest

from contracts.enums import MissionState, PatchPolicyStatus, PatchProvenance
from contracts.errors import CandidateSetFrozenError
from missions.models import PatchCandidate
from orchestrator import candidates
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
        files_changed=1,
        lines_changed=len([line for line in diff.splitlines() if line[:1] in "+-"]),
        policy_status=PatchPolicyStatus.ACCEPTED,
        trace_id=TRACE,
        now=NOW,
    )


def test_cannot_add_candidate_after_verification_starts(mission, finding):
    """The named test from D-046.

    Without this, *"add one more candidate and re-verify"* reaches generate-until-pass
    with no transition-table change for a reviewer to catch — the one failure mode here
    that leaves no diff.
    """
    walk_to(mission, MissionState.PATCH)

    first = _record(mission, finding, CANDIDATE_A.read_text())
    second = _record(mission, finding, CANDIDATE_B.read_text())
    assert PatchCandidate.objects.filter(mission=mission).count() == 2

    walk_to_verify(mission)
    candidates.record_verification(
        mission.id,
        patch_id=first.id,
        gates=gate_matrix(),
        started_at=NOW,
        finished_at=NOW,
        trace_id=TRACE,
        now=NOW,
    )

    mission.refresh_from_db()
    assert mission.verification_started_at is not None

    with pytest.raises(CandidateSetFrozenError) as excinfo:
        _record(mission, finding, CANDIDATE_A.read_text())

    assert "candidate set" in str(excinfo.value)
    assert PatchCandidate.objects.filter(mission=mission).count() == 2
    assert second.id in set(
        PatchCandidate.objects.filter(mission=mission).values_list("id", flat=True)
    )


def test_the_freeze_is_a_column_not_a_convention(mission, finding):
    """Reading the mechanism directly: the refusal survives a caller that never touches
    `assert_candidate_set_open` and goes straight at the recorder."""
    walk_to(mission, MissionState.PATCH)
    first = _record(mission, finding, CANDIDATE_A.read_text())
    walk_to_verify(mission)
    candidates.record_verification(
        mission.id,
        patch_id=first.id,
        gates=gate_matrix(),
        started_at=NOW,
        finished_at=NOW,
        trace_id=TRACE,
        now=NOW,
    )

    mission.refresh_from_db()
    frozen_at = mission.verification_started_at

    with pytest.raises(CandidateSetFrozenError):
        _record(mission, finding, CANDIDATE_B.read_text())

    mission.refresh_from_db()
    # The freeze timestamp is the first verification's, not the latest attempt's — a
    # refused insert must not move the boundary it was refused by.
    assert mission.verification_started_at == frozen_at


def test_a_candidate_before_verification_is_accepted(mission, finding):
    """The freeze must not be so eager that the normal fan-out cannot happen."""
    walk_to(mission, MissionState.PATCH)
    _record(mission, finding, CANDIDATE_A.read_text())
    _record(mission, finding, CANDIDATE_B.read_text())
    assert PatchCandidate.objects.filter(mission=mission).count() == 2

    mission.refresh_from_db()
    assert mission.verification_started_at is None


def walk_to_verify(mission) -> None:
    from orchestrator import transitions

    if mission.state_enum is MissionState.PATCH:
        transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)
        mission.refresh_from_db()
