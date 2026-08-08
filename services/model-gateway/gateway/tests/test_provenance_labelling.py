"""The honesty constraint: a replayed response is never presented as live inference.

Issue #82 makes this the point of the feature rather than a footnote on it, and its
acceptance criteria name the string. This module covers:

- the UI renders "model output recorded <date>, replayed", not "model-generated"
- the exported evidence report carries the same wording
- **no code path can present a replayed response as live** — a test asserts it
- D-049 Part 1: the fallback branch points at the humbler claim, so a forgotten field
  produces an understatement rather than an overclaim
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from gateway.provenance import (
    ProvenanceClaim,
    ResponseProvenance,
    ResponseSource,
    claim_for,
    describe,
    render_for_evidence,
    render_for_ui,
)
from gateway.schemas import GenerationRequest
from gateway.service import build_gateway
from gateway.settings import GatewaySettings
from gateway.tests.conftest import FAKE_ARTIFACT_SHA, FakeLiveBackend

CAPTURED = datetime(2026, 8, 6, 21, 45, tzinfo=UTC)
NOW = datetime(2026, 8, 13, 9, 30, tzinfo=UTC)

REPLAYED = ResponseProvenance(
    source=ResponseSource.RECORDED_TRANSCRIPT,
    model_name="qwen2.5-coder-1.5b-instruct-q4_k_m",
    model_artifact_sha256=FAKE_ARTIFACT_SHA,
    served_from="http://127.0.0.1:8080/v1",
    generated_at=NOW,
    replayed_from_transcript=f"{'d' * 64}.json",
    captured_at=CAPTURED,
    transcript_sha256="d" * 64,
)

LIVE = ResponseProvenance(
    source=ResponseSource.LIVE_INFERENCE,
    model_name="qwen2.5-coder-1.5b-instruct-q4_k_m",
    model_artifact_sha256=FAKE_ARTIFACT_SHA,
    served_from="http://127.0.0.1:8080/v1",
    generated_at=NOW,
)

OPERATOR = ResponseProvenance(
    source=ResponseSource.OPERATOR_SUPPLIED,
    generated_at=NOW,
)


# --------------------------------------------------------------------------------------
# The mandated strings
# --------------------------------------------------------------------------------------


def test_the_replay_label_is_the_string_the_issue_asks_for() -> None:
    assert describe(REPLAYED) == "model output recorded 2026-08-06, replayed"


def test_the_ui_payload_carries_the_replay_label_and_not_model_generated() -> None:
    payload = render_for_ui(REPLAYED)
    assert payload["label"] == "model output recorded 2026-08-06, replayed"
    assert payload["is_replayed"] is True
    assert payload["transcript_sha256"] == "d" * 64
    assert "model-generated" not in str(payload).lower()


def test_the_evidence_report_carries_the_same_wording_as_the_ui() -> None:
    """The two must not be able to drift, so one is asserted to contain the other."""
    assert describe(REPLAYED) in render_for_evidence(REPLAYED)
    assert "not generated during this mission" in render_for_evidence(REPLAYED)
    assert "sha256:" + "d" * 64 in render_for_evidence(REPLAYED)


def test_the_evidence_report_says_the_gates_ran_live_against_the_replayed_diff() -> None:
    """Coupling rule C3 in the fallback ladder — the part a judge should care about."""
    assert "ran against it in this mission, unchanged" in render_for_evidence(REPLAYED)


def test_the_operator_supplied_label_is_never_model_generated() -> None:
    assert describe(OPERATOR) == "operator-supplied candidate"
    assert "model-generated" not in render_for_evidence(OPERATOR)
    assert "model-generated" not in str(render_for_ui(OPERATOR))


# --------------------------------------------------------------------------------------
# No code path presents a replayed response as live
# --------------------------------------------------------------------------------------

#: Every function in this package that turns provenance into something a human reads.
#: `test_provenance_chokepoint.py` asserts this list is exhaustive; this one asserts each
#: entry behaves. Together they are the "no code path" claim.
RENDERERS = (describe, render_for_ui, render_for_evidence)


@pytest.mark.parametrize("renderer", RENDERERS, ids=lambda f: f.__name__)
def test_no_renderer_presents_a_replayed_response_as_live(renderer) -> None:
    rendered = str(renderer(REPLAYED)).lower()
    assert "replayed" in rendered
    for forbidden in ("model-generated", "live inference", "generated now", "generating"):
        assert forbidden not in rendered, (
            f"{renderer.__name__} described a replayed response with {forbidden!r}. The "
            "fallback ladder §4 forbids that string for a replayed candidate."
        )


def test_the_gateway_response_for_a_replay_renders_as_replayed_end_to_end(
    replay_settings: GatewaySettings, request_: GenerationRequest, recorded: str
) -> None:
    """Through the real object graph rather than a hand-built provenance."""
    gateway = build_gateway(replay_settings)
    response = gateway.generate(request_)

    assert gateway.ui_payload(response)["label"] == "model output recorded 2026-08-06, replayed"
    assert "model-generated" not in render_for_evidence(response.provenance)


def test_a_replayed_response_cannot_be_relabelled_by_editing_one_field() -> None:
    """The provenance validator refuses the half-states that would make a lie possible."""
    with pytest.raises(ValueError, match="together or not at all"):
        REPLAYED.model_copy(update={"captured_at": None}).model_validate(
            REPLAYED.model_copy(update={"captured_at": None}).model_dump()
        )

    with pytest.raises(ValueError, match="requires replayed_from_transcript"):
        ResponseProvenance(source=ResponseSource.RECORDED_TRANSCRIPT, generated_at=NOW)

    with pytest.raises(ValueError, match="cannot carry replay fields"):
        ResponseProvenance(
            source=ResponseSource.OPERATOR_SUPPLIED,
            replayed_from_transcript="x.json",
            captured_at=CAPTURED,
            transcript_sha256="d" * 64,
        )


def test_source_has_no_default_so_it_must_be_stated() -> None:
    with pytest.raises(ValueError, match="source"):
        ResponseProvenance()  # type: ignore[call-arg]


# --------------------------------------------------------------------------------------
# D-049 Part 1: silence points at the weaker claim
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing",
    [
        {"generated_at": None},
        {"served_from": ""},
        {"model_name": ""},
    ],
    ids=["no timestamp", "no host", "no model name"],
)
def test_an_incomplete_live_record_understates_rather_than_overstates(missing: dict) -> None:
    """A forgotten field must produce an understatement.

    This is the direction D-049 Part 1 corrects. The dangerous default is the one that
    claims live inference when nobody said anything; here, anything short of a complete
    live record renders as *not attested*, which is a weaker claim than the truth rather
    than a stronger one.
    """
    partial = LIVE.model_copy(update=missing)
    assert claim_for(partial) is ProvenanceClaim.NOT_ATTESTED
    assert describe(partial) == (
        "model output, provenance not attested — not presented as live inference"
    )
    assert "live inference" not in describe(partial).replace("not presented as live inference", "")


def test_a_complete_live_record_is_the_only_thing_that_claims_live_inference() -> None:
    assert claim_for(LIVE) is ProvenanceClaim.LIVE_INFERENCE
    assert describe(LIVE) == "model-generated (live inference 2026-08-13)"


def test_the_contract_dict_always_states_all_three_replay_fields() -> None:
    """Mitigation for BUG-007, which is open and not ours to fix.

    `ModelProvenance`'s replay fields default to the *stronger* claim on `main`. A gateway
    record therefore never omits them — for a live response it states three explicit
    `None`s rather than relying on a default that points at "live".
    """
    for provenance in (LIVE, REPLAYED, OPERATOR):
        contract = provenance.to_contract_dict()
        for field in ("replayed_from_transcript", "captured_at", "transcript_sha256"):
            assert field in contract, f"{field} omitted for {provenance.source}"

    assert LIVE.contract_patch_provenance() == "MODEL_GENERATED"
    assert REPLAYED.contract_patch_provenance() == "MODEL_GENERATED"
    assert OPERATOR.contract_patch_provenance() == "OPERATOR_SUPPLIED"


def test_confidence_travels_but_is_never_a_gate(
    live_settings: GatewaySettings, request_: GenerationRequest
) -> None:
    """Rule 2 for this seat: confidence is displayed, never trusted.

    Asserted two ways — a low-confidence candidate is returned unchanged rather than
    retried or suppressed, and the UI payload carries the note that says so.
    """
    backend = FakeLiveBackend()
    backend.candidate = backend.candidate.model_copy(update={"confidence": 0.01})
    gateway = build_gateway(live_settings, live_backend=backend)

    response = gateway.generate(request_)
    assert response.candidate.confidence == 0.01
    assert backend.calls == 1, "a low score must not trigger a retry"
    assert "not an input to any gate" in str(gateway.ui_payload(response)["confidence_note"])
