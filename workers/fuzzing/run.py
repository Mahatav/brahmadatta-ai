"""Mission-facing wrapper for the libFuzzer campaign (#28)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from adapters.cpp.errors import AdapterError, StepFailure
from adapters.cpp.fuzzing import FuzzFailure, FuzzToolchainRecord, run_libfuzzer_campaign
from packages.sandbox.container import ContainerJailPolicy

__all__ = ["FuzzingOutcome", "emit_fuzzing_events", "run_fuzzing_stage"]

_EVENT_STAGE_STARTED = "STAGE_STARTED"
_EVENT_STAGE_COMPLETED = "STAGE_COMPLETED"
_EVENT_MISSION_FAILED = "MISSION_FAILED"
_MISSION_STATE_STRESS_TEST = "STRESS_TEST"
_MISSION_STAGE_STRESS_TEST = "STRESS_TEST"


@dataclass(frozen=True, slots=True)
class FuzzingOutcome:
    """Field names mirror `contracts.schemas.evidence.FuzzingReport`."""

    mission_id: str
    mode: str
    harness: str
    engine: str
    runtime_seconds: float
    executions: int
    crashes_found: int
    unique_crashes: int
    corpus_size: int
    sanitizers: tuple[str, ...]
    recorded_at: datetime
    finding_ids: tuple[str, ...] = ()
    replay_source: str | None = None
    coverage: int = 0
    artifact_refs: tuple[str, ...] = ()
    toolchain: FuzzToolchainRecord | None = None
    failure: FuzzFailure | None = None
    run_output_excerpt: str = ""
    raw_events: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @property
    def ran(self) -> bool:
        return self.mode == "LIVE_CAMPAIGN" and self.failure is None

    def as_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "mode": self.mode,
            "harness": self.harness,
            "engine": self.engine,
            "runtime_seconds": self.runtime_seconds,
            "executions": self.executions,
            "crashes_found": self.crashes_found,
            "unique_crashes": self.unique_crashes,
            "corpus_size": self.corpus_size,
            "sanitizers": list(self.sanitizers),
            "finding_ids": list(self.finding_ids),
            "replay_source": self.replay_source,
            "recorded_at": self.recorded_at.isoformat(),
            "coverage": self.coverage,
            "artifact_refs": list(self.artifact_refs),
            "toolchain": self.toolchain.as_dict() if self.toolchain else None,
            "failure": self.failure.as_dict() if self.failure else None,
            "run_output_excerpt": self.run_output_excerpt,
        }


def run_fuzzing_stage(
    mission_id: str | uuid.UUID,
    source_dir: Path | str,
    *,
    policy: ContainerJailPolicy,
    budget_seconds: int = 1800,
) -> FuzzingOutcome:
    """Run the D4 live libFuzzer campaign and return an evidence-shaped outcome."""
    mission_id_str = str(mission_id)
    recorded_at = datetime.now(UTC)
    try:
        result = run_libfuzzer_campaign(
            source_dir,
            policy,
            budget_seconds=budget_seconds,
            mission_ref=mission_id_str,
        )
    except StepFailure as exc:
        return _not_run_from_failure(
            mission_id_str,
            recorded_at,
            FuzzFailure(
                step=exc.step.value,
                command=exc.command,
                exit_code=exc.exit_code,
                first_error=exc.first_error,
                timed_out=exc.timed_out,
                detail=exc.detail,
            ),
        )
    except (AdapterError, ValueError) as exc:
        message = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
        return _not_run_from_failure(
            mission_id_str,
            recorded_at,
            FuzzFailure(
                step="PROBE_TOOLCHAIN",
                command=(),
                exit_code=-1,
                first_error=message,
            ),
        )

    metrics = result.metrics
    if result.failure is not None:
        return _not_run_from_failure(mission_id_str, recorded_at, result.failure)
    return FuzzingOutcome(
        mission_id=mission_id_str,
        mode="LIVE_CAMPAIGN",
        harness="pktcfg_fuzz_one_input",
        engine=result.engine,
        runtime_seconds=result.runtime_seconds,
        executions=metrics.executions,
        crashes_found=metrics.crashes_found,
        unique_crashes=metrics.unique_crashes,
        corpus_size=metrics.corpus_size,
        sanitizers=metrics.sanitizers,
        recorded_at=recorded_at,
        coverage=metrics.coverage,
        artifact_refs=metrics.artifact_paths,
        toolchain=result.toolchain,
        run_output_excerpt=_excerpt(result.run.stdout + "\n" + result.run.stderr)
        if result.run is not None
        else "",
        raw_events=result.events,
    )


def emit_fuzzing_events(
    outcome: FuzzingOutcome, *, sequence_start: int = 1
) -> list[dict[str, Any]]:
    """Return event-shaped dictionaries for the mission event stream."""
    base_time = outcome.recorded_at.isoformat()
    envelope = {
        "mission_id": outcome.mission_id,
        "stage": _MISSION_STAGE_STRESS_TEST,
        "state": _MISSION_STATE_STRESS_TEST,
    }
    started = {
        "id": str(uuid.uuid4()),
        "sequence": sequence_start,
        "timestamp": base_time,
        "type": _EVENT_STAGE_STARTED,
        "status": "RUNNING",
        "severity": "INFO",
        "message": "Building and running the libFuzzer harness.",
        "payload": {
            "kind": "stage_progress",
            "stage": _MISSION_STAGE_STRESS_TEST,
            "percent_complete": 0.0,
            "detail": "cmake -DPKTCFG_FUZZ=ON; libFuzzer headless campaign",
        },
        "evidence_refs": [],
        "metrics": {},
        **envelope,
    }
    completed = {
        "id": str(uuid.uuid4()),
        "sequence": sequence_start + 1,
        "timestamp": base_time,
        "type": _EVENT_STAGE_COMPLETED if outcome.ran else _EVENT_MISSION_FAILED,
        "status": "SUCCEEDED" if outcome.ran else "FAILED",
        "severity": "HIGH" if outcome.crashes_found else "INFO" if outcome.ran else "ERROR",
        "message": _summary_message(outcome),
        "payload": {"kind": "fuzzing", "report": outcome.as_dict()},
        "evidence_refs": list(outcome.artifact_refs),
        "metrics": {
            "executions": float(outcome.executions),
            "coverage": float(outcome.coverage),
            "crashes_found": float(outcome.crashes_found),
            "unique_crashes": float(outcome.unique_crashes),
            "runtime_seconds": outcome.runtime_seconds,
        },
        **envelope,
    }
    return [started, completed]


def _not_run_from_failure(
    mission_id: str,
    recorded_at: datetime,
    failure: FuzzFailure,
) -> FuzzingOutcome:
    return FuzzingOutcome(
        mission_id=mission_id,
        mode="NOT_RUN",
        harness="pktcfg_fuzz_one_input",
        engine="libFuzzer",
        runtime_seconds=0.0,
        executions=0,
        crashes_found=0,
        unique_crashes=0,
        corpus_size=0,
        sanitizers=(),
        recorded_at=recorded_at,
        failure=failure,
        run_output_excerpt=failure.detail,
        raw_events=(),
    )


def _summary_message(outcome: FuzzingOutcome) -> str:
    if outcome.failure is not None:
        return (
            f"Fuzzing did not run: {outcome.failure.step} failed "
            f"({outcome.failure.first_error})"
        )
    return (
        f"Fuzzing complete: {outcome.executions} executions, "
        f"{outcome.unique_crashes} unique crashes in {outcome.runtime_seconds:.1f}s"
    )


def _excerpt(output: str, *, limit: int = 12000) -> str:
    return output[-limit:]
