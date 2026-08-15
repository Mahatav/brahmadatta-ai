"""Mission-scoped lifecycle for the local CodeLlama/Ollama host (#36)."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from contracts.enums import EventStatus, EventType, MissionStage, Severity
from missions.models import Mission
from orchestrator import events


@dataclass(frozen=True)
class ModelHostLifecycleConfig:
    enabled: bool
    runtime: str
    compose_file: str
    profile: str
    service: str
    resource_id: str
    lease_seconds: int
    command_timeout_seconds: int


def config_from_settings() -> ModelHostLifecycleConfig:
    raw = getattr(settings, "MODEL_HOST_LIFECYCLE", {})
    compose_file = str(raw.get("compose_file", ""))
    if compose_file and not Path(compose_file).is_absolute():
        compose_file = str((Path(settings.BASE_DIR).parent.parent / compose_file).resolve())
    return ModelHostLifecycleConfig(
        enabled=bool(raw.get("enabled", False)),
        runtime=str(raw.get("runtime", "docker")),
        compose_file=compose_file,
        profile=str(raw.get("profile", "model")),
        service=str(raw.get("service", "model-host")),
        resource_id=str(raw.get("resource_id", "model-host")),
        lease_seconds=int(raw.get("lease_seconds", 1800)),
        command_timeout_seconds=int(raw.get("command_timeout_seconds", 60)),
    )


def start_model_host_lease(
    mission_id: UUID,
    *,
    trace_id: str,
    now=None,
    cfg: ModelHostLifecycleConfig | None = None,
) -> None:
    """Start the local model host when a mission enters PATCH.

    Failure is intentionally a degraded event, not an exception. The deterministic
    patch path remains valid and the operator can see exactly why the model path was
    unavailable.
    """

    now = now or timezone.now()
    cfg = cfg or config_from_settings()

    if not cfg.enabled:
        return

    problem = _config_problem(cfg)
    if problem:
        _emit_degraded(mission_id, trace_id=trace_id, detail=problem, now=now)
        return

    command = _compose_command(cfg, "up", "-d", cfg.service)
    try:
        _run(command, timeout=cfg.command_timeout_seconds)
    except (OSError, subprocess.SubprocessError) as exc:
        _emit_degraded(
            mission_id,
            trace_id=trace_id,
            detail=f"{type(exc).__name__}: {exc}",
            now=now,
        )
        return

    _emit_started(mission_id, trace_id=trace_id, cfg=cfg, now=now)


def stop_model_host_lease(
    mission_id: UUID,
    *,
    cfg: ModelHostLifecycleConfig | None = None,
) -> tuple[bool, str]:
    """Stop the model host if this mission recorded a lease start."""

    cfg = cfg or config_from_settings()
    if not cfg.enabled or not _mission_started_lease(mission_id, cfg.resource_id):
        return True, "no model-host lease recorded for this mission"

    problem = _config_problem(cfg)
    if problem:
        return False, problem

    command = _compose_command(cfg, "stop", cfg.service)
    try:
        _run(command, timeout=cfg.command_timeout_seconds)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    return True, "model-host stopped by mission-scoped lease reaper"


def _compose_command(
    cfg: ModelHostLifecycleConfig, *args: str
) -> list[str]:
    return [
        cfg.runtime,
        "compose",
        "-f",
        cfg.compose_file,
        "--profile",
        cfg.profile,
        *args,
    ]


def _config_problem(cfg: ModelHostLifecycleConfig) -> str:
    if shutil.which(cfg.runtime) is None:
        return f"{cfg.runtime!r} runtime not available; deterministic tier remains active"
    if not cfg.compose_file:
        return "MODEL_HOST_COMPOSE_FILE is empty; deterministic tier remains active"
    if not Path(cfg.compose_file).is_file():
        return f"compose file not found: {cfg.compose_file}"
    return ""


def _run(command: Sequence[str], *, timeout: int) -> None:
    subprocess.run(
        list(command),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )


def _mission_started_lease(mission_id: UUID, resource_id: str) -> bool:
    mission = Mission.objects.filter(pk=mission_id).first()
    if mission is None:
        return False
    return mission.events.filter(
        type=EventType.RESOURCE_USAGE_SAMPLED.value,
        message__contains=resource_id,
    ).exists()


def _emit_started(
    mission_id: UUID,
    *,
    trace_id: str,
    cfg: ModelHostLifecycleConfig,
    now,
) -> None:
    with transaction.atomic():
        mission = Mission.objects.select_for_update().get(pk=mission_id)
        events.emit(
            mission,
            EventType.RESOURCE_USAGE_SAMPLED,
            f"Model host lease started: {cfg.resource_id}",
            {
                "kind": "resource_usage",
                "usage": {
                    "cpu_seconds": 0,
                    "peak_memory_mb": 0,
                    "wall_seconds": cfg.lease_seconds,
                    "sandbox_count": 0,
                    "gpu_seconds": 0,
                },
            },
            trace_id=trace_id,
            stage=MissionStage.PATCH,
            state=mission.state_enum,
            status=EventStatus.SUCCEEDED,
            severity=Severity.INFO,
            metrics={
                "model_host_lease_seconds": float(cfg.lease_seconds),
                "model_host_started": 1.0,
            },
            timestamp=now,
        )


def _emit_degraded(
    mission_id: UUID,
    *,
    trace_id: str,
    detail: str,
    now,
) -> None:
    with transaction.atomic():
        mission = Mission.objects.select_for_update().get(pk=mission_id)
        events.emit(
            mission,
            EventType.LOG,
            "Model host unavailable; deterministic tier remains active.",
            {
                "kind": "log",
                "text": f"model-host degraded: {detail}",
            },
            trace_id=trace_id,
            stage=MissionStage.PATCH,
            state=mission.state_enum,
            status=EventStatus.FAILED,
            severity=Severity.MEDIUM,
            metrics={"model_host_degraded": 1.0},
            timestamp=now,
        )
