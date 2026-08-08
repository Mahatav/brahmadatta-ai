"""D-045, the half that cannot live in `contracts/`.

BUG-004(c): withholding a record from the guard reaches a verdict the full set would not
support. That is undetectable from inside a pure function handed the set — no validation
in `contracts/` closes it. The guarantee lives at the database boundary, and these are
the tests that fail if a future refactor quietly moves it back out.

**Which record, precisely.** `derive_mission_verdict` is any-VERIFIED-wins, so dropping
a `REJECTED` record cannot change the mission verdict — it is a no-op. The record whose
removal reaches `VERIFIED` is a **`HUMAN_REVIEW_REQUIRED`** one, because that outranks
everything. D-045 and this file's first draft both had it backwards; corrected by the
round-2 security review §13.1.
"""

from __future__ import annotations

import ast
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


def test_a_dropped_human_review_record_cannot_reach_verified(mission, finding):
    """Two candidates, one VERIFIED and one HUMAN_REVIEW; the mission verdict is
    HUMAN_REVIEW. A caller that wanted VERIFIED would have to hide the second record —
    and there is no parameter to hide it through.

    **Renamed from `test_a_dropped_rejection_cannot_reach_verified` (SEC-23c).** The
    body was always this case; the old name described a different and vacuous one.
    `derive_mission_verdict` is any-VERIFIED-wins, so `[VERIFIED, REJECTED]` and
    `[VERIFIED]` both derive `VERIFIED` — dropping a rejection changes nothing and a
    guard refusing it would be refusing nothing. The record whose removal reaches
    `VERIFIED` is a `HUMAN_REVIEW_REQUIRED` one. D-045's framing had this backwards and
    the PR body propagated it; corrected by the round-2 security review §13.1.
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


def test_a_mission_with_an_unloadable_record_can_still_be_failed(mission, finding):
    """SEC-20, the availability half.

    `transition` loads the verification set unconditionally, before the guards — and it
    must keep doing so, because that unconditional load is what closes BUG-004(c).
    Making it conditional on the target state would reopen the hole; the review flagged
    that shortcut specifically.

    So the abort paths tolerate an *unreadable* set instead. `_ABORTS` exists precisely
    so that getting out safely is never blocked by the bookkeeping, and one corrupt row
    used to block `→ CANCELLING` and `→ FAILED` along with everything else.
    """
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

    # Corrupt the stored matrix beneath the ORM. A queryset `.update()` never calls
    # `save()`, so it goes around `VerificationRecord.clean()` — which is now the only
    # way to produce such a row, i.e. exactly the residual case: a row written by an
    # older build, or by hand at 3am.
    #
    # (An earlier version of this test used raw SQL keyed on `str(mission.id)`. Django
    # stores UUIDs as bare hex on SQLite, so it matched no rows and the test passed
    # while asserting nothing. The control assertion below is why that got caught.)
    updated = VerificationRecord.objects.filter(mission=mission).update(
        gates={"not": "a gate matrix"}
    )
    assert updated == 1, "the corruption did not take; the rest of this test is vacuous"

    with pytest.raises(Exception):
        repository.load_verifications(mission.id)

    # Forward progress is refused — a verdict must never be derived from a set we
    # could not read.
    with pytest.raises(Exception):
        transitions.transition(
            mission.id, MissionState.EXPORTING, trace_id=TRACE, now=NOW
        )

    # But the mission can still be got out of.
    transitions.transition(mission.id, MissionState.FAILED, trace_id=TRACE, now=NOW)
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.FAILED


def test_the_evidence_load_is_not_conditional_on_the_target_state():
    """The shortcut both reviewers warned against, closed structurally.

    The tempting fix for the wedged-mission case is `if target in _ABORTS: skip the
    load`. That silently reopens BUG-004(c), because the completeness guarantee *is* the
    load happening on every path. What is conditional is only how a **failure** of the
    load is handled — `_tolerate_if_aborting` runs the loader first and decides
    afterwards.

    Read from the AST rather than by regex, so a refactor that moves the call into a
    helper (which is exactly what happened while fixing BUG-020) does not turn this test
    into a no-op that passes because it stopped finding anything to check.
    """
    tree = ast.parse(inspect.getsource(transitions))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "transition"
    )

    def references(node) -> bool:
        return any(
            isinstance(child, ast.Attribute) and child.attr == "load_verifications"
            for child in ast.walk(node)
        )

    assert references(function), (
        "transition() no longer loads the verification set at all. That load is the "
        "completeness guarantee for invariant B (D-045)."
    )

    conditional = [
        node
        for node in ast.walk(function)
        if isinstance(node, (ast.If, ast.IfExp)) and references(node)
    ]
    assert not conditional, (
        "the evidence load sits inside a conditional in transition(). It must run on "
        "every transition; only its failure may be handled differently. Making it "
        "conditional on the target state reopens BUG-004(c) with nothing to announce it."
    )



def test_a_dropped_rejection_cannot_reach_verified(mission, finding):
    """The case D-045 named — written out, including the part where it is *not* the
    dangerous one (BUG-023 / SEC-23c).

    D-045, this PR's first body, and this file's first draft all described the
    uncatchable case as "a set with a `REJECTED` record dropped". Two reviewers
    independently showed that framing is wrong, and it matters, because a reader who
    inherits it will build the wrong guard. So the correction is executed here rather
    than asserted in a comment:

    `derive_mission_verdict` is any-`VERIFIED`-wins. `[VERIFIED, REJECTED]` and
    `[VERIFIED]` both derive `VERIFIED`. Dropping a rejection therefore **cannot change
    the mission verdict**, and a guard that refused it would be refusing nothing. The
    record whose removal reaches `VERIFIED` is a `HUMAN_REVIEW_REQUIRED` one — that is
    `test_a_dropped_human_review_record_cannot_reach_verified`, above.

    What a dropped rejection *does* cost is the evidence, and that is worth a test of
    its own: the D6 differentiator is showing the `Rejected` beside the `Verified`, so
    a mission that reached `VERIFIED` while its rejection went missing would be making
    a weaker claim than it earned — and a `MissionVerdictSummary` that reported one
    candidate while two exist would be misreporting its own basis.
    """
    from contracts.schemas.evidence import CandidateVerdict, MissionVerdictSummary
    from contracts.verdict import derive_mission_verdict
    from pydantic import ValidationError as PydanticValidationError

    # 1. The vacuity, executed. This is the assertion that stops the wrong model coming
    #    back the next time someone re-derives it from the decision record.
    assert (
        derive_mission_verdict([Verdict.VERIFIED, Verdict.REJECTED])
        is derive_mission_verdict([Verdict.VERIFIED])
        is Verdict.VERIFIED
    )

    # 2. The demo pair, through the sanctioned path.
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
        gates=gate_matrix(regression=GateStatus.FAIL),
        started_at=NOW,
        finished_at=NOW,
        trace_id=TRACE,
        now=NOW,
    )
    transitions.transition(mission.id, MissionState.EXPORTING, trace_id=TRACE, now=NOW)
    transitions.transition(mission.id, MissionState.VERIFIED, trace_id=TRACE, now=NOW)

    mission.refresh_from_db()
    assert mission.state_enum is MissionState.VERIFIED

    # 3. The rejection cannot be hidden, because the set is loaded rather than supplied.
    loaded = repository.load_verifications(mission.id)
    assert sorted(str(record.verdict) for record in loaded) == [
        "REJECTED",
        "VERIFIED",
    ]

    # 4. ...and a summary that dropped it would be refused by its own validator, so the
    #    rejection cannot be lost between the database and the judge either.
    with pytest.raises(PydanticValidationError):
        MissionVerdictSummary(
            mission_verdict=Verdict.VERIFIED,
            candidates=[
                CandidateVerdict(
                    patch_id=first.id,
                    verification_id=loaded[0].id,
                    verdict=Verdict.VERIFIED,
                    provenance=PatchProvenance.OPERATOR_SUPPLIED,
                )
            ],
            verified_count=1,
            rejected_count=1,  # claims a rejection it is not carrying
        )


def test_an_unparseable_authorization_does_not_wedge_the_abort_path(mission, finding):
    """BUG-020, widened.

    The malformed row that blocks an exit need not be a gate matrix. An `Authorization`
    that cannot be loaded into its schema would raise on the same code path — and an
    abort is authorization-exempt by the transition table, so that value was never going
    to be read. Every read of the mission's own bookkeeping is tolerant on the abort
    path, not just the evidence one.
    """
    from missions.models import Authorization

    walk_to(mission, MissionState.BASELINE)

    # `statement` has min_length=20 in the contract; a shorter one cannot be loaded.
    Authorization.objects.filter(mission=mission).update(statement="too short")
    with pytest.raises(Exception):
        repository.load_active_authorization(mission, NOW)

    with pytest.raises(Exception):
        transitions.transition(mission.id, MissionState.TRIAGE, trace_id=TRACE, now=NOW)

    transitions.transition(mission.id, MissionState.CANCELLING, trace_id=TRACE, now=NOW)
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.CANCELLING


def test_the_abort_tolerance_does_not_extend_to_forward_progress(mission, finding):
    """The tolerance is scoped, and this is what stops it becoming a blanket try/except.

    A mission whose evidence cannot be read must not reach a verdict state. Only
    CANCELLING and FAILED are reachable.
    """
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
    updated = VerificationRecord.objects.filter(mission=mission).update(
        gates={"not": "a gate matrix"}
    )
    assert updated == 1

    for forward in (MissionState.EXPORTING, MissionState.PAUSED):
        with pytest.raises(Exception):
            transitions.transition(mission.id, forward, trace_id=TRACE, now=NOW)

    mission.refresh_from_db()
    assert mission.state_enum is MissionState.VERIFY
