"""`POST /missions/{id}/patches` (T-3, D-008) — the HTTP surface: auth, validation,
provenance, and dispatch into a real `VERIFY` job.

Real toolchain, real gate verdicts (both `VERIFIED` and `REJECTED`, driven entirely
through this HTTP endpoint) live in
`orchestrator/tests/test_operator_candidate_submission.py`, mirroring
`orchestrator/tests/test_verify_dispatch.py`'s own split between fast routing tests
here and the real-executor proof there.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from django.conf import settings
from django.test import Client

from contracts.enums import (
    AnalyzerTool,
    DiscoveryMethod,
    FindingCategory,
    LanguageAdapter,
    MissionState,
    PatchPolicyStatus,
    PatchProvenance,
    Severity,
)
from missions.models import Authorization, Finding, Job, JobKind, Mission, Snapshot
from orchestrator import transitions

pytestmark = pytest.mark.django_db

OPERATOR = settings.CONTROL_API_TOKENS["operator"]
REVIEWER = settings.CONTROL_API_TOKENS["reviewer"]
NOW = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
TRACE = "test-trace-operator-candidate"

VALID_DIFF = """diff --git a/src/decode.c b/src/decode.c
index 0180959..a06b601 100644
--- a/src/decode.c
+++ b/src/decode.c
@@ -72,6 +72,8 @@ size_t pkt_decoded_length(const uint8_t *src, size_t len, int escaped)
             continue;
         }

+        need += 1;
+
         /* Every remaining byte is copied through as-is. */
         need += 1;
         i += 1;
"""


def bearer(token: str) -> dict[str, str]:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.fixture
def client() -> Client:
    return Client()


@pytest.fixture
def mission_in_patch() -> tuple[Mission, Finding]:
    mission = Mission.objects.create(
        name="pktcfg demo",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={
            "patch": {
                "allowed_paths": ["src/decode.c"],
                "max_files_changed": 1,
                "max_lines_changed": 40,
            }
        },
    )
    Authorization.objects.create(
        mission=mission,
        statement="I am authorized to test this repository on behalf of the owner.",
        granted_by="Mahatav Arora",
        # `record_patch_candidate`/`transitions.transition` in the endpoint under test
        # read real wall-clock time (no `now=` is threaded through the HTTP request),
        # while `walk_to`-style setup in this fixture uses the fixed `NOW` below —
        # generous on both sides so this test's authorization window covers whichever
        # of the two a given check reads, regardless of what time of day the suite runs.
        granted_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=3650),
        repository_ref="file:///demo/repositories/pktcfg",
    )
    Snapshot.objects.create(
        mission=mission,
        commit_sha="0" * 40,
        archive_sha256="a" * 64,
        file_count=31,
        bytes_total=120_000,
    )
    finding = Finding.objects.create(
        mission=mission,
        category=FindingCategory.HEAP_BUFFER_OVERFLOW.value,
        severity=Severity.HIGH.value,
        tool=AnalyzerTool.ADDRESS_SANITIZER.value,
        discovery_method=DiscoveryMethod.FUZZING_CAMPAIGN.value,
        file_path="src/decode.c",
        line=74,
        function="pkt_decoded_length",
        fingerprint="pktcfg-literal-tab-overflow",
        reproducible=True,
        title="heap-buffer-overflow expanding a literal tab",
        detected_at=NOW,
    )
    for state in (
        MissionState.AUTHORIZED,
        MissionState.SNAPSHOTTED,
        MissionState.VALIDATING,
        MissionState.BASELINE,
        MissionState.TRIAGE,
        MissionState.STRESS_TEST,
        MissionState.CORRELATE,
        MissionState.PATCH,
    ):
        transitions.transition(mission.id, state, trace_id=TRACE, now=NOW)
    mission.refresh_from_db()
    return mission, finding


def _post(client: Client, mission_id, finding_id, diff, *, token=OPERATOR, rationale=""):
    return client.post(
        f"/api/v1/missions/{mission_id}/patches",
        data=json.dumps(
            {"finding_id": str(finding_id), "diff": diff, "rationale": rationale}
        ),
        content_type="application/json",
        **bearer(token),
    )


def test_submitting_a_candidate_requires_operator_role(client, mission_in_patch):
    mission, finding = mission_in_patch
    response = _post(client, mission.id, finding.id, VALID_DIFF, token=REVIEWER)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_submitting_a_candidate_requires_a_token(client, mission_in_patch):
    mission, finding = mission_in_patch
    response = client.post(
        f"/api/v1/missions/{mission.id}/patches",
        data=json.dumps({"finding_id": str(finding.id), "diff": VALID_DIFF}),
        content_type="application/json",
    )
    assert response.status_code == 401


def test_valid_submission_is_recorded_as_operator_supplied_and_never_carries_model_provenance(
    client, mission_in_patch
):
    mission, finding = mission_in_patch
    response = _post(client, mission.id, finding.id, VALID_DIFF, rationale="operator fix")

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["mission_id"] == str(mission.id)
    assert body["finding_id"] == str(finding.id)
    assert body["provenance"] == PatchProvenance.OPERATOR_SUPPLIED.value
    assert body["model"] is None
    assert body["rationale"] == "operator fix"
    assert body["policy_status"] == PatchPolicyStatus.ACCEPTED.value


def test_a_caller_cannot_claim_model_generated_provenance(client, mission_in_patch):
    """`OperatorPatchCandidateRequest` has no `provenance` field at all — an operator
    posting a diff has no vocabulary to claim it came from the model."""
    mission, finding = mission_in_patch
    response = client.post(
        f"/api/v1/missions/{mission.id}/patches",
        data=json.dumps(
            {
                "finding_id": str(finding.id),
                "diff": VALID_DIFF,
                "provenance": "MODEL_GENERATED",
            }
        ),
        content_type="application/json",
        **bearer(OPERATOR),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_accepted_submission_transitions_patch_to_verify_and_enqueues_a_real_verify_job(
    client, mission_in_patch
):
    mission, finding = mission_in_patch
    response = _post(client, mission.id, finding.id, VALID_DIFF)
    assert response.status_code == 201, response.content
    patch_id = response.json()["id"]

    mission.refresh_from_db()
    assert mission.state_enum is MissionState.VERIFY

    job = Job.objects.get(mission=mission, kind=JobKind.VERIFY)
    assert job.payload == {"patch_id": patch_id}
    assert job.state == "QUEUED"


def test_a_second_accepted_submission_to_the_same_still_open_mission_also_dispatches(
    client, mission_in_patch
):
    """Mirrors the fan-out `orchestrator/tests/test_verify_dispatch.py` already
    exercises directly: two operator candidates against one mission, both reach
    VERIFY, no candidate-set-frozen error before any verification has actually run."""
    mission, finding = mission_in_patch
    first = _post(client, mission.id, finding.id, VALID_DIFF)
    assert first.status_code == 201, first.content

    second = _post(client, mission.id, finding.id, VALID_DIFF, rationale="second try")
    assert second.status_code == 201, second.content
    assert second.json()["id"] != first.json()["id"]

    assert Job.objects.filter(mission=mission, kind=JobKind.VERIFY).count() == 2
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.VERIFY


def test_policy_rejected_submission_is_recorded_but_nothing_is_enqueued(
    client, mission_in_patch
):
    """The mission fixture's own policy allows only `src/decode.c`; a diff touching a
    different path is policy-rejected by the same real, deterministic
    `evaluate_patch_policy` a model-generated candidate goes through."""
    mission, finding = mission_in_patch
    out_of_scope_diff = VALID_DIFF.replace("src/decode.c", "src/other.c")

    response = _post(client, mission.id, finding.id, out_of_scope_diff)

    assert response.status_code == 201, response.content
    assert response.json()["policy_status"] == PatchPolicyStatus.REJECTED_PATH_NOT_ALLOWED.value
    assert not Job.objects.filter(mission=mission, kind=JobKind.VERIFY).exists()
    mission.refresh_from_db()
    # Deliberately NOT advanced: a mission with nothing accepted stays in PATCH so a
    # follow-up submission remains possible, rather than parking in a VERIFY stage
    # with no job that will ever move it onward.
    assert mission.state_enum is MissionState.PATCH


def test_unknown_mission_is_404(client):
    from uuid import uuid4

    response = _post(client, uuid4(), uuid4(), VALID_DIFF)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_a_finding_from_another_mission_is_404(client, mission_in_patch):
    mission, _finding = mission_in_patch
    other = Mission.objects.create(
        name="other",
        repository_ref="file:///demo/repositories/other",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    foreign_finding = Finding.objects.create(
        mission=other,
        category=FindingCategory.HEAP_BUFFER_OVERFLOW.value,
        severity=Severity.HIGH.value,
        tool=AnalyzerTool.ADDRESS_SANITIZER.value,
        discovery_method=DiscoveryMethod.FUZZING_CAMPAIGN.value,
        file_path="src/decode.c",
        fingerprint="other",
        reproducible=True,
        title="other mission's finding",
        detected_at=NOW,
    )

    response = _post(client, mission.id, foreign_finding.id, VALID_DIFF)
    assert response.status_code == 404


def test_a_mission_not_yet_in_patch_refuses_the_submission(client):
    mission = Mission.objects.create(
        name="too early",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    finding = Finding.objects.create(
        mission=mission,
        category=FindingCategory.HEAP_BUFFER_OVERFLOW.value,
        severity=Severity.HIGH.value,
        tool=AnalyzerTool.ADDRESS_SANITIZER.value,
        discovery_method=DiscoveryMethod.FUZZING_CAMPAIGN.value,
        file_path="src/decode.c",
        fingerprint="too-early",
        reproducible=True,
        title="too early",
        detected_at=NOW,
    )

    response = _post(client, mission.id, finding.id, VALID_DIFF)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_unknown_request_fields_are_rejected(client, mission_in_patch):
    mission, finding = mission_in_patch
    response = client.post(
        f"/api/v1/missions/{mission.id}/patches",
        data=json.dumps(
            {"finding_id": str(finding.id), "diff": VALID_DIFF, "surprise": True}
        ),
        content_type="application/json",
        **bearer(OPERATOR),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
