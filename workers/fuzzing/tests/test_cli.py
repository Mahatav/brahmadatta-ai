from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path

from adapters.cpp.fuzzing import FuzzFailure
from workers.fuzzing import cli
from workers.fuzzing.run import FuzzingOutcome

PINNED_IMAGE = "llvm-fuzzer@sha256:" + "b" * 64


def test_cli_writes_d5_fuzzing_gate_evidence(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "fuzzing.json"

    monkeypatch.setattr(cli, "run_fuzzing_stage", lambda *args, **kwargs: _outcome(crashes=1))

    stdout = io.StringIO()
    stderr = io.StringIO()
    code = cli.main(
        ["--image", PINNED_IMAGE, "--output", str(output), "--events"],
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 0
    record = json.loads(output.read_text())
    streamed = json.loads(stdout.getvalue())
    assert record == streamed
    assert record["schema"] == "brahmadatta.d5_fuzzing_gate.v1"
    assert record["gate"]["passed"] is True
    assert record["gate"]["sanitizer_confirmed"] is True
    assert record["gate"]["mode"] == "LIVE_CAMPAIGN"
    assert record["gate"]["crashes_found"] == 1
    assert "AddressSanitizer" in record["fuzzing"]["run_output_excerpt"]
    assert [event["type"] for event in record["events"]] == ["STAGE_STARTED", "STAGE_COMPLETED"]
    assert stderr.getvalue() == ""


def test_cli_fails_when_fuzzer_finds_no_crash(monkeypatch) -> None:
    monkeypatch.setattr(cli, "run_fuzzing_stage", lambda *args, **kwargs: _outcome(crashes=0))

    stdout = io.StringIO()
    stderr = io.StringIO()
    code = cli.main(["--image", PINNED_IMAGE], stdout=stdout, stderr=stderr)

    assert code == 1
    record = json.loads(stdout.getvalue())
    assert record["gate"]["passed"] is False
    assert "D5 fuzzing gate failed" in stderr.getvalue()


def test_cli_reports_gate_runner_blockers(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise RuntimeError("container runtime is unavailable")

    monkeypatch.setattr(cli, "run_fuzzing_stage", fail)

    stdout = io.StringIO()
    stderr = io.StringIO()
    code = cli.main(["--image", PINNED_IMAGE], stdout=stdout, stderr=stderr)

    assert code == 2
    assert stdout.getvalue() == ""
    assert "container runtime is unavailable" in stderr.getvalue()


def _outcome(*, crashes: int) -> FuzzingOutcome:
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    return FuzzingOutcome(
        mission_id="mission-fuzzing",
        mode="LIVE_CAMPAIGN",
        harness="pktcfg_fuzz_one_input",
        engine="libFuzzer",
        runtime_seconds=2.5,
        executions=2048,
        crashes_found=crashes,
        unique_crashes=crashes,
        corpus_size=8,
        sanitizers=("address",),
        recorded_at=now,
        coverage=44,
        artifact_refs=("fuzz-artifacts/crash-abc",) if crashes else (),
        run_output_excerpt=(
            "SUMMARY: AddressSanitizer: heap-buffer-overflow src/decode.c:43 in emit_tab"
            if crashes
            else "#2048 DONE cov: 44"
        ),
        failure=None
        if crashes
        else FuzzFailure(
            step="RUN",
            command=("pktcfg_fuzz",),
            exit_code=0,
            first_error="no crash found",
        ),
    )
