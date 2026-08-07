"""A verdict may not be derived from a model confidence value.

Four independent guards are asserted here, because this is the rule most likely to be
eroded by a well-meaning change six days from now:

1. `derive_verdict` accepts one argument and it is the gate matrix.
2. Gate schemas forbid extra fields, so confidence cannot be smuggled in.
3. No field named after a confidence score is reachable from the gate matrix.
4. `VerificationRecord` re-derives the verdict and refuses to exist if the stored
   verdict does not follow from the gates.
"""

from __future__ import annotations

import inspect
import typing
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from contracts.enums import (
    GateName,
    GateStatus,
    PatchPolicyStatus,
    PatchProvenance,
    Verdict,
)
from contracts.schemas.evidence import (
    CandidateVerdict,
    MissionVerdictSummary,
    ModelProvenance,
    PatchCandidate,
    VerificationRecord,
)
from contracts.verdict import (
    GateMatrix,
    GateResult,
    derive_mission_verdict,
    derive_verdict,
    iter_nested_field_names,
)

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)


def gate(name: GateName, status: GateStatus) -> GateResult:
    return GateResult(name=name, status=status, tool="ctest 3.28.3", detail="")


def matrix(compile_=GateStatus.PASS, reproducer=GateStatus.PASS, regression=GateStatus.PASS, **kwargs) -> GateMatrix:
    return GateMatrix(
        compile=gate(GateName.COMPILE, compile_),
        reproducer_eliminated=gate(GateName.REPRODUCER_ELIMINATED, reproducer),
        regression_preserved=gate(GateName.REGRESSION_PRESERVED, regression),
        **kwargs,
    )


# --- 1. the signature -----------------------------------------------------------


def test_derive_verdict_takes_only_a_gate_matrix():
    signature = inspect.signature(derive_verdict)
    assert list(signature.parameters) == ["gates"]
    assert signature.parameters["gates"].default is inspect.Parameter.empty
    # Resolved rather than read literally: the module uses postponed annotations.
    hints = typing.get_type_hints(derive_verdict)
    assert hints["gates"] is GateMatrix
    assert hints["return"] is Verdict


# --- 2. no smuggling ------------------------------------------------------------


def test_gate_result_rejects_a_confidence_field():
    with pytest.raises(ValidationError):
        GateResult(
            name=GateName.COMPILE,
            status=GateStatus.PASS,
            confidence=0.99,  # type: ignore[call-arg]
        )


def test_gate_matrix_rejects_an_extra_gate():
    with pytest.raises(ValidationError):
        GateMatrix(
            compile=gate(GateName.COMPILE, GateStatus.PASS),
            reproducer_eliminated=gate(GateName.REPRODUCER_ELIMINATED, GateStatus.PASS),
            regression_preserved=gate(GateName.REGRESSION_PRESERVED, GateStatus.PASS),
            model_says_fine=0.99,  # type: ignore[call-arg]
        )


# --- 3. nothing confidence-shaped on the verdict path ---------------------------


def test_no_confidence_field_is_reachable_from_the_gate_matrix():
    names = set(iter_nested_field_names(GateMatrix))
    offenders = {
        name
        for name in names
        if any(token in name.lower() for token in ("confidence", "score", "probability", "likelihood"))
    }
    assert not offenders, f"confidence-shaped fields on the verdict path: {offenders}"


def test_confidence_exists_exactly_once_in_the_contract_and_is_display_only():
    assert "confidence" in ModelProvenance.model_fields
    field = ModelProvenance.model_fields["confidence"]
    assert "DISPLAY ONLY" in (field.description or "")


# --- the truth table ------------------------------------------------------------


@pytest.mark.parametrize(
    ("gates", "expected"),
    [
        (matrix(), Verdict.VERIFIED),
        (matrix(regression=GateStatus.FAIL), Verdict.REJECTED),
        (matrix(reproducer=GateStatus.FAIL), Verdict.REJECTED),
        (matrix(compile_=GateStatus.FAIL), Verdict.REJECTED),
        (matrix(regression=GateStatus.NOT_RUN), Verdict.HUMAN_REVIEW_REQUIRED),
        (matrix(compile_=GateStatus.ERROR), Verdict.HUMAN_REVIEW_REQUIRED),
    ],
)
def test_verdict_truth_table(gates: GateMatrix, expected: Verdict):
    assert derive_verdict(gates) is expected


def test_cut_optional_gates_default_to_not_run_and_do_not_block_a_verdict():
    """Static delta and renewed fuzzing are cut; their absence is disclosed, not fatal."""
    gates = matrix()
    assert gates.static_delta.status is GateStatus.NOT_RUN
    assert gates.renewed_fuzzing.status is GateStatus.NOT_RUN
    assert derive_verdict(gates) is Verdict.VERIFIED


def test_an_optional_gate_that_ran_and_failed_rejects():
    gates = matrix(
        static_delta=gate(GateName.STATIC_DELTA, GateStatus.FAIL),
    )
    assert derive_verdict(gates) is Verdict.REJECTED


# --- the mission verdict over N candidates ---------------------------------------


@pytest.mark.parametrize(
    ("verdicts", "expected"),
    [
        ([], Verdict.HUMAN_REVIEW_REQUIRED),
        ([Verdict.VERIFIED], Verdict.VERIFIED),
        ([Verdict.REJECTED], Verdict.REJECTED),
        # The demo: one holds, one does not.
        ([Verdict.VERIFIED, Verdict.REJECTED], Verdict.VERIFIED),
        ([Verdict.REJECTED, Verdict.REJECTED], Verdict.REJECTED),
        (
            [Verdict.VERIFIED, Verdict.HUMAN_REVIEW_REQUIRED],
            Verdict.HUMAN_REVIEW_REQUIRED,
        ),
    ],
)
def test_mission_verdict_derivation(verdicts, expected):
    assert derive_mission_verdict(verdicts) is expected


def test_a_verdict_summary_cannot_misreport_its_own_basis():
    candidates = [
        CandidateVerdict(
            patch_id=uuid4(),
            verification_id=uuid4(),
            verdict=Verdict.VERIFIED,
            provenance=PatchProvenance.MODEL_GENERATED,
        ),
        CandidateVerdict(
            patch_id=uuid4(),
            verification_id=uuid4(),
            verdict=Verdict.REJECTED,
            provenance=PatchProvenance.OPERATOR_SUPPLIED,
        ),
    ]
    summary = MissionVerdictSummary(
        mission_verdict=Verdict.VERIFIED,
        candidates=candidates,
        verified_count=1,
        rejected_count=1,
    )
    assert summary.rejected_count == 1

    # The rejection cannot be quietly dropped from the counts.
    with pytest.raises(ValidationError):
        MissionVerdictSummary(
            mission_verdict=Verdict.VERIFIED,
            candidates=candidates,
            verified_count=1,
            rejected_count=0,
        )

    # ...nor can the mission verdict contradict the candidates.
    with pytest.raises(ValidationError):
        MissionVerdictSummary(
            mission_verdict=Verdict.REJECTED,
            candidates=candidates,
            verified_count=1,
            rejected_count=1,
        )


# --- 4. the record cannot lie ---------------------------------------------------


def verification(gates: GateMatrix, verdict: Verdict) -> VerificationRecord:
    return VerificationRecord(
        id=uuid4(),
        mission_id=uuid4(),
        patch_id=uuid4(),
        gates=gates,
        verdict=verdict,
        started_at=NOW,
        finished_at=NOW + timedelta(seconds=42),
    )


def test_a_record_whose_verdict_matches_its_gates_is_valid():
    record = verification(matrix(), Verdict.VERIFIED)
    assert record.verdict is Verdict.VERIFIED


def test_a_verified_record_over_a_failed_regression_cannot_be_constructed():
    """The demo's scenario 7: the tempting fix that kills the crash and the tests."""
    with pytest.raises(ValidationError) as excinfo:
        verification(matrix(regression=GateStatus.FAIL), Verdict.VERIFIED)
    assert "does not follow from the gate matrix" in str(excinfo.value)


def test_a_verified_record_over_ungated_evidence_cannot_be_constructed():
    with pytest.raises(ValidationError):
        verification(matrix(regression=GateStatus.NOT_RUN), Verdict.VERIFIED)


def test_a_maximally_confident_model_cannot_change_the_verdict():
    """The whole rule, end to end: 100% claimed confidence, failing regression."""
    candidate = PatchCandidate(
        id=uuid4(),
        mission_id=uuid4(),
        finding_id=uuid4(),
        provenance=PatchProvenance.MODEL_GENERATED,
        model=ModelProvenance(
            model_name="local-small-code-model",
            served_from="127.0.0.1:8000",
            confidence=1.0,
        ),
        diff="--- a/parser.c\n+++ b/parser.c\n",
        files_changed=1,
        lines_changed=3,
        policy_status=PatchPolicyStatus.ACCEPTED,
        created_at=NOW,
    )
    assert candidate.model is not None and candidate.model.confidence == 1.0
    assert derive_verdict(matrix(regression=GateStatus.FAIL)) is Verdict.REJECTED


def test_a_replayed_response_declares_all_three_replay_fields():
    """Replay mode is the fallback for a CPU-served model on day five (CTO review).
    A replayed response is legitimate; a half-declared one is indistinguishable from a
    live generation, which is the claim we must not inflate."""
    replayed = ModelProvenance(
        model_name="local-small-code-model",
        served_from="127.0.0.1:8000",
        replayed_from_transcript="artifact://transcripts/parser-lib-attempt-3",
        captured_at=NOW - timedelta(days=1),
        transcript_sha256="c" * 64,
    )
    assert replayed.is_replayed is True

    live = ModelProvenance(
        model_name="local-small-code-model", served_from="127.0.0.1:8000"
    )
    assert live.is_replayed is False


@pytest.mark.parametrize(
    "partial",
    [
        {"replayed_from_transcript": "artifact://transcripts/x"},
        {"transcript_sha256": "c" * 64},
        {"captured_at": NOW},
        {
            "replayed_from_transcript": "artifact://transcripts/x",
            "transcript_sha256": "c" * 64,
        },
    ],
)
def test_a_partially_declared_replay_is_rejected(partial: dict):
    with pytest.raises(ValidationError):
        ModelProvenance(
            model_name="local-small-code-model",
            served_from="127.0.0.1:8000",
            **partial,
        )


def test_a_model_generated_candidate_must_carry_provenance():
    with pytest.raises(ValidationError):
        PatchCandidate(
            id=uuid4(),
            mission_id=uuid4(),
            finding_id=uuid4(),
            provenance=PatchProvenance.MODEL_GENERATED,
            model=None,
            diff="",
            files_changed=1,
            lines_changed=1,
            policy_status=PatchPolicyStatus.ACCEPTED,
            created_at=NOW,
        )


def test_an_operator_candidate_cannot_be_dressed_as_model_output():
    """Honesty constraint from the P0 cut §3 / D-008."""
    with pytest.raises(ValidationError):
        PatchCandidate(
            id=uuid4(),
            mission_id=uuid4(),
            finding_id=uuid4(),
            provenance=PatchProvenance.OPERATOR_SUPPLIED,
            model=ModelProvenance(model_name="local-small-code-model", served_from="127.0.0.1:8000"),
            diff="",
            files_changed=1,
            lines_changed=1,
            policy_status=PatchPolicyStatus.ACCEPTED,
            created_at=NOW,
        )
