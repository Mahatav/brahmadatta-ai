"""#36 — local model host is leased for PATCH and torn down visibly."""

from __future__ import annotations

import pytest
from django.test import override_settings

from contracts.enums import EventStatus, EventType, MissionState, Severity
from missions.models import MissionEvent
from orchestrator import model_host, teardown
from orchestrator.tests.conftest import NOW, TRACE, walk_to

pytestmark = pytest.mark.django_db(transaction=True)


def _settings(compose_file: str) -> dict:
    return {
        "enabled": True,
        "runtime": "docker",
        "compose_file": compose_file,
        "profile": "model",
        "service": "model-host",
        "resource_id": "model-host",
        "lease_seconds": 900,
        "command_timeout_seconds": 3,
    }


def test_relative_compose_file_resolves_from_repo_root():
    with override_settings(
        MODEL_HOST_LIFECYCLE=_settings("infrastructure/compose/docker-compose.yml")
    ):
        cfg = model_host.config_from_settings()

    assert cfg.compose_file.endswith("infrastructure/compose/docker-compose.yml")
    assert not cfg.compose_file.startswith("infrastructure/")


def test_entering_patch_starts_a_model_host_lease(
    monkeypatch, tmp_path, mission
):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    commands: list[list[str]] = []
    monkeypatch.setattr(model_host.shutil, "which", lambda runtime: f"/usr/bin/{runtime}")
    monkeypatch.setattr(
        model_host,
        "_run",
        lambda command, *, timeout: commands.append(list(command)),
    )

    with override_settings(MODEL_HOST_LIFECYCLE=_settings(str(compose))):
        walk_to(mission, MissionState.PATCH)

    assert commands == [
        [
            "docker",
            "compose",
            "-f",
            str(compose),
            "--profile",
            "model",
            "up",
            "-d",
            "model-host",
        ]
    ]
    event = MissionEvent.objects.get(
        mission=mission,
        type=EventType.RESOURCE_USAGE_SAMPLED.value,
        message__contains="model-host",
    )
    assert event.status == EventStatus.SUCCEEDED
    assert event.payload["usage"]["wall_seconds"] == 900
    assert event.metrics["model_host_lease_seconds"] == 900.0


def test_model_host_start_degrades_without_blocking_patch(monkeypatch, mission):
    monkeypatch.setattr(model_host.shutil, "which", lambda runtime: None)

    with override_settings(MODEL_HOST_LIFECYCLE=_settings("compose.yml")):
        walk_to(mission, MissionState.PATCH)

    mission.refresh_from_db()
    assert mission.state_enum is MissionState.PATCH

    event = MissionEvent.objects.get(
        mission=mission,
        type=EventType.LOG.value,
        message="Model host unavailable; deterministic tier remains active.",
    )
    assert event.status == EventStatus.FAILED
    assert event.severity == Severity.MEDIUM
    assert event.metrics["model_host_degraded"] == 1.0


def test_model_host_reaper_stops_recorded_lease(monkeypatch, tmp_path, mission):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    commands: list[list[str]] = []
    monkeypatch.setattr(model_host.shutil, "which", lambda runtime: f"/usr/bin/{runtime}")
    monkeypatch.setattr(
        model_host,
        "_run",
        lambda command, *, timeout: commands.append(list(command)),
    )

    with override_settings(MODEL_HOST_LIFECYCLE=_settings(str(compose))):
        walk_to(mission, MissionState.PATCH)
        outcomes = teardown.teardown_started_compute(
            mission.id,
            trace_id=TRACE,
            reason="verification finished",
            reapers=[teardown.ModelHostReaper()],
            now=NOW,
        )

    assert commands[-1] == [
        "docker",
        "compose",
        "-f",
        str(compose),
        "--profile",
        "model",
        "stop",
        "model-host",
    ]
    assert outcomes == (
        teardown.TeardownOutcome(
            resource_kind="model-host",
            resource_id="model-host",
            released=True,
            detail="model-host stopped by mission-scoped lease reaper",
        ),
    )
    event = MissionEvent.objects.filter(
        mission=mission,
        type=EventType.TEARDOWN_CONFIRMED.value,
        payload__resource_kind="model-host",
    ).get()
    assert event.payload["released"] is True
