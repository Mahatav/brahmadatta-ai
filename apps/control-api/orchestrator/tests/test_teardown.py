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
