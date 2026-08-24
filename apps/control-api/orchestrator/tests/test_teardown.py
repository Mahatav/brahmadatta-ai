"""D4 #72 — teardown is mission-scoped, visible, and fail-loud."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import pytest

from contracts.enums import (
    EventStatus,
    EventType,
    LanguageAdapter,
    MissionState,
    Severity,
)
from missions.lifecycle import lifecycle_write
from missions.models import Mission, MissionEvent
from orchestrator import teardown, transitions
from orchestrator.tests.conftest import NOW, TRACE, walk_to

pytestmark = pytest.mark.django_db(transaction=True)


@dataclass
class FakeReaper:
    outcomes: tuple[teardown.TeardownOutcome, ...] = ()
    fail: Exception | None = None
    resource_kind: str = "sandbox"
    seen: list[UUID] | None = None

    def teardown_mission(self, mission_id: UUID):
        if self.seen is not None:
            self.seen.append(mission_id)
        if self.fail is not None:
            raise self.fail
        return self.outcomes


def _outcome(resource_id: str = "sandbox-1", *, released: bool = True):
    return teardown.TeardownOutcome(
        resource_kind="sandbox",
        resource_id=resource_id,
        released=released,
        detail="mock teardown",
    )


def test_teardown_success_is_written_to_the_event_stream(mission):
    outcomes = teardown.teardown_started_compute(
        mission.id,
        trace_id=TRACE,
        reason="normal completion",
        reapers=[FakeReaper((_outcome(),))],
        now=NOW,
    )

    assert outcomes == (_outcome(),)
    event = MissionEvent.objects.get(mission=mission, type=EventType.TEARDOWN_CONFIRMED)
    assert event.status == EventStatus.SUCCEEDED
    assert event.severity == Severity.INFO
    assert event.payload == {
        "kind": "teardown",
        "resource_kind": "sandbox",
        "resource_id": "sandbox-1",
        "released": True,
        "detail": "mock teardown",
    }


def test_teardown_failure_is_reported_then_raised(mission):
    with pytest.raises(teardown.TeardownFailedError) as excinfo:
        teardown.teardown_started_compute(
            mission.id,
            trace_id=TRACE,
            reason="stage failure",
            reapers=[FakeReaper(fail=RuntimeError("daemon refused rm"))],
            now=NOW,
        )

    assert "sandbox:mission-scoped-reaper" in str(excinfo.value)
    event = MissionEvent.objects.get(mission=mission, type=EventType.TEARDOWN_CONFIRMED)
    assert event.status == EventStatus.FAILED
    assert event.severity == Severity.HIGH
    assert event.payload["released"] is False
    assert "RuntimeError: daemon refused rm" in event.payload["detail"]


def test_transition_to_cancel_runs_teardown_after_the_state_event(monkeypatch, mission):
    seen: list[UUID] = []
    fake = FakeReaper((_outcome("cancelled-sandbox"),), seen=seen)
    monkeypatch.setattr(teardown, "default_reapers", lambda: (fake,))

    walk_to(mission, MissionState.STRESS_TEST)
    result = transitions.transition(
        mission.id,
        MissionState.CANCELLING,
        trace_id=TRACE,
        reason="operator cancel",
        now=NOW,
    )

    assert seen == [mission.id]
    events = list(MissionEvent.objects.filter(mission=mission).order_by("sequence"))
    assert events[result.sequence - 1].sequence == result.sequence
    assert events[result.sequence - 1].type == EventType.MISSION_CANCELLED
    assert events[-1].type == EventType.TEARDOWN_CONFIRMED
    assert events[-1].payload["resource_id"] == "cancelled-sandbox"


def test_transition_to_failed_runs_teardown(monkeypatch, mission):
    seen: list[UUID] = []
    fake = FakeReaper((_outcome("failed-run-sandbox"),), seen=seen)
    monkeypatch.setattr(teardown, "default_reapers", lambda: (fake,))

    walk_to(mission, MissionState.BASELINE)
    transitions.transition(
        mission.id, MissionState.FAILED, trace_id=TRACE, reason="stage failed", now=NOW
    )

    mission.refresh_from_db()
    assert mission.state_enum is MissionState.FAILED
    assert seen == [mission.id]
    assert MissionEvent.objects.filter(
        mission=mission,
        type=EventType.TEARDOWN_CONFIRMED,
        payload__resource_id="failed-run-sandbox",
    ).exists()


def test_terminal_states_are_teardown_boundaries():
    assert transitions._requires_teardown(MissionState.VERIFIED) is True
    assert transitions._requires_teardown(MissionState.REJECTED) is True
    assert transitions._requires_teardown(MissionState.HUMAN_REVIEW) is True
    assert transitions._requires_teardown(MissionState.CANCELLED) is True
    assert transitions._requires_teardown(MissionState.CANCELLING) is True
    assert transitions._requires_teardown(MissionState.BASELINE) is False


# --------------------------------------------------------------------------------
# SnapshotWorkspaceReaper (#180, SEC-49): the backstop for a worker killed outright
# before run_worker._run_executor's own `finally` could remove its own directory.
# --------------------------------------------------------------------------------


def test_snapshot_workspace_reaper_removes_a_stray_extraction_directory(tmp_path, mission, settings):
    """Simulates the exact orphan #180 named: a worker process killed (OOM, SIGKILL,
    host crash) between `materialize_snapshot` returning and `run_worker`'s own
    cleanup running, leaving a `<uuid4>` directory nobody ever removed."""
    workspace_root = tmp_path / "workspaces"
    settings.SNAPSHOT_WORKSPACE_ROOT = str(workspace_root)
    mission_root = workspace_root / str(mission.id)
    stray = mission_root / "deadbeefdeadbeefdeadbeefdeadbeef"
    stray.mkdir(parents=True)
    (stray / "src.c").write_text("int x;\n")

    outcomes = teardown.SnapshotWorkspaceReaper().teardown_mission(mission.id)

    assert len(outcomes) == 1
    assert outcomes[0].resource_kind == "snapshot-workspace"
    assert outcomes[0].released is True
    assert not mission_root.exists()


def test_snapshot_workspace_reaper_is_a_safe_no_op_when_nothing_is_there(tmp_path, mission, settings):
    settings.SNAPSHOT_WORKSPACE_ROOT = str(tmp_path / "workspaces")
    assert teardown.SnapshotWorkspaceReaper().teardown_mission(mission.id) == ()


def test_default_reapers_includes_the_snapshot_workspace_reaper():
    assert any(
        isinstance(reaper, teardown.SnapshotWorkspaceReaper)
        for reaper in teardown.default_reapers()
    )


def test_terminal_transition_sweeps_a_stray_snapshot_workspace(monkeypatch, tmp_path, mission, settings):
    """End to end, through the real teardown path a `-> FAILED` transition already
    triggers (`transitions._requires_teardown`) -- not the isolated reaper unit test
    above."""
    workspace_root = tmp_path / "workspaces"
    settings.SNAPSHOT_WORKSPACE_ROOT = str(workspace_root)
    mission_root = workspace_root / str(mission.id)
    stray = mission_root / "leftover-uuid"
    stray.mkdir(parents=True)
    (stray / "src.c").write_text("int x;\n")

    monkeypatch.setattr(teardown, "default_reapers", lambda: (teardown.SnapshotWorkspaceReaper(),))

    walk_to(mission, MissionState.BASELINE)
    transitions.transition(
        mission.id, MissionState.FAILED, trace_id=TRACE, reason="stage failed", now=NOW
    )

    assert not mission_root.exists()
    assert MissionEvent.objects.filter(
        mission=mission,
        type=EventType.TEARDOWN_CONFIRMED,
        payload__resource_kind="snapshot-workspace",
        payload__released=True,
    ).exists()


def test_crash_recovery_sweeps_a_stray_snapshot_workspace_for_an_active_mission(tmp_path, settings):
    """`recover_orphaned_compute` (startup crash recovery) applies the same reaper
    set to every non-terminal mission -- the same assumption `DockerSandboxReaper`
    already relies on there (nothing legitimate is still using this mission's
    resources once the orchestrator is recovering from a crash)."""
    workspace_root = tmp_path / "workspaces"
    settings.SNAPSHOT_WORKSPACE_ROOT = str(workspace_root)
    active = Mission.objects.create(
        name="active-with-orphan",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    mission_root = workspace_root / str(active.id)
    stray = mission_root / "leftover-uuid"
    stray.mkdir(parents=True)
    (stray / "src.c").write_text("int x;\n")

    outcomes = teardown.recover_orphaned_compute(
        trace_id=TRACE,
        reapers=[teardown.SnapshotWorkspaceReaper()],
        now=NOW,
    )

    assert not mission_root.exists()
    assert len(outcomes) == 1
    assert outcomes[0].resource_kind == "snapshot-workspace"
    assert outcomes[0].released is True


def test_crash_recovery_reaps_only_non_terminal_missions():
    active = Mission.objects.create(
        name="active",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    terminal = Mission.objects.create(
        name="terminal",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    with lifecycle_write():
        Mission.objects.filter(pk=terminal.id).update(
            state=MissionState.CANCELLED.value
        )
    seen: list[UUID] = []

    outcomes = teardown.recover_orphaned_compute(
        trace_id=TRACE,
        reapers=[FakeReaper((_outcome("recovered-sandbox"),), seen=seen)],
        now=NOW,
    )

    assert seen == [active.id]
    assert outcomes == (_outcome("recovered-sandbox"),)
    assert MissionEvent.objects.filter(
        mission=active,
        type=EventType.TEARDOWN_CONFIRMED,
        payload__resource_id="recovered-sandbox",
    ).exists()
    assert not MissionEvent.objects.filter(mission=terminal).exists()


def test_docker_sandbox_reaper_reports_a_failed_removal_as_not_released(monkeypatch):
    """SEC-51 (#182): `DockerSandboxReaper.teardown_mission` used to report
    `released=True` for every container `reap_orphans` merely *found*, regardless of
    whether `docker rm -f` actually succeeded — this reproduces the exact scenario
    from the issue: one container's removal succeeds and another's fails, and the
    reaper must tell them apart rather than reporting both as clean.

    Consequential since PR #179's `teardown_transition_policy` routes
    `CANCELLING` -> `CANCELLED`/`FAILED` off exactly this `released` flag: a wedged
    container that fails to be removed must now correctly fail teardown instead of
    being reported as released.
    """
    import shutil

    from packages.sandbox.container import ContainerRemoval

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/docker")

    def fake_reap_orphans(*, runtime, mission_ref, **_kwargs):
        return [
            ContainerRemoval(container_id="good123", removed=True),
            ContainerRemoval(
                container_id="wedged456",
                removed=False,
                error="Error response from daemon: removal in progress",
            ),
        ]

    monkeypatch.setattr("packages.sandbox.container.reap_orphans", fake_reap_orphans)

    reaper = teardown.DockerSandboxReaper()
    outcomes = reaper.teardown_mission(UUID(int=0))

    by_id = {outcome.resource_id: outcome for outcome in outcomes}
    assert by_id["good123"].released is True
    assert by_id["wedged456"].released is False
    assert "removal in progress" in by_id["wedged456"].detail
