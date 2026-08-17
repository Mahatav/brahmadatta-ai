"""HTTP read paths for the evidence database (#32)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from django.conf import settings
from django.test import Client

from contracts.enums import (
    AnalyzerTool,
    DiscoveryMethod,
    EvidenceSource,
    FindingCategory,
    FuzzingMode,
    GateName,
    GateStatus,
    LanguageAdapter,
    PatchPolicyStatus,
    PatchProvenance,
    Severity,
)
from contracts.verdict import GateMatrix, GateResult
from missions.models import (
    BaselineReport,
    Finding,
    FuzzingReport,
    Mission,
    PatchCandidate,
    Reproducer,
    VerificationRecord,
)

pytestmark = pytest.mark.django_db

OPERATOR = settings.CONTROL_API_TOKENS["operator"]
REVIEWER = settings.CONTROL_API_TOKENS["reviewer"]
NOW = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
ARTIFACT = {
    "uri": "artifact://mission/reproducer/crash.bin",
    "kind": "crash-input",
    "sha256": "a" * 64,
    "size_bytes": 22,
}


def bearer(token: str) -> dict[str, str]:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.fixture
def client() -> Client:
    return Client()


@pytest.fixture
def evidence_rows():
    from datetime import timedelta

    from missions.models import Authorization, Snapshot

    mission = Mission.objects.create(
        name="pktcfg",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    # Snapshot + Authorization: assemble_evidence_bundle/export_mission (#168, T6)
    # require both to exist for this mission — see orchestrator.evidence_bundle's
    # EvidenceUnavailableError. Added here rather than a second fixture so the
    # existing findings/baseline/fuzzing/patch tests below keep working unmodified.
    Authorization.objects.create(
        mission=mission,
        statement="I am authorized to test this repository on behalf of the owner.",
        granted_by="Mahatav Arora",
        granted_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(hours=8),
        repository_ref="file:///demo/repositories/pktcfg",
    )
    Snapshot.objects.create(
        mission=mission,
        commit_sha="0" * 40,
        archive_sha256="d" * 64,
        file_count=31,
        bytes_total=120_000,
    )
    finding = Finding.objects.create(
        mission=mission,
        category=FindingCategory.HEAP_BUFFER_OVERFLOW.value,
        severity=Severity.CRITICAL.value,
        tool=AnalyzerTool.ADDRESS_SANITIZER.value,
        discovery_method=DiscoveryMethod.FUZZING_CAMPAIGN.value,
        file_path="src/decode.c",
        line=43,
        function="emit_tab",
        fingerprint="asan:emit-tab",
        reproducible=True,
        title="literal tab overflows decode buffer",
        sanitizer_report="sanitized stack only",
        code_slice="bounded source slice",
        detected_at=NOW,
    )
    Reproducer.objects.create(
        finding=finding,
        minimized=True,
        replay_attempts=5,
        replay_successes=5,
        test_command="./pktcfg_replay crash.bin 5",
        artifact=ARTIFACT,
        created_at=NOW,
    )
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
        log_ref={
            "uri": "artifact://mission/baseline/ctest-log",
            "kind": "ctest-log",
            "sha256": "b" * 64,
            "size_bytes": 4096,
        },
    )
    FuzzingReport.objects.create(
        mission=mission,
        mode=FuzzingMode.REPLAYED_CORPUS.value,
        harness="pktcfg_fuzz_one_input",
        engine="pktcfg_replay",
        runtime_seconds=3.0,
        executions=9,
        crashes_found=1,
        unique_crashes=1,
        corpus_size=9,
        sanitizers=["address", "undefined"],
        replay_source="artifact://mission/corpus/pktcfg-seed-corpus",
        recorded_at=NOW,
    )
    patch = PatchCandidate.objects.create(
        mission=mission,
        finding=finding,
        provenance=PatchProvenance.OPERATOR_SUPPLIED.value,
        diff="diff --git a/src/decode.c b/src/decode.c\n",
        files_changed=1,
        lines_changed=7,
        policy_status=PatchPolicyStatus.ACCEPTED.value,
        created_at=NOW,
    )
    verification = VerificationRecord.objects.create(
        mission=mission,
        patch=patch,
        gates=_passing_gates().model_dump(mode="json"),
        verdict="VERIFIED",
        started_at=NOW,
        finished_at=NOW,
        worktree_sha256="c" * 64,
    )
    return mission, finding, patch, verification


def test_findings_are_queryable_by_mission(client: Client, evidence_rows):
    mission, finding, _, _ = evidence_rows

    response = client.get(f"/api/v1/missions/{mission.id}/findings", **bearer(OPERATOR))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(finding.id)
    assert body["items"][0]["location"]["file_path"] == "src/decode.c"


def test_finding_detail_is_queryable_by_mission_and_finding(client: Client, evidence_rows):
    mission, finding, _, _ = evidence_rows

    response = client.get(
        f"/api/v1/missions/{mission.id}/findings/{finding.id}", **bearer(OPERATOR)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["id"] == str(finding.id)
    assert body["reproducer"]["artifact"]["sha256"] == "a" * 64
    assert body["reproducer"]["artifact"].keys() == ARTIFACT.keys()
    assert "content" not in json.dumps(body)


def test_baseline_fuzzing_patch_and_verification_reads(client: Client, evidence_rows):
    mission, _, patch, verification = evidence_rows

    assert (
        client.get(f"/api/v1/missions/{mission.id}/baseline", **bearer(OPERATOR)).json()[
            "tests_passed"
        ]
        == 8
    )
    assert (
        client.get(f"/api/v1/missions/{mission.id}/fuzzing", **bearer(OPERATOR)).json()[
            "unique_crashes"
        ]
        == 1
    )
    patches = client.get(f"/api/v1/missions/{mission.id}/patches", **bearer(OPERATOR)).json()
    assert patches["items"][0]["id"] == str(patch.id)

    response = client.get(
        f"/api/v1/missions/{mission.id}/patches/{patch.id}/verification",
        **bearer(OPERATOR),
    )
    assert response.status_code == 200
    assert response.json()["id"] == str(verification.id)
    assert response.json()["verdict"] == "VERIFIED"


def _override_export_roots(settings, tmp_path):
    settings.ARTIFACT_ROOT = tmp_path / "artifacts"
    settings.EXPORT_WORKSPACE_ROOT = tmp_path / "exports"


def test_get_evidence_bundle_returns_the_assembled_bundle(
    client: Client, evidence_rows, settings, tmp_path
):
    """`GET /evidence` (#168, T6) — previously `NotImplementedYetError`, now a real
    read over `orchestrator.evidence_bundle.assemble_evidence_bundle`."""
    _override_export_roots(settings, tmp_path)
    mission, finding, patch, _verification = evidence_rows

    response = client.get(f"/api/v1/missions/{mission.id}/evidence", **bearer(OPERATOR))

    assert response.status_code == 200
    body = response.json()
    assert body["mission_id"] == str(mission.id)
    assert body["baseline"]["tests_passed"] == 8
    assert body["fuzzing"]["unique_crashes"] == 1
    assert len(body["findings"]) == 1
    assert body["findings"][0]["id"] == str(finding.id)
    assert len(body["patches"]) == 1
    assert body["patches"][0]["id"] == str(patch.id)
    assert len(body["verifications"]) == 1
    assert body["verifications"][0]["verdict"] == "VERIFIED"
    assert body["verdict_summary"]["mission_verdict"] == "VERIFIED"
    assert body["recommended_patch_id"] == str(patch.id)
    assert body["isolation_mode"] == "SUBPROCESS_JAIL"
    assert "content" not in json.dumps(body)


def test_get_evidence_bundle_404s_for_unknown_mission(client: Client):
    response = client.get(
        "/api/v1/missions/00000000-0000-0000-0000-000000000000/evidence",
        **bearer(OPERATOR),
    )
    assert response.status_code == 404


def test_export_evidence_writes_a_durable_bundle_and_returns_202(
    client: Client, evidence_rows, settings, tmp_path
):
    """`POST /export` (#168, T6) — previously `NotImplementedYetError`, now a real
    write via `orchestrator.evidence_export.export_mission`: a durable, content-
    addressed tarball under `ARTIFACT_ROOT`, an `Export` row, and a 202 receipt."""
    _override_export_roots(settings, tmp_path)
    mission, _, _, _ = evidence_rows

    response = client.post(
        f"/api/v1/missions/{mission.id}/export",
        data=json.dumps({"formats": ["markdown", "json"], "include_artifacts": False}),
        content_type="application/json",
        **bearer(OPERATOR),
    )

    assert response.status_code == 202
    body = response.json()
    assert body["mission_id"] == str(mission.id)
    assert body["formats"] == ["markdown", "json"]
    assert len(body["artifacts"]) == 1
    artifact_ref = body["artifacts"][0]
    assert artifact_ref["kind"] == "evidence_bundle"
    stored_path = settings.ARTIFACT_ROOT / artifact_ref["sha256"][:2] / artifact_ref["sha256"]
    assert stored_path.is_file()


def test_export_evidence_requires_operator_role(client: Client, evidence_rows):
    mission, _, _, _ = evidence_rows

    response = client.post(
        f"/api/v1/missions/{mission.id}/export",
        data=json.dumps({}),
        content_type="application/json",
        **bearer(REVIEWER),
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------------
# SEC-50, D-071c: GET /evidence must be safe on its own, not only via POST /export
# ---------------------------------------------------------------------------------
#
# `get_evidence` calls `assemble_evidence_bundle` directly and never touches
# `orchestrator.evidence_export` — the SEC-48 fix, which only sanitized inside
# `export_mission`, left this endpoint returning the raw bundle. `READ_ROLES`
# includes REVIEWER, a read-only role with no export audit trail, so this exercises
# the exact exploit scenario the reviewer reproduced: one authenticated GET, no
# `POST /export` involved at all.


_POISONED_CONNECTION_STRING_DETAIL = (
    "cmake configure: -- Configuring done\n"
    "-- DATABASE_URL=postgresql://brahmadatta:s3cr3t-pw@10.0.0.5:5432/prod\n"
    "CMake Error: could not find CMAKE_C_COMPILER exit=1"
)


@pytest.fixture
def poisoned_evidence_rows():
    from datetime import timedelta

    from missions.models import Authorization, Snapshot

    mission = Mission.objects.create(
        name="pktcfg-poisoned",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    Authorization.objects.create(
        mission=mission,
        statement="I am authorized to test this repository on behalf of the owner.",
        granted_by="Mahatav Arora",
        granted_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(hours=8),
        repository_ref="file:///demo/repositories/pktcfg",
    )
    Snapshot.objects.create(
        mission=mission,
        commit_sha="0" * 40,
        archive_sha256="d" * 64,
        file_count=31,
        bytes_total=120_000,
    )
    finding = Finding.objects.create(
        mission=mission,
        category=FindingCategory.HEAP_BUFFER_OVERFLOW.value,
        severity=Severity.CRITICAL.value,
        tool=AnalyzerTool.ADDRESS_SANITIZER.value,
        discovery_method=DiscoveryMethod.FUZZING_CAMPAIGN.value,
        file_path="src/decode.c",
        line=43,
        function="emit_tab",
        fingerprint="asan:emit-tab-poisoned",
        reproducible=True,
        title="literal tab overflows decode buffer",
        sanitizer_report="sanitized stack only",
        code_slice="bounded source slice",
        detected_at=NOW,
    )
    patch = PatchCandidate.objects.create(
        mission=mission,
        finding=finding,
        provenance=PatchProvenance.OPERATOR_SUPPLIED.value,
        diff="diff --git a/src/decode.c b/src/decode.c\n",
        files_changed=1,
        lines_changed=7,
        policy_status=PatchPolicyStatus.ACCEPTED.value,
        created_at=NOW,
    )
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
    VerificationRecord.objects.create(
        mission=mission,
        patch=patch,
        gates=poisoned_matrix.model_dump(mode="json"),
        verdict="REJECTED",
        started_at=NOW,
        finished_at=NOW,
        worktree_sha256="c" * 64,
    )
    return mission


def test_get_evidence_bundle_redacts_poisoned_gate_detail_for_a_reviewer(
    client: Client, poisoned_evidence_rows
):
    """SEC-50: rebuilds the exact D-071b reproduction (a fabricated `DATABASE_URL=
    postgresql://...` line embedded in a poisoned `compile` gate's `detail`) and
    calls `GET /evidence` — no `POST /export` anywhere in this test — as a REVIEWER,
    the read-only, apparently-external-facing role the reviewer flagged as the exact
    blast radius. Before the fix, both `postgresql://` and `s3cr3t-pw` were present
    verbatim in this response body."""
    mission = poisoned_evidence_rows

    response = client.get(f"/api/v1/missions/{mission.id}/evidence", **bearer(REVIEWER))

    assert response.status_code == 200
    raw_body = response.content.decode()
    for fragment in ("DATABASE_URL", "postgresql://", "s3cr3t-pw", "10.0.0.5", "CMake Error"):
        assert fragment not in raw_body, (
            f"GET /evidence leaked a secret-shaped fragment ({fragment!r}) to a "
            f"REVIEWER — SEC-50 regression"
        )
    assert "[redacted at export boundary" in raw_body


def _passing_gates() -> GateMatrix:
    def gate(name: GateName) -> GateResult:
        return GateResult(
            name=name,
            status=GateStatus.PASS,
            evidence_source=EvidenceSource.TOOL_EXECUTION,
            tool="ctest 3.28.3",
        )

    return GateMatrix(
        compile=gate(GateName.COMPILE),
        reproducer_eliminated=gate(GateName.REPRODUCER_ELIMINATED),
        regression_preserved=gate(GateName.REGRESSION_PRESERVED),
    )
