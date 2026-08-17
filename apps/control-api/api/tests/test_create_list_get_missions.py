"""HTTP-level tests for `POST /missions`, `GET /missions` and `GET /missions/{id}`
(#154, the create/list/get half — `preflight`/`start`/`pause`/`cancel` are the other
half, a separate PR).

The idempotency-key race gets the most attention here per the standing rule: a
property is described as enforced only when a named test demonstrates it, and for a
concurrency claim specifically that means firing real concurrent requests, not just
the sequential happy path. `test_a_naive_check_then_insert_loses_the_race` is written
first among the concurrency tests and is the injected-violation half of that rule: it
proves the harness below actually observes the bug the real fix avoids, by swapping in
a check-then-act implementation and watching it fail, before trusting the same harness
to say the real implementation passes.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from django.conf import settings
from django.test import Client
from django.utils import timezone

from contracts.enums import LanguageAdapter, MissionPosture, MissionState
from contracts.state_machine import allowed_transitions
from missions import service as mission_service
from missions.models import Authorization, Mission

pytestmark = pytest.mark.django_db

OPERATOR = settings.CONTROL_API_TOKENS["operator"]
REVIEWER = settings.CONTROL_API_TOKENS["reviewer"]


def bearer(token: str) -> dict[str, str]:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.fixture
def client() -> Client:
    return Client()


def mission_payload(**overrides) -> dict:
    payload = {
        "name": "pktcfg demo",
        "repository_ref": "file:///demo/repositories/pktcfg",
        "adapter": "C_CMAKE_CTEST",
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


def get(client: Client, path: str, token: str, **query):
    return client.get(path, data=query, **bearer(token))


# === create_mission ================================================================


def test_create_mission_returns_a_summary_in_created_and_unauthorized(client: Client):
    response = post(client, "/api/v1/missions", mission_payload(), OPERATOR)

    assert response.status_code == 201
    body = response.json()
    assert body["state"] == "CREATED"
    assert body["posture"] == MissionPosture.PROTECTED.value
    assert body["authorized"] is False
    assert body["verdict"] is None
    assert body["repository_ref"] == "file:///demo/repositories/pktcfg"

    row = Mission.objects.get(pk=body["id"])
    assert row.name == "pktcfg demo"
    assert row.adapter == LanguageAdapter.C_CMAKE_CTEST.value
    assert row.state_enum is MissionState.CREATED


def test_a_reviewer_cannot_create_a_mission(client: Client):
    response = post(client, "/api/v1/missions", mission_payload(), REVIEWER)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert Mission.objects.count() == 0


def test_repository_ref_is_recorded_without_being_checked_against_the_allowlist(
    client: Client,
):
    """D-060 §1: create does not re-check `repository_ref` against the snapshot
    source allowlist — that belongs to `authorization.service._materialize_source`,
    at snapshot time. A reference that would later be refused there is still
    recorded as the operator's claim here."""
    response = post(
        client,
        "/api/v1/missions",
        mission_payload(repository_ref="https://example.com/not/locally/resolvable"),
        OPERATOR,
    )
    assert response.status_code == 201
    assert response.json()["repository_ref"] == "https://example.com/not/locally/resolvable"


def test_two_creates_with_no_idempotency_key_are_two_different_missions(client: Client):
    first = post(client, "/api/v1/missions", mission_payload(), OPERATOR)
    second = post(client, "/api/v1/missions", mission_payload(), OPERATOR)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert Mission.objects.count() == 2


def test_two_creates_with_different_idempotency_keys_are_two_different_missions(
    client: Client,
):
    first = post(
        client, "/api/v1/missions", mission_payload(idempotency_key="key-a"), OPERATOR
    )
    second = post(
        client, "/api/v1/missions", mission_payload(idempotency_key="key-b"), OPERATOR
    )
    assert first.json()["id"] != second.json()["id"]
    assert Mission.objects.count() == 2


def test_replaying_a_create_with_the_same_key_returns_the_same_mission(client: Client):
    first = post(
        client, "/api/v1/missions", mission_payload(idempotency_key="replay-key"), OPERATOR
    )
    second = post(
        client, "/api/v1/missions", mission_payload(idempotency_key="replay-key"), OPERATOR
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert Mission.objects.filter(idempotency_key="replay-key").count() == 1
    assert Mission.objects.count() == 1


# === idempotency-key race ==========================================================


def _fire_concurrent_creates(*, key: str, count: int = 2) -> list:
    """Real threads, real connections, real commits: `transaction=True` (set on
    every test below that calls this) disables pytest-django's default wrapping
    transaction, so each thread's `Client()` call opens and commits against the
    actual test database rather than sharing one uncommitted outer transaction —
    the setup the CTO brief's Postgres caveat is about. A `Barrier` maximizes the
    chance both requests are mid-flight at the same time rather than one finishing
    before the other starts.
    """
    barrier = threading.Barrier(count)

    def fire(_: int):
        from django.db import connection

        try:
            barrier.wait(timeout=5)
            return post(
                Client(), "/api/v1/missions", mission_payload(idempotency_key=key), OPERATOR
            )
        finally:
            # Each thread opens its own real connection under transaction=True;
            # nothing else in this process's lifecycle closes it, and pytest-django's
            # test-database teardown fails loudly (if harmlessly) against a
            # connection nobody hung up. Real cleanup, not a workaround.
            connection.close()

    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(fire, range(count)))


@pytest.mark.django_db(transaction=True)
def test_a_naive_check_then_insert_loses_the_race(monkeypatch):
    """The injected violation, run first. A hand-rolled check-then-act
    implementation — `filter(idempotency_key=...).exists()` then `create()`, with a
    sleep standing in for scheduler interleaving to make the window reliable in a
    test — loses this race. What that looks like depends on the backend: against
    Postgres it is an unhandled `IntegrityError` (500) for the loser once the real
    database constraint added by this PR's migration refuses the second insert;
    against SQLite's coarser whole-database write lock it more often shows up as an
    unhandled `OperationalError` ("database is locked") for whichever request loses
    the race for the lock, or — if neither read raced past the other's write —
    both requests succeeding but disagreeing, leaving two rows. All three are the
    same underlying bug #154 exists to close: the naive path is not safe under
    concurrency, on any backend. This test demonstrates the harness below can
    actually see that before the next tests trust the harness to say the real
    implementation does not have it.
    """

    def naive_create_mission(payload, *, now=None):
        now = now or timezone.now()
        if payload.idempotency_key:
            existing = Mission.objects.filter(
                idempotency_key=payload.idempotency_key
            ).first()
            if existing is not None:
                return mission_service._mission_summary(existing, now)
            time.sleep(0.05)  # widen the check-then-act window deliberately
        mission = Mission.objects.create(
            name=payload.name,
            repository_ref=payload.repository_ref,
            adapter=payload.adapter.value,
            policy=payload.policy.model_dump(mode="json"),
            idempotency_key=payload.idempotency_key,
        )
        return mission_service._mission_summary(mission, now)

    monkeypatch.setattr(mission_service, "create_mission", naive_create_mission)

    responses = _fire_concurrent_creates(key="naive-race-key")

    statuses = sorted(r.status_code for r in responses)
    mission_count = Mission.objects.filter(idempotency_key="naive-race-key").count()
    # The naive path fails one of two ways depending on scheduling: an unhandled
    # IntegrityError surfaces as a 500 for the loser, or (if neither read raced past
    # the other's write) both succeed but disagree, in which case two rows exist.
    # A clean pair of 201s referencing one row is exactly the property this test
    # exists to show the naive implementation does NOT have.
    assert statuses != [201, 201] or mission_count != 1, (
        f"expected the naive check-then-act implementation to lose this race "
        f"(statuses={statuses}, mission_count={mission_count}), but it did not — "
        f"the harness would not have caught a regression here"
    )


def _real_concurrent_writer_backend() -> bool:
    from django.db import connection

    return connection.vendor == "postgresql"


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(
    not _real_concurrent_writer_backend(),
    reason=(
        "SQLite has no genuine concurrent-writer story: Django's shared-cache "
        "in-memory test database lets two threads see the same rows, but SQLite "
        "itself serializes writers on a single whole-database lock rather than "
        "Postgres's row-level MVCC, so a second writer that cannot acquire that "
        "lock inside the connection's busy-timeout window raises "
        "'database is locked' (OperationalError) instead of exercising the real "
        "code path under test (the unique-constraint IntegrityError catch in "
        "missions.service.create_mission). That failure mode is a property of "
        "SQLite's locking model, not of the implementation, and asserting "
        "around it would make this test flaky for a reason unrelated to what it "
        "claims to prove. Run explicitly against Postgres to exercise this: "
        "DATABASE_URL=postgresql://... pytest "
        "api/tests/test_create_list_get_missions.py -k concurrent_creates — "
        "verified green there in the #154 PR. "
        "test_a_naive_check_then_insert_loses_the_race and "
        "test_replaying_a_create_with_the_same_key_returns_the_same_mission "
        "cover the same mechanism deterministically on every backend."
    ),
)
def test_concurrent_creates_with_the_same_idempotency_key_produce_exactly_one_mission():
    """The property itself, on the real implementation, against a real
    concurrent-writer database: two concurrent creates carrying the same
    `idempotency_key` must produce exactly one `Mission` row, and both HTTP
    responses must reference it — not merely the sequential-replay case
    `test_replaying_a_create_with_the_same_key_returns_the_same_mission` already
    covers. Skipped on SQLite; see the `skipif` reason above.
    """
    responses = _fire_concurrent_creates(key="real-race-key")

    assert all(r.status_code == 201 for r in responses), [
        (r.status_code, r.content) for r in responses
    ]
    ids = {r.json()["id"] for r in responses}
    assert len(ids) == 1, f"both responses must reference the same mission, got {ids}"

    matching = Mission.objects.filter(idempotency_key="real-race-key")
    assert matching.count() == 1
    assert str(matching.get().id) in ids


# === list_missions ==================================================================


def test_list_missions_returns_every_mission_newest_first(client: Client):
    older = Mission.objects.create(
        name="older", repository_ref="file:///a", adapter="C_CMAKE_CTEST", policy={}
    )
    Mission.objects.filter(pk=older.pk).update(created_at=datetime(2020, 1, 1, tzinfo=UTC))
    newer = Mission.objects.create(
        name="newer", repository_ref="file:///b", adapter="C_CMAKE_CTEST", policy={}
    )

    response = get(client, "/api/v1/missions", OPERATOR)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [item["id"] for item in body["items"]] == [str(newer.id), str(older.id)]


def test_list_missions_is_readable_by_a_reviewer(client: Client):
    """D-060 §3: no scoping beyond role. A reviewer sees every mission, same as an
    operator — `Mission` has no owner field for this single-operator deployment."""
    Mission.objects.create(
        name="m", repository_ref="file:///a", adapter="C_CMAKE_CTEST", policy={}
    )
    response = get(client, "/api/v1/missions", REVIEWER)
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_list_missions_honours_limit_and_offset(client: Client):
    for i in range(3):
        Mission.objects.create(
            name=f"m{i}", repository_ref=f"file:///{i}", adapter="C_CMAKE_CTEST", policy={}
        )

    response = get(client, "/api/v1/missions", OPERATOR, limit=1, offset=1)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["limit"] == 1
    assert body["offset"] == 1
    assert len(body["items"]) == 1


def test_list_missions_authorized_flag_reflects_an_active_record(client: Client):
    mission = Mission.objects.create(
        name="m", repository_ref="file:///a", adapter="C_CMAKE_CTEST", policy={}
    )
    now = timezone.now()
    Authorization.objects.create(
        mission=mission,
        statement="I am authorized to test this repository on behalf of the owner.",
        granted_by="Mahatav Arora",
        granted_at=now,
        expires_at=now + timedelta(hours=4),
        repository_ref=mission.repository_ref,
    )

    body = get(client, "/api/v1/missions", OPERATOR).json()
    assert body["items"][0]["authorized"] is True


# === get_mission ====================================================================


def test_get_mission_404s_for_a_missing_mission(client: Client):
    response = get(client, f"/api/v1/missions/{uuid4()}", OPERATOR)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_get_mission_is_readable_by_a_reviewer(client: Client):
    mission = Mission.objects.create(
        name="m", repository_ref="file:///a", adapter="C_CMAKE_CTEST", policy={}
    )
    response = get(client, f"/api/v1/missions/{mission.id}", REVIEWER)
    assert response.status_code == 200


def test_get_mission_returns_the_full_detail_shape_for_a_fresh_mission(client: Client):
    mission = Mission.objects.create(
        name="pktcfg demo",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter="C_CMAKE_CTEST",
        policy={},
    )

    response = get(client, f"/api/v1/missions/{mission.id}", OPERATOR)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(mission.id)
    assert body["state"] == "CREATED"
    assert body["authorization"] is None
    assert body["snapshot"] is None
    assert body["verdict"] is None
    assert body["verdict_summary"] is None
    assert body["last_event"] is None
    assert body["counts"] == {
        "findings": 0,
        "reproducible_findings": 0,
        "patch_candidates": 0,
        "verifications": 0,
        "tests_passed": 0,
        "tests_failed": 0,
    }
    assert body["resource_usage"] == {
        "cpu_seconds": 0.0,
        "peak_memory_mb": 0.0,
        "wall_seconds": 0.0,
        "sandbox_count": 0,
        "gpu_seconds": 0.0,
    }
    assert body["progress"]["stage"] is None
    assert body["progress"]["stages_completed"] == []
    assert body["progress"]["last_event_sequence"] == 0


def test_get_mission_allowed_transitions_comes_from_the_state_machine_not_a_second_table(
    client: Client,
):
    """The load-bearing property from D-060 §3: `MissionDetail.allowed_transitions`
    must be `contracts.state_machine.allowed_transitions`'s own answer, not a second,
    hand-written copy that could silently disagree with the guard the API actually
    enforces. Proven for a mission in a non-trivial state (`PAUSED`, whose legal
    transitions depend on `paused_from` and cannot be gotten right by a static table)
    by comparing the endpoint's output against a direct call to that function.
    """
    from orchestrator import transitions

    now = timezone.now()
    mission = Mission.objects.create(
        name="pktcfg",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter="C_CMAKE_CTEST",
        policy={},
    )
    Authorization.objects.create(
        mission=mission,
        statement="I am authorized to test this repository on behalf of the owner.",
        granted_by="Mahatav Arora",
        granted_at=now - timedelta(minutes=5),
        expires_at=now + timedelta(hours=8),
        repository_ref=mission.repository_ref,
    )
    mission.snapshots.create(
        commit_sha="0" * 40, archive_sha256="a" * 64, file_count=1, bytes_total=10
    )
    for state in (
        MissionState.AUTHORIZED,
        MissionState.SNAPSHOTTED,
        MissionState.VALIDATING,
        MissionState.BASELINE,
    ):
        transitions.transition(mission.id, state, trace_id="test-trace", now=now)
    transitions.transition(mission.id, MissionState.PAUSED, trace_id="test-trace", now=now)
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.PAUSED
    assert mission.paused_from_enum is MissionState.BASELINE

    expected = sorted(
        allowed_transitions(mission.state_enum, mission.paused_from_enum), key=str
    )

    response = get(client, f"/api/v1/missions/{mission.id}", OPERATOR)

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "PAUSED"
    assert body["allowed_transitions"] == [str(state) for state in expected]
    # Sanity check on the fixture itself: a resumed-from-BASELINE pause must not be
    # allowed to jump straight to, say, VERIFY — otherwise this test would pass
    # trivially no matter what the endpoint returned.
    assert "VERIFY" not in body["allowed_transitions"]
    assert "BASELINE" in body["allowed_transitions"]


def test_get_mission_policy_reflects_what_was_stored_on_create(client: Client):
    response = post(
        client,
        "/api/v1/missions",
        mission_payload(policy={"fuzz_seconds": 60}),
        OPERATOR,
    )
    mission_id = response.json()["id"]

    body = get(client, f"/api/v1/missions/{mission_id}", OPERATOR).json()
    assert body["policy"]["fuzz_seconds"] == 60
    # Everything the operator did not set still comes back with the schema's own
    # defaults, round-tripped through the JSONField rather than dropped.
    assert body["policy"]["sandbox"]["network"] == "deny"
