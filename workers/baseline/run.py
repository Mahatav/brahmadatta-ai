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

## Compiler diagnostics (#23, D-144)

`BaselineOutcome.compiler_diagnostics` is `adapters.cpp.compiler_diagnostics.
parse_compiler_diagnostics` run against the SAME `cmake --build` invocation's captured
stdout/stderr this stage already runs for the D3 gate — never a second build just to see
warnings. Populated whenever the build step itself completed (every case except a
DETECT/PROBE_TOOLCHAIN/CONFIGURE failure, where no compiler ever ran), along with the
compiler identity `read_compiler_identity` already recorded for that same build
(`compiler_id`/`compiler_version`, reused from `build_result.toolchain`, not re-probed).
Turning these into `Finding`/`StageToolRun` rows — including the cross-tool dedup #23's
own acceptance criterion asks for — is `workers/baseline/dispatch.py`'s job, the same
Django-aware boundary that already turns `BaselineOutcome` into a `BaselineReport` row;
this module stays framework-free (see the compiler-toolchain-engineer role file and the
D-026 boundary this package's other modules already document).
"""

from __future__ import annotations

import shutil
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from adapters.cpp.compiler_diagnostics import CompilerDiagnostic, parse_compiler_diagnostics
from adapters.cpp.detect import BuildSystem, detect
from adapters.cpp.errors import AdapterError, BuildStep, StepFailure, ToolchainError
from adapters.cpp.pipeline import BuildResult, run_variant
from adapters.cpp.snapshot import SnapshotInfo, hash_source_tree
from adapters.cpp.toolchain import ISOLATION_UNPROTECTED_AGAINST, require_pinned
from adapters.cpp.variants import Variant
from packages.sandbox import (
    ISOLATION_MODE,
    ContainerJailPolicy,
    ContainerJailRunner,
    Jail,
    JailPolicy,
)
from packages.sandbox.container import ISOLATION_MODE as CONTAINER_ISOLATION_MODE

#: What `--network none` / `--cap-drop ALL` / `--read-only` / a pinned image (D-024,
#: `packages/sandbox/container.py`) leave genuinely unresolved, for the same honest
#: "isolation_unprotected_against" reporting `ISOLATION_UNPROTECTED_AGAINST` gives the
#: subprocess path — see that constant's own docstring (`adapters/cpp/toolchain.py`) for
#: the shape this mirrors. Deliberately much shorter: network egress, filesystem reads
#: outside the jail root, and toolchain reproducibility are the three items
#: `ISOLATION_UNPROTECTED_AGAINST` names that a `--network none` container with a single
#: bind mount and a real pinned `image_digest` actually closes (D-024 §6.2 conditions
#: 1/5, and `require_pinned` below). What is left, honestly: this is still a rootful
#: Docker daemon (D-024 accepted this substitution for rootless Podman explicitly, not
#: silently — see `packages/sandbox/container.py`'s own module docstring), and
#: `--cap-drop ALL`/`--security-opt no-new-privileges` narrow but do not add seccomp or a
#: user namespace on top of the fixed non-root uid.
CONTAINER_ISOLATION_UNPROTECTED_AGAINST: tuple[str, ...] = (
    "a container-runtime escape reaching host root (D-024 accepted a rootful daemon, "
    "not rootless, as the substitute for Podman not being installed on the build host)",
    "no seccomp profile or Linux user namespace beyond the fixed non-root uid/gid and "
    "--cap-drop ALL",
)

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
    """Present when the stage could not complete. Never present alongside a pass.

    `detail` (a tail of captured stderr) stands in for the on-disk log artifact this
    field used to reference: `packages.sandbox.Jail` deletes its whole scratch directory,
    including anything a failed configure/build step wrote, the moment its `with` block
    exits (D-053/D-054) — there is no persistent path left to hand back once
    `run_baseline_stage` returns. See `adapters/cpp/pipeline.py`'s module docstring.
    """

    step: str
    target: str
    command: tuple[str, ...]
    exit_code: int
    first_error: str
    detail: str
    timed_out: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "target": self.target,
            "command": list(self.command),
            "exit_code": self.exit_code,
            "first_error": self.first_error,
            "detail": self.detail,
            "timed_out": self.timed_out,
        }


@dataclass(frozen=True, slots=True)
class BaselineOutcome:
    """Field names match `contracts.schemas.evidence.BaselineReport` exactly.

    `passed` is a computed property, not a stored field — same rule as the contract
    schema, so the outcome cannot be constructed with a `passed=True` that disagrees with
    its own counts.

    `compiler_diagnostics`/`compiler_id`/`compiler_version` (#23): structurally parsed
    out of the SAME build invocation this stage already runs for the D3 gate — no
    second build. Populated whenever the build step itself completed (`build_result is
    not None` in `run_baseline_stage`, i.e. every case except DETECT/PROBE_TOOLCHAIN/
    CONFIGURE/BUILD failing outright), which is the compiler-version-and-diagnostics
    identity `read_compiler_identity` (`adapters/cpp/toolchain.py`) already recorded as
    part of `build_result.toolchain` — reused here, not re-probed. `compiler_id`/
    `compiler_version` are `"unknown"` only in the one case where the build step itself
    never ran (a `DETECT`/`PROBE_TOOLCHAIN`/`CONFIGURE` failure) — never fabricated.
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
    compiler_diagnostics: tuple[CompilerDiagnostic, ...] = ()
    compiler_id: str = "unknown"
    compiler_version: str = "unknown"

    @property
    def passed(self) -> bool:
        """The D3 gate signal. Identical formula to `BaselineReport.passed`:
        configure and build succeeded, at least one test ran, and none failed."""
        return (
            self.configure_ok and self.build_ok and self.tests_total > 0 and self.tests_failed == 0
        )

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
            "compiler_diagnostics": [d.as_dict() for d in self.compiler_diagnostics],
            "compiler_id": self.compiler_id,
            "compiler_version": self.compiler_version,
        }


def _failure_from_step_failure(exc: StepFailure) -> BaselineFailureDetail:
    return BaselineFailureDetail(
        step=exc.step.value,
        target=exc.target,
        command=exc.command,
        exit_code=exc.exit_code,
        first_error=exc.first_error,
        detail=exc.detail,
        timed_out=exc.timed_out,
    )


def _failure_from_adapter_error(
    exc: AdapterError, step: BuildStep, target: str
) -> BaselineFailureDetail:
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
        detail="",
        timed_out=False,
    )


#: Directories never worth copying into a `ContainerJailRunner`'s bind mount before a
#: BASELINE build — mirrors `orchestrator/verification.py::VerificationBaseline.
#: ignored_names`'s identical list for the identical reason (a `.git` history or a stale
#: build tree left in the mission's extracted source is real, reachable I/O this stage
#: does not need to pay for). Irrelevant to the subprocess-`Jail` path, which builds
#: out-of-place against the original `source_dir` and never copies it anywhere.
_CONTAINER_SOURCE_COPY_IGNORED_NAMES: tuple[str, ...] = (
    ".git",
    "build",
    "cmake-build-debug",
    "cmake-build-release",
)


def run_baseline_stage(
    mission_id: str | uuid.UUID,
    source_dir: Path | str,
    workspace_root: Path | str,
    *,
    jail_policy: JailPolicy | None = None,
    container_policy: ContainerJailPolicy | None = None,
    extra_cmake_args: Mapping[str, str] | None = None,
) -> BaselineOutcome:
    """Run the baseline stage for one mission. Never raises on a red or broken build —
    every failure mode this module knows about is converted into a `BaselineOutcome` with
    `passed=False` and `failure` populated. Only a programming error (a bug in this
    module) escapes as an unhandled exception.

    ``extra_cmake_args`` (#290): extra CMake ``-D`` cache entries threaded verbatim into
    `adapters/cpp/pipeline.py::run_variant`'s `extra_cache_entries` parameter — the
    operator's escape hatch for a real, pre-2021 CMake target whose own
    `cmake_minimum_required` predates CMake 4.0's policy floor and would otherwise fail
    CONFIGURE before this stage can produce even a legitimate red result. `workers/
    baseline/dispatch.py` is the one caller that populates this, from
    `MissionPolicy.baseline_extra_cmake_args` (`contracts/schemas/missions.py`) on the
    authorizing mission. `None` (the default) is the pre-#290 behavior, unchanged.

    Opens exactly one jail for the whole configure+build+ctest sequence and closes it
    before returning — its scratch directory, including `BuildResult.build_dir`, does not
    survive past this call (D-053/D-054). The one artifact worth keeping — the CTest
    JUnit report — is copied out to `workspace_root` (which is NOT inside the jail and is
    not deleted) while the jail is still open, and `BaselineOutcome.log_ref` points at
    that durable copy, not the ephemeral original.

    ``container_policy`` (#181/SEC-57): when given, this stage runs inside
    `packages.sandbox.container.ContainerJail` (via `ContainerJailRunner`, `packages/
    sandbox/container_runner.py`) instead of the subprocess-only `packages.sandbox.Jail`
    — D-024's `--network none`/`--cap-drop ALL`/`--read-only` isolation, real for a
    mission's own build/test suite (BASELINE runs a target's own, potentially
    adversarial, `CMakeLists.txt`/CTest configuration — see #181's own finding). `None`
    (the default) is the pre-#181 behavior, unchanged: `workers/baseline/dispatch.py`
    decides which to pass based on whether `settings.SANDBOX_BUILD_IMAGE` is configured.

    The container path additionally copies `source_dir` into the jail's own bind-mounted
    root before building — `ContainerJail` has exactly one mount point (`packages/
    sandbox/container.py::_docker_run_args`, `-v {root}:/workspace:rw`), unlike the
    subprocess `Jail`, which shares the whole host filesystem and can build out-of-place
    against the original `source_dir` with no copy at all (`adapters/cpp/pipeline.py`'s
    own `-S <source_dir>` argument, resolved as a bare host path). The copy is the one
    real, load-bearing difference this function's two branches have beyond which jail
    class they open — see `_CONTAINER_SOURCE_COPY_IGNORED_NAMES`.
    """
    started = time.monotonic()
    mission_id_str = str(mission_id)
    recorded_at = datetime.now(UTC)
    source = Path(source_dir).resolve()

    # #17 AC 4: the snapshot hash is recorded regardless of what happens next — computed
    # before configure/build even start, so it reflects the exact input attempted. Always
    # hashes the ORIGINAL source, never the container path's own in-jail copy — the
    # snapshot must describe the exact, unmodified mission input either way.
    snapshot = hash_source_tree(source)

    workspace = Path(workspace_root).resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    build_result: BuildResult | None = None
    failure: BaselineFailureDetail | None = None
    adapter_name = "UNKNOWN"
    log_ref: str | None = None
    compiler_diagnostics: tuple[CompilerDiagnostic, ...] = ()
    compiler_id = "unknown"
    compiler_version = "unknown"

    using_container = container_policy is not None
    image_digest = require_pinned(container_policy.image) if using_container else None
    isolation_mode = CONTAINER_ISOLATION_MODE if using_container else ISOLATION_MODE
    isolation_unprotected_against = (
        CONTAINER_ISOLATION_UNPROTECTED_AGAINST if using_container else ISOLATION_UNPROTECTED_AGAINST
    )

    jail_cm = (
        ContainerJailRunner.create(container_policy, parent=workspace, mission_ref=mission_id_str)
        if using_container
        else Jail.create(jail_policy, parent=workspace)
    )
    with jail_cm as jail:
        try:
            build_source = source
            if using_container:
                # See this function's own docstring: the container's one bind mount has
                # to actually contain the source before `-S <path>` (built from it,
                # `adapters/cpp/pipeline.py::_configure_argv`) means anything inside the
                # container's own mount namespace.
                build_source = jail.root / source.name
                shutil.copytree(
                    source,
                    build_source,
                    ignore=shutil.ignore_patterns(*_CONTAINER_SOURCE_COPY_IGNORED_NAMES),
                )
            build_result = run_variant(
                build_source,
                jail,
                Variant.BASELINE,
                image_digest=image_digest,
                extra_cache_entries=extra_cmake_args,
            )
            adapter_name = build_result.detected.build_system.value
            # #23: structurally parse the compiler diagnostics out of the SAME
            # `cmake --build` invocation the D3 gate already ran — while the jail is
            # still open, since `build_result.build.stdout`/`.stderr` (a `JailResult`)
            # do not survive past the `with` block any more than `build_dir` does (see
            # this module's own docstring and `adapters/cpp/pipeline.py`'s). Reuses the
            # compiler identity `run_variant` already read out of the CMake-generated
            # build tree (`read_compiler_identity`, `adapters/cpp/toolchain.py`) rather
            # than probing the compiler a second time.
            compiler_diagnostics = parse_compiler_diagnostics(
                build_result.build.stdout + "\n" + build_result.build.stderr
            )
            compiler_id = build_result.toolchain.compiler_id
            compiler_version = build_result.toolchain.compiler_version
            # Copy the one artifact worth keeping out of the jail before it tears down.
            # Everything else in BaselineOutcome is already-extracted data
            # (CTestSummary's counts), not a path into the jail.
            durable_junit = workspace / f"{mission_id_str}-baseline-ctest-junit.xml"
            durable_junit.write_bytes(Path(build_result.ctest.junit_path).read_bytes())
            log_ref = str(durable_junit)
        except StepFailure as exc:
            failure = _failure_from_step_failure(exc)
            adapter_name = _adapter_name_or_unknown(source)
            # A BUILD-step failure still carries whatever the compiler printed before
            # the fatal error, but only the truncated tail `StepFailure.detail` kept
            # (`adapters/cpp/pipeline.py`'s own `stderr[-2000:]`) — the full transcript
            # does not survive past this jail closing. Parsed on a best-effort basis;
            # `compiler_id`/`compiler_version` stay "unknown" here (`read_
            # compiler_identity` never ran — `run_variant` raises before reaching it on
            # a BUILD failure), an honest gap rather than a fabricated identity.
            if exc.step is BuildStep.BUILD:
                compiler_diagnostics = parse_compiler_diagnostics(failure.detail)
        except (ToolchainError, AdapterError) as exc:
            step = (
                BuildStep.PROBE_TOOLCHAIN if isinstance(exc, ToolchainError) else BuildStep.DETECT
            )
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
            log_ref=log_ref,
            compiler_diagnostics=compiler_diagnostics,
            compiler_id=compiler_id,
            compiler_version=compiler_version,
            isolation_mode=isolation_mode,
            isolation_unprotected_against=isolation_unprotected_against,
        )

    # Configure, build, or toolchain probing did not complete. Recorded as a red baseline
    # with zero counts — never as a pass, never hidden. `configure_ok`/`build_ok` reflect
    # exactly how far the pipeline got: DETECT/PROBE_TOOLCHAIN failures mean neither ran;
    # a CONFIGURE StepFailure means configure itself failed; a BUILD StepFailure means
    # configure succeeded and build did not.
    assert failure is not None
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
        compiler_diagnostics=compiler_diagnostics,
        compiler_id=compiler_id,
        compiler_version=compiler_version,
        log_ref=None,  # no durable artifact for a configure/build failure — see `failure.detail`
        failure=failure,
        isolation_mode=isolation_mode,
        isolation_unprotected_against=isolation_unprotected_against,
    )


def _adapter_name_or_unknown(source: Path) -> str:
    """Best-effort adapter name for a report even when detection itself failed."""
    try:
        return detect(source).build_system.value
    except AdapterError:
        return (
            BuildSystem.C_CMAKE_CTEST.value if (source / "CMakeLists.txt").is_file() else "UNKNOWN"
        )


def emit_baseline_events(
    outcome: BaselineOutcome, *, sequence_start: int = 1
) -> list[dict[str, Any]]:
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
