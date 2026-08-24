"""Materializing a mission's stored snapshot archive back onto disk (#168, T0b).

Every stage executor from `BASELINE` onward needs a real, writable directory on disk
to point a build/test tool at (`workers.baseline.run_baseline_stage`'s `source_dir`,
`orchestrator.verification.run_verification`'s `worktree`) — and today the only thing
recorded for a mission's snapshot is a `Snapshot` row naming a digest and an `Artifact`
row indexing content-addressed bytes under `ARTIFACT_ROOT/<sha256[0:2]>/<sha256>`
(`authorization.store`). Nothing turns the second of those into the first. This module
is that missing step, and nothing else: `authorization.archive.extract_archive` does
the actual, safety-checked extraction; everything here is resolving *which* archive a
mission's stage should extract and *where* the result should land.

## Failure modes this module refuses rather than guesses through

* **No snapshot recorded at all** — a mission that has not reached `SNAPSHOTTED` yet,
  or one whose ingest never completed. `SnapshotArtifactUnavailableError`.
* **A `Snapshot` row exists, but its archive bytes are not on disk** — the row was
  written, but ingestion was interrupted before (or failed after) the bytes reached
  their content-addressed location, or `ARTIFACT_ROOT` was reconfigured or wiped
  between then and now. Checked directly against the filesystem, not inferred from the
  `Artifact` index row's mere existence — see `_resolve_archive_path`.
  `SnapshotArtifactUnavailableError`.
* **The archive is on disk but unsafe or unreadable** — corrupt, truncated, or
  carrying a member `authorization.archive.extract_archive` refuses (a path-traversal
  name, a symlink/hardlink, a non-file/non-directory type, or a member whose declared
  or actual size would push the extraction past `settings.SNAPSHOT_MAX_BYTES` — a
  decompression bomb; round-4 review, HIGH-1). Propagated as
  `authorization.errors.UnreadableArchiveError` — this module adds no translation
  layer over that refusal, since "unreadable" and "unsafe" both already mean the same
  thing to a caller: there is nothing here to extract. This is also why
  `extract_archive` is called with `max_bytes=settings.SNAPSHOT_MAX_BYTES` below,
  rather than some independently-chosen extraction ceiling: it is the same number
  `authorization.service.create_mission_snapshot` already caps the *ingested* archive
  at, so the two ends of the round-trip cannot drift apart.
* **The write side fails** — a full disk, a permission error, anything else stopping
  bytes from reaching the fresh workspace directory once the archive itself has
  already passed every safety check. Propagated as
  `authorization.errors.SnapshotExtractionFailedError`.

## Isolation

Every call gets its own fresh directory — `<workspace_root>/<mission_id>/<uuid4>` —
never a path reused across calls or shared between missions. Two stages of the same
mission (or two retries of the same stage after a crash) each get an independent tree;
neither can observe or corrupt what the other wrote. `authorization.archive.
extract_archive` itself already refuses to extract into a directory that exists, which
is the second, independent enforcement of the same property at the one function that
actually writes to disk.

## Cleanup (#180, SEC-49)

This module only ever creates directories under `workspace_root` — it never removes
one, and callers must not assume it will. Two other places own that:
`missions.management.commands.run_worker`'s `_run_executor` removes the one directory
this function just returned, in a `finally`, the moment the caller's executor is done
with it (the normal path, for every job); `orchestrator.teardown.
SnapshotWorkspaceReaper` removes a mission's entire directory tree here, backstop-style,
once that mission reaches a teardown boundary (a worker killed outright before the
first path could run, or simply "this mission is done and nothing here is needed
again"). See either one's own docstring for why the boundary sits where it does.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from django.conf import settings

from authorization import archive, store
from authorization.errors import MissionNotFoundError, SnapshotArtifactUnavailableError
from missions.models import Mission
from orchestrator.repository import latest_snapshot_sha256


@dataclass(frozen=True)
class MaterializedSnapshot:
    """A mission's snapshot archive, extracted to a fresh directory on disk."""

    mission_id: str
    archive_sha256: str
    path: Path
    file_count: int
    bytes_total: int


def default_workspace_root() -> Path:
    """`SNAPSHOT_WORKSPACE_ROOT`, or a sibling of `ARTIFACT_ROOT` if unset.

    A function rather than a module-level constant so it always reads the setting at
    call time — the same reason every other root in this codebase
    (`authorization.service`'s reads of `ARTIFACT_ROOT`/`SNAPSHOT_SOURCE_ROOT`) is read
    from `django.conf.settings` at the point of use instead of being captured at import
    time, where a test's `override_settings` would never be seen.
    """
    configured = getattr(settings, "SNAPSHOT_WORKSPACE_ROOT", None)
    if configured:
        return Path(configured)
    return Path(settings.ARTIFACT_ROOT).parent / "workspaces"


def _resolve_archive_path(mission: Mission) -> tuple[str, Path]:
    """This mission's latest recorded snapshot digest and its real bytes on disk.

    Fails closed at both of the two points where "recorded" and "actually present"
    can diverge: no `Snapshot` row at all, and a `Snapshot` row whose digest has no
    file under `ARTIFACT_ROOT` (an interrupted or since-deleted ingest — the
    `Artifact` index row is *not* trusted as a substitute for checking the filesystem
    directly, since it is possible for that row to exist while the bytes it
    describes do not, or vice versa, and only the filesystem check answers the
    question this function actually needs answered: is there something here to
    extract).
    """
    sha256 = latest_snapshot_sha256(mission)
    if sha256 is None:
        raise SnapshotArtifactUnavailableError(
            "This mission has no recorded snapshot to extract. Ingest a snapshot "
            "before materializing one.",
            details={"mission_id": str(mission.id)},
        )

    archive_path = store.path_for(Path(settings.ARTIFACT_ROOT), sha256)
    if not archive_path.is_file():
        raise SnapshotArtifactUnavailableError(
            "This mission's snapshot is recorded but its archive bytes are not in "
            "the artifact store. The snapshot ingest may have failed partway "
            "through, or the artifact store was reset since it ran.",
            details={"mission_id": str(mission.id), "archive_sha256": sha256},
        )
    return sha256, archive_path


def materialize_snapshot(
    mission_id: UUID, *, workspace_root: Path | None = None
) -> MaterializedSnapshot:
    """Extract this mission's latest recorded snapshot to a fresh directory and
    return where it landed.

    `workspace_root` defaults to `default_workspace_root()`; a caller may pass its
    own (a test, or a future per-run override) but every call still gets its own
    fresh `<root>/<mission_id>/<uuid4>` directory underneath it — see the module
    docstring's "Isolation" section.
    """
    try:
        mission = Mission.objects.get(pk=mission_id)
    except Mission.DoesNotExist as exc:
        raise MissionNotFoundError(
            "No mission with that id.", details={"mission_id": str(mission_id)}
        ) from exc

    sha256, archive_path = _resolve_archive_path(mission)

    root = workspace_root if workspace_root is not None else default_workspace_root()
    mission_root = root / str(mission.id)
    mission_root.mkdir(parents=True, mode=0o700, exist_ok=True)
    dest_dir = mission_root / uuid.uuid4().hex

    info = archive.extract_archive(
        archive_path, dest_dir, max_bytes=settings.SNAPSHOT_MAX_BYTES
    )

    return MaterializedSnapshot(
        mission_id=str(mission.id),
        archive_sha256=sha256,
        path=dest_dir,
        file_count=info.file_count,
        bytes_total=info.bytes_total,
    )
