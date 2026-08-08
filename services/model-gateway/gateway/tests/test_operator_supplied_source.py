"""Rung 3 of the fallback ladder, through the same seam as the other two.

The ladder's §2.3 notes that the rejected-patch case has been operator-supplied since
D-008, and its §4 forbids "model-generated" for such a candidate in the UI, the report and
the narration. Routing it through the gateway is what makes that mechanical instead of
remembered.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gateway.backends import OperatorSuppliedSource
from gateway.errors import OperatorCandidateError
from gateway.provenance import ResponseSource, describe, render_for_evidence
from gateway.schemas import GenerationRequest
from gateway.service import ModelGateway
from gateway.settings import GatewayMode, GatewaySettings

DIFF = """--- a/src/parse.c
+++ b/src/parse.c
@@ -118,7 +118,7 @@
-    while (cursor < end) {
+    while (cursor + 1 < end) {
"""


@pytest.fixture
def diff_file(tmp_path: Path) -> Path:
    path = tmp_path / "candidate-b.patch"
    path.write_text(DIFF, encoding="utf-8")
    return path


def _gateway(store_root: Path, diff_file: Path) -> ModelGateway:
    settings = GatewaySettings(mode=GatewayMode.REPLAY, transcript_root=store_root).validate()
    return ModelGateway(settings, OperatorSuppliedSource(diff_file))


def test_an_operator_candidate_travels_the_same_path_and_schema(
    tmp_path: Path, diff_file: Path, request_: GenerationRequest
) -> None:
    response = _gateway(tmp_path, diff_file).generate(request_)

    assert response.candidate.diff == DIFF
    assert response.candidate.touched_files == ("src/parse.c",)
    assert response.provenance.source is ResponseSource.OPERATOR_SUPPLIED


def test_it_is_never_labelled_as_model_output(
    tmp_path: Path, diff_file: Path, request_: GenerationRequest
) -> None:
    response = _gateway(tmp_path, diff_file).generate(request_)

    assert describe(response.provenance) == "operator-supplied candidate"
    assert "model-generated" not in render_for_evidence(response.provenance)
    assert response.provenance.contract_patch_provenance() == "OPERATOR_SUPPLIED"


def test_no_confidence_is_invented_for_a_human_written_diff(
    tmp_path: Path, diff_file: Path, request_: GenerationRequest
) -> None:
    """BUG-008 is about invented strings on an operator-supplied record. None here."""
    response = _gateway(tmp_path, diff_file).generate(request_)

    assert response.candidate.confidence is None
    assert response.provenance.confidence is None
    assert response.provenance.model_name == ""
    assert response.provenance.model_artifact_sha256 is None
    assert response.provenance.served_from == ""


@pytest.mark.parametrize("content", ["", "   \n\n"], ids=["empty", "whitespace"])
def test_an_empty_candidate_file_is_refused(
    tmp_path: Path, request_: GenerationRequest, content: str
) -> None:
    path = tmp_path / "empty.patch"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(OperatorCandidateError, match="no candidate to supply"):
        _gateway(tmp_path, path).generate(request_)


def test_a_missing_candidate_file_is_refused(tmp_path: Path, request_: GenerationRequest) -> None:
    with pytest.raises(OperatorCandidateError, match="cannot read"):
        _gateway(tmp_path, tmp_path / "nope.patch").generate(request_)


def test_the_shipped_rejected_patch_fixture_loads_if_it_is_present(
    tmp_path: Path, request_: GenerationRequest
) -> None:
    """The ladder names `patches/candidate-b-rejected-crash-only-fix.patch` from #74."""
    fixture = (
        Path(__file__).resolve().parents[4]
        / "demo"
        / "repositories"
        / "pktcfg"
        / "patches"
        / "candidate-b-rejected-crash-only-fix.patch"
    )
    if not fixture.is_file():
        pytest.skip("demo/repositories/pktcfg is not present")

    response = _gateway(tmp_path, fixture).generate(request_)
    assert response.candidate.diff.strip()
    assert describe(response.provenance) == "operator-supplied candidate"
