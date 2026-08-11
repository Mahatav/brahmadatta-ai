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
    mission = Mission.objects.create(
        name="pktcfg",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
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

    response = client.get(
        f"/api/v1/missions/{mission.id}/findings", **bearer(OPERATOR)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(finding.id)
    assert body["items"][0]["location"]["file_path"] == "src/decode.c"


def test_finding_detail_is_queryable_by_mission_and_finding(
    client: Client, evidence_rows
):
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
        client.get(f"/api/v1/missions/{mission.id}/baseline", **bearer(OPERATOR))
        .json()["tests_passed"]
        == 8
    )
    assert (
        client.get(f"/api/v1/missions/{mission.id}/fuzzing", **bearer(OPERATOR))
        .json()["unique_crashes"]
        == 1
    )
    patches = client.get(
        f"/api/v1/missions/{mission.id}/patches", **bearer(OPERATOR)
    ).json()
    assert patches["items"][0]["id"] == str(patch.id)

    response = client.get(
        f"/api/v1/missions/{mission.id}/patches/{patch.id}/verification",
        **bearer(OPERATOR),
    )
    assert response.status_code == 200
    assert response.json()["id"] == str(verification.id)
    assert response.json()["verdict"] == "VERIFIED"


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
