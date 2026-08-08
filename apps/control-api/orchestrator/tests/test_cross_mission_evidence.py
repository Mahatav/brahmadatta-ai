"""SEC-15 — a candidate from another mission cannot be verified into this one.

## The attack, and why every guard before it behaved correctly

D-046 freezes a mission's *candidate set*. On its own it does not freeze the set of
candidates that can be verified **into** that mission, because the verification writer
never asked which mission a candidate came from.

So: mission A owns exactly one candidate and it was `REJECTED`. A is frozen, so
`record_patch_candidate` correctly refuses another. Create a second mission — an
ordinary operator action — add a candidate there, and verify *that* candidate into A. A
reaches terminal `VERIFIED`.

No forged record. No direct database write. No transition-table change. No convention
broken. `assert_verdict_is_evidenced` sees a real `VerificationRecord` whose `mission_id`
genuinely is A's — the mission-binding check is bypassed not by forging a record but by
**relabelling one at creation time**, and that check reads the column the writer got to
set. A check downstream of a writer can only confirm the label the writer chose.

That is generate-until-pass with one extra step. It is HIGH today only because the HTTP
routers return 501; it is Critical the moment a route supplies a request-provided
`patch_id`.
"""

from __future__ import annotations

import pytest

from contracts.enums import (
    GateStatus,
    LanguageAdapter,
    MissionState,
    PatchPolicyStatus,
    PatchProvenance,
    Verdict,
)
from contracts.errors import CrossMissionEvidenceError
from missions.models import Authorization, Finding, Mission, Snapshot, VerificationRecord
from orchestrator import candidates, transitions
from orchestrator.tests.conftest import (
    CANDIDATE_A,
    CANDIDATE_B,
    NOW,
    SNAPSHOT_SHA,
    TRACE,
    gate_matrix,
    walk_to,
)

pytestmark = pytest.mark.django_db(transaction=True)


def _second_mission() -> tuple[Mission, Finding]:
    """An ordinary second mission. Creating one is a normal operator action."""
    from datetime import timedelta

    other = Mission.objects.create(
        name="attacker's own mission",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    Authorization.objects.create(
        mission=other,
        statement="I am authorized to test this repository on behalf of the owner.",
        granted_by="Mahatav Arora",
        granted_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(hours=8),
        repository_ref="file:///demo/repositories/pktcfg",
    )
    Snapshot.objects.create(
        mission=other, archive_sha256=SNAPSHOT_SHA, file_count=31, bytes_total=120_000
    )
    finding = Finding.objects.create(
        mission=other,
        category="HEAP_BUFFER_OVERFLOW",
        severity="HIGH",
        tool="ADDRESS_SANITIZER",
        discovery_method="FUZZING_CAMPAIGN",
        file_path="src/decode.c",
        line=74,
        fingerprint="pktcfg-literal-tab-overflow",
        reproducible=True,
        title="heap-buffer-overflow expanding a literal tab",
        detected_at=NOW,
    )
    return other, finding


def _candidate(mission, finding, path):
    return candidates.record_patch_candidate(
        mission.id,
        finding_id=finding.id,
        provenance=PatchProvenance.OPERATOR_SUPPLIED,
        diff=path.read_text(),
        files_changed=1,
        lines_changed=7,
        policy_status=PatchPolicyStatus.ACCEPTED,
        trace_id=TRACE,
        now=NOW,
    )


def test_a_candidate_from_another_mission_cannot_be_verified_into_this_one(
    mission, finding
):
    """The named test from SEC-15, building the exact two-mission shape."""
    # Mission A: one candidate, and it is the one that fails the regression suite.
    walk_to(mission, MissionState.PATCH)
    a_candidate = _candidate(mission, finding, CANDIDATE_B)
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)
    candidates.record_verification(
        mission.id,
        patch_id=a_candidate.id,
        gates=gate_matrix(regression=GateStatus.FAIL),
        started_at=NOW,
        finished_at=NOW,
        trace_id=TRACE,
        now=NOW,
    )

    mission.refresh_from_db()
    assert mission.verification_started_at is not None, "mission A must be frozen"

    # Mission B: an ordinary second mission with a candidate that passes.
    other, other_finding = _second_mission()
    walk_to(other, MissionState.PATCH)
    b_candidate = _candidate(other, other_finding, CANDIDATE_A)

    # The attack: verify B's candidate into A.
    with pytest.raises(CrossMissionEvidenceError) as excinfo:
        candidates.record_verification(
            mission.id,
            patch_id=b_candidate.id,
            gates=gate_matrix(),
            started_at=NOW,
            finished_at=NOW,
            trace_id=TRACE,
            now=NOW,
        )
    assert "belongs to mission" in str(excinfo.value)

    # Nothing was written, and A's verdict is still the one its own evidence supports.
    assert VerificationRecord.objects.filter(mission=mission).count() == 1
    transitions.transition(mission.id, MissionState.EXPORTING, trace_id=TRACE, now=NOW)
    transitions.transition(mission.id, MissionState.REJECTED, trace_id=TRACE, now=NOW)

    mission.refresh_from_db()
    assert mission.state_enum is MissionState.REJECTED
    assert mission.verdict == Verdict.REJECTED.value


def test_the_frozen_mission_cannot_reach_verified_by_borrowing_evidence(
    mission, finding
):
    """The consequence, asserted directly: A must not be able to become VERIFIED."""
    walk_to(mission, MissionState.PATCH)
    a_candidate = _candidate(mission, finding, CANDIDATE_B)
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)
    candidates.record_verification(
        mission.id,
        patch_id=a_candidate.id,
        gates=gate_matrix(regression=GateStatus.FAIL),
        started_at=NOW,
        finished_at=NOW,
        trace_id=TRACE,
        now=NOW,
    )

    other, other_finding = _second_mission()
    walk_to(other, MissionState.PATCH)
    b_candidate = _candidate(other, other_finding, CANDIDATE_A)

    with pytest.raises(CrossMissionEvidenceError):
        candidates.record_verification(
            mission.id,
            patch_id=b_candidate.id,
            gates=gate_matrix(),
            started_at=NOW,
            finished_at=NOW,
            trace_id=TRACE,
            now=NOW,
        )

    transitions.transition(mission.id, MissionState.EXPORTING, trace_id=TRACE, now=NOW)
    from contracts.errors import VerificationRequiredError

    with pytest.raises(VerificationRequiredError):
        transitions.transition(mission.id, MissionState.VERIFIED, trace_id=TRACE, now=NOW)


def test_a_verification_cannot_be_recorded_without_an_active_authorization(
    mission, finding
):
    """SEC-21. The freeze is a side effect of this function, so an unguarded call sets
    it on a mission that has not reached PATCH — closing the candidate set before there
    are any candidates."""
    from contracts.errors import AuthorizationRequiredError

    walk_to(mission, MissionState.PATCH)
    candidate = _candidate(mission, finding, CANDIDATE_A)
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)

    Authorization.objects.filter(mission=mission).update(revoked_at=NOW)

    with pytest.raises(AuthorizationRequiredError):
        candidates.record_verification(
            mission.id,
            patch_id=candidate.id,
            gates=gate_matrix(),
            started_at=NOW,
            finished_at=NOW,
            trace_id=TRACE,
            now=NOW,
        )

    mission.refresh_from_db()
    assert mission.verification_started_at is None, (
        "a refused verification must not close the candidate set"
    )


def test_a_verification_cannot_be_recorded_before_the_mission_reaches_verify(
    mission, finding
):
    """SEC-21, the other half: recording one in CREATED is a denial of service on the
    mission's own purpose."""
    from contracts.errors import InvalidStateTransitionError

    walk_to(mission, MissionState.PATCH)
    candidate = _candidate(mission, finding, CANDIDATE_A)

    with pytest.raises(InvalidStateTransitionError):
        candidates.record_verification(
            mission.id,
            patch_id=candidate.id,
            gates=gate_matrix(),
            started_at=NOW,
            finished_at=NOW,
            trace_id=TRACE,
            now=NOW,
        )

    mission.refresh_from_db()
    assert mission.verification_started_at is None


def test_a_candidate_can_only_be_verified_once(mission, finding):
    """SEC-23(a). The property held under review but had no test of its own, so it
    survived only until someone changed OneToOneField to ForeignKey for a plausible
    reason. Re-verifying until it passes is D-046's failure at the other end."""
    from django.db import IntegrityError

    walk_to(mission, MissionState.PATCH)
    candidate = _candidate(mission, finding, CANDIDATE_B)
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)

    candidates.record_verification(
        mission.id,
        patch_id=candidate.id,
        gates=gate_matrix(regression=GateStatus.FAIL),
        started_at=NOW,
        finished_at=NOW,
        trace_id=TRACE,
        now=NOW,
    )
    with pytest.raises(IntegrityError):
        candidates.record_verification(
            mission.id,
            patch_id=candidate.id,
            gates=gate_matrix(),
            started_at=NOW,
            finished_at=NOW,
            trace_id=TRACE,
            now=NOW,
        )
