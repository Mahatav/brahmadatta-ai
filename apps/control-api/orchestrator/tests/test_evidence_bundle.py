"""`orchestrator.evidence_bundle.assemble_evidence_bundle` (#168, T6).

Three shapes of test, per the assignment:

1. A full-data bundle — baseline, a finding with its reproducer, a fuzzing report,
   two patch candidates (one `VERIFIED`, one `REJECTED`) — carries everything, and the
   mission-level verdict/recommendation are derived, not copied.
2. A partial-data bundle — a mission that reached `EXPORTING` with nothing recorded
   past its snapshot/authorization (the "CORRELATE found nothing to bind" shape) —
   discloses every absence explicitly rather than fabricating or silently omitting a
   section.
3. Failure modes: no mission, and a mission with no snapshot/authorization at all.
"""

from __future__ import annotations

import pytest

from authorization.errors import MissionNotFoundError
from contracts.enums import (
    EvidenceSource,
    FuzzingMode,
    GateName,
    GateStatus,
    LanguageAdapter,
    MissionState,
    PatchPolicyStatus,
    PatchProvenance,
    Verdict,
)
from contracts.verdict import GateMatrix, GateResult
from missions.models import (
    BaselineReport,
    FuzzingReport,
    Mission,
    ResourceSample,
)
from orchestrator import candidates, transitions
from orchestrator.evidence_bundle import EvidenceUnavailableError, assemble_evidence_bundle
from orchestrator.evidence_export import render_gate_matrix, render_markdown
from orchestrator.tests.conftest import (
    CANDIDATE_A,
    CANDIDATE_B,
    NOW,
    TRACE,
    gate_matrix,
    walk_to,
)

pytestmark = pytest.mark.django_db(transaction=True)

#: The exact D-071b reproduction scenario, rebuilt here (SEC-50, D-071c): a
#: fabricated `DATABASE_URL=postgresql://...` line spliced into captured
#: subprocess-shaped text, on a `FAIL` gate.
_POISONED_CONNECTION_STRING_DETAIL = (
    "cmake configure: -- Configuring done\n"
    "-- DATABASE_URL=postgresql://brahmadatta:s3cr3t-pw@10.0.0.5:5432/prod\n"
    "CMake Error: could not find CMAKE_C_COMPILER exit=1"
)


def _two_candidate_mission(mission, finding):
    """Drive the mission to `EXPORTING` (not further) with two verified/rejected
    candidates — the fixture `orchestrator/tests/test_fan_out.py::_run_the_demo_pair`
    mirrors, kept local so this file does not depend on another test module's private
    helper."""
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
    mission.refresh_from_db()
    return candidate_a, candidate_b


# ---------------------------------------------------------------------------------
# 1. Full data
# ---------------------------------------------------------------------------------


def test_full_data_bundle_carries_everything(mission, finding):
    from missions.models import Reproducer

    BaselineReport.objects.create(
        mission=mission,
        configure_ok=True,
        build_ok=True,
        tests_total=8,
        tests_passed=8,
        tests_failed=0,
        duration_seconds=3.2,
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        recorded_at=NOW,
    )
    FuzzingReport.objects.create(
        mission=mission,
        mode=FuzzingMode.LIVE_CAMPAIGN.value,
        harness="pktcfg_fuzz_one_input",
        engine="libFuzzer",
        runtime_seconds=1800.0,
        executions=12_000_000,
        crashes_found=3,
        unique_crashes=1,
        corpus_size=42,
        sanitizers=["address", "undefined"],
        recorded_at=NOW,
    )
    Reproducer.objects.create(
        finding=finding,
        minimized=True,
        replay_attempts=5,
        replay_successes=5,
        test_command="./pktcfg_replay crash.bin 5",
        artifact={
            "uri": "artifact://mission/reproducer/crash.bin",
            "kind": "crash-input",
            "sha256": "a" * 64,
            "size_bytes": 22,
        },
        created_at=NOW,
    )
    ResourceSample.objects.create(
        mission=mission,
        cpu_seconds=12.5,
        peak_memory_mb=512.0,
        wall_seconds=30.0,
        sandbox_count=2,
        sampled_at=NOW,
    )
    ResourceSample.objects.create(
        mission=mission,
        cpu_seconds=4.5,
        peak_memory_mb=900.0,
        wall_seconds=10.0,
        sandbox_count=1,
        sampled_at=NOW,
    )

    candidate_a, candidate_b = _two_candidate_mission(mission, finding)

    bundle = assemble_evidence_bundle(mission.id, now=NOW)

    assert bundle.mission_id == mission.id
    assert bundle.snapshot_sha256
    assert bundle.authorization_statement

    assert bundle.baseline is not None
    assert bundle.baseline.passed is True

    assert bundle.fuzzing is not None
    assert bundle.fuzzing.unique_crashes == 1

    assert len(bundle.findings) == 1
    assert len(bundle.reproducers) == 1
    assert bundle.reproducers[0].minimized is True

    assert {p.id for p in bundle.patches} == {candidate_a.id, candidate_b.id}
    assert len(bundle.verifications) == 2
    assert {str(v.verdict) for v in bundle.verifications} == {"VERIFIED", "REJECTED"}

    assert bundle.verdict_summary is not None
    assert bundle.verdict_summary.mission_verdict == Verdict.VERIFIED
    assert bundle.verdict_summary.verified_count == 1
    assert bundle.verdict_summary.rejected_count == 1
    assert bundle.recommended_patch_id == candidate_a.id

    # Resource usage is a real sum/max over the two ResourceSample rows, not a guess.
    assert bundle.resource_usage.cpu_seconds == pytest.approx(17.0)
    assert bundle.resource_usage.peak_memory_mb == pytest.approx(900.0)
    assert bundle.resource_usage.sandbox_count == 3

    # gates_not_run discloses the two optional gates neither candidate ran (the
    # conftest gate_matrix() helper leaves static_delta/renewed_fuzzing at their
    # NOT_RUN default), never silently dropped.
    assert len(bundle.gates_not_run) == 4  # 2 candidates x 2 not-run optional gates
    assert all("STATIC_DELTA" in e or "RENEWED_FUZZING" in e for e in bundle.gates_not_run)

    # The always-on subprocess-jail disclosure is present (D-049; #15 is not built).
    kinds = {str(s.kind) for s in bundle.substitutions}
    assert "SUBPROCESS_JAIL_ISOLATION" in kinds
    # Both candidates are OPERATOR_SUPPLIED in this fixture -> disclosed too.
    assert "OPERATOR_SUPPLIED_PATCH" in kinds

    # And the markdown renderer states the verdict and both candidates, not just the
    # schema round-tripping cleanly.
    markdown = render_markdown(bundle)
    assert "VERIFIED" in markdown
    assert str(candidate_a.id) in markdown
    assert str(candidate_b.id) in markdown
    assert "No baseline recorded" not in markdown
    assert "No patch candidates" not in markdown

    matrix = render_gate_matrix(bundle)
    assert len(matrix) == 2
    assert {row["verdict"] for row in matrix} == {"VERIFIED", "REJECTED"}


# ---------------------------------------------------------------------------------
# 2. Partial data — honest disclosure, not a fabricated placeholder
# ---------------------------------------------------------------------------------


def test_partial_data_bundle_discloses_absence_honestly(mission):
    """A mission that reached `EXPORTING` with nothing recorded past its snapshot and
    authorization — the shape a `CORRELATE`-found-nothing mission would carry if it
    reached this stage. Every optional section is `None`/empty, never a fabricated
    zeroed placeholder, and `render_markdown` says so in words."""
    walk_to(mission, MissionState.EXPORTING)

    bundle = assemble_evidence_bundle(mission.id, now=NOW)

    assert bundle.baseline is None
    assert bundle.fuzzing is None
    assert bundle.findings == []
    assert bundle.reproducers == []
    assert bundle.patches == []
    assert bundle.verifications == []
    assert bundle.verdict_summary is None
    assert bundle.recommended_patch_id is None
    assert bundle.gates_not_run == []

    # Resource usage still has to be a real (zeroed) ResourceUsage — the schema
    # requires one — but the markdown explicitly flags that as "not measured", not
    # "measured at zero".
    assert bundle.resource_usage.cpu_seconds == 0.0
    assert bundle.resource_usage.sandbox_count == 0

    markdown = render_markdown(bundle)
    assert "No baseline recorded for this mission." in markdown
    assert "No fuzzing report recorded for this mission." in markdown
    assert "No findings recorded" in markdown
    assert "No patch candidates" in markdown
    assert "No verdict yet" in markdown
    assert "no `ResourceSample` rows exist" in markdown

    # No fabricated gate matrix rows either.
    assert render_gate_matrix(bundle) == []


# ---------------------------------------------------------------------------------
# 3. Failure modes
# ---------------------------------------------------------------------------------


def test_unknown_mission_raises_mission_not_found():
    with pytest.raises(MissionNotFoundError):
        assemble_evidence_bundle("00000000-0000-0000-0000-000000000000", now=NOW)


def test_no_snapshot_raises_evidence_unavailable(db):
    bare = Mission.objects.create(
        name="no snapshot",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    with pytest.raises(EvidenceUnavailableError):
        assemble_evidence_bundle(bare.id, now=NOW)


def test_no_authorization_raises_evidence_unavailable(db):
    from missions.models import Snapshot

    bare = Mission.objects.create(
        name="no authorization",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    Snapshot.objects.create(
        mission=bare,
        commit_sha="0" * 40,
        archive_sha256="f" * 64,
        file_count=1,
        bytes_total=1,
    )
    with pytest.raises(EvidenceUnavailableError):
        assemble_evidence_bundle(bare.id, now=NOW)


# ---------------------------------------------------------------------------------
# 4. SEC-50, D-071c — sanitized at the source, not only at the export boundary
# ---------------------------------------------------------------------------------
#
# `GET /missions/{id}/evidence` (`api/routers/evidence.py::get_evidence`) calls
# `assemble_evidence_bundle` directly and returns the result as the ninja response
# body — it never goes anywhere near `orchestrator.evidence_export`, so the SEC-48
# fix (which only sanitized at the export boundary) left this function's raw,
# unredacted output reaching that endpoint. This is the reviewer's exact
# reproduction of that scenario, run directly against `assemble_evidence_bundle` and
# serialized with `.model_dump_json()` the same way django-ninja does for the HTTP
# response — the adversarial test the fix is proven against.


def test_poisoned_detail_is_redacted_by_assemble_evidence_bundle_itself(mission, finding):
    """Rebuilds the identical D-071b reproduction (a fabricated `DATABASE_URL=
    postgresql://...` line embedded in a poisoned `compile` gate's `detail`), calls
    `assemble_evidence_bundle` directly (exactly what `get_evidence` does, with no
    intervening `export_mission` call), and serializes with `.model_dump_json()`
    (exactly what django-ninja does for the response). Before the SEC-50 fix, both
    `postgresql://` and `s3cr3t-pw` were present verbatim in this output; this test
    fails if that regresses."""
    walk_to(mission, MissionState.PATCH)
    candidate = candidates.record_patch_candidate(
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
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)
    poisoned_matrix = GateMatrix(
        compile=GateResult(
            name=GateName.COMPILE,
            status=GateStatus.FAIL,
            evidence_source=EvidenceSource.TOOL_EXECUTION,
            tool="cmake",
            detail=_POISONED_CONNECTION_STRING_DETAIL,
        ),
        reproducer_eliminated=GateResult.not_run(
            GateName.REPRODUCER_ELIMINATED,
            "Not run: configure failed before a replay binary existed.",
        ),
        regression_preserved=GateResult.not_run(
            GateName.REGRESSION_PRESERVED, "Not run: configure failed."
        ),
    )
    candidates.record_verification(
        mission.id,
        patch_id=candidate.id,
        gates=poisoned_matrix,
        started_at=NOW,
        finished_at=NOW,
        trace_id=TRACE,
        now=NOW,
    )
    transitions.transition(mission.id, MissionState.EXPORTING, trace_id=TRACE, now=NOW)

    # No call to export_mission anywhere in this test — this is exactly what
    # `get_evidence` does: read the bundle directly and hand it to the caller.
    bundle = assemble_evidence_bundle(mission.id, now=NOW)
    serialized = bundle.model_dump_json()  # what django-ninja serializes to the client

    for fragment in ("DATABASE_URL", "postgresql://", "s3cr3t-pw", "10.0.0.5", "CMake Error"):
        assert fragment not in serialized, (
            f"assemble_evidence_bundle's own model_dump_json() leaked a secret-shaped "
            f"fragment ({fragment!r}) — SEC-50 regression"
        )
    assert "[redacted at export boundary" in serialized

    # And on the raw Python object too, not just the serialized string — proves the
    # sanitization happened at assembly, not as an artifact of JSON encoding.
    for record in bundle.verifications:
        for result in record.gates.results():
            assert "postgresql://" not in (result.detail or "")
            assert "s3cr3t-pw" not in (result.detail or "")


def test_benign_detail_survives_assemble_evidence_bundle_unchanged(mission, finding):
    """The false-positive guard, at the same layer: a real, honest gate outcome —
    including `contracts/verdict.py`'s own `_CUT_REASON`, present on every
    `GateMatrix` by default — must survive `assemble_evidence_bundle` unredacted."""
    walk_to(mission, MissionState.PATCH)
    candidate = candidates.record_patch_candidate(
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
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)
    candidates.record_verification(
        mission.id,
        patch_id=candidate.id,
        gates=gate_matrix(),  # all PASS, benign tool/detail — the conftest default
        started_at=NOW,
        finished_at=NOW,
        trace_id=TRACE,
        now=NOW,
    )
    transitions.transition(mission.id, MissionState.EXPORTING, trace_id=TRACE, now=NOW)

    bundle = assemble_evidence_bundle(mission.id, now=NOW)
    serialized = bundle.model_dump_json()

    assert "[redacted at export boundary" not in serialized
    assert "Not run: cut from the seven-day build" in serialized
