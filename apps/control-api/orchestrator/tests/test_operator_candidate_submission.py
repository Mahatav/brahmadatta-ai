"""T-3 (D-008, D-084, D-085): the actual proof this task exists to produce.

Three live rehearsals of the #50 D7 gate found there was no HTTP-reachable path for
an operator to supply a patch candidate, and the gate's own acceptance criteria need
**both** a `Verified` and a `Rejected` verdict produced in one run — a poor fit for a
live, non-deterministic model. This file drives `demo/repositories/pktcfg`'s own
`candidate-a-correct-bounds-fix.patch` and `candidate-b-rejected-crash-only-fix.patch`
through the real, unmodified pipeline **entirely through
`POST /missions/{id}/patches`** (the real Django test `Client`, real HTTP request/
response cycle, real auth) against one mission with a real, passed `BaselineReport`,
and confirms both verdicts come out the other end through the real `VERIFY` executor
— no scripted `GateMatrix`, no monkeypatch, real `git apply`/`cmake`/`ctest`.

Mirrors `orchestrator/tests/test_verify_dispatch.py::
test_the_real_pktcfg_pair_reaches_export_through_the_real_executor` exactly on the
VERIFY-and-onward half (same real executor, same real transition policy, same real
demo target) — the only thing new here is *how the candidates got recorded*: through
this task's HTTP endpoint instead of a direct `candidates.record_patch_candidate`
call in test setup. That is the entire point of this file.
"""

from __future__ import annotations

import json
import shutil
from datetime import timedelta

import pytest
from django.conf import settings
from django.test import Client, override_settings
from django.utils import timezone

from authorization.store import ingest_from_path
from contracts.enums import MissionState, PatchPolicyStatus, PatchProvenance, Verdict
from missions.models import BaselineReport, Job, JobKind, Mission, Reproducer, VerificationRecord
from orchestrator import transitions
from orchestrator.executors import ExecutorContext, JobOutcome, executor_for, transition_policy_for
from orchestrator.tests.conftest import CANDIDATE_A, CANDIDATE_B, NOW, TRACE, walk_to

pytestmark = pytest.mark.django_db(transaction=True)

DEMO_REPOSITORY = CANDIDATE_A.parents[1]
CRASH = DEMO_REPOSITORY / "crash" / "crash-literal-tab.bin"
OPERATOR_TOKEN = settings.CONTROL_API_TOKENS["operator"]


def bearer() -> dict[str, str]:
    return {"HTTP_AUTHORIZATION": f"Bearer {OPERATOR_TOKEN}"}


def _extend_authorization(mission: Mission) -> None:
    """`record_verification` (called from inside the real `_verify_executor`) reads
    real wall-clock time, not the fixed `NOW` every other write in this test uses —
    see `test_verify_dispatch.py`'s identical helper and docstring note."""
    mission.authorizations.update(expires_at=timezone.now() + timedelta(days=1))


def _submit(client: Client, mission_id, finding_id, diff_path, *, rationale: str) -> dict:
    response = client.post(
        f"/api/v1/missions/{mission_id}/patches",
        data=json.dumps(
            {
                "finding_id": str(finding_id),
                "diff": diff_path.read_text(),
                "rationale": rationale,
            }
        ),
        content_type="application/json",
        **bearer(),
    )
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["provenance"] == PatchProvenance.OPERATOR_SUPPLIED.value
    assert body["policy_status"] == PatchPolicyStatus.ACCEPTED.value
    return body


def _run_real_verify_job(mission: Mission, patch_id: str, tmp_path) -> None:
    """Claim-and-run one `VERIFY` job through the real registered executor and real
    transition policy — the same two functions `manage.py run_worker` and
    `manage.py run_orchestrator` call in production, invoked directly against the
    real demo target rather than through a materialized snapshot, exactly as
    `test_verify_dispatch.py`'s own real-toolchain tests do."""
    job = Job.objects.get(mission=mission, kind=JobKind.VERIFY, payload={"patch_id": patch_id})
    ctx = ExecutorContext(
        job=job,
        mission=mission,
        source_dir=DEMO_REPOSITORY,
        workspace_root=tmp_path / "workspace",
        trace_id=TRACE,
        cancel_requested=lambda: False,
    )
    executor = executor_for(JobKind.VERIFY)
    result = executor(ctx)
    assert result.outcome is JobOutcome.SUCCEEDED, result.detail

    job.state = "SUCCEEDED"
    job.finished_at = timezone.now()
    job.save(update_fields=["state", "finished_at"])

    policy = transition_policy_for(JobKind.VERIFY)
    next_state = policy(job, mission)
    if next_state is not None:
        transitions.transition(mission.id, next_state, trace_id=TRACE, now=NOW)


@pytest.mark.skipif(not DEMO_REPOSITORY.is_dir(), reason="demo target not present")
@pytest.mark.skipif(shutil.which("cmake") is None, reason="cmake not installed")
@pytest.mark.skipif(shutil.which("ctest") is None, reason="ctest not installed")
def test_candidate_a_and_b_both_verdicts_through_the_http_endpoint_and_the_real_executor(
    mission, finding, tmp_path
):
    client = Client()
    artifact_root = tmp_path / "artifacts"

    with override_settings(ARTIFACT_ROOT=artifact_root):
        # A real reproducer artifact, content-addressed the same way authorization.
        # store ingests one in production — without this, the reproducer gate has no
        # file to replay and resolves to NOT_RUN, which would derive HUMAN_REVIEW_
        # REQUIRED for candidate_a instead of VERIFIED (see contracts.verdict.
        # derive_verdict: a NOT_RUN required gate is never a silent pass).
        ingest = ingest_from_path(artifact_root, CRASH, max_bytes=10_000_000)
        Reproducer.objects.create(
            finding=finding,
            minimized=True,
            replay_attempts=1,
            replay_successes=1,
            test_command="pktcfg_replay crash-literal-tab.bin",
            artifact={
                "uri": f"artifact://{mission.id}/reproducer/{ingest.sha256}",
                "kind": "reproducer_input",
                "sha256": ingest.sha256,
                "size_bytes": ingest.bytes_written,
            },
            created_at=NOW,
        )

        # A real, passed BaselineReport (D-085's own measured pktcfg numbers: 8/8
        # ctest cases), so `run_verification`'s regression gate has a real
        # denominator to check against rather than the no-check default (P0-5).
        BaselineReport.objects.create(
            mission=mission,
            configure_ok=True,
            build_ok=True,
            tests_total=8,
            tests_passed=8,
            tests_failed=0,
            duration_seconds=1.0,
            adapter="C_CMAKE_CTEST",
            recorded_at=NOW,
        )

        walk_to(mission, MissionState.PATCH)
        _extend_authorization(mission)

        candidate_a = _submit(client, mission.id, finding.id, CANDIDATE_A, rationale="bounds fix")
        mission.refresh_from_db()
        assert mission.state_enum is MissionState.VERIFY  # first accepted submission advances it

        candidate_b = _submit(
            client, mission.id, finding.id, CANDIDATE_B, rationale="crash-only fix"
        )
        assert candidate_b["id"] != candidate_a["id"]

        assert Job.objects.filter(mission=mission, kind=JobKind.VERIFY).count() == 2

        _run_real_verify_job(mission, candidate_a["id"], tmp_path)
        mission.refresh_from_db()
        assert mission.state_enum is MissionState.VERIFY  # candidate_b's job still pending

        _run_real_verify_job(mission, candidate_b["id"], tmp_path)
        mission.refresh_from_db()
        assert mission.state_enum is MissionState.EXPORTING

    records = {
        str(record.patch_id): record.verdict
        for record in VerificationRecord.objects.filter(mission=mission)
    }
    assert records[candidate_a["id"]] == Verdict.VERIFIED.value
    assert records[candidate_b["id"]] == Verdict.REJECTED.value

    # The mission-level verdict: any-VERIFIED-wins (contracts.verdict.derive_mission_verdict).
    transitions.transition(mission.id, MissionState.VERIFIED, trace_id=TRACE, now=NOW)
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.VERIFIED
    assert mission.verdict == Verdict.VERIFIED.value

    # Provenance never inflated (D-008): both candidates are labelled exactly what
    # they are, end to end — recorded via HTTP, not the model gateway.
    for candidate in (candidate_a, candidate_b):
        assert candidate["provenance"] == PatchProvenance.OPERATOR_SUPPLIED.value
        assert candidate["model"] is None
