"""The authorization gate and the transition table.

The hard constraint under test: *a mission stage must be unable to run without an
authorization record*. Every stage but AUTHORIZE is checked individually, because a
gate that covers eight of nine stages is not a gate.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from contracts.authorization import AuthorizationRecord
from contracts.enums import GateName, GateStatus, MissionStage, MissionState, Verdict
from contracts.errors import (
    AuthorizationRequiredError,
    InvalidStateTransitionError,
    VerificationRequiredError,
)
from contracts.schemas.evidence import VerificationRecord
from contracts.state_machine import (
    STAGES_REQUIRING_AUTHORIZATION,
    assert_stage_can_run,
    assert_transition,
)
from contracts.verdict import GateMatrix, GateResult

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
SNAPSHOT = "a" * 64
OTHER_SNAPSHOT = "b" * 64


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
    regression: GateStatus = GateStatus.PASS, verdict: Verdict = Verdict.VERIFIED
) -> VerificationRecord:
    def gate(name: GateName, status: GateStatus) -> GateResult:
        return GateResult(name=name, status=status, tool="ctest 3.28.3")

    return VerificationRecord(
        id=uuid4(),
        mission_id=uuid4(),
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
        assert_transition(current, target, auth, NOW)
    assert_transition(
        MissionState.EXPORTING,
        MissionState.VERIFIED,
        auth,
        NOW,
        verifications=[make_verification()],
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
            assert_transition(source, target, None, NOW)


def _incoming_sources():
    from contracts.state_machine import TRANSITIONS

    return TRANSITIONS


def test_terminal_verdict_states_require_authorization():
    with pytest.raises((AuthorizationRequiredError, VerificationRequiredError)):
        assert_transition(MissionState.EXPORTING, MissionState.VERIFIED, None, NOW)


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
            MissionState.EXPORTING, target, make_authorization(), NOW
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
        )


def test_a_rejected_verdict_reaches_the_rejected_state():
    rejected = make_verification(regression=GateStatus.FAIL, verdict=Verdict.REJECTED)
    assert_transition(
        MissionState.EXPORTING,
        MissionState.REJECTED,
        make_authorization(),
        NOW,
        verifications=[rejected],
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
    )
    # ...and the same pair cannot be presented as an all-clear failure either.
    with pytest.raises(VerificationRequiredError):
        assert_transition(
            MissionState.EXPORTING,
            MissionState.REJECTED,
            make_authorization(),
            NOW,
            verifications=[verified, rejected],
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
    )
    with pytest.raises(VerificationRequiredError):
        assert_transition(
            MissionState.EXPORTING,
            MissionState.VERIFIED,
            make_authorization(),
            NOW,
            verifications=[verified, unrun],
        )


def test_human_review_before_verification_needs_no_record():
    """Policy can require a person long before any gate has run."""
    for source in (MissionState.CORRELATE, MissionState.PATCH, MissionState.VERIFY):
        assert_transition(
            source, MissionState.HUMAN_REVIEW, make_authorization(), NOW
        )


def test_illegal_transition_is_refused_even_with_authorization():
    with pytest.raises(InvalidStateTransitionError):
        assert_transition(
            MissionState.CREATED, MissionState.VERIFIED, make_authorization(), NOW
        )


def test_skipping_verification_is_refused():
    with pytest.raises(InvalidStateTransitionError):
        assert_transition(
            MissionState.PATCH, MissionState.VERIFIED, make_authorization(), NOW
        )


def test_cancellation_never_blocked_by_a_missing_authorization():
    """Losing authority is a reason to stop, not a reason to be unable to."""
    assert_transition(MissionState.BASELINE, MissionState.CANCELLING, None, NOW)
    assert_transition(MissionState.CANCELLING, MissionState.CANCELLED, None, NOW)
    assert_transition(MissionState.STRESS_TEST, MissionState.FAILED, None, NOW)


def test_cancelled_has_its_own_posture_and_is_not_shown_as_failed():
    from contracts.enums import MissionPosture, posture_for

    assert posture_for(MissionState.CANCELLED) is MissionPosture.CANCELLED
    assert posture_for(MissionState.CANCELLING) is MissionPosture.CANCELLED
    assert posture_for(MissionState.FAILED) is MissionPosture.FAILED


def test_a_terminal_mission_cannot_be_restarted():
    for state in (MissionState.VERIFIED, MissionState.REJECTED, MissionState.CANCELLED):
        with pytest.raises(InvalidStateTransitionError):
            assert_transition(
                state, MissionState.BASELINE, make_authorization(), NOW
            )
