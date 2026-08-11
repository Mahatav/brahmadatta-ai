from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from adapters.cpp.fuzzing import (
    FuzzFailure,
    FuzzToolchainRecord,
    LibFuzzerMetrics,
    LibFuzzerRunResult,
)
from adapters.cpp.toolchain import ToolVersion
from packages.sandbox.container import ContainerJailPolicy
from workers.fuzzing.run import FuzzingOutcome, emit_fuzzing_events, run_fuzzing_stage

PINNED_IMAGE = "llvm-fuzzer@sha256:" + "b" * 64
REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def pktcfg_source() -> Path:
    return REPO_ROOT / "demo" / "repositories" / "pktcfg"


def _toolchain() -> FuzzToolchainRecord:
    return FuzzToolchainRecord(
        image=PINNED_IMAGE,
        isolation_mode="CONTAINER_NO_NETWORK",
        tools=(
            ToolVersion(name="cmake", version="4.2.3", path="cmake"),
            ToolVersion(name="clang", version="19.1.7", path="clang"),
        ),
    )


def test_run_fuzzing_stage_shapes_live_campaign(
    monkeypatch: pytest.MonkeyPatch, pktcfg_source: Path
) -> None:
    mission_id = uuid.uuid4()

    def fake_run(*args, **kwargs) -> LibFuzzerRunResult:  # type: ignore[no-untyped-def]
        return LibFuzzerRunResult(
            harness="pktcfg_fuzz",
            engine="libFuzzer",
            runtime_seconds=2.5,
            metrics=LibFuzzerMetrics(
                executions=2048,
                crashes_found=1,
                unique_crashes=1,
                coverage=55,
                corpus_size=8,
                artifact_paths=("fuzz-artifacts/crash-abc",),
                sanitizers=("address",),
            ),
            toolchain=_toolchain(),
            events=({"type": "STAGE_PROGRESS", "metrics": {"executions": 2048.0}},),
        )

    monkeypatch.setattr("workers.fuzzing.run.run_libfuzzer_campaign", fake_run)
    outcome = run_fuzzing_stage(
        mission_id,
        pktcfg_source,
        policy=ContainerJailPolicy(image=PINNED_IMAGE),
        budget_seconds=30,
    )

    assert outcome.mode == "LIVE_CAMPAIGN"
    assert outcome.executions == 2048
    assert outcome.unique_crashes == 1
    assert outcome.coverage == 55
    assert outcome.artifact_refs == ("fuzz-artifacts/crash-abc",)
    assert outcome.toolchain is not None
    assert outcome.as_dict()["toolchain"]["pinned"] is True


def test_run_fuzzing_stage_reports_toolchain_blocker(
    monkeypatch: pytest.MonkeyPatch, pktcfg_source: Path
) -> None:
    def fake_run(*args, **kwargs) -> LibFuzzerRunResult:  # type: ignore[no-untyped-def]
        raise ValueError("image reference is not pinned to a digest: 'llvm:latest'")

    monkeypatch.setattr("workers.fuzzing.run.run_libfuzzer_campaign", fake_run)
    outcome = run_fuzzing_stage(
        "mission-1",
        pktcfg_source,
        policy=ContainerJailPolicy(image=PINNED_IMAGE),
    )

    assert outcome.mode == "NOT_RUN"
    assert outcome.executions == 0
    assert outcome.failure is not None
    assert "not pinned" in outcome.failure.first_error


def test_emit_fuzzing_events_for_crash_campaign() -> None:
    outcome = FuzzingOutcome(
        mission_id=str(uuid.uuid4()),
        mode="LIVE_CAMPAIGN",
        harness="pktcfg_fuzz_one_input",
        engine="libFuzzer",
        runtime_seconds=3.2,
        executions=4096,
        crashes_found=1,
        unique_crashes=1,
        corpus_size=8,
        sanitizers=("address", "undefined"),
        recorded_at=datetime.now(timezone.utc),
        coverage=99,
        artifact_refs=("fuzz-artifacts/crash-abc",),
        toolchain=_toolchain(),
    )

    events = emit_fuzzing_events(outcome, sequence_start=10)

    assert [event["sequence"] for event in events] == [10, 11]
    assert events[0]["type"] == "STAGE_STARTED"
    assert events[1]["type"] == "STAGE_COMPLETED"
    assert events[1]["severity"] == "HIGH"
    assert events[1]["payload"]["kind"] == "fuzzing"
    assert events[1]["payload"]["report"]["mode"] == "LIVE_CAMPAIGN"
    assert events[1]["metrics"]["executions"] == 4096.0


def test_emit_fuzzing_events_for_not_run_failure() -> None:
    outcome = FuzzingOutcome(
        mission_id="mission-1",
        mode="NOT_RUN",
        harness="pktcfg_fuzz_one_input",
        engine="libFuzzer",
        runtime_seconds=0.0,
        executions=0,
        crashes_found=0,
        unique_crashes=0,
        corpus_size=0,
        sanitizers=(),
        recorded_at=datetime.now(timezone.utc),
        failure=FuzzFailure(
            step="BUILD",
            command=("cmake", "--build", "build"),
            exit_code=2,
            first_error="libclang_rt.fuzzer_osx.a not found",
        ),
    )

    events = emit_fuzzing_events(outcome)

    assert events[1]["type"] == "MISSION_FAILED"
    assert events[1]["status"] == "FAILED"
    assert "libclang_rt.fuzzer_osx.a" in events[1]["message"]
