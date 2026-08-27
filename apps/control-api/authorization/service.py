"""Business logic behind `POST /missions/{id}/authorize` and `.../snapshot` (#18).

Both functions share one shape, and the shape is the point:

1. `SELECT ... FOR UPDATE` the mission row **first**. Every id and ref the request
   carries is checked against that locked row, never against what the caller merely
   claims it refers to — the lesson from SEC-15 on PR #110, where a candidate's
   `patch_id` was accepted without ever being compared to the mission being verified.
   Here: `AuthorizationRequest.repository_ref` is checked against `mission.repository_ref`
   (`_authorize`), and the archive `source`/`archive_ref`/`repository_ref` used to
   locate bytes is resolved only against paths the mission and the deployment
   allowlist actually permit (`_materialize_source`).
2. Write the new row (`Authorization` / `Snapshot`, both append-only models).
3. Hand the mission to `orchestrator.transitions.transition` **inside the same
   transaction**. A refused transition raises, the transaction rolls back, and the
   row from step 2 never commits — there is no state where an `Authorization` or
   `Snapshot` row exists but the mission's state does not reflect it.

The snapshot path additionally calls `authorization.guard.require_active_authorization`
immediately after locking the row and before resolving or reading anything — see that
module's docstring for why the check at the end of `transition` is not early enough on
its own.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from authorization import archive, store, target_allowlist
from authorization.errors import (
    AuthorizationScopeError,
    InvalidOperatorInputError,
    MissionNotFoundError,
    RepositoryOutOfScopeError,
    SnapshotAlreadyRecordedError,
    SnapshotArtifactClaimedError,
    SnapshotArtifactUnavailableError,
    SnapshotDigestMismatchError,
)
from authorization.guard import require_active_authorization
from contracts.authorization import AuthorizationRecord as AuthorizationSchema
from contracts.authorization import AuthorizationRequest
from contracts.enums import MissionStage, MissionState
from contracts.schemas.missions import SnapshotRecord as SnapshotSchema
from contracts.schemas.missions import SnapshotRequest
from missions.models import Artifact, Authorization, Mission, Snapshot
from orchestrator import transitions


def _lock_mission(mission_id: uuid.UUID) -> Mission:
    """`SELECT ... FOR UPDATE`, or `MissionNotFoundError`. Must run inside a transaction."""
    try:
        return Mission.objects.select_for_update().get(pk=mission_id)
    except Mission.DoesNotExist as exc:
        raise MissionNotFoundError(
            "No mission with that id.", details={"mission_id": str(mission_id)}
        ) from exc


def _require_consistent_artifact_metadata(artifact: Artifact, info) -> None:
    """The one residual check D-087/D-088 keep in place of raw cross-mission exclusivity.

    An existing `Artifact` row for this digest whose `kind`/`size_bytes` disagree with
    what this mission's own materialized/hashed source just produced is a genuine
    hash-workflow contradiction — under SHA-256 collision resistance it would require
    a hash break to occur legitimately — and is refused with the same, already-named,
    already-tested exception `#207`'s cross-mission check used to raise. This is a
    strictly more precise invariant than "different mission ID," which was never the
    real risk signal (see D-087's and D-088's records for the full analysis).
    """
    if artifact.kind != "snapshot" or artifact.size_bytes != info.bytes_total:
        raise SnapshotArtifactClaimedError(details={"sha256": artifact.sha256})


def authorize_mission(
    mission_id: uuid.UUID,
    payload: AuthorizationRequest,
    *,
    trace_id: str,
    now=None,
) -> AuthorizationSchema:
    """Record an operator's declaration of authority, and move CREATED -> AUTHORIZED.

    A mission not currently `CREATED` still accepts a new `Authorization` row — a
    renewal, for a mission whose original grant is close to `expires_at` — but does not
    attempt a state transition, since `CREATED -> AUTHORIZED` is the only transition
    this action drives and it is legal exactly once. `contracts.state_machine` picks
    the newest *active* record for every later check
    (`orchestrator.repository.load_active_authorization`), so a renewal takes effect
    immediately without needing to touch the mission's state at all.
    """
    now = now or timezone.now()
    with transaction.atomic():
        mission = _lock_mission(mission_id)

        if payload.repository_ref != mission.repository_ref:
            raise AuthorizationScopeError(
                details={
                    "mission_repository_ref": mission.repository_ref,
                    "requested_repository_ref": payload.repository_ref,
                },
            )

        expires_at = now + timedelta(minutes=payload.valid_for_minutes)
        record = Authorization.objects.create(
            mission=mission,
            statement=payload.statement,
            granted_by=payload.granted_by,
            granted_at=now,
            expires_at=expires_at,
            repository_ref=mission.repository_ref,
        )

        if mission.state_enum is MissionState.CREATED:
            transitions.transition(
                mission.id,
                MissionState.AUTHORIZED,
                trace_id=trace_id,
                reason=f"authorized by {payload.granted_by}",
                now=now,
            )

        return AuthorizationSchema.model_validate(record)


def create_mission_snapshot(
    mission_id: uuid.UUID,
    payload: SnapshotRequest,
    *,
    trace_id: str,
    now=None,
) -> SnapshotSchema:
    """Ingest an immutable snapshot: verify authorization, hash, index, record, gate.

    Refuses before reading a single byte if no active authorization covers `INGEST`
    (`authorization.guard.require_active_authorization`). Refuses if the archive's
    real, server-computed digest does not match what the caller asserted
    (`SnapshotDigestMismatchError`) — a swapped archive cannot silently inherit the
    caller's claimed hash, because the stored path is keyed by the hash this function
    computed, never by the one it was told.

    Mission-scoped claiming (D-087/D-088, closing `#207`/SEC-27). `Artifact.sha256` is
    the content-addressed index, not a per-mission lock: a digest already indexed by
    another mission is a legitimate content-dedup hit, not a conflict, so it is reused
    rather than refused. `Artifact.mission` is not read as an authorization or
    access-control gate anywhere downstream (`orchestrator.snapshot._resolve_archive_path`
    resolves purely by `sha256` against the filesystem), and the real per-mission
    provenance unit — `Snapshot`, append-only, one row per mission — is untouched by
    this: every mission that reuses a digest still gets its own fresh `Snapshot` row
    and independently re-runs and re-earns its own full pipeline. The one case still
    refused is a genuine hash-workflow contradiction: an existing `Artifact` row for
    this digest whose `kind`/`size_bytes` disagree with what this mission's own
    materialized source just produced — that would require a SHA-256 break to occur
    legitimately, and is a sharper signal than "different mission ID" ever was.
    """
    now = now or timezone.now()
    with transaction.atomic():
        mission = _lock_mission(mission_id)

        require_active_authorization(mission, MissionStage.INGEST, now)

        existing = mission.snapshots.order_by("-created_at").first()
        if existing is not None:
            if existing.archive_sha256 == payload.archive_sha256:
                return SnapshotSchema.model_validate(existing)
            raise SnapshotAlreadyRecordedError(
                details={
                    "existing_archive_sha256": existing.archive_sha256,
                    "requested_archive_sha256": payload.archive_sha256,
                },
            )

        source_path, cleanup = _materialize_source(mission, payload)
        try:
            result = store.ingest_from_path(
                Path(settings.ARTIFACT_ROOT),
                source_path,
                max_bytes=settings.SNAPSHOT_MAX_BYTES,
            )
        finally:
            cleanup()

        if result.sha256 != payload.archive_sha256:
            raise SnapshotDigestMismatchError(
                details={
                    "asserted_archive_sha256": payload.archive_sha256,
                    "computed_archive_sha256": result.sha256,
                },
            )

        info = archive.enumerate_members(result.path)

        existing_artifact = Artifact.objects.filter(pk=result.sha256).first()
        if existing_artifact is not None:
            _require_consistent_artifact_metadata(existing_artifact, info)
            # D-087/D-088: a digest another mission already indexed is a legitimate
            # content-dedup hit, not a conflict — reuse the existing Artifact row
            # rather than reassigning or duplicating it. This mission still earns its
            # own independent Snapshot row below.
        else:
            # The mission-row lock only ever protects *one* mission's row, so two
            # different missions' transactions never contend for the same lock — the
            # read above and this write are a check-then-act pair with nothing
            # spanning both, across missions. Under real concurrent writers the loser
            # here does not lose the *property* (`artifact.sha256` is the primary key,
            # so exactly one Artifact row can ever exist for a digest regardless of
            # the race) — without this catch it would lose the *documented refusal*:
            # a raw `IntegrityError` off the unique-violation, which `api.errors`
            # renders as an unhandled 500 rather than a clean outcome. Catching it
            # here turns "correct in outcome, wrong in the telling" into "correct in
            # both" without changing behavior in the non-racing case at all.
            #
            # The `create` runs inside its own nested `atomic()` — a savepoint, not a
            # new transaction — deliberately: on Postgres, an `IntegrityError` marks
            # the *enclosing* transaction as unusable for every statement that
            # follows, even if the exception itself is caught in Python. Without the
            # savepoint here, catching the error would stop the 500 but the next
            # statement (the `Snapshot.objects.create` below, still inside the outer
            # `transaction.atomic()` from `create_mission_snapshot`) would raise
            # `TransactionManagementError` instead — trading one unhandled exception
            # for another. The savepoint rolls back only this `create`, leaving the
            # mission-row lock and everything already written under it intact.
            try:
                with transaction.atomic():
                    Artifact.objects.create(
                        sha256=result.sha256,
                        kind="snapshot",
                        size_bytes=info.bytes_total,
                        mission=mission,
                    )
            except IntegrityError:
                winner = Artifact.objects.get(pk=result.sha256)
                _require_consistent_artifact_metadata(winner, info)
                # The winner's metadata is consistent with what this mission just
                # produced — a race against a concurrent legitimate ingest of the
                # same content (this mission's own retry, or another mission's
                # dedup hit). Nothing to refuse; reuse the winner's row.

        snapshot_row = Snapshot.objects.create(
            mission=mission,
            commit_sha=payload.commit_sha,
            archive_sha256=result.sha256,
            file_count=info.file_count,
            bytes_total=info.bytes_total,
        )

        transitions.transition(
            mission.id,
            MissionState.SNAPSHOTTED,
            trace_id=trace_id,
            reason="snapshot ingested",
            now=now,
        )

        return SnapshotSchema.model_validate(snapshot_row)


def _resolve_under_root(root: Path, ref: str) -> Path:
    """A relative path under `root`, refusing anything that could escape it."""
    if not ref or ref.startswith("/") or ".." in Path(ref).parts:
        raise InvalidOperatorInputError(
            "archive_ref must be a relative path with no parent references.",
            details={"archive_ref": ref},
        )
    root_resolved = root.resolve()
    candidate = (root_resolved / ref).resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise InvalidOperatorInputError(
            "archive_ref escapes the snapshot staging root.",
            details={"archive_ref": ref},
        )
    return candidate


def _repository_lookup_name(repository_ref: str) -> str:
    """Return the traversal-free lookup key used beneath the source allowlist.

    `repository_ref` is server-side mission data, not a value this request supplies —
    but it still gets the same treatment as path input. A scheme this function does
    not recognize is refused rather than guessed at; live remote fetch is out of scope.

    Only the reference's final path component is used to locate a directory, and only
    directly under `SNAPSHOT_SOURCE_ROOT` — `file:///demo/repositories/pktcfg` and
    `pktcfg` resolve identically. That is deliberate: nothing about the path an
    operator writes in `repository_ref` is walked or joined literally, so there is no
    string an operator can construct here that reaches outside the allowlisted root —
    the lookup key is a name, not a path.
    """
    ref = repository_ref
    if ref.startswith("file://"):
        ref = ref[len("file://") :]
    elif "://" in ref:
        raise RepositoryOutOfScopeError(
            "Only local, allowlisted repository references are ingestable by this "
            "endpoint; remote fetch is out of scope.",
            details={"repository_ref": repository_ref},
        )

    name = PurePosixPath(ref.replace("\\", "/")).name
    if not name or name in {".", ".."}:
        raise RepositoryOutOfScopeError(details={"repository_ref": repository_ref})
    return name


def _resolve_repository_ref(repository_ref: str) -> Path:
    """Resolve an unambiguous mission repository beneath the source allowlist.

    Basename lookup deliberately discards path-shaped input before joining it to the
    allowlisted root. Distinct repository references that collapse to the same key are
    refused, however: silently selecting one would bind a mission's evidence to the
    wrong repository (SEC-29).

    #181/SEC-57 fast-follow condition (a): `target_allowlist.assert_target_allowed`
    additionally refuses a `name` outside the SEC-57 target allowlist, while that
    gate's own self-expiring window is still open — see that module's own docstring
    for why it is presently a no-op (`is_enforced()` is `False` for any date after
    2026-08-20) and why it is built anyway.
    """
    name = _repository_lookup_name(repository_ref)
    target_allowlist.assert_target_allowed(name)
    for candidate_ref in Mission.objects.values_list("repository_ref", flat=True):
        if candidate_ref == repository_ref:
            continue
        try:
            candidate_name = _repository_lookup_name(candidate_ref)
        except RepositoryOutOfScopeError:
            # A remote/unsupported reference cannot claim a local lookup key.
            continue
        if candidate_name == name:
            raise RepositoryOutOfScopeError(
                "repository_ref is ambiguous within the snapshot source allowlist.",
                details={"repository_ref": repository_ref, "lookup_name": name},
            )

    root = Path(settings.SNAPSHOT_SOURCE_ROOT).resolve()
    candidate = (root / name).resolve()
    if candidate != root and root not in candidate.parents:
        raise RepositoryOutOfScopeError(details={"repository_ref": repository_ref})
    if not candidate.is_dir():
        raise SnapshotArtifactUnavailableError(
            "repository_ref does not resolve to a readable local directory.",
            details={"repository_ref": repository_ref},
        )
    return candidate


def _materialize_source(
    mission: Mission, payload: SnapshotRequest
) -> tuple[Path, Callable[[], None]]:
    """A real file on disk to hash, plus a cleanup callback for any temp file made.

    Three cases, all resolved against fixed, mission-owned boundaries rather than a
    caller-chosen one: an uploaded archive under
    `SNAPSHOT_STAGING_ROOT/<mission_id>`, an already-materialized export under the
    same mission staging namespace (`source="git"` with `archive_ref` set — e.g.
    produced by a future ingest job per the architecture spec's note that a remote
    fetch belongs ahead of this endpoint, not inside it), or a fresh deterministic
    tar built from the mission's own repository directory under `SNAPSHOT_SOURCE_ROOT`.
    """
    if payload.source == "upload" or payload.archive_ref:
        if not payload.archive_ref:
            raise InvalidOperatorInputError(
                "source='upload' requires archive_ref.",
                details={"source": payload.source},
            )
        staging_root = archive.mission_staging_root(
            Path(settings.SNAPSHOT_STAGING_ROOT), mission.id
        )
        path = _resolve_under_root(staging_root, payload.archive_ref)
        if not path.is_file():
            raise SnapshotArtifactUnavailableError(
                "No archive at archive_ref in this mission's snapshot staging root. "
                "Stage the archive for this mission before recording the snapshot.",
                details={
                    "archive_ref": payload.archive_ref,
                    "mission_id": str(mission.id),
                },
            )
        return path, lambda: None

    source_dir = _resolve_repository_ref(mission.repository_ref)
    tmp_root = Path(settings.ARTIFACT_ROOT) / ".tmp"
    tmp_root.mkdir(parents=True, mode=0o700, exist_ok=True)
    tmp_path = tmp_root / f"{uuid.uuid4().hex}.tar"
    archive.build_tar_from_directory(source_dir, tmp_path)
    return tmp_path, lambda: tmp_path.unlink(missing_ok=True)
