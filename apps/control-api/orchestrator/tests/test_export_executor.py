"""`JobKind.EXPORT` executor + transition policy (#168, T6).

Four shapes of test, mirroring the assignment:

1. Registration against the shared contract (same one-liner every other T* executor
   test file opens with).
2. A full-data export: `SUCCEEDED`, a real `Export`/`Artifact` row, a receipt whose
   tarball actually exists in `ARTIFACT_ROOT`, and a transition policy that routes to
   `VERIFIED` — cross-checked against the real state machine via
   `orchestrator.transitions.transition`, same discipline `test_baseline_executor.py`
   uses.
3. Idempotent re-run (D-061 §3): a second executor call against the same mission does
   not re-render, re-tar, or duplicate the `Export`/`Artifact` row.
4. The zero-verifications trap this task's own handoff documents: a mission that
   reaches `EXPORTING` with no `VerificationRecord` at all must route to `FAILED`, not
   `HUMAN_REVIEW` — `assert_verdict_is_evidenced` refuses every verdict target,
   `HUMAN_REVIEW` included, when there is no evidence, and a policy that tried it would
   409-loop the mission in `EXPORTING` forever (the literal bug D-061 §6 names this
   task to prevent, one stage later).
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from contracts.enums import ErrorCode, MissionState, PatchPolicyStatus, PatchProvenance
from missions.models import Artifact, Export, Job, JobKind, JobState, Mission
from orchestrator import candidates, executors, transitions
from orchestrator.evidence_export import export_mission
from orchestrator.executors import ExecutorContext, JobOutcome
from orchestrator.export_executor import export_executor, export_transition_policy
from orchestrator.tests.conftest import CANDIDATE_A, NOW, TRACE, gate_matrix, walk_to

pytestmark = pytest.mark.django_db(transaction=True)


def _job(mission: Mission, *, state: str = JobState.RUNNING, result: dict | None = None) -> Job:
    return Job.objects.create(
        mission=mission,
        kind=JobKind.EXPORT,
        state=state,
        result=result or {},
        attempt=1,
        max_attempts=3,
        run_after=NOW,
        deadline_at=NOW + timedelta(minutes=30),
    )


def _ctx(mission: Mission, job: Job, tmp_path: Path) -> ExecutorContext:
    return ExecutorContext(
        job=job,
        mission=mission,
        source_dir=tmp_path / "unused-source",
        workspace_root=tmp_path / "workspace",
        trace_id=TRACE,
        cancel_requested=lambda: False,
    )


def _verified_mission(mission, finding):
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
        gates=gate_matrix(),
        started_at=NOW,
        finished_at=NOW,
        trace_id=TRACE,
        now=NOW,
    )
    transitions.transition(mission.id, MissionState.EXPORTING, trace_id=TRACE, now=NOW)
    mission.refresh_from_db()
    return candidate


# ---------------------------------------------------------------------------------
# 1. Registration
# ---------------------------------------------------------------------------------


def test_export_is_registered_against_the_shared_contract():
    assert executors.executor_for(JobKind.EXPORT) is export_executor
    assert executors.transition_policy_for(JobKind.EXPORT) is export_transition_policy


# ---------------------------------------------------------------------------------
# 2. Full-data export: SUCCEEDED, real durable artifact, correct routing
# ---------------------------------------------------------------------------------


def test_executor_writes_a_durable_bundle_and_policy_routes_to_verified(
    mission, finding, tmp_path, settings
):
    settings.ARTIFACT_ROOT = tmp_path / "artifacts"
    settings.EXPORT_WORKSPACE_ROOT = tmp_path / "exports"

    _verified_mission(mission, finding)

    job = _job(mission)
    result = export_executor(_ctx(mission, job, tmp_path))

    assert result.outcome is JobOutcome.SUCCEEDED
    assert result.error_code is None
    assert result.result["reused_existing"] is False
    assert result.result["artifact_count"] == 1

    export_row = Export.objects.get(mission=mission)
    assert str(export_row.id) == result.result["export_id"]
    assert export_row.formats == ["markdown", "json"]
    assert export_row.recommended_patch_id is not None

    artifact = Artifact.objects.get(mission=mission, kind="evidence_bundle")
    assert artifact.size_bytes > 0
    stored_path = settings.ARTIFACT_ROOT / artifact.sha256[:2] / artifact.sha256
    assert stored_path.is_file(), "the tarball must actually be on disk under ARTIFACT_ROOT"

    terminal_job = Job.objects.get(pk=job.id)
    terminal_job.state = JobState.SUCCEEDED
    terminal_job.result = result.result
    terminal_job.save(update_fields=["state", "result"])

    target = export_transition_policy(terminal_job, mission)
    assert target is MissionState.VERIFIED

    # Cross-checked against the real state machine, not just returned by the policy.
    transitions.transition(mission.id, target, trace_id=TRACE, now=NOW)
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.VERIFIED


def test_executor_reports_failed_export_as_failed_outcome(
    monkeypatch, mission, finding, tmp_path, settings
):
    settings.ARTIFACT_ROOT = tmp_path / "artifacts"
    settings.EXPORT_WORKSPACE_ROOT = tmp_path / "exports"
    _verified_mission(mission, finding)

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    import orchestrator.export_executor as export_executor_module

    monkeypatch.setattr(export_executor_module, "export_mission", _boom)

    job = _job(mission)
    result = export_executor(_ctx(mission, job, tmp_path))

    assert result.outcome is JobOutcome.FAILED
    assert result.error_code is ErrorCode.INTERNAL_ERROR
    assert result.retry is True  # attempt(1) < max_attempts(3)

    terminal_job = Job.objects.get(pk=job.id)
    terminal_job.state = JobState.FAILED
    terminal_job.result = result.result
    terminal_job.save(update_fields=["state", "result"])
    assert export_transition_policy(terminal_job, mission) is MissionState.FAILED


# ---------------------------------------------------------------------------------
# 3. Idempotent re-run (D-061 §3)
# ---------------------------------------------------------------------------------


def test_rerunning_the_executor_reuses_the_existing_export(mission, finding, tmp_path, settings):
    """SEC-42 (#176) / D-086: `job_mission_kind_unique` now makes two literal `Job`
    rows for `(mission, EXPORT)` impossible, matching production reality — a re-run
    reuses the *same* row via `retry_job`, it never gets a second one
    (`orchestrator.queue.ensure_jobs_enqueued`'s own docstring). The second executor
    call below reuses `first_job` rather than creating a `second_job`, the same way
    `test_executor_writes_a_durable_bundle_and_policy_routes_to_verified` above
    reuses `job` after mutating it in place, instead of the pre-fix version's two
    separately created rows."""
    settings.ARTIFACT_ROOT = tmp_path / "artifacts"
    settings.EXPORT_WORKSPACE_ROOT = tmp_path / "exports"
    _verified_mission(mission, finding)

    first_job = _job(mission)
    first = export_executor(_ctx(mission, first_job, tmp_path))
    assert first.result["reused_existing"] is False

    second = export_executor(_ctx(mission, first_job, tmp_path))

    assert second.outcome is JobOutcome.SUCCEEDED
    assert second.result["reused_existing"] is True
    assert second.result["export_id"] == first.result["export_id"]

    assert Export.objects.filter(mission=mission).count() == 1
    assert Artifact.objects.filter(mission=mission, kind="evidence_bundle").count() == 1


def test_export_mission_reuse_existing_false_creates_a_fresh_row_but_no_duplicate_bytes(
    mission, finding, tmp_path, settings
):
    """The HTTP-facing caller (`reuse_existing=False`): each call is a distinct
    export action (a new `Export` row, a new `export_id`), but the underlying tarball
    bytes are still content-addressed, so two exports of unchanged evidence never
    duplicate the artifact on disk — only the `Export` row is new."""
    settings.ARTIFACT_ROOT = tmp_path / "artifacts"
    settings.EXPORT_WORKSPACE_ROOT = tmp_path / "exports"
    _verified_mission(mission, finding)

    first = export_mission(mission.id, reuse_existing=False, now=NOW)
    second = export_mission(mission.id, reuse_existing=False, now=NOW)

    assert first.receipt.export_id != second.receipt.export_id
    assert Export.objects.filter(mission=mission).count() == 2
    # Same bundle content (same `now`) -> same tarball sha256 -> one Artifact row.
    assert Artifact.objects.filter(mission=mission, kind="evidence_bundle").count() == 1


# ---------------------------------------------------------------------------------
# 4. The zero-verifications trap
# ---------------------------------------------------------------------------------


def test_zero_verifications_routes_to_failed_never_a_verdict_state(mission, tmp_path, settings):
    """A mission that reached `EXPORTING` with no `VerificationRecord` at all (the
    `walk_to` fixture can produce this even though the real job-backed pipeline
    should not, per `CORRELATE`'s own routing — see `export_transition_policy`'s
    docstring). `HUMAN_REVIEW` looks like the "safe" choice and is not one:
    `assert_verdict_is_evidenced` refuses it exactly as it refuses `VERIFIED`."""
    walk_to(mission, MissionState.EXPORTING)

    settings.ARTIFACT_ROOT = tmp_path / "artifacts"
    settings.EXPORT_WORKSPACE_ROOT = tmp_path / "exports"

    job = _job(mission)
    result = export_executor(_ctx(mission, job, tmp_path))
    assert (
        result.outcome is JobOutcome.SUCCEEDED
    )  # the bundle itself is honestly empty, not an error

    terminal_job = Job.objects.get(pk=job.id)
    terminal_job.state = JobState.SUCCEEDED
    terminal_job.result = result.result
    terminal_job.save(update_fields=["state", "result"])

    target = export_transition_policy(terminal_job, mission)
    assert target is MissionState.FAILED

    # And it is in fact legal — the whole point of not guessing HUMAN_REVIEW/VERIFIED.
    transitions.transition(mission.id, target, trace_id=TRACE, now=NOW)
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.FAILED


def test_cancelled_job_defers_rather_than_guessing(mission):
    job = _job(mission, state=JobState.CANCELLED)
    assert export_transition_policy(job, mission) is None
