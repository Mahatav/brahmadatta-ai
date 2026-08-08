"""The baseline stage (#17): the mission's first real stage.

This is where the D3 gate lives. `docs/09-company/01-vision-and-p0-cut.md` §4 states it as
the literal string: the target reaches `BASELINE_PASSED` in the Command Center, showing a
real `ctest` summary. `apps.control_api.contracts.enums.EventType` pins the same string
with a comment worth repeating here: *"It is an outcome, not a mission state — the mission
state is `BASELINE` while the stage runs, then `TRIAGE`."* This module never invents a
mission-state string; it produces the two outcome events and the report they carry.

`run_baseline_stage` is the one entry point. It:

1. Hashes the source tree (`adapters/cpp/snapshot.py`) before anything runs, so the
   recorded result is provably about one specific, unmodified input — matching #17's
   "immutable snapshot hash recorded alongside."
2. Drives the C/C++ adapter's `BASELINE` variant (`adapters/cpp/pipeline.py`) inside a
   `Jail`.
3. Converts the result into a `BaselineOutcome` whose field names match
   `contracts.schemas.evidence.BaselineReport` exactly, so wiring this into the real
   contract type once #14's Django models exist is `BaselineReport(**outcome.as_dict())`
   with no translation layer.
4. Builds the two events #17 asks for — `BASELINE_RECORDED` then `BASELINE_PASSED` or
   `BASELINE_FAILED` — as plain dicts shaped like `contracts.schemas.envelope.MissionEvent`
   with a `BaselinePayload`. No orchestrator or event bus exists yet (#12), so nothing here
   posts these anywhere; `emit_baseline_events` is what a caller — the future orchestrator,
   or a script proving the D3 gate by hand — calls to get the exact envelope it would send.

**A red baseline is a valid, complete result, not an exception.** `configure`/`build`
failures and CTest itself failing to produce a trustworthy report are caught here and
turned into `passed=False` with the failure detail attached — never re-raised past this
function, and never silently reported as a pass. This is the direct implementation of
#17's second acceptance criterion and the role file's rule 2: *"A baseline that was never
green is a finding, not a blocker to hide."*
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from adapters.cpp.detect import BuildSystem, detect
from adapters.cpp.errors import AdapterError, BuildStep, StepFailure, ToolchainError
from adapters.cpp.jail import ISOLATION_MODE, ISOLATION_UNPROTECTED_AGAINST, Jail, JailLimits
from adapters.cpp.pipeline import BuildResult, run_variant
from adapters.cpp.snapshot import SnapshotInfo, hash_source_tree
from adapters.cpp.variants import Variant

__all__ = ["BaselineFailureDetail", "BaselineOutcome", "emit_baseline_events", "run_baseline_stage"]

#: Mirrors `contracts.enums.EventType`. Duplicated as plain strings — this package does not
#: import Django/pydantic contracts (D-026 boundary; see the compiler-toolchain-engineer
#: role file and the PR body for why). Equality with the real enum values is asserted by
#: `adapters/cpp/tests/test_contract_conformance.py`.
_EVENT_BASELINE_RECORDED = "BASELINE_RECORDED"
_EVENT_BASELINE_PASSED = "BASELINE_PASSED"
_EVENT_BASELINE_FAILED = "BASELINE_FAILED"
_MISSION_STATE_BASELINE = "BASELINE"
_MISSION_STAGE_BASELINE = "BASELINE"


@dataclass(frozen=True, slots=True)
class BaselineFailureDetail:
    """Present when the stage could not complete. Never present alongside a pass."""

    step: str
    target: str
    command: tuple[str, ...]
    exit_code: int
    first_error: str
    log_path: str | None
    timed_out: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "target": self.target,
            "command": list(self.command),
            "exit_code": self.exit_code,
            "first_error": self.first_error,
            "log_path": self.log_path,
            "timed_out": self.timed_out,
        }


@dataclass(frozen=True, slots=True)
class BaselineOutcome:
    """Field names match `contracts.schemas.evidence.BaselineReport` exactly.

    `passed` is a computed property, not a stored field — same rule as the contract
    schema, so the outcome cannot be constructed with a `passed=True` that disagrees with
    its own counts.
    """

    mission_id: str
    configure_ok: bool
    build_ok: bool
    tests_total: int
    tests_passed: int
    tests_failed: int
    duration_seconds: float
    adapter: str
    recorded_at: datetime
    snapshot: SnapshotInfo
    isolation_mode: str = ISOLATION_MODE
    isolation_unprotected_against: tuple[str, ...] = field(default=ISOLATION_UNPROTECTED_AGAINST)
    failure: BaselineFailureDetail | None = None
    log_ref: str | None = None

    @property
    def passed(self) -> bool:
        """The D3 gate signal. Identical formula to `BaselineReport.passed`:
        configure and build succeeded, at least one test ran, and none failed."""
        return self.configure_ok and self.build_ok and self.tests_total > 0 and self.tests_failed == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "configure_ok": self.configure_ok,
            "build_ok": self.build_ok,
            "tests_total": self.tests_total,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "duration_seconds": self.duration_seconds,
            "adapter": self.adapter,
            "recorded_at": self.recorded_at.isoformat(),
            "passed": self.passed,
            "log_ref": self.log_ref,
            "snapshot": self.snapshot.as_dict(),
            "isolation_mode": self.isolation_mode,
            "isolation_unprotected_against": list(self.isolation_unprotected_against),
            "failure": self.failure.as_dict() if self.failure else None,
        }


def _failure_from_step_failure(exc: StepFailure) -> BaselineFailureDetail:
    return BaselineFailureDetail(
        step=exc.step.value,
        target=exc.target,
        command=exc.command,
        exit_code=exc.exit_code,
        first_error=exc.first_error,
        log_path=exc.log_path,
        timed_out=exc.timed_out,
    )


def _failure_from_adapter_error(exc: AdapterError, step: BuildStep, target: str) -> BaselineFailureDetail:
    """AdapterError/ToolchainError carry no command or exit code — nothing ran. Recorded
    with `command=()` and `exit_code=-1` (a sentinel no real process ever returns) so the
    absence of a command is visible in the report rather than papered over with `0`."""
    message = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
    return BaselineFailureDetail(
        step=step.value,
        target=target,
        command=(),
        exit_code=-1,
        first_error=message,
        log_path=None,
        timed_out=False,
    )


def run_baseline_stage(
    mission_id: str | uuid.UUID,
    source_dir: Path | str,
    workspace_root: Path | str,
    *,
    jail_limits: JailLimits | None = None,
) -> BaselineOutcome:
    """Run the baseline stage for one mission. Never raises on a red or broken build —
    every failure mode this module knows about is converted into a `BaselineOutcome` with
    `passed=False` and `failure` populated. Only a programming error (a bug in this
    module) escapes as an unhandled exception.
    """
    started = time.monotonic()
    mission_id_str = str(mission_id)
    recorded_at = datetime.now(UTC)
    source = Path(source_dir).resolve()

    # #17 AC 4: the snapshot hash is recorded regardless of what happens next — computed
    # before configure/build even start, so it reflects the exact input attempted.
    snapshot = hash_source_tree(source)

    workspace = Path(workspace_root).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    jail = Jail(workspace, limits=jail_limits or JailLimits())

    build_result: BuildResult | None = None
    failure: BaselineFailureDetail | None = None
    adapter_name = "UNKNOWN"

    try:
        build_result = run_variant(source, jail, Variant.BASELINE)
        adapter_name = build_result.detected.build_system.value
    except StepFailure as exc:
        failure = _failure_from_step_failure(exc)
        adapter_name = _adapter_name_or_unknown(source)
    except (ToolchainError, AdapterError) as exc:
        step = BuildStep.PROBE_TOOLCHAIN if isinstance(exc, ToolchainError) else BuildStep.DETECT
        failure = _failure_from_adapter_error(exc, step, str(source))
        adapter_name = _adapter_name_or_unknown(source)

    duration = time.monotonic() - started

    if build_result is not None:
        return BaselineOutcome(
            mission_id=mission_id_str,
            configure_ok=build_result.configure_ok,
            build_ok=build_result.build_ok,
            tests_total=build_result.ctest.total,
            tests_passed=build_result.ctest.passed,
            tests_failed=build_result.ctest.failed,
            duration_seconds=duration,
            adapter=adapter_name,
            recorded_at=recorded_at,
            snapshot=snapshot,
            log_ref=build_result.ctest.junit_path,
        )

    # Configure, build, or toolchain probing did not complete. Recorded as a red baseline
    # with zero counts — never as a pass, never hidden. `configure_ok`/`build_ok` reflect
    # exactly how far the pipeline got: DETECT/PROBE_TOOLCHAIN failures mean neither ran;
    # a CONFIGURE StepFailure means configure itself failed; a BUILD StepFailure means
    # configure succeeded and build did not.
    assert failure is not None  # noqa: S101 - one of the two branches above always sets it
    configure_ok = failure.step not in (
        BuildStep.DETECT.value,
        BuildStep.PROBE_TOOLCHAIN.value,
        BuildStep.CONFIGURE.value,
    )
    build_ok = configure_ok and failure.step not in (BuildStep.BUILD.value,)
    return BaselineOutcome(
        mission_id=mission_id_str,
        configure_ok=configure_ok,
        build_ok=build_ok,
        tests_total=0,
        tests_passed=0,
        tests_failed=0,
        duration_seconds=duration,
        adapter=adapter_name,
        recorded_at=recorded_at,
        snapshot=snapshot,
        log_ref=failure.log_path,
        failure=failure,
    )


def _adapter_name_or_unknown(source: Path) -> str:
    """Best-effort adapter name for a report even when detection itself failed."""
    try:
        return detect(source).build_system.value
    except AdapterError:
        return BuildSystem.C_CMAKE_CTEST.value if (source / "CMakeLists.txt").is_file() else "UNKNOWN"


def emit_baseline_events(outcome: BaselineOutcome, *, sequence_start: int = 1) -> list[dict[str, Any]]:
    """The `BASELINE_RECORDED` + `BASELINE_PASSED`/`BASELINE_FAILED` pair, shaped like
    `contracts.schemas.envelope.MissionEvent` carrying a `BaselinePayload`.

    `sequence_start` lets a caller that already knows its next mission-event sequence
    number (D-024 condition C7: allocated inside the same transaction as the mission row
    lock) slot these in without renumbering. Returned, not sent — there is nothing to send
    to yet (#12).
    """
    base_time = outcome.recorded_at
    envelope_common = {
        "mission_id": outcome.mission_id,
        "stage": _MISSION_STAGE_BASELINE,
        "state": _MISSION_STATE_BASELINE,
    }

    recorded_event = {
        "id": str(uuid.uuid4()),
        "sequence": sequence_start,
        "timestamp": base_time.isoformat(),
        "type": _EVENT_BASELINE_RECORDED,
        "status": "COMPLETED",
        "severity": "INFO",
        "message": (
            f"Baseline recorded: {outcome.tests_passed}/{outcome.tests_total} tests passed "
            f"in {outcome.duration_seconds:.1f}s"
        ),
        "payload": {"kind": "baseline", "report": outcome.as_dict()},
        "evidence_refs": [outcome.log_ref] if outcome.log_ref else [],
        "metrics": {
            "tests_total": float(outcome.tests_total),
            "tests_passed": float(outcome.tests_passed),
            "tests_failed": float(outcome.tests_failed),
            "duration_seconds": outcome.duration_seconds,
        },
        **envelope_common,
    }

    outcome_type = _EVENT_BASELINE_PASSED if outcome.passed else _EVENT_BASELINE_FAILED
    outcome_severity = "INFO" if outcome.passed else "ERROR"
    outcome_message = (
        f"BASELINE_PASSED: {outcome.tests_passed}/{outcome.tests_total} ctest cases passed"
        if outcome.passed
        else _failure_message(outcome)
    )
    outcome_event = {
        "id": str(uuid.uuid4()),
        "sequence": sequence_start + 1,
        "timestamp": base_time.isoformat(),
        "type": outcome_type,
        "status": "COMPLETED" if outcome.passed else "FAILED",
        "severity": outcome_severity,
        "message": outcome_message,
        "payload": {"kind": "baseline", "report": outcome.as_dict()},
        "evidence_refs": [outcome.log_ref] if outcome.log_ref else [],
        "metrics": recorded_event["metrics"],
        **envelope_common,
    }

    return [recorded_event, outcome_event]


def _failure_message(outcome: BaselineOutcome) -> str:
    if outcome.failure is not None:
        return (
            f"BASELINE_FAILED: {outcome.failure.step} failed for '{outcome.failure.target}' "
            f"(exit {outcome.failure.exit_code}): {outcome.failure.first_error}"
        )
    return (
        f"BASELINE_FAILED: {outcome.tests_failed}/{outcome.tests_total} ctest cases failed "
        "or did not run"
    )
