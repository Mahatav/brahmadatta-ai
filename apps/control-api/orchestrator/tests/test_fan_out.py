"""#80 — `PATCH` produces N candidates, `VERIFY` produces N verification runs.

**Scope, stated plainly.** This exercises the fan-out *data and state path* end to end:
two real candidate diffs from the committed demo target (#74), two persisted candidates,
two persisted verification runs each with its own gate matrix and its own derived
verdict, and a mission verdict derived from the set. It does **not** compile anything,
run ctest, or run a fuzzer. The gate matrices are supplied by the test, standing in for
what the verifier (#38) will produce. What is demonstrated is that the state machine,
the persistence and the derivation carry two candidates with different outcomes to a
single terminal state — not that the toolchain produces those outcomes.

The stage timeline stays linear throughout: `PATCH → VERIFY → EXPORTING → VERIFIED`,
one visit each, no cyclic transition. That is the fan-out decision (b) from the
architecture spec §2.3, and it is asserted below rather than assumed.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from contracts.enums import (
    GateStatus,
    IsolationMode,
    MissionState,
    PatchPolicyStatus,
    PatchProvenance,
    Verdict,
)
from contracts.schemas.common import ResourceUsage
from contracts.schemas.evidence import (
    CandidateVerdict,
    EvidenceBundle,
    MissionVerdictSummary,
)
from missions.models import MissionEvent, PatchCandidate, VerificationRecord
from orchestrator import candidates, repository, transitions
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


def test_two_candidates_one_verified_one_rejected_from_one_operator_action(
    mission, finding
):
    """The D6 kill criterion's shape (P0 cut §3 steps 6 and 7).

    Candidate A is the correct bounds fix; candidate B fixes the crash by truncating
    tab expansion, which breaks the tab-expansion test. Both are committed `.patch`
    files in `demo/repositories/pktcfg/patches/`, so this runs today with no model.
    """
    walk_to(mission, MissionState.PATCH)

    candidate_a = candidates.record_patch_candidate(
        mission.id,
        finding_id=finding.id,
        provenance=PatchProvenance.OPERATOR_SUPPLIED,
        diff=CANDIDATE_A.read_text(),
        files_changed=1,
        lines_changed=7,
        policy_status=PatchPolicyStatus.ACCEPTED,
        trace_id=TRACE,
        now=NOW,
    )
    candidate_b = candidates.record_patch_candidate(
        mission.id,
        finding_id=finding.id,
        provenance=PatchProvenance.OPERATOR_SUPPLIED,
        diff=CANDIDATE_B.read_text(),
        files_changed=1,
        lines_changed=6,
        policy_status=PatchPolicyStatus.ACCEPTED,
        trace_id=TRACE,
        now=NOW,
    )
    assert PatchCandidate.objects.filter(mission=mission).count() == 2

    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)

    # A holds. B eliminates the reproducer but fails the regression suite — which is
    # exactly what makes it the honest rejection rather than a strawman.
    candidates.record_verification(
        mission.id,
        patch_id=candidate_a.id,
        gates=gate_matrix(),
        started_at=NOW,
        finished_at=NOW,
        trace_id=TRACE,
        now=NOW,
    )
    candidates.record_verification(
        mission.id,
        patch_id=candidate_b.id,
        gates=gate_matrix(regression=GateStatus.FAIL),
        started_at=NOW,
        finished_at=NOW,
        trace_id=TRACE,
        now=NOW,
    )

    records = VerificationRecord.objects.filter(mission=mission).order_by("started_at")
    assert records.count() == 2
    assert {r.verdict for r in records} == {
        Verdict.VERIFIED.value,
        Verdict.REJECTED.value,
    }

    transitions.transition(mission.id, MissionState.EXPORTING, trace_id=TRACE, now=NOW)
    transitions.transition(mission.id, MissionState.VERIFIED, trace_id=TRACE, now=NOW)

    mission.refresh_from_db()
    assert mission.state_enum is MissionState.VERIFIED
    assert mission.verdict == Verdict.VERIFIED.value


def test_the_stage_timeline_stays_linear(mission, finding):
    """Decision (b), not (a): the fan-out is data, not a loop.

    A cyclic `VERIFY -> PATCH` edge would make the Command Center render
    "PATCH (2nd time)" and break `sequence` as a monotone progress indicator. Each
    state appears at most once in the mission's own event history.
    """
    _run_the_demo_pair(mission, finding)

    entered = [
        event.state
        for event in MissionEvent.objects.filter(
            mission=mission, type="STATE_CHANGED"
        ).order_by("sequence")
    ]
    duplicates = {state for state in entered if entered.count(state) > 1}
    assert not duplicates, f"a state was entered more than once: {sorted(duplicates)}"
    assert entered.count(MissionState.PATCH.value) == 1
    assert entered.count(MissionState.VERIFY.value) == 1
    assert entered.count(MissionState.EXPORTING.value) == 1


def test_the_event_sequence_is_gap_free(mission, finding):
    """`sequence` is the SSE `id:` field; a client detects a gap by arithmetic."""
    _run_the_demo_pair(mission, finding)
    sequences = list(
        MissionEvent.objects.filter(mission=mission)
        .order_by("sequence")
        .values_list("sequence", flat=True)
    )
    assert sequences == list(range(1, len(sequences) + 1))


def test_the_evidence_bundle_carries_both_records_and_names_the_recommendation(
    mission, finding
):
    """D-048. The bundle shows the rejection beside the verified patch, and says which
    diff we stand behind — derived from the records, not chosen by hand."""
    candidate_a, candidate_b = _run_the_demo_pair(mission, finding)

    verifications = repository.load_verifications(mission.id)
    patches = [
        _patch_schema(row)
        for row in PatchCandidate.objects.filter(mission=mission).order_by("created_at")
    ]
    by_patch = {record.patch_id: record for record in verifications}

    summary = MissionVerdictSummary(
        mission_verdict=Verdict.VERIFIED,
        candidates=[
            CandidateVerdict(
                patch_id=patch.id,
                verification_id=by_patch[patch.id].id,
                verdict=by_patch[patch.id].verdict,
                provenance=patch.provenance,
            )
            for patch in patches
        ],
        verified_count=1,
        rejected_count=1,
    )

    bundle = EvidenceBundle(
        mission_id=mission.id,
        generated_at=NOW,
        snapshot_sha256=SNAPSHOT_SHA,
        authorization_statement="I am authorized to test this repository.",
        patches=patches,
        verifications=verifications,
        verdict_summary=summary,
        recommended_patch_id=candidate_a.id,
        resource_usage=ResourceUsage(
            cpu_seconds=1.0, peak_memory_mb=1.0, wall_seconds=1.0, sandbox_count=1
        ),
        isolation_mode=IsolationMode.ROOTLESS_CONTAINER,
    )

    assert len(bundle.verifications) == 2
    assert bundle.recommended_patch_id == candidate_a.id
    assert {record.verdict for record in bundle.verifications} == {
        Verdict.VERIFIED,
        Verdict.REJECTED,
    }

    # And the rejected candidate cannot be recommended. This is the D-048 point: the
    # field is derived and validated, so it cannot name the diff we did not stand
    # behind — including at 2am on D7.
    fields = bundle.model_dump()
    fields["recommended_patch_id"] = candidate_b.id
    with pytest.raises(ValidationError) as excinfo:
        EvidenceBundle(**fields)
    assert "no VERIFIED verification record" in str(excinfo.value)


def _run_the_demo_pair(mission, finding):
    walk_to(mission, MissionState.PATCH)
    candidate_a = candidates.record_patch_candidate(
        mission.id,
        finding_id=finding.id,
        provenance=PatchProvenance.OPERATOR_SUPPLIED,
        diff=CANDIDATE_A.read_text(),
        files_changed=1,
        lines_changed=7,
        policy_status=PatchPolicyStatus.ACCEPTED,
        trace_id=TRACE,
        now=NOW,
    )
    candidate_b = candidates.record_patch_candidate(
        mission.id,
        finding_id=finding.id,
        provenance=PatchProvenance.OPERATOR_SUPPLIED,
        diff=CANDIDATE_B.read_text(),
        files_changed=1,
        lines_changed=6,
        policy_status=PatchPolicyStatus.ACCEPTED,
        trace_id=TRACE,
        now=NOW,
    )
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)
    candidates.record_verification(
        mission.id,
        patch_id=candidate_a.id,
        gates=gate_matrix(),
        started_at=NOW,
        finished_at=NOW,
        trace_id=TRACE,
        now=NOW,
    )
    candidates.record_verification(
        mission.id,
        patch_id=candidate_b.id,
        gates=gate_matrix(regression=GateStatus.FAIL),
        started_at=NOW,
        finished_at=NOW,
        trace_id=TRACE,
        now=NOW,
    )
    transitions.transition(mission.id, MissionState.EXPORTING, trace_id=TRACE, now=NOW)
    transitions.transition(mission.id, MissionState.VERIFIED, trace_id=TRACE, now=NOW)
    mission.refresh_from_db()
    return candidate_a, candidate_b


def _patch_schema(row):
    from contracts.schemas.evidence import PatchCandidate as PatchCandidateSchema

    return PatchCandidateSchema(
        id=row.id,
        mission_id=row.mission_id,
        finding_id=row.finding_id,
        provenance=row.provenance,
        model=row.model_provenance,
        diff=row.diff,
        files_changed=row.files_changed,
        lines_changed=row.lines_changed,
        policy_status=row.policy_status,
        policy_detail=row.policy_detail,
        rationale=row.rationale,
        created_at=row.created_at,
    )
