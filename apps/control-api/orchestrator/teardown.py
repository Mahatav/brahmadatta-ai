"""Safe teardown for compute started by a mission (#72).

The sandbox and model layers own the mechanics of stopping their processes. This module
owns the mission-level guarantee: when the orchestrator exits a run through success,
failure, cancel, or crash recovery, every reaper is invoked and every outcome is written
to the mission event stream. A teardown failure is an event and an exception, not a log
line that can disappear during the demo.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from contracts.enums import EventStatus, EventType, MissionState, Severity
from missions.models import Mission
from orchestrator import events


@dataclass(frozen=True)
class TeardownOutcome:
    resource_kind: str
    resource_id: str
    released: bool
    detail: str = ""


class MissionComputeReaper(Protocol):
    """A component capable of releasing compute associated with one mission."""

    resource_kind: str

    def teardown_mission(self, mission_id: UUID) -> Sequence[TeardownOutcome]:
        """Release resources for `mission_id`, returning one outcome per resource."""


class TeardownFailedError(RuntimeError):
    """Raised after failure outcomes have already been persisted as mission events."""

    def __init__(self, outcomes: Sequence[TeardownOutcome]) -> None:
        self.outcomes = tuple(outcomes)
        failed = [outcome for outcome in outcomes if not outcome.released]
        resources = ", ".join(
            f"{outcome.resource_kind}:{outcome.resource_id}" for outcome in failed
        )
        super().__init__(f"teardown failed for {resources}")


class DockerSandboxReaper:
    """Remove labelled sandbox containers left by this mission.

    If the runtime binary is absent, this host cannot have started this Docker-family
    sandbox path through this process, so the reaper reports no resources. If the binary
    exists but the daemon refuses the operation, that is a real inability to prove
    zero-stray state and is reported by the coordinator as a failed teardown event.
    """

    resource_kind = "sandbox"

    def __init__(self, *, runtime: str = "docker") -> None:
        self.runtime = runtime

    def teardown_mission(self, mission_id: UUID) -> Sequence[TeardownOutcome]:
        if shutil.which(self.runtime) is None:
            return ()
        try:
            from packages.sandbox.container import reap_orphans
        except ModuleNotFoundError:
            return ()
        removed = reap_orphans(runtime=self.runtime, mission_ref=str(mission_id))
        return tuple(
            TeardownOutcome(
                resource_kind=self.resource_kind,
                resource_id=container_id,
                released=True,
                detail="container removed by mission-scoped orphan reaper",
            )
            for container_id in removed
        )


class SnapshotWorkspaceReaper:
    """Remove this mission's extracted-snapshot workspace directory, whole (#180,
    SEC-49).

    The primary cleanup path lives elsewhere: `run_worker._run_executor` removes
    each `<SNAPSHOT_WORKSPACE_ROOT>/<mission_id>/<uuid4>` directory itself, in a
    `finally`, the moment the executor that requested it (`orchestrator.snapshot.
    materialize_snapshot`) returns. This reaper is the backstop for what that
    `finally` cannot reach — a worker process killed outright (OOM, SIGKILL, host
    crash) between `materialize_snapshot` returning and that `finally` running,
    which leaves an orphaned `<uuid4>` directory with no code left running that
    still intends to clean it up.

    Reused here rather than duplicated: this class follows the same
    `MissionComputeReaper` shape as `DockerSandboxReaper`/`ModelHostReaper` above,
    so it participates in the same two call sites those do —
    `teardown_started_compute` (a mission-terminal or `CANCELLING` transition, or a
    `TEARDOWN` job) and `recover_orphaned_compute` (startup crash recovery). Both are
    already the established convention this project uses for "nothing legitimate can
    still need this mission's resources" — `DockerSandboxReaper` already tears down
    *every* sandbox container tagged for a mission on that same assumption, not just
    ones it can prove are orphaned. A workspace directory is no more likely to be in
    active use at either of those two points than a sandbox container already is.

    Removes the **whole** per-mission directory (`<uuid4>` extraction directories
    the primary path missed, *and* `ExecutorContext.workspace_root`'s own scratch
    content — e.g. `workers/fuzzing/dispatch.py`'s durable crash-artifact copies,
    D-106) rather than hunting for individual stray `<uuid4>` directories: unlike
    `run_worker`'s per-job cleanup, this only ever runs once the mission has reached
    a point where nothing further will read *any* of it, so there is no narrower
    "safe to remove" boundary to respect here the way there is mid-mission.
    """

    resource_kind = "snapshot-workspace"

    def teardown_mission(self, mission_id: UUID) -> Sequence[TeardownOutcome]:
        from orchestrator import snapshot as snapshot_module

        mission_root = snapshot_module.default_workspace_root() / str(mission_id)
        if not mission_root.exists():
            return ()
        try:
            shutil.rmtree(mission_root)
        except OSError as exc:
            return (
                TeardownOutcome(
                    resource_kind=self.resource_kind,
                    resource_id=str(mission_root),
                    released=False,
                    detail=f"{type(exc).__name__}: {exc}",
                ),
            )
        return (
            TeardownOutcome(
                resource_kind=self.resource_kind,
                resource_id=str(mission_root),
                released=True,
                detail="extracted snapshot workspace directory removed",
            ),
        )


class ModelHostReaper:
    """Stop a mission-scoped model-host lease if PATCH started one."""

    resource_kind = "model-host"

    def teardown_mission(self, mission_id: UUID) -> Sequence[TeardownOutcome]:
        from orchestrator import model_host

        cfg = model_host.config_from_settings()
        released, detail = model_host.stop_model_host_lease(mission_id, cfg=cfg)
        if detail == "no model-host lease recorded for this mission":
            return ()
        return (
            TeardownOutcome(
                resource_kind=self.resource_kind,
                resource_id=cfg.resource_id,
                released=released,
                detail=detail,
            ),
        )


def default_reapers() -> tuple[MissionComputeReaper, ...]:
    runtime = getattr(settings, "SANDBOX_POLICY", {}).get("runtime", "docker")
    return (
        DockerSandboxReaper(runtime=runtime),
        ModelHostReaper(),
        SnapshotWorkspaceReaper(),
    )


def teardown_started_compute(
    mission_id: UUID,
    *,
    trace_id: str,
    reason: str,
    reapers: Iterable[MissionComputeReaper] | None = None,
    now=None,
) -> tuple[TeardownOutcome, ...]:
    """Release all compute known for a mission and emit event-stream state.

    Returns successful outcomes and raises `TeardownFailedError` if any reaper fails.
    The exception is raised only *after* a failed `TEARDOWN_CONFIRMED` event is persisted,
    so callers cannot accidentally swallow the operator-visible state.
    """

    now = now or timezone.now()
    selected = tuple(reapers) if reapers is not None else default_reapers()
    outcomes: list[TeardownOutcome] = []

    for reaper in selected:
        try:
            outcomes.extend(reaper.teardown_mission(mission_id))
        except Exception as exc:  # noqa: BLE001 - failure is converted into evidence
            outcomes.append(
                TeardownOutcome(
                    resource_kind=getattr(
                        reaper, "resource_kind", type(reaper).__name__
                    ),
                    resource_id="mission-scoped-reaper",
                    released=False,
                    detail=f"{type(exc).__name__}: {exc}",
                )
            )

    if not outcomes:
        outcomes.append(
            TeardownOutcome(
                resource_kind="orchestrator",
                resource_id="no-started-compute",
                released=True,
                detail="no mission-scoped compute was running",
            )
        )

    for outcome in outcomes:
        _emit_outcome(mission_id, outcome, trace_id=trace_id, reason=reason, now=now)

    if any(not outcome.released for outcome in outcomes):
        raise TeardownFailedError(outcomes)
    return tuple(outcomes)


def recover_orphaned_compute(
    *,
    trace_id: str,
    reapers: Iterable[MissionComputeReaper] | None = None,
    now=None,
) -> tuple[TeardownOutcome, ...]:
    """Crash-recovery entry point for startup code.

    It scans non-terminal missions and runs the same mission-scoped teardown path the
    normal transition hook uses. This function is explicit rather than hidden in
    `AppConfig.ready()` so tests and the eventual process supervisor can call it at a
    safe point, after the database and container runtime are reachable.
    """

    outcomes: list[TeardownOutcome] = []
    active = Mission.objects.exclude(
        state__in=[
            MissionState.VERIFIED.value,
            MissionState.REJECTED.value,
            MissionState.HUMAN_REVIEW.value,
            MissionState.FAILED.value,
            MissionState.CANCELLED.value,
        ]
    ).values_list("id", flat=True)
    for mission_id in active:
        outcomes.extend(
            teardown_started_compute(
                mission_id,
                trace_id=trace_id,
                reason="orchestrator startup crash recovery",
                reapers=reapers,
                now=now,
            )
        )
    return tuple(outcomes)


def _emit_outcome(
    mission_id: UUID,
    outcome: TeardownOutcome,
    *,
    trace_id: str,
    reason: str,
    now,
) -> None:
    status = EventStatus.SUCCEEDED if outcome.released else EventStatus.FAILED
    severity = Severity.INFO if outcome.released else Severity.HIGH
    message = (
        f"Teardown confirmed for {outcome.resource_kind}:{outcome.resource_id}"
        if outcome.released
        else f"Teardown failed for {outcome.resource_kind}:{outcome.resource_id}"
    )

    with transaction.atomic():
        mission = Mission.objects.select_for_update().get(pk=mission_id)
        events.emit(
            mission,
            EventType.TEARDOWN_CONFIRMED,
            message,
            {
                "kind": "teardown",
                "resource_kind": outcome.resource_kind,
                "resource_id": outcome.resource_id,
                "released": outcome.released,
                "detail": outcome.detail or reason,
            },
            trace_id=trace_id,
            stage=None,
            state=mission.state_enum,
            status=status,
            severity=severity,
            timestamp=now,
        )
