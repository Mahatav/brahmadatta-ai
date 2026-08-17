"""HTTP-level tests for `preflight`/`start`/`pause`/`cancel` (#154).

`create_mission`/`list_missions`/`get_mission` are a different engineer's slice of the
same issue and are still `NotImplementedYetError` stubs as this file is written — a
mission here is seeded directly through the ORM (as `test_authorize_snapshot.py`
already does for the same reason) and driven to `SNAPSHOTTED` through the two
endpoints that are already real (`/authorize`, `/snapshot`), then, where a test needs a
state past `VALIDATING` that no HTTP endpoint in this product drives yet, through
`orchestrator.transitions.transition` directly — the same real writer the HTTP
endpoints themselves call, not a shortcut around it.

The full create -> authorize -> snapshot -> preflight -> start walk the CTO brief asks
for (D-060 §4) is intentionally not written here: it would fail on the first step until
the sibling engineer's `create_mission` lands, and a partial version against a stub
proves nothing. Follow-up once that PR merges.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest import mock
from uuid import uuid4

import pytest
from django.conf import settings
from django.db import connection, connections
from django.test import Client, override_settings

from authorization.archive import build_tar_from_directory
from contracts.enums import LanguageAdapter, MissionState
from missions.models import Mission, MissionEvent
from orchestrator import transitions

pytestmark = pytest.mark.django_db(transaction=True)

OPERATOR = settings.CONTROL_API_TOKENS["operator"]
REVIEWER = settings.CONTROL_API_TOKENS["reviewer"]


def bearer(token: str) -> dict[str, str]:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def post(client: Client, path: str, payload: dict, token: str):
    return client.post(
        path, data=json.dumps(payload), content_type="application/json", **bearer(token)
    )


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
        yield {"source_root": source_root}


@pytest.fixture
def repo_dir(roots, mission: Mission) -> Path:
    target = roots["source_root"] / "pktcfg"
    (target / "src").mkdir(parents=True)
    (target / "src" / "main.c").write_text("int main(void) { return 0; }\n")
    return target


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


def _authorize(client: Client, mission: Mission) -> None:
    response = post(
        client, f"/api/v1/missions/{mission.id}/authorize", authorize_payload(), OPERATOR
    )
    assert response.status_code == 201


def _snapshot(client: Client, mission: Mission, repo_dir: Path) -> None:
    import hashlib

    out = repo_dir.parent / "expected.tar"
    build_tar_from_directory(repo_dir, out)
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    response = post(
        client,
        f"/api/v1/missions/{mission.id}/snapshot",
        {"source": "git", "archive_sha256": digest},
        OPERATOR,
    )
    assert response.status_code == 201


def _snapshotted_mission(client: Client, mission: Mission, repo_dir: Path) -> Mission:
    """Drives `mission` to SNAPSHOTTED through the two endpoints already wired."""
    _authorize(client, mission)
    _snapshot(client, mission, repo_dir)
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.SNAPSHOTTED
    return mission


def _walk_to_baseline(mission: Mission) -> None:
    """Past what any of these four endpoints can drive to today — the same real
    writer (`orchestrator.transitions.transition`) the endpoints themselves call,
    not a shortcut that bypasses it.

    Deliberately does not pass a fixed `now`: the authorization backing this mission
    was granted moments ago at real wall-clock time by `_authorize` (an HTTP call, not
    a fixture), so this has to check against real "now" too, not a constant that could
    be on either side of that grant's expiry depending on when the suite happens to run.
    """
    for state in (MissionState.VALIDATING, MissionState.BASELINE):
        transitions.transition(
            mission.id, state, trace_id="test-trace-0000000000000000"
        )
    mission.refresh_from_db()


# === preflight (non-mutating, D-060 §1) ==========================================


def test_preflight_reports_ready_once_authorized_and_snapshotted(
    client: Client, mission: Mission, roots, repo_dir: Path
):
    _snapshotted_mission(client, mission, repo_dir)

    response = client.post(
        f"/api/v1/missions/{mission.id}/preflight",
        content_type="application/json",
        **bearer(OPERATOR),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mission_id"] == str(mission.id)
    assert body["passed"] is True
    assert body["blocking_codes"] == []
    names = {check["name"] for check in body["checks"]}
    assert {
        "legal_transition",
        "resume_origin",
        "verdict_evidenced",
        "authorization_and_stage",
    } <= names
    assert all(check["passed"] for check in body["checks"])


def test_preflight_reports_not_ready_without_raising_when_unauthorized(
    client: Client, mission: Mission
):
    """CREATED, never authorized: preflight still answers 200 with a report, not a
    4xx — a mission that is not ready is the normal answer, not a failed request."""
    response = client.post(
        f"/api/v1/missions/{mission.id}/preflight",
        content_type="application/json",
        **bearer(OPERATOR),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert body["blocking_codes"]
    assert "INVALID_STATE_TRANSITION" in body["blocking_codes"]
    assert "INVALID_AUTHORIZATION" in body["blocking_codes"]


def test_preflight_never_mutates_the_mission(
    client: Client, mission: Mission, roots, repo_dir: Path
):
    _snapshotted_mission(client, mission, repo_dir)
    events_before = MissionEvent.objects.filter(mission=mission).count()

    response = client.post(
        f"/api/v1/missions/{mission.id}/preflight",
        content_type="application/json",
        **bearer(OPERATOR),
    )
    assert response.status_code == 200

    mission.refresh_from_db()
    assert mission.state_enum is MissionState.SNAPSHOTTED
    assert MissionEvent.objects.filter(mission=mission).count() == events_before


def test_preflight_against_a_missing_mission_is_404(client: Client):
    response = client.post(
        f"/api/v1/missions/{uuid4()}/preflight",
        content_type="application/json",
        **bearer(OPERATOR),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_a_reviewer_cannot_preflight(client: Client, mission: Mission):
    response = client.post(
        f"/api/v1/missions/{mission.id}/preflight",
        content_type="application/json",
        **bearer(REVIEWER),
    )
    assert response.status_code == 403


# === start ========================================================================


def test_start_moves_snapshotted_to_validating(
    client: Client, mission: Mission, roots, repo_dir: Path
):
    _snapshotted_mission(client, mission, repo_dir)

    response = post(
        client,
        f"/api/v1/missions/{mission.id}/start",
        {"confirm_authorized": True},
        OPERATOR,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["mission_id"] == str(mission.id)
    assert body["accepted"] is True
    assert body["trace_id"]

    mission.refresh_from_db()
    assert mission.state_enum is MissionState.VALIDATING

    # EventType.PREFLIGHT_COMPLETED fires on entry to VALIDATING (see
    # missions.service.start_mission's docstring for why that name and this action
    # are the same transition, not two).
    last_event = MissionEvent.objects.filter(mission=mission).order_by("-sequence").first()
    assert last_event.type == "PREFLIGHT_COMPLETED"


def test_start_against_a_missing_mission_is_404(client: Client):
    response = post(
        client,
        f"/api/v1/missions/{uuid4()}/start",
        {"confirm_authorized": True},
        OPERATOR,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_starting_a_mission_twice_is_a_clean_409_not_a_double_transition(
    client: Client, mission: Mission, roots, repo_dir: Path
):
    _snapshotted_mission(client, mission, repo_dir)

    first = post(
        client,
        f"/api/v1/missions/{mission.id}/start",
        {"confirm_authorized": True},
        OPERATOR,
    )
    assert first.status_code == 202

    second = post(
        client,
        f"/api/v1/missions/{mission.id}/start",
        {"confirm_authorized": True},
        OPERATOR,
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "INVALID_STATE_TRANSITION"

    mission.refresh_from_db()
    assert mission.state_enum is MissionState.VALIDATING


def test_starting_before_snapshot_is_refused(client: Client, mission: Mission):
    """CREATED -> VALIDATING is not in the transition table; a clean 409, not a 500."""
    response = post(
        client,
        f"/api/v1/missions/{mission.id}/start",
        {"confirm_authorized": True},
        OPERATOR,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


# === pause / cancel ===============================================================


def test_pause_records_paused_from_and_returns_202(
    client: Client, mission: Mission, roots, repo_dir: Path
):
    _snapshotted_mission(client, mission, repo_dir)
    _walk_to_baseline(mission)

    response = post(
        client, f"/api/v1/missions/{mission.id}/pause", {"reason": "operator break"}, OPERATOR
    )

    assert response.status_code == 202
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.PAUSED
    assert mission.paused_from_enum is MissionState.BASELINE


def test_pause_from_a_non_pausable_state_is_a_clean_409(client: Client, mission: Mission):
    response = post(
        client, f"/api/v1/missions/{mission.id}/pause", {"reason": "too early"}, OPERATOR
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_pause_against_a_missing_mission_is_404(client: Client):
    response = post(
        client, f"/api/v1/missions/{uuid4()}/pause", {"reason": "x"}, OPERATOR
    )
    assert response.status_code == 404


def test_a_reviewer_cannot_pause(client: Client, mission: Mission):
    response = post(
        client, f"/api/v1/missions/{mission.id}/pause", {"reason": "x"}, REVIEWER
    )
    assert response.status_code == 403


def test_cancel_moves_a_fresh_mission_to_cancelling(client: Client, mission: Mission):
    response = post(
        client,
        f"/api/v1/missions/{mission.id}/cancel",
        {"reason": "operator abort", "confirm": True},
        OPERATOR,
    )

    assert response.status_code == 202
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.CANCELLING


def test_cancel_against_a_missing_mission_is_404(client: Client):
    response = post(
        client,
        f"/api/v1/missions/{uuid4()}/cancel",
        {"reason": "x", "confirm": True},
        OPERATOR,
    )
    assert response.status_code == 404


# === the race (#110's shape, applied to pause/cancel) =============================

#: BUG-022 (the CI workflow's own `pytest` job comment): SQLite's `SELECT ... FOR
#: UPDATE` compiles to a no-op, and its single-writer *file* lock is a different
#: mechanism that fails these two tests with an unhandled `OperationalError` rather
#: than exercising row-level contention at all — confirmed by hand while writing this
#: file, not assumed. CI already runs the whole suite against Postgres in one lane for
#: exactly this reason; this skip only affects a developer's local `pytest` with no
#: `DATABASE_URL` override, so the property is "not proven here" instead of a
#: misleading local failure that looks like these two tests are broken.
_requires_real_row_locking = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Real row-level locking is required to prove this race; SQLite is a no-op "
    "for SELECT ... FOR UPDATE. Run with DATABASE_URL pointed at Postgres, as CI does.",
)


def _run_concurrently(mission_id, path: str, payload: dict, *, block_in: str):
    """Fire two real HTTP requests at the same mutating endpoint on separate threads
    and separate DB connections, forcing them to overlap at the row lock.

    `block_in` names the module-level function inside `orchestrator.transitions` to
    pause the *first* caller in, after it has taken `SELECT ... FOR UPDATE` but before
    it commits — so the second caller's own lock attempt is guaranteed to actually
    contend for the row Postgres is holding, rather than merely running twice in
    sequence fast enough to look like a race without ever being one.
    """
    first_holds_lock = threading.Event()
    release_first = threading.Event()
    original = getattr(transitions, block_in)

    def _slow(*args, **kwargs):
        first_holds_lock.set()
        release_first.wait(timeout=5)
        return original(*args, **kwargs)

    responses: dict[str, object] = {}

    def _call(name: str) -> None:
        try:
            client = Client()
            responses[name] = post(client, path, payload, OPERATOR)
        finally:
            connections.close_all()

    with mock.patch.object(transitions, block_in, side_effect=_slow):
        t1 = threading.Thread(target=_call, args=("first",))
        t1.start()
        assert first_holds_lock.wait(timeout=5), "first caller never reached the lock"
        t2 = threading.Thread(target=_call, args=("second",))
        t2.start()
        # Give the second thread a real chance to attempt (and block on) the row lock
        # Postgres is holding for `first` before releasing it.
        time.sleep(0.3)
        release_first.set()
        t1.join(timeout=5)
        t2.join(timeout=5)

    return responses["first"], responses["second"]


@_requires_real_row_locking
def test_two_concurrent_pause_calls_on_the_same_mission_serialize_one_wins_one_409(
    client: Client, mission: Mission, roots, repo_dir: Path
):
    _snapshotted_mission(client, mission, repo_dir)
    _walk_to_baseline(mission)

    path = f"/api/v1/missions/{mission.id}/pause"
    payload = {"reason": "race"}
    first, second = _run_concurrently(mission.id, path, payload, block_in="_apply")

    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [202, 409], (first.status_code, second.status_code, first.json(), second.json())

    loser = first if first.status_code == 409 else second
    assert loser.json()["error"]["code"] == "INVALID_STATE_TRANSITION"

    mission.refresh_from_db()
    assert mission.state_enum is MissionState.PAUSED
    assert mission.paused_from_enum is MissionState.BASELINE
    # Exactly one MISSION_PAUSED event was appended, never two — the loser never wrote.
    assert MissionEvent.objects.filter(mission=mission, type="MISSION_PAUSED").count() == 1


@_requires_real_row_locking
def test_two_concurrent_cancel_calls_on_the_same_mission_serialize_one_wins_one_409(
    client: Client, mission: Mission
):
    path = f"/api/v1/missions/{mission.id}/cancel"
    payload = {"reason": "race", "confirm": True}
    first, second = _run_concurrently(mission.id, path, payload, block_in="_apply")

    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [202, 409], (first.status_code, second.status_code, first.json(), second.json())

    loser = first if first.status_code == 409 else second
    assert loser.json()["error"]["code"] == "INVALID_STATE_TRANSITION"

    mission.refresh_from_db()
    assert mission.state_enum is MissionState.CANCELLING
    assert MissionEvent.objects.filter(mission=mission, type="MISSION_CANCELLED").count() == 1
