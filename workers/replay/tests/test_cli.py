from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path

from workers.replay import cli
from workers.replay.run import ReplayFinding, ReplayOutcome, ReplayReproducerRecord


def test_cli_writes_d4_d5_gate_evidence(
    monkeypatch, tmp_path: Path  # noqa: ANN001
) -> None:
    output = tmp_path / "gate.json"

    monkeypatch.setattr(cli, "run_replay_stage", lambda *args, **kwargs: _outcome(confirmed=True))

    stdout = io.StringIO()
    stderr = io.StringIO()
    code = cli.main(["--output", str(output), "--events"], stdout=stdout, stderr=stderr)

    assert code == 0
    record = json.loads(output.read_text())
    streamed = json.loads(stdout.getvalue())
    assert record == streamed
    assert record["schema"] == "brahmadatta.d4_d5_gate.v1"
    assert record["gate"]["passed"] is True
    assert record["gate"]["sanitizer_confirmed"] is True
    assert record["gate"]["clean_replay_passed"] is True
    assert record["gate"]["minimized_reproducer"] is True
    assert record["gate"]["fuzzing_mode"] == "NOT_RUN"
    assert record["gate"]["discovery_method"] == "REPLAYED_REPRODUCER"
    assert [event["type"] for event in record["events"]] == [
        "STAGE_COMPLETED",
        "FINDING_RECORDED",
        "REPRODUCER_RECORDED",
    ]
    assert stderr.getvalue() == ""


def test_cli_fails_when_gate_does_not_replay_five_of_five(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(cli, "run_replay_stage", lambda *args, **kwargs: _outcome(confirmed=False))

    stdout = io.StringIO()
    stderr = io.StringIO()
    code = cli.main([], stdout=stdout, stderr=stderr)

    assert code == 1
    record = json.loads(stdout.getvalue())
    assert record["gate"]["passed"] is False
    assert record["gate"]["clean_replay_passed"] is False
    assert "D5 gate failed" in stderr.getvalue()


def test_cli_reports_gate_runner_blockers(monkeypatch) -> None:  # noqa: ANN001
    def fail(*args, **kwargs):  # noqa: ANN001
        raise FileNotFoundError("stored reproducer not found")

    monkeypatch.setattr(cli, "run_replay_stage", fail)

    stdout = io.StringIO()
    stderr = io.StringIO()
    code = cli.main([], stdout=stdout, stderr=stderr)

    assert code == 2
    assert stdout.getvalue() == ""
    assert "stored reproducer not found" in stderr.getvalue()


def _outcome(*, confirmed: bool) -> ReplayOutcome:
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    finding = ReplayFinding(
        id="finding-1",
        mission_id="mission-1",
        category="HEAP_BUFFER_OVERFLOW",
        severity="CRITICAL",
        tool="ADDRESS_SANITIZER",
        discovery_method="REPLAYED_REPRODUCER",
        replay_source="artifact://reproducer/crash-literal-tab.bin",
        file_path="src/decode.c",
        line=43,
        function="emit_tab",
        fingerprint="replayed:ADDRESS_SANITIZER:heap-buffer-overflow:emit_tab:abcd",
        reproducible=True,
        detected_at=now,
        title="heap buffer overflow in emit_tab at decode.c:43",
        sanitizer_report="SUMMARY: AddressSanitizer: heap-buffer-overflow src/decode.c:43 in emit_tab",
    )
    reproducer = ReplayReproducerRecord(
        id="reproducer-1",
        finding_id="finding-1",
        minimized=True,
        replay_attempts=5,
        replay_successes=5 if confirmed else 4,
        test_command="./pktcfg_replay crash-literal-tab.bin x5",
        artifact={
            "uri": "artifact://reproducer/crash-literal-tab.bin",
            "kind": "crash-input",
            "sha256": "a" * 64,
            "size_bytes": 22,
        },
        created_at=now,
    )
    return ReplayOutcome(
        mission_id="mission-1",
        source_dir="/repo/demo/repositories/pktcfg",
        replay_source="artifact://reproducer/crash-literal-tab.bin",
        replay_attempts=5,
        replay_successes=5 if confirmed else 4,
        duration_seconds=1.25,
        build_variant="ASAN_UBSAN",
        fuzzing_report={
            "mission_id": "mission-1",
            "mode": "NOT_RUN",
            "harness": "pktcfg_fuzz_one_input",
            "engine": "libFuzzer",
            "runtime_seconds": 0.0,
            "executions": 0,
            "crashes_found": 0,
            "unique_crashes": 0,
            "corpus_size": 0,
            "sanitizers": ["address", "undefined"],
            "finding_ids": [],
            "replay_source": None,
            "recorded_at": now.isoformat(),
        },
        finding=finding,
        reproducer=reproducer,
        captured_stdout="",
        captured_stderr=finding.sanitizer_report,
        recorded_at=now,
    )
