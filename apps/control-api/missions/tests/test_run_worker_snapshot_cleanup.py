"""#180 (SEC-49): `run_worker`'s materialized snapshot workspace is actually removed.

`orchestrator.snapshot.materialize_snapshot` extracts a fresh, isolated
`<SNAPSHOT_WORKSPACE_ROOT>/<mission_id>/<uuid4>` directory on every claim, and
nothing ever removed one -- see the issue, and `run_worker`'s own module docstring
("Cleaning up the materialized snapshot workspace") for the fix. These tests prove,
through the real `run_worker` command (not a private helper called in isolation),
that:

1. The directory is present and populated *while* the executor is running (so the
   fix is not accidentally deleting it too early).
2. It is gone once the job finishes, on both the success and the unhandled-exception
   path -- `_run_executor`'s `finally` is unconditional.
3. The per-mission *parent* directory (`ExecutorContext.workspace_root`) is left
   alone -- that is deliberately not this cleanup's job, see
   `orchestrator.teardown.SnapshotWorkspaceReaper` for the backstop that does own it.
"""

from __future__ import annotations

import io
from datetime import timedelta
from pathlib import Path

import pytest
from django.core.management import call_command
from django.test import override_settings

from authorization import archive, store
from contracts.enums import MissionState
from missions.models import Artifact, Job, JobKind, JobState, Mission, Snapshot
from orchestrator import executors
from orchestrator.executors import ExecutorContext, ExecutorResult, JobOutcome
from orchestrator.tests.conftest import NOW, walk_to

pytestmark = pytest.mark.django_db(transaction=True)


def _write_real_snapshot(tmp_path: Path, mission: Mission, artifact_root: Path) -> None:
    """Same helper `orchestrator/tests/test_snapshot.py` uses: a real source tree,
    tarred, ingested into `artifact_root`, and recorded as a real `Snapshot` row --
    so `materialize_snapshot` has real bytes on disk to extract, not a fixture stub."""
    source = tmp_path / "repo-src"
    (source / "src").mkdir(parents=True)
    (source / "src" / "main.c").write_text("int main(void) { return 0; }\n")

    tar_path = tmp_path / "built.tar"
    archive.build_tar_from_directory(source, tar_path)
    result = store.ingest_from_path(artifact_root, tar_path, max_bytes=10_000_000)
    info = archive.enumerate_members(result.path)

    Artifact.objects.create(
        sha256=result.sha256, kind="snapshot", size_bytes=info.bytes_total, mission=mission
    )
    Snapshot.objects.create(
        mission=mission,
        archive_sha256=result.sha256,
        file_count=info.file_count,
        bytes_total=info.bytes_total,
    )


def _queue_baseline_job(mission: Mission) -> Job:
    walk_to(mission, MissionState.BASELINE)
    return Job.objects.create(
        mission=mission,
        kind=JobKind.BASELINE,
        state=JobState.QUEUED,
        run_after=NOW,
        deadline_at=NOW + timedelta(hours=1),
    )


def test_materialized_workspace_is_removed_after_a_successful_job(tmp_path, mission, monkeypatch):
    artifact_root = tmp_path / "artifacts"
    workspace_root = tmp_path / "workspaces"
    _write_real_snapshot(tmp_path, mission, artifact_root)
    job = _queue_baseline_job(mission)

    seen: dict[str, Path] = {}

    def _fake_executor(ctx: ExecutorContext) -> ExecutorResult:
        # Prove it's really there, populated, *while* the executor is running --
        # not just absent at the start.
        assert ctx.source_dir.is_dir()
        assert (ctx.source_dir / "src" / "main.c").is_file()
        seen["source_dir"] = ctx.source_dir
        seen["mission_root"] = ctx.workspace_root
        return ExecutorResult(outcome=JobOutcome.SUCCEEDED, detail="ok")

    monkeypatch.setitem(executors.EXECUTOR_REGISTRY, JobKind.BASELINE, _fake_executor)

    with override_settings(ARTIFACT_ROOT=str(artifact_root), SNAPSHOT_WORKSPACE_ROOT=str(workspace_root)):
        out = io.StringIO()
        call_command("run_worker", once=True, stdout=out)

    job.refresh_from_db()
    assert job.state == JobState.SUCCEEDED
    assert "source_dir" in seen, "the fake executor never ran"
    assert not seen["source_dir"].exists(), (
        "materialized snapshot workspace directory was not removed after the job finished"
    )
    # The per-mission parent (workspace_root) is deliberately left alone by this
    # cleanup path -- it may hold scratch content a later job in the same mission
    # still needs (ExecutorContext.workspace_root's own docstring).
    assert seen["mission_root"].exists()


def test_materialized_workspace_is_removed_even_when_the_executor_raises(tmp_path, mission, monkeypatch):
    artifact_root = tmp_path / "artifacts"
    workspace_root = tmp_path / "workspaces"
    _write_real_snapshot(tmp_path, mission, artifact_root)
    job = _queue_baseline_job(mission)

    seen: dict[str, Path] = {}

    def _blowing_up_executor(ctx: ExecutorContext) -> ExecutorResult:
        seen["source_dir"] = ctx.source_dir
        raise RuntimeError("a stage bug, simulated")

    monkeypatch.setitem(executors.EXECUTOR_REGISTRY, JobKind.BASELINE, _blowing_up_executor)

    with override_settings(ARTIFACT_ROOT=str(artifact_root), SNAPSHOT_WORKSPACE_ROOT=str(workspace_root)):
        out = io.StringIO()
        call_command("run_worker", once=True, stdout=out)

    job.refresh_from_db()
    assert job.state == JobState.FAILED
    assert "source_dir" in seen
    assert not seen["source_dir"].exists(), (
        "materialized snapshot workspace directory leaked after an unhandled "
        "executor exception -- the finally in _run_executor must run regardless"
    )


def test_materialized_workspace_is_removed_after_a_reported_failure(tmp_path, mission, monkeypatch):
    artifact_root = tmp_path / "artifacts"
    workspace_root = tmp_path / "workspaces"
    _write_real_snapshot(tmp_path, mission, artifact_root)
    job = _queue_baseline_job(mission)

    seen: dict[str, Path] = {}

    def _failing_executor(ctx: ExecutorContext) -> ExecutorResult:
        seen["source_dir"] = ctx.source_dir
        return ExecutorResult(outcome=JobOutcome.FAILED, detail="BASELINE_BUILD_FAILED")

    monkeypatch.setitem(executors.EXECUTOR_REGISTRY, JobKind.BASELINE, _failing_executor)

    with override_settings(ARTIFACT_ROOT=str(artifact_root), SNAPSHOT_WORKSPACE_ROOT=str(workspace_root)):
        call_command("run_worker", once=True, stdout=io.StringIO())

    job.refresh_from_db()
    assert job.state == JobState.FAILED
    assert not seen["source_dir"].exists()
