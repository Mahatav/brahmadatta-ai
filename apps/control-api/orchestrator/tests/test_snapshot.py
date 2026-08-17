"""orchestrator.snapshot: materializing a mission's stored snapshot archive to disk
(#168, T0b)."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from django.test import override_settings

from authorization import archive, store
from authorization.errors import MissionNotFoundError, SnapshotArtifactUnavailableError
from missions.models import Artifact, Mission, Snapshot
from orchestrator.snapshot import materialize_snapshot

pytestmark = pytest.mark.django_db(transaction=True)


def _write_real_snapshot(tmp_path: Path, mission: Mission, artifact_root: Path) -> tuple[str, Path]:
    """Build a real source tree, tar it, ingest the tar into `artifact_root` (the same
    path `authorization.store`/`authorization.service` use for a real snapshot), and
    record the `Artifact` + `Snapshot` rows a real `POST .../snapshot` would have
    written. Returns the digest and the original source tree for comparison."""
    source = tmp_path / "repo-src"
    (source / "src").mkdir(parents=True)
    (source / "src" / "main.c").write_text("int main(void) { return 0; }\n")
    (source / "README.md").write_text("demo target\n")

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
    return result.sha256, source


def test_materialize_snapshot_round_trips_the_real_archive(tmp_path, mission):
    artifact_root = tmp_path / "artifacts"
    workspace_root = tmp_path / "workspaces"
    sha256, source = _write_real_snapshot(tmp_path, mission, artifact_root)

    with override_settings(ARTIFACT_ROOT=artifact_root):
        materialized = materialize_snapshot(mission.id, workspace_root=workspace_root)

    assert materialized.archive_sha256 == sha256
    assert materialized.mission_id == str(mission.id)
    assert materialized.path.is_dir()
    assert workspace_root.resolve() in materialized.path.resolve().parents

    source_files = sorted(
        p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file()
    )
    extracted_files = sorted(
        p.relative_to(materialized.path).as_posix()
        for p in materialized.path.rglob("*")
        if p.is_file()
    )
    assert extracted_files == source_files
    for rel in source_files:
        assert (materialized.path / rel).read_bytes() == (source / rel).read_bytes()
    assert materialized.file_count == len(source_files)


def test_materialize_snapshot_gives_each_call_a_fresh_isolated_directory(tmp_path, mission):
    """Two materializations of the same mission (e.g. a retried stage after a crash)
    never share or reuse a directory — each gets its own tree."""
    artifact_root = tmp_path / "artifacts"
    workspace_root = tmp_path / "workspaces"
    _write_real_snapshot(tmp_path, mission, artifact_root)

    with override_settings(ARTIFACT_ROOT=artifact_root):
        first = materialize_snapshot(mission.id, workspace_root=workspace_root)
        second = materialize_snapshot(mission.id, workspace_root=workspace_root)

    assert first.path != second.path
    assert first.path.is_dir()
    assert second.path.is_dir()
    # Writing into the second call's directory did not touch the first's content.
    assert (first.path / "src" / "main.c").exists()
    assert (second.path / "src" / "main.c").exists()


def test_materialize_snapshot_uses_the_default_workspace_root_when_none_is_given(
    tmp_path, mission
):
    artifact_root = tmp_path / "artifacts"
    default_root = tmp_path / "default-workspaces"
    _write_real_snapshot(tmp_path, mission, artifact_root)

    with override_settings(ARTIFACT_ROOT=artifact_root, SNAPSHOT_WORKSPACE_ROOT=default_root):
        materialized = materialize_snapshot(mission.id)

    assert default_root.resolve() in materialized.path.resolve().parents


def test_materialize_snapshot_refuses_a_mission_with_no_snapshot(tmp_path):
    mission = Mission.objects.create(
        name="no snapshot yet",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter="C_CMAKE_CTEST",
    )
    with pytest.raises(SnapshotArtifactUnavailableError):
        materialize_snapshot(mission.id, workspace_root=tmp_path / "workspaces")


def test_materialize_snapshot_refuses_when_the_recorded_archive_bytes_are_missing(
    tmp_path, mission
):
    """The `mission` fixture records a real `Snapshot` row (a fixed digest) but never
    ingests bytes for it anywhere — exactly the partial/failed-snapshot shape: a row
    says a snapshot exists, and there is nothing on disk under `ARTIFACT_ROOT` for its
    digest. This must fail closed, not synthesize an empty directory."""
    artifact_root = tmp_path / "artifacts"
    with override_settings(ARTIFACT_ROOT=artifact_root):
        with pytest.raises(SnapshotArtifactUnavailableError):
            materialize_snapshot(mission.id, workspace_root=tmp_path / "workspaces")


def test_materialize_snapshot_refuses_an_unknown_mission(tmp_path):
    with pytest.raises(MissionNotFoundError):
        materialize_snapshot(uuid.uuid4(), workspace_root=tmp_path / "workspaces")
