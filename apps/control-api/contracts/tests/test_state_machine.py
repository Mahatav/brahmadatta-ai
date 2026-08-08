"""The authorization gate and the transition table.

The hard constraint under test: *a mission stage must be unable to run without an
authorization record*. Every stage but AUTHORIZE is checked individually, because a
gate that covers eight of nine stages is not a gate.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from contracts.authorization import AuthorizationRecord
from contracts.enums import (
    EvidenceSource,
    GateName,
    GateStatus,
    MissionStage,
    MissionState,
    PatchProvenance,
    Verdict,
)
from contracts.errors import (
    AuthorizationRequiredError,
    CandidateSetFrozenError,
    InvalidStateTransitionError,
    VerificationRequiredError,
)
from contracts.schemas.evidence import CandidateVerdict, VerificationRecord
from contracts.state_machine import (
    PAUSABLE_STATES,
    STAGES_REQUIRING_AUTHORIZATION,
    allowed_transitions,
    assert_candidate_set_open,
    assert_resume,
    assert_stage_can_run,
    assert_transition,
    derive_mission_outcome,
)
from contracts.verdict import GateMatrix, GateResult

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
SNAPSHOT = "a" * 64
OTHER_SNAPSHOT = "b" * 64

#: The mission under test. `assert_transition` takes it as a required keyword-only
#: argument so the verdict guard can bind every record it is shown to one mission
#: (D-045); there is no default, so nobody transitions "a mission" by accident.
MISSION = UUID("11111111-1111-4111-8111-111111111111")
OTHER_MISSION = UUID("22222222-2222-4222-8222-222222222222")


def make_authorization(**overrides) -> AuthorizationRecord:
    data = {
        "id": uuid4(),
        "mission_id": uuid4(),
        "statement": "I am authorized to test this repository on behalf of the owner.",
        "granted_by": "Mahatav Arora",
        "granted_at": NOW - timedelta(minutes=5),
        "expires_at": NOW + timedelta(hours=4),
        "repository_ref": "file:///demo/targets/parser-lib",
    }
    data.update(overrides)
    return AuthorizationRecord(**data)


def make_verification(
    regression: GateStatus = GateStatus.PASS,
    verdict: Verdict = Verdict.VERIFIED,
    mission_id: UUID = MISSION,
    record_id: UUID | None = None,
) -> VerificationRecord:
    def gate(name: GateName, status: GateStatus) -> GateResult:
        source = (
            EvidenceSource.REPLAYED_ARTIFACT
            if status is GateStatus.NOT_RUN
            else EvidenceSource.TOOL_EXECUTION
        )
        return GateResult(
            name=name, status=status, evidence_source=source, tool="ctest 3.28.3"
        )

    return VerificationRecord(
        id=record_id or uuid4(),
        mission_id=mission_id,
        patch_id=uuid4(),
        gates=GateMatrix(
            compile=gate(GateName.COMPILE, GateStatus.PASS),
            reproducer_eliminated=gate(GateName.REPRODUCER_ELIMINATED, GateStatus.PASS),
            regression_preserved=gate(GateName.REGRESSION_PRESERVED, regression),
        ),
        verdict=verdict,
        started_at=NOW,
        finished_at=NOW + timedelta(seconds=30),
    )


@pytest.mark.parametrize("stage", sorted(STAGES_REQUIRING_AUTHORIZATION))
def test_no_stage_runs_without_an_authorization_record(stage: MissionStage):
    with pytest.raises(AuthorizationRequiredError):
        assert_stage_can_run(stage, None, NOW)


def test_every_stage_except_authorize_requires_authorization():
    assert STAGES_REQUIRING_AUTHORIZATION == frozenset(
        set(MissionStage) - {MissionStage.AUTHORIZE}
    )


def test_recording_the_authorization_itself_needs_no_prior_record():
    assert_stage_can_run(MissionStage.AUTHORIZE, None, NOW)


@pytest.mark.parametrize("stage", sorted(STAGES_REQUIRING_AUTHORIZATION))
def test_every_stage_runs_with_an_active_record(stage: MissionStage):
    assert_stage_can_run(stage, make_authorization(), NOW)


def test_expired_authorization_is_refused():
    expired = make_authorization(expires_at=NOW - timedelta(seconds=1))
    with pytest.raises(AuthorizationRequiredError):
        assert_stage_can_run(MissionStage.BASELINE, expired, NOW)


def test_revoked_authorization_is_refused():
    revoked = make_authorization(revoked_at=NOW - timedelta(minutes=1))
    with pytest.raises(AuthorizationRequiredError):
        assert_stage_can_run(MissionStage.STRESS_TEST, revoked, NOW)


def test_authorization_bound_to_another_snapshot_is_refused():
    """Swapping the archive after authorization does not inherit the authority."""
    bound = make_authorization(snapshot_sha256=SNAPSHOT)
    assert_stage_can_run(MissionStage.BASELINE, bound, NOW, SNAPSHOT)
    with pytest.raises(AuthorizationRequiredError):
        assert_stage_can_run(MissionStage.BASELINE, bound, NOW, OTHER_SNAPSHOT)


def test_unbound_authorization_covers_the_first_snapshot_it_sees():
    assert_stage_can_run(MissionStage.BASELINE, make_authorization(), NOW, SNAPSHOT)


# --- transitions ---------------------------------------------------------------


def test_happy_path_walks_end_to_end():
    auth = make_authorization()
    path = [
        (MissionState.CREATED, MissionState.AUTHORIZED),
        (MissionState.AUTHORIZED, MissionState.SNAPSHOTTED),
        (MissionState.SNAPSHOTTED, MissionState.VALIDATING),
        (MissionState.VALIDATING, MissionState.BASELINE),
        (MissionState.BASELINE, MissionState.TRIAGE),
        (MissionState.TRIAGE, MissionState.STRESS_TEST),
        (MissionState.STRESS_TEST, MissionState.CORRELATE),
        (MissionState.CORRELATE, MissionState.PATCH),
        (MissionState.PATCH, MissionState.VERIFY),
        (MissionState.VERIFY, MissionState.EXPORTING),
    ]
    for current, target in path:
        assert_transition(current, target, auth, NOW, mission_id=MISSION)
    assert_transition(
        MissionState.EXPORTING,
        MissionState.VERIFIED,
        auth,
        NOW,
        verifications=[make_verification()],
        mission_id=MISSION,
    )


def test_work_states_are_unreachable_without_authorization():
    for target in (
        MissionState.SNAPSHOTTED,
        MissionState.VALIDATING,
        MissionState.BASELINE,
        MissionState.TRIAGE,
        MissionState.STRESS_TEST,
        MissionState.CORRELATE,
        MissionState.PATCH,
        MissionState.VERIFY,
        MissionState.EXPORTING,
    ):
        source = next(
            state
            for state, targets in _incoming_sources().items()
            if target in targets and state is not MissionState.PAUSED
        )
        with pytest.raises(AuthorizationRequiredError):
            assert_transition(source, target, None, NOW, mission_id=MISSION)


def _incoming_sources():
    from contracts.state_machine import TRANSITIONS

    return TRANSITIONS


def test_terminal_verdict_states_require_authorization():
    with pytest.raises((AuthorizationRequiredError, VerificationRequiredError)):
        assert_transition(
            MissionState.EXPORTING,
            MissionState.VERIFIED,
            None,
            NOW,
            mission_id=MISSION,
        )


# --- a verdict state must be evidenced -------------------------------------------


@pytest.mark.parametrize(
    "target",
    [MissionState.VERIFIED, MissionState.REJECTED, MissionState.HUMAN_REVIEW],
)
def test_no_verdict_state_without_a_verification_record(target: MissionState):
    """The core invariant: the state a judge reads off the Core cannot be reached
    with nothing behind it."""
    with pytest.raises(VerificationRequiredError):
        assert_transition(
            MissionState.EXPORTING, target, make_authorization(), NOW,
            mission_id=MISSION,
        )


def test_a_verification_record_for_a_different_verdict_does_not_justify_the_state():
    rejected = make_verification(
        regression=GateStatus.FAIL, verdict=Verdict.REJECTED
    )
    with pytest.raises(VerificationRequiredError):
        assert_transition(
            MissionState.EXPORTING,
            MissionState.VERIFIED,
            make_authorization(),
            NOW,
            verifications=[rejected],
            mission_id=MISSION,
        )


def test_a_rejected_verdict_reaches_the_rejected_state():
    rejected = make_verification(regression=GateStatus.FAIL, verdict=Verdict.REJECTED)
    assert_transition(
        MissionState.EXPORTING,
        MissionState.REJECTED,
        make_authorization(),
        NOW,
        verifications=[rejected],
        mission_id=MISSION,
    )


def test_the_demo_pair_reaches_verified_with_the_rejection_still_counted():
    """P0 cut §3 steps 6 and 7 / the D6 gate: one Verified and one Rejected from a
    single operator action. The mission terminal state is derived from both."""
    verified = make_verification()
    rejected = make_verification(regression=GateStatus.FAIL, verdict=Verdict.REJECTED)
    assert_transition(
        MissionState.EXPORTING,
        MissionState.VERIFIED,
        make_authorization(),
        NOW,
        verifications=[verified, rejected],
        mission_id=MISSION,
    )
    # ...and the same pair cannot be presented as an all-clear failure either.
    with pytest.raises(VerificationRequiredError):
        assert_transition(
            MissionState.EXPORTING,
            MissionState.REJECTED,
            make_authorization(),
            NOW,
            verifications=[verified, rejected],
            mission_id=MISSION,
        )


def test_a_run_needing_human_review_outranks_a_success_elsewhere():
    verified = make_verification()
    unrun = make_verification(
        regression=GateStatus.NOT_RUN, verdict=Verdict.HUMAN_REVIEW_REQUIRED
    )
    assert_transition(
        MissionState.EXPORTING,
        MissionState.HUMAN_REVIEW,
        make_authorization(),
        NOW,
        verifications=[verified, unrun],
        mission_id=MISSION,
    )
    with pytest.raises(VerificationRequiredError):
        assert_transition(
            MissionState.EXPORTING,
            MissionState.VERIFIED,
            make_authorization(),
            NOW,
            verifications=[verified, unrun],
            mission_id=MISSION,
        )


def test_human_review_before_verification_needs_no_record():
    """Policy can require a person long before any gate has run."""
    for source in (MissionState.CORRELATE, MissionState.PATCH, MissionState.VERIFY):
        assert_transition(
            source, MissionState.HUMAN_REVIEW, make_authorization(), NOW,
            mission_id=MISSION,
        )


def test_illegal_transition_is_refused_even_with_authorization():
    with pytest.raises(InvalidStateTransitionError):
        assert_transition(
            MissionState.CREATED, MissionState.VERIFIED, make_authorization(), NOW,
            mission_id=MISSION,
        )


def test_skipping_verification_is_refused():
    with pytest.raises(InvalidStateTransitionError):
        assert_transition(
            MissionState.PATCH, MissionState.VERIFIED, make_authorization(), NOW,
            mission_id=MISSION,
        )


def test_cancellation_never_blocked_by_a_missing_authorization():
    """Losing authority is a reason to stop, not a reason to be unable to."""
    assert_transition(
        MissionState.BASELINE, MissionState.CANCELLING, None, NOW, mission_id=MISSION
    )
    assert_transition(
        MissionState.CANCELLING, MissionState.CANCELLED, None, NOW, mission_id=MISSION
    )
    assert_transition(
        MissionState.STRESS_TEST, MissionState.FAILED, None, NOW, mission_id=MISSION
    )


def test_cancelled_has_its_own_posture_and_is_not_shown_as_failed():
    from contracts.enums import MissionPosture, posture_for

    assert posture_for(MissionState.CANCELLED) is MissionPosture.CANCELLED
    assert posture_for(MissionState.CANCELLING) is MissionPosture.CANCELLED
    assert posture_for(MissionState.FAILED) is MissionPosture.FAILED


def test_a_terminal_mission_cannot_be_restarted():
    for state in (MissionState.VERIFIED, MissionState.REJECTED, MissionState.CANCELLED):
        with pytest.raises(InvalidStateTransitionError):
            assert_transition(
                state, MissionState.BASELINE, make_authorization(), NOW,
                mission_id=MISSION,
            )


# --- D-045: the guard checks the records, not just their shape --------------------


class _LookalikeVerification:
    """A stand-in with a `.verdict` attribute and no gate matrix anywhere.

    This is BUG-003 as QA reproduced it. The D1 guard read `record.verdict` off
    whatever it was handed, so this satisfied it — which meant the annotation
    `Sequence[VerificationRecord]` was documentation, not a mechanism.
    """

    def __init__(self, verdict: Verdict = Verdict.VERIFIED) -> None:
        self.verdict = verdict
        self.id = uuid4()
        self.mission_id = MISSION


def test_guard_rejects_a_lookalike_without_a_gate_matrix():
    with pytest.raises(VerificationRequiredError) as excinfo:
        assert_transition(
            MissionState.EXPORTING,
            MissionState.VERIFIED,
            make_authorization(),
            NOW,
            verifications=[_LookalikeVerification()],  # type: ignore[list-item]
            mission_id=MISSION,
        )
    assert "not a VerificationRecord" in str(excinfo.value)


def test_a_candidate_verdict_does_not_satisfy_the_guard():
    """QA's attack case B2 by name: `CandidateVerdict` has a `.verdict` field and is a
    real contract schema, which made it the most plausible accidental substitution."""
    stand_in = CandidateVerdict(
        patch_id=uuid4(),
        verification_id=uuid4(),
        verdict=Verdict.VERIFIED,
        provenance=PatchProvenance.MODEL_GENERATED,
    )
    with pytest.raises(VerificationRequiredError):
        assert_transition(
            MissionState.EXPORTING,
            MissionState.VERIFIED,
            make_authorization(),
            NOW,
            verifications=[stand_in],  # type: ignore[list-item]
            mission_id=MISSION,
        )


def test_another_missions_verification_does_not_justify_this_verdict():
    """BUG-004 case C6d. The D1 guard had no mission id at all, so a VERIFIED record
    belonging to any other mission was accepted."""
    borrowed = make_verification(mission_id=OTHER_MISSION)
    with pytest.raises(VerificationRequiredError) as excinfo:
        assert_transition(
            MissionState.EXPORTING,
            MissionState.VERIFIED,
            make_authorization(),
            NOW,
            verifications=[borrowed],
            mission_id=MISSION,
        )
    assert "does not justify" in str(excinfo.value) or "belongs to mission" in str(
        excinfo.value
    )


def test_the_same_record_supplied_twice_cannot_outvote_one_supplied_once():
    """Without de-duplication, [verified, verified, rejected] is still a majority
    argument someone could reach for. Deduped, this is exactly the demo pair, which
    derives VERIFIED — and the REJECTED one is still counted."""
    verified = make_verification()
    rejected = make_verification(regression=GateStatus.FAIL, verdict=Verdict.REJECTED)

    # The duplicate collapses: two copies of `verified` plus one `rejected` is the
    # same input as one of each.
    assert_transition(
        MissionState.EXPORTING,
        MissionState.VERIFIED,
        make_authorization(),
        NOW,
        verifications=[verified, verified, rejected],
        mission_id=MISSION,
    )

    # And a duplicated HUMAN_REVIEW record still outranks a duplicated VERIFIED one.
    unrun = make_verification(
        regression=GateStatus.NOT_RUN, verdict=Verdict.HUMAN_REVIEW_REQUIRED
    )
    with pytest.raises(VerificationRequiredError):
        assert_transition(
            MissionState.EXPORTING,
            MissionState.VERIFIED,
            make_authorization(),
            NOW,
            verifications=[verified, verified, verified, unrun],
            mission_id=MISSION,
        )


def test_the_guard_cannot_be_run_without_naming_a_mission():
    """`mission_id` is keyword-only with no default, so the binding cannot be skipped
    by a caller who did not think about it."""
    import inspect

    parameter = inspect.signature(assert_transition).parameters["mission_id"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty

    with pytest.raises(TypeError):
        assert_transition(  # type: ignore[call-arg]
            MissionState.CREATED, MissionState.AUTHORIZED, make_authorization(), NOW
        )


# --- D-046: the candidate set closes when VERIFY begins ---------------------------


def test_assert_candidate_set_open_passes_before_any_verification():
    assert_candidate_set_open([])


def test_assert_candidate_set_open_refuses_once_a_verification_exists():
    with pytest.raises(CandidateSetFrozenError):
        assert_candidate_set_open([make_verification()])


# --- D-047: resume goes back where it came from -----------------------------------


def test_a_mission_paused_in_baseline_cannot_resume_into_exporting():
    """BUG-005, the forward half. The seven-step walk QA ran ended
    PAUSED -> EXPORTING -> VERIFIED, reaching a terminal verdict having never entered
    PATCH or VERIFY."""
    with pytest.raises(InvalidStateTransitionError) as excinfo:
        assert_transition(
            MissionState.PAUSED,
            MissionState.EXPORTING,
            make_authorization(),
            NOW,
            mission_id=MISSION,
            paused_from=MissionState.BASELINE,
        )
    assert "resumes only into the state it paused from" in str(excinfo.value)


def test_a_mission_paused_in_verify_cannot_resume_into_baseline():
    """The backward half, which is the one nobody had named: re-running BASELINE would
    write a second BaselineReport for the same snapshot, and BaselineReport is the
    denominator for 'regression preserved' (P0-5)."""
    with pytest.raises(InvalidStateTransitionError):
        assert_transition(
            MissionState.PAUSED,
            MissionState.BASELINE,
            make_authorization(),
            NOW,
            mission_id=MISSION,
            paused_from=MissionState.VERIFY,
        )


@pytest.mark.parametrize("origin", sorted(MissionState(s) for s in PAUSABLE_STATES))
def test_a_paused_mission_resumes_into_its_own_origin(origin: MissionState):
    assert_transition(
        MissionState.PAUSED,
        origin,
        make_authorization(),
        NOW,
        mission_id=MISSION,
        paused_from=origin,
    )


def test_a_pause_with_no_recorded_origin_can_only_abort():
    """Fail closed. An unknown origin must not stand in for any origin."""
    for target in (MissionState.CANCELLING, MissionState.FAILED):
        assert_transition(
            MissionState.PAUSED, target, None, NOW, mission_id=MISSION, paused_from=None
        )
    with pytest.raises(InvalidStateTransitionError):
        assert_transition(
            MissionState.PAUSED,
            MissionState.BASELINE,
            make_authorization(),
            NOW,
            mission_id=MISSION,
            paused_from=None,
        )


def test_allowed_transitions_for_a_paused_mission_names_one_resume_target():
    """The UI disables its buttons from this list rather than duplicating the state
    machine, so it has to agree with the guard."""
    assert allowed_transitions(MissionState.PAUSED, MissionState.VERIFY) == frozenset(
        {MissionState.VERIFY, MissionState.CANCELLING, MissionState.FAILED}
    )
    assert allowed_transitions(MissionState.PAUSED) == frozenset(
        {MissionState.CANCELLING, MissionState.FAILED}
    )


def test_assert_resume_is_a_no_op_outside_paused():
    assert_resume(MissionState.BASELINE, MissionState.TRIAGE, None)


# --- the fan-out derives the mission's terminal state (#80) -----------------------


@pytest.mark.parametrize(
    ("verdicts", "expected"),
    [
        ([], MissionState.HUMAN_REVIEW),
        ([Verdict.VERIFIED], MissionState.VERIFIED),
        ([Verdict.REJECTED], MissionState.REJECTED),
        ([Verdict.VERIFIED, Verdict.REJECTED], MissionState.VERIFIED),
        ([Verdict.REJECTED, Verdict.REJECTED], MissionState.REJECTED),
        (
            [Verdict.VERIFIED, Verdict.HUMAN_REVIEW_REQUIRED],
            MissionState.HUMAN_REVIEW,
        ),
    ],
)
def test_derive_mission_outcome(verdicts, expected):
    assert derive_mission_outcome(verdicts) is expected
