"""SEC-16 — `transitions.transition` is the only writer of a mission's lifecycle fields.

The review's judgement was that the previous defence was *"real but not a mechanism, and
one import away from being undone"*, and it proved that by execution rather than
assertion: with two `HUMAN_REVIEW_REQUIRED`-and-`VERIFIED` records on disk, calling the
public `assert_transition` with the set pruned to just the `VERIFIED` one and then
`mission.save()` reached terminal `VERIFIED` in four lines, with no test failing. A
queryset `.update()` walked `CREATED → VERIFIED` in one statement.

Both are closed here at runtime. The review-time half — which is what actually protects
against the future refactor the CTO named — is
`tests/architecture/test_mission_state_single_writer.py`.
"""

from __future__ import annotations

import pytest

from contracts.enums import GateStatus, MissionState, PatchPolicyStatus, PatchProvenance
from contracts.errors import MissionStateWriteError
from missions.models import Mission
from orchestrator import candidates, transitions
from orchestrator.tests.conftest import (
    CANDIDATE_A,
    CANDIDATE_B,
    NOW,
    TRACE,
    gate_matrix,
    walk_to,
)

pytestmark = pytest.mark.django_db(transaction=True)


def test_mission_state_cannot_be_written_by_save(mission):
    """The second half of the review's exploit: `assert_transition` may have been
    talked into saying yes, but the write itself now refuses."""
    walk_to(mission, MissionState.BASELINE)

    mission.state = MissionState.VERIFIED.value
    with pytest.raises(MissionStateWriteError):
        mission.save()

    mission.refresh_from_db()
    assert mission.state_enum is MissionState.BASELINE


def test_mission_state_cannot_be_written_by_a_queryset_update(mission):
    """`.update()` never calls `save()`. Both doors have to be shut or neither is."""
    with pytest.raises(MissionStateWriteError):
        Mission.objects.filter(pk=mission.id).update(
            state=MissionState.VERIFIED.value, verdict="VERIFIED"
        )

    mission.refresh_from_db()
    assert mission.state_enum is MissionState.CREATED
    assert mission.verdict is None


@pytest.mark.parametrize(
    "field", ["state", "paused_from", "verdict", "verification_started_at"]
)
def test_every_lifecycle_field_is_guarded(field: str):
    """Not just `state`. `paused_from` carries D-047 and `verification_started_at`
    carries D-046; a guard that covered only the first would leave both rulings
    writable from anywhere."""
    from missions.lifecycle import LIFECYCLE_FIELDS

    assert field in LIFECYCLE_FIELDS


def test_the_pruned_set_exploit_no_longer_reaches_a_terminal_state(mission, finding):
    """The review's exploit, end to end, as it was executed.

    Records on disk are [VERIFIED, HUMAN_REVIEW_REQUIRED], which derive HUMAN_REVIEW.
    The honestly-fed guard refuses VERIFIED. The pruned-set call still persuades the
    guard — that is inherent and is why the completeness guarantee is not in the guard —
    but the write that used to follow it now raises.
    """
    from contracts.state_machine import assert_transition
    from orchestrator import repository

    walk_to(mission, MissionState.PATCH)
    first = candidates.record_patch_candidate(
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
    second = candidates.record_patch_candidate(
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
    for patch, gates in (
        (first, gate_matrix()),
        (second, gate_matrix(regression=GateStatus.NOT_RUN)),
    ):
        candidates.record_verification(
            mission.id,
            patch_id=patch.id,
            gates=gates,
            started_at=NOW,
            finished_at=NOW,
            trace_id=TRACE,
            now=NOW,
        )
    transitions.transition(mission.id, MissionState.EXPORTING, trace_id=TRACE, now=NOW)
    mission.refresh_from_db()

    records = repository.load_verifications(mission.id)
    assert len(records) == 2

    pruned = [r for r in records if r.verdict.value == "VERIFIED"]
    assert len(pruned) == 1

    # A real authorization, so the only thing under test is the verdict guard. Feeding
    # None here would make the guard refuse for an unrelated reason and prove nothing.
    authorization = repository.load_active_authorization(mission, NOW)
    assert authorization is not None

    # The guard, fed a pruned set, still says yes. That is the property no in-function
    # validation can fix, and it is exactly why the write is guarded instead.
    assert_transition(
        MissionState.EXPORTING,
        MissionState.VERIFIED,
        authorization,
        NOW,
        repository.latest_snapshot_sha256(mission),
        pruned,
        mission_id=mission.id,
        paused_from=None,
    )

    mission.state = MissionState.VERIFIED.value
    mission.verdict = "VERIFIED"
    with pytest.raises(MissionStateWriteError):
        mission.save()

    mission.refresh_from_db()
    assert mission.state_enum is MissionState.EXPORTING
    assert mission.verdict is None


def test_an_ordinary_data_edit_is_not_refused(mission):
    """The guard is narrow on purpose. A blanket refusal is the kind people route
    around, and `name`/`policy` are ordinary data."""
    mission.name = "renamed"
    mission.save(update_fields=["name", "updated_at"])

    mission.refresh_from_db()
    assert mission.name == "renamed"

    Mission.objects.filter(pk=mission.id).update(repository_ref="file:///elsewhere")
    mission.refresh_from_db()
    assert mission.repository_ref == "file:///elsewhere"
