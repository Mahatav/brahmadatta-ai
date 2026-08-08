"""D-045, the half that cannot live in `contracts/`.

BUG-004(c): dropping a `REJECTED` record reaches `VERIFIED`. That is undetectable from
inside a pure function handed the set — no validation in `contracts/` closes it. The
guarantee lives at the database boundary, and these are the tests that fail if a future
refactor quietly moves it back out.
"""

from __future__ import annotations

import inspect

import pytest

from contracts.enums import (
    GateStatus,
    MissionState,
    PatchPolicyStatus,
    PatchProvenance,
    Verdict,
)
from contracts.errors import VerificationRequiredError
from missions.models import VerificationRecord
from orchestrator import candidates, repository, transitions
from orchestrator.tests.conftest import (
    CANDIDATE_A,
    CANDIDATE_B,
    NOW,
    TRACE,
    gate_matrix,
    walk_to,
)

pytestmark = pytest.mark.django_db(transaction=True)


def _two_candidates(mission, finding):
    made = []
    for path in (CANDIDATE_A, CANDIDATE_B):
        made.append(
            candidates.record_patch_candidate(
                mission.id,
                finding_id=finding.id,
                provenance=PatchProvenance.OPERATOR_SUPPLIED,
                diff=path.read_text(),
                files_changed=1,
                lines_changed=8,
                policy_status=PatchPolicyStatus.ACCEPTED,
                trace_id=TRACE,
                now=NOW,
            )
        )
    return made


def test_transition_takes_no_verification_argument_from_its_caller():
    """The structural form of the rule.

    If `transition` accepted the records, a caller could hand it a filtered set and the
    guard would have no way to know. It does not: the only parameters are the mission,
    the target, and bookkeeping. The records are loaded inside.
    """
    parameters = set(inspect.signature(transitions.transition).parameters)
    assert "verifications" not in parameters
    assert "verification_records" not in parameters
    assert parameters == {"mission_id", "target", "trace_id", "reason", "now"}


def test_the_records_are_loaded_by_mission_with_no_filter():
    """`load_verifications` is the completeness guarantee, so it has to be total.

    A `.exclude(...)`, a `.filter(verdict=...)` or a slice anywhere in it would
    reintroduce BUG-004(c) with nothing to announce it. Read structurally rather than
    trusting the docstring.
    """
    source = inspect.getsource(repository.load_verifications)
    for narrowing in (".exclude(", "verdict=", "[:", ".first()", ".last()"):
        assert narrowing not in source, (
            f"load_verifications contains {narrowing!r}. It is the completeness "
            f"guarantee for invariant B; anything that narrows the set reintroduces "
            f"BUG-004(c) with no test failure to announce it."
        )


def test_a_dropped_rejection_cannot_reach_verified(mission, finding):
    """The case QA reproduced. Two candidates, one VERIFIED and one HUMAN_REVIEW; the
    mission verdict is HUMAN_REVIEW. A caller that wanted VERIFIED would have to hide
    the second record — and there is no parameter to hide it through.
    """
    walk_to(mission, MissionState.PATCH)
    first, second = _two_candidates(mission, finding)
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)

    candidates.record_verification(
        mission.id,
        patch_id=first.id,
        gates=gate_matrix(),
        started_at=NOW,
        finished_at=NOW,
        trace_id=TRACE,
        now=NOW,
    )
    candidates.record_verification(
        mission.id,
        patch_id=second.id,
        gates=gate_matrix(regression=GateStatus.NOT_RUN),
        started_at=NOW,
        finished_at=NOW,
        trace_id=TRACE,
        now=NOW,
    )

    transitions.transition(mission.id, MissionState.EXPORTING, trace_id=TRACE, now=NOW)

    with pytest.raises(VerificationRequiredError):
        transitions.transition(
            mission.id, MissionState.VERIFIED, trace_id=TRACE, now=NOW
        )

    # And the honest outcome is reachable.
    transitions.transition(
        mission.id, MissionState.HUMAN_REVIEW, trace_id=TRACE, now=NOW
    )
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.HUMAN_REVIEW
    assert mission.verdict == Verdict.HUMAN_REVIEW_REQUIRED.value


def test_a_verdict_state_is_refused_against_an_empty_database(mission):
    """#77's original case, now against real rows rather than a default argument."""
    walk_to(mission, MissionState.EXPORTING)
    assert VerificationRecord.objects.filter(mission=mission).count() == 0

    for target in (
        MissionState.VERIFIED,
        MissionState.REJECTED,
        MissionState.HUMAN_REVIEW,
    ):
        with pytest.raises(VerificationRequiredError):
            transitions.transition(mission.id, target, trace_id=TRACE, now=NOW)

    mission.refresh_from_db()
    assert mission.state_enum is MissionState.EXPORTING


def test_another_missions_records_are_never_loaded(mission, finding, db):
    """The mission binding, exercised through the loader rather than the guard."""
    from missions.models import Mission

    other = Mission.objects.create(
        name="unrelated",
        repository_ref="file:///demo/repositories/other",
        adapter="C_CMAKE_CTEST",
        policy={},
    )
    walk_to(mission, MissionState.PATCH)
    first, _ = _two_candidates(mission, finding)
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)
    candidates.record_verification(
        mission.id,
        patch_id=first.id,
        gates=gate_matrix(),
        started_at=NOW,
        finished_at=NOW,
        trace_id=TRACE,
        now=NOW,
    )

    assert len(repository.load_verifications(mission.id)) == 1
    assert repository.load_verifications(other.id) == []
