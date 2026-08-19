"""HTTP-level tests for `POST .../authorize` and `POST .../snapshot` (#18).

This is the gate that makes every later claim in the product legitimate: an operator
authorizes a repository, the system takes an immutable snapshot and records its hash,
and nothing runs before either step. The tests below are grouped around the four
acceptance criteria on issue #18, each with the refusal path proven by actually
triggering it — a green assertion with nothing injected to make it fail is not
evidence of anything.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from django.conf import settings
from django.test import Client, override_settings

from authorization.archive import build_tar_from_directory, mission_staging_root
from contracts.enums import LanguageAdapter, MissionState
from missions.models import Artifact, Authorization, Mission, Snapshot

pytestmark = pytest.mark.django_db

OPERATOR = settings.CONTROL_API_TOKENS["operator"]
REVIEWER = settings.CONTROL_API_TOKENS["reviewer"]


def bearer(token: str) -> dict[str, str]:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.fixture
def client() -> Client:
    return Client()


@pytest.fixture
def mission() -> Mission:
    return Mission.objects.create(
        name="pktcfg",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )


@pytest.fixture
def roots(tmp_path: Path):
    """Fresh artifact/source/staging roots per test, never the real repo tree."""
    artifact_root = tmp_path / "artifacts"
    source_root = tmp_path / "sources"
    staging_root = tmp_path / "uploads"
    source_root.mkdir()
    staging_root.mkdir()
    with override_settings(
        ARTIFACT_ROOT=artifact_root,
        SNAPSHOT_SOURCE_ROOT=source_root,
        SNAPSHOT_STAGING_ROOT=staging_root,
        SNAPSHOT_MAX_BYTES=10_000_000,
    ):
        yield {
            "artifact_root": artifact_root,
            "source_root": source_root,
            "staging_root": staging_root,
        }


@pytest.fixture
def repo_dir(roots, mission: Mission) -> Path:
    """A real directory under SNAPSHOT_SOURCE_ROOT named after the mission's own
    repository_ref, with real file content the endpoint can snapshot."""
    target = roots["source_root"] / "pktcfg"
    (target / "src").mkdir(parents=True)
    (target / "src" / "main.c").write_text("int main(void) { return 0; }\n")
    (target / ".git").mkdir()
    (target / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    return target


def expected_digest(source_dir: Path, tmp_path: Path) -> str:
    """Build the same tar the endpoint would build, to get the real expected digest."""
    out = tmp_path / "expected.tar"
    build_tar_from_directory(source_dir, out)
    return hashlib.sha256(out.read_bytes()).hexdigest()


def stage_upload_archive(
    roots: dict[str, Path], mission: Mission, source_dir: Path, archive_ref: str
) -> str:
    staged_path = mission_staging_root(roots["staging_root"], mission.id) / archive_ref
    staged_path.parent.mkdir(parents=True, exist_ok=True)
    build_tar_from_directory(source_dir, staged_path)
    return hashlib.sha256(staged_path.read_bytes()).hexdigest()


def authorize_payload(**overrides) -> dict:
    payload = {
        "statement": "I am the registered owner and authorize this scan for the AI "
        "Kavach competition.",
        "granted_by": "Mahatav Arora",
        "repository_ref": "file:///demo/repositories/pktcfg",
        "valid_for_minutes": 240,
    }
    payload.update(overrides)
    return payload


def post(client: Client, path: str, payload: dict, token: str):
    return client.post(
        path,
        data=json.dumps(payload),
        content_type="application/json",
        **bearer(token),
    )


# === 1. Authorization is an explicit, recorded operator action =================


def test_authorize_records_an_operator_identity_and_a_server_timestamp(
    client: Client, mission: Mission
):
    before = datetime.now(UTC)
    response = post(
        client, f"/api/v1/missions/{mission.id}/authorize", authorize_payload(), OPERATOR
    )
    after = datetime.now(UTC)

    assert response.status_code == 201
    body = response.json()
    assert body["granted_by"] == "Mahatav Arora"
    assert body["mission_id"] == str(mission.id)
    # granted_at is server time, not anything the client could have sent — the
    # request schema (AuthorizationRequest) has no such field at all.
    granted_at = datetime.fromisoformat(body["granted_at"].replace("Z", "+00:00"))
    assert before - timedelta(seconds=5) <= granted_at <= after + timedelta(seconds=5)

    record = Authorization.objects.get(pk=body["id"])
    assert record.mission_id == mission.id
    assert record.granted_by == "Mahatav Arora"

    mission.refresh_from_db()
    assert mission.state_enum is MissionState.AUTHORIZED


def test_authorization_request_cannot_set_granted_at_itself(client: Client, mission: Mission):
    """The client cannot back-date or forward-date a grant: the field does not exist
    on the request schema, so trying to supply it is a 422, not a silent override."""
    response = post(
        client,
        f"/api/v1/missions/{mission.id}/authorize",
        authorize_payload(granted_at="2020-01-01T00:00:00Z"),
        OPERATOR,
    )
    assert response.status_code == 422


def test_a_reviewer_cannot_authorize(client: Client, mission: Mission):
    response = post(
        client, f"/api/v1/missions/{mission.id}/authorize", authorize_payload(), REVIEWER
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert Authorization.objects.count() == 0


def test_authorize_against_a_missing_mission_is_404(client: Client):
    response = post(
        client, f"/api/v1/missions/{uuid4()}/authorize", authorize_payload(), OPERATOR
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_authorization_for_a_different_repository_is_refused(client: Client, mission: Mission):
    """SEC-15's lesson applied here: the declared repository_ref is checked against
    the mission's own row, under the same lock, not merely accepted."""
    response = post(
        client,
        f"/api/v1/missions/{mission.id}/authorize",
        authorize_payload(repository_ref="file:///demo/repositories/some-other-target"),
        OPERATOR,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INVALID_AUTHORIZATION"
    assert Authorization.objects.count() == 0
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.CREATED


def test_a_refused_authorize_leaves_no_authorization_row_behind(client: Client, mission: Mission):
    """The write and the transition happen in one transaction: if either would fail,
    neither is left committed."""
    post(
        client,
        f"/api/v1/missions/{mission.id}/authorize",
        authorize_payload(repository_ref="file:///wrong"),
        OPERATOR,
    )
    assert Authorization.objects.filter(mission=mission).count() == 0


def test_reauthorizing_a_mission_past_created_adds_a_record_without_retransitioning(
    client: Client, mission: Mission
):
    post(client, f"/api/v1/missions/{mission.id}/authorize", authorize_payload(), OPERATOR)
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.AUTHORIZED

    response = post(
        client, f"/api/v1/missions/{mission.id}/authorize", authorize_payload(), OPERATOR
    )
    assert response.status_code == 201
    assert Authorization.objects.filter(mission=mission).count() == 2
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.AUTHORIZED


# === 2 & 4. No stage runs without an authorization record — the refusal path ====


def test_snapshot_without_an_authorization_is_refused(client: Client, mission: Mission, roots):
    """The central refusal path for #18: a mission with no Authorization record at
    all must not be snapshotted."""
    response = client.post(
        f"/api/v1/missions/{mission.id}/snapshot",
        data=json.dumps({"source": "git", "archive_sha256": "0" * 64}),
        content_type="application/json",
        **bearer(OPERATOR),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INVALID_AUTHORIZATION"
    assert Snapshot.objects.filter(mission=mission).count() == 0
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.CREATED


def test_snapshot_with_an_expired_authorization_is_refused(
    client: Client, mission: Mission, roots
):
    """An authorization that has lapsed is exactly as absent as one that never
    existed — expiry is enforced, not merely stored."""
    now = datetime.now(UTC)
    Authorization.objects.create(
        mission=mission,
        statement="I am the registered owner and authorize this scan.",
        granted_by="Mahatav Arora",
        granted_at=now - timedelta(hours=5),
        expires_at=now - timedelta(hours=1),
        repository_ref=mission.repository_ref,
    )
    response = client.post(
        f"/api/v1/missions/{mission.id}/snapshot",
        data=json.dumps({"source": "git", "archive_sha256": "0" * 64}),
        content_type="application/json",
        **bearer(OPERATOR),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INVALID_AUTHORIZATION"


def test_snapshot_with_a_revoked_authorization_is_refused(client: Client, mission: Mission, roots):
    now = datetime.now(UTC)
    Authorization.objects.create(
        mission=mission,
        statement="I am the registered owner and authorize this scan.",
        granted_by="Mahatav Arora",
        granted_at=now - timedelta(minutes=10),
        expires_at=now + timedelta(hours=4),
        revoked_at=now - timedelta(minutes=1),
        repository_ref=mission.repository_ref,
    )
    response = client.post(
        f"/api/v1/missions/{mission.id}/snapshot",
        data=json.dumps({"source": "git", "archive_sha256": "0" * 64}),
        content_type="application/json",
        **bearer(OPERATOR),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INVALID_AUTHORIZATION"


def test_a_reviewer_cannot_snapshot(client: Client, mission: Mission, roots):
    response = client.post(
        f"/api/v1/missions/{mission.id}/snapshot",
        data=json.dumps({"source": "git", "archive_sha256": "0" * 64}),
        content_type="application/json",
        **bearer(REVIEWER),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# === 3. The hash is server-computed and immutable ===============================


def _authorize(client: Client, mission: Mission) -> None:
    response = post(
        client, f"/api/v1/missions/{mission.id}/authorize", authorize_payload(), OPERATOR
    )
    assert response.status_code == 201


def test_snapshot_records_a_server_computed_hash_and_advances_the_mission(
    client: Client, mission: Mission, roots, repo_dir: Path, tmp_path: Path
):
    _authorize(client, mission)
    digest = expected_digest(repo_dir, tmp_path)

    response = post(
        client,
        f"/api/v1/missions/{mission.id}/snapshot",
        {"source": "git", "archive_sha256": digest},
        OPERATOR,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["archive_sha256"] == digest
    assert body["file_count"] == 1
    assert body["immutable"] is True

    row = Snapshot.objects.get(pk=body["id"])
    assert row.archive_sha256 == digest

    artifact = Artifact.objects.get(pk=digest)
    assert artifact.mission_id == mission.id
    stored_path = Path(settings.ARTIFACT_ROOT) / digest[:2] / digest
    assert stored_path.is_file()
    assert hashlib.sha256(stored_path.read_bytes()).hexdigest() == digest

    mission.refresh_from_db()
    assert mission.state_enum is MissionState.SNAPSHOTTED


def test_a_digest_the_server_cannot_verify_is_refused(
    client: Client, mission: Mission, roots, repo_dir: Path
):
    """Inject the violation: assert a digest that does not match what is actually on
    disk, and confirm the endpoint refuses rather than trusting the claim."""
    _authorize(client, mission)

    response = post(
        client,
        f"/api/v1/missions/{mission.id}/snapshot",
        {"source": "git", "archive_sha256": "f" * 64},
        OPERATOR,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"
    assert Snapshot.objects.filter(mission=mission).count() == 0
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.AUTHORIZED


def test_upload_archive_ref_is_scoped_to_the_requesting_mission(
    client: Client, mission: Mission, roots, repo_dir: Path
):
    """SEC-30: an archive staged for mission B cannot be read by mission A just
    because both operators know the same archive_ref string."""
    other = Mission.objects.create(
        name="pktcfg-upload-owner",
        repository_ref="file:///demo/repositories/pktcfg-upload-owner",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    digest = stage_upload_archive(roots, other, repo_dir, "build.tar")

    _authorize(client, mission)
    response = post(
        client,
        f"/api/v1/missions/{mission.id}/snapshot",
        {"source": "upload", "archive_ref": "build.tar", "archive_sha256": digest},
        OPERATOR,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"
    assert Snapshot.objects.filter(mission=mission).count() == 0
    assert Artifact.objects.filter(pk=digest).count() == 0
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.AUTHORIZED

    post(
        client,
        f"/api/v1/missions/{other.id}/authorize",
        authorize_payload(repository_ref=other.repository_ref),
        OPERATOR,
    )
    owner_response = post(
        client,
        f"/api/v1/missions/{other.id}/snapshot",
        {"source": "upload", "archive_ref": "build.tar", "archive_sha256": digest},
        OPERATOR,
    )
    assert owner_response.status_code == 201
    assert Snapshot.objects.get(mission=other).archive_sha256 == digest
    assert Artifact.objects.get(pk=digest).mission_id == other.id


def test_a_swapped_archive_is_refused(client: Client, mission: Mission, roots, repo_dir: Path, tmp_path: Path):
    """A snapshot already exists; a second call naming a different digest for the same
    mission must not silently replace it — the record is write-once."""
    _authorize(client, mission)
    digest = expected_digest(repo_dir, tmp_path)
    first = post(
        client,
        f"/api/v1/missions/{mission.id}/snapshot",
        {"source": "git", "archive_sha256": digest},
        OPERATOR,
    )
    assert first.status_code == 201

    (repo_dir / "src" / "extra.c").write_text("void extra(void) {}\n")
    new_digest = expected_digest(repo_dir, tmp_path)
    assert new_digest != digest

    second = post(
        client,
        f"/api/v1/missions/{mission.id}/snapshot",
        {"source": "git", "archive_sha256": new_digest},
        OPERATOR,
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "CONFLICT"
    assert Snapshot.objects.filter(mission=mission).count() == 1
    assert Snapshot.objects.get(mission=mission).archive_sha256 == digest


def test_reposting_the_same_digest_is_idempotent(
    client: Client, mission: Mission, roots, repo_dir: Path, tmp_path: Path
):
    _authorize(client, mission)
    digest = expected_digest(repo_dir, tmp_path)

    first = post(
        client,
        f"/api/v1/missions/{mission.id}/snapshot",
        {"source": "git", "archive_sha256": digest},
        OPERATOR,
    )
    second = post(
        client,
        f"/api/v1/missions/{mission.id}/snapshot",
        {"source": "git", "archive_sha256": digest},
        OPERATOR,
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert Snapshot.objects.filter(mission=mission).count() == 1


def test_an_archive_digest_already_claimed_by_another_mission_is_reused_not_refused(
    client: Client, mission: Mission, roots, repo_dir: Path, tmp_path: Path
):
    """D-087/D-088 (closing `#207`/SEC-27): two missions producing byte-identical
    snapshots is a legitimate content-dedup hit, not a conflict. The second mission
    reuses the existing `Artifact` row — never reassigning it — and still earns its
    own independent `Snapshot` row and its own full pipeline re-run."""
    _authorize(client, mission)
    digest = expected_digest(repo_dir, tmp_path)
    first = post(
        client,
        f"/api/v1/missions/{mission.id}/snapshot",
        {"source": "git", "archive_sha256": digest},
        OPERATOR,
    )
    assert first.status_code == 201

    other = Mission.objects.create(
        name="pktcfg-again",
        repository_ref="file:///demo/repositories/pktcfg-again",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    other_dir = roots["source_root"] / "pktcfg-again"
    (other_dir / "src").mkdir(parents=True)
    (other_dir / "src" / "main.c").write_text("int main(void) { return 0; }\n")
    (other_dir / ".git").mkdir()
    (other_dir / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    other_digest = expected_digest(other_dir, tmp_path)
    assert other_digest == digest  # byte-identical content -> the same real hash

    post(
        client, f"/api/v1/missions/{other.id}/authorize",
        authorize_payload(repository_ref="file:///demo/repositories/pktcfg-again"),
        OPERATOR,
    )
    response = post(
        client,
        f"/api/v1/missions/{other.id}/snapshot",
        {"source": "git", "archive_sha256": other_digest},
        OPERATOR,
    )
    assert response.status_code == 201
    assert Snapshot.objects.filter(mission=other).count() == 1
    assert Snapshot.objects.get(mission=other).archive_sha256 == digest
    # Exactly one Artifact row for the digest, still owned by whichever mission
    # first claimed it — reused, not duplicated or reassigned.
    assert Artifact.objects.filter(pk=digest).count() == 1
    assert Artifact.objects.get(pk=digest).mission_id == mission.id
    other.refresh_from_db()
    assert other.state_enum is MissionState.SNAPSHOTTED


def test_an_artifact_with_mismatched_metadata_for_the_same_digest_is_refused(
    client: Client, mission: Mission, roots, repo_dir: Path, tmp_path: Path
):
    """D-087/D-088's residual, more precise check, replacing the removed raw
    cross-mission exclusivity check: an existing `Artifact` row for this digest whose
    `kind`/`size_bytes` disagree with what this mission's own materialized source just
    produced is a genuine hash-workflow contradiction, and is still refused."""
    other = Mission.objects.create(
        name="pktcfg-stale-index",
        repository_ref="file:///demo/repositories/pktcfg-stale-index",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    digest = expected_digest(repo_dir, tmp_path)
    # A pre-existing artifact index row for this exact digest, but with metadata that
    # could not legitimately describe the same bytes -- simulating an ingest-pipeline
    # bug rather than a real dedup hit.
    Artifact.objects.create(
        sha256=digest, kind="snapshot", size_bytes=999_999, mission=other
    )

    _authorize(client, mission)
    response = post(
        client,
        f"/api/v1/missions/{mission.id}/snapshot",
        {"source": "git", "archive_sha256": digest},
        OPERATOR,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"
    assert Snapshot.objects.filter(mission=mission).count() == 0
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.AUTHORIZED
    # The stale row is untouched, not silently overwritten.
    assert Artifact.objects.get(pk=digest).size_bytes == 999_999


def test_deleting_the_claiming_mission_lets_a_new_mission_reclaim_the_digest(
    client: Client, mission: Mission, roots, repo_dir: Path, tmp_path: Path
):
    """D-088's flagged regression test. `Artifact.mission` is `on_delete=CASCADE`. If
    the first-claiming mission's row is ever hard-deleted (only reachable today via
    the scoped dev-DB-reset runbook (T-6), never via any product code path), the
    `Artifact` row cascades away with it -- but the physical bytes under
    `ARTIFACT_ROOT` are untouched by a DB-row delete, and a later ingest of the same
    content self-heals cleanly by creating a fresh `Artifact` row via the existing
    idempotent-write path, rather than leaving the digest permanently unclaimable or
    orphaning the second mission's evidence."""
    _authorize(client, mission)
    digest = expected_digest(repo_dir, tmp_path)

    first = post(
        client,
        f"/api/v1/missions/{mission.id}/snapshot",
        {"source": "git", "archive_sha256": digest},
        OPERATOR,
    )
    assert first.status_code == 201
    assert Artifact.objects.filter(pk=digest).count() == 1
    stored_path = Path(settings.ARTIFACT_ROOT) / digest[:2] / digest
    assert stored_path.is_file()

    mission.delete()
    assert Artifact.objects.filter(pk=digest).count() == 0
    assert stored_path.is_file()  # disk-level store is untouched by the DB delete

    other = Mission.objects.create(
        name="pktcfg-after-reset",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    post(
        client,
        f"/api/v1/missions/{other.id}/authorize",
        authorize_payload(),
        OPERATOR,
    )
    second = post(
        client,
        f"/api/v1/missions/{other.id}/snapshot",
        {"source": "git", "archive_sha256": digest},
        OPERATOR,
    )
    assert second.status_code == 201
    assert Snapshot.objects.get(mission=other).archive_sha256 == digest
    artifact = Artifact.objects.get(pk=digest)
    assert artifact.mission_id == other.id
    assert hashlib.sha256(stored_path.read_bytes()).hexdigest() == digest
    other.refresh_from_db()
    assert other.state_enum is MissionState.SNAPSHOTTED


def test_a_toctou_race_with_mismatched_metadata_is_refused_not_a_500(
    client: Client, mission: Mission, roots, repo_dir: Path, tmp_path: Path, monkeypatch
):
    """SEC-27 (round-4 security review), updated for D-087/D-088. The mission-row lock
    only ever protects one mission's row, so the read-then-write pair that claims an
    `Artifact` for a digest is not atomic across *different* missions' transactions —
    under real concurrent Postgres writers, the review reproduced a losing request
    getting an unhandled `IntegrityError` (500). D-087/D-088 removed the raw
    cross-mission exclusivity refusal (a same-digest race across missions is now a
    legitimate dedup hit, reused rather than refused — see
    `test_an_archive_digest_already_claimed_by_another_mission_is_reused_not_refused`),
    but the race can still land on a genuine metadata contradiction, and that must
    still surface as the documented `SnapshotArtifactClaimedError` (409), never a raw
    500.

    Reproduced deterministically here, without needing live threads or a Postgres
    container: another mission's `Artifact` row for this digest is written directly,
    with `size_bytes` that could not legitimately describe the same content —
    simulating a concurrent winner whose ingest disagreed with this mission's own —
    and `Artifact.objects.filter(...).first()` is patched to return `None` for exactly
    the query `create_mission_snapshot` makes, simulating the read that ran *before*
    the winner's row was visible. This is the same window the review found; the only
    difference is how the interleaving is forced. The unpatched
    `Artifact.objects.create(...)` then hits the real unique constraint on `sha256`
    for real, against the real (SQLite) database — the `IntegrityError` this test
    observes is genuine, not simulated.
    """
    _authorize(client, mission)
    digest = expected_digest(repo_dir, tmp_path)

    other = Mission.objects.create(
        name="pktcfg-racer",
        repository_ref="file:///demo/repositories/pktcfg-racer",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    Artifact.objects.create(
        sha256=digest, kind="snapshot", size_bytes=999_999, mission=other
    )

    from authorization import service as service_module

    real_filter = service_module.Artifact.objects.filter

    def _filter_that_misses_the_concurrent_winner(*args, **kwargs):
        if kwargs.get("pk") == digest:
            return service_module.Artifact.objects.none()
        return real_filter(*args, **kwargs)

    monkeypatch.setattr(
        service_module.Artifact.objects, "filter", _filter_that_misses_the_concurrent_winner
    )

    response = post(
        client,
        f"/api/v1/missions/{mission.id}/snapshot",
        {"source": "git", "archive_sha256": digest},
        OPERATOR,
    )
    monkeypatch.undo()  # assertions below must see the real, unpatched query

    assert response.status_code == 409, (
        f"expected the documented 409, got {response.status_code}: {response.content!r}"
    )
    assert response.json()["error"]["code"] == "CONFLICT"
    assert Snapshot.objects.filter(mission=mission).count() == 0
    # Exactly one Artifact row for this digest, still owned by the original winner —
    # the race did not corrupt or duplicate the claim, only (before the fix) the
    # error surfaced on the loser was wrong.
    assert Artifact.objects.filter(pk=digest).count() == 1
    assert Artifact.objects.get(pk=digest).mission_id == other.id


def test_a_toctou_race_with_matching_metadata_reuses_without_a_500(
    client: Client, mission: Mission, roots, repo_dir: Path, tmp_path: Path, monkeypatch
):
    """The companion case to the mismatched-metadata race above: when the concurrent
    winner's `Artifact` row is a legitimate dedup hit (matching `kind`/`size_bytes`),
    the race must resolve to a clean, successful reuse — not a 500, and not a 409
    either, since D-087/D-088 removed the cross-mission refusal itself."""
    _authorize(client, mission)
    digest = expected_digest(repo_dir, tmp_path)

    other = Mission.objects.create(
        name="pktcfg-racer-legit",
        repository_ref="file:///demo/repositories/pktcfg-racer-legit",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    from authorization import archive as archive_module

    tar_path = tmp_path / "race-expected.tar"
    archive_module.build_tar_from_directory(repo_dir, tar_path)
    real_bytes_total = archive_module.enumerate_members(tar_path).bytes_total
    Artifact.objects.create(
        sha256=digest, kind="snapshot", size_bytes=real_bytes_total, mission=other
    )

    from authorization import service as service_module

    real_filter = service_module.Artifact.objects.filter

    def _filter_that_misses_the_concurrent_winner(*args, **kwargs):
        if kwargs.get("pk") == digest:
            return service_module.Artifact.objects.none()
        return real_filter(*args, **kwargs)

    monkeypatch.setattr(
        service_module.Artifact.objects, "filter", _filter_that_misses_the_concurrent_winner
    )

    response = post(
        client,
        f"/api/v1/missions/{mission.id}/snapshot",
        {"source": "git", "archive_sha256": digest},
        OPERATOR,
    )
    monkeypatch.undo()

    assert response.status_code == 201, (
        f"expected a clean reuse, got {response.status_code}: {response.content!r}"
    )
    assert Snapshot.objects.get(mission=mission).archive_sha256 == digest
    assert Artifact.objects.filter(pk=digest).count() == 1
    assert Artifact.objects.get(pk=digest).mission_id == other.id


def test_repository_ref_with_an_unsupported_scheme_is_refused(client: Client, roots):
    """SEC-28 (round-4 security review): this refusal fires only *after* authorize
    has already succeeded, so its code must not claim the authorization is what
    failed — UNSUPPORTED_REPOSITORY, matching UnreadableArchiveError's sibling case
    in the same module, not INVALID_AUTHORIZATION."""
    mission = Mission.objects.create(
        name="remote",
        repository_ref="https://example.com/some/repo.git",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    authorize_response = post(
        client,
        f"/api/v1/missions/{mission.id}/authorize",
        authorize_payload(repository_ref="https://example.com/some/repo.git"),
        OPERATOR,
    )
    assert authorize_response.status_code == 201  # the authorization itself is valid
    response = post(
        client,
        f"/api/v1/missions/{mission.id}/snapshot",
        {"source": "git", "archive_sha256": "0" * 64},
        OPERATOR,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "UNSUPPORTED_REPOSITORY"


def test_different_repository_refs_with_the_same_basename_are_refused(
    client: Client, mission: Mission, repo_dir: Path
):
    """SEC-29: distinct repository identities must never collapse to one source."""
    other = Mission.objects.create(
        name="other-pktcfg",
        repository_ref="file:///another-owner/repositories/pktcfg",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    for candidate in (mission, other):
        authorization = post(
            client,
            f"/api/v1/missions/{candidate.id}/authorize",
            authorize_payload(repository_ref=candidate.repository_ref),
            OPERATOR,
        )
        assert authorization.status_code == 201
        response = post(
            client,
            f"/api/v1/missions/{candidate.id}/snapshot",
            {"source": "git", "archive_sha256": "0" * 64},
            OPERATOR,
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "UNSUPPORTED_REPOSITORY"
        assert Snapshot.objects.filter(mission=candidate).count() == 0


# === Validation ===================================================================


def test_unknown_fields_on_authorize_are_rejected(client: Client, mission: Mission):
    response = post(
        client,
        f"/api/v1/missions/{mission.id}/authorize",
        authorize_payload(surprise=True),
        OPERATOR,
    )
    assert response.status_code == 422


def test_a_malformed_archive_sha256_is_rejected(client: Client, mission: Mission, roots):
    response = post(
        client,
        f"/api/v1/missions/{mission.id}/snapshot",
        {"source": "git", "archive_sha256": "not-a-hex-digest"},
        OPERATOR,
    )
    assert response.status_code == 422
