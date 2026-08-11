"""Stored-reproducer replay stage (#83)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from adapters.cpp.pipeline import ReproducerResult
from adapters.cpp.sanitizer import SanitizerFinding
from workers.replay import run as replay_run
from workers.replay.run import emit_replay_events, run_replay_stage


def test_replay_path_records_skipped_fuzzing_without_starting_a_campaign(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, pktcfg_source: Path
) -> None:
    calls: list[tuple[str, tuple[str, ...]]] = []

    def fake_run_variant(source_dir, jail, variant):  # noqa: ANN001
        assert Path(source_dir) == pktcfg_source
        assert variant.value == "ASAN_UBSAN"
        return SimpleNamespace(build_dir=tmp_path / "build-asan-ubsan")

    def fake_run_reproducer(jail, binary_path, args, *, spec):  # noqa: ANN001
        calls.append((Path(binary_path).name, args))
        return ReproducerResult(
            argv=(str(binary_path), *args),
            exit_code=1,
            duration_seconds=0.01,
            findings=(
                SanitizerFinding(
                    tool="ADDRESS_SANITIZER",
                    kind="heap-buffer-overflow",
                    message="ERROR: AddressSanitizer: heap-buffer-overflow",
                    function="emit_tab",
                    file="src/decode.c",
                    line=43,
                    raw="SUMMARY: AddressSanitizer: heap-buffer-overflow src/decode.c:43 in emit_tab",
                ),
            ),
            timed_out=False,
            captured_stdout="",
            captured_stderr="SUMMARY: AddressSanitizer: heap-buffer-overflow src/decode.c:43 in emit_tab",
        )

    monkeypatch.setattr(replay_run, "run_variant", fake_run_variant)
    monkeypatch.setattr(replay_run, "run_reproducer", fake_run_reproducer)

    outcome = run_replay_stage("mission-replay-unit", pktcfg_source, tmp_path / "workspace")
    events = emit_replay_events(outcome)

    assert len(calls) == 5
    assert all(binary == "pktcfg_replay" for binary, _ in calls)
    assert all(args[1] == "1" for _, args in calls)
    assert all("pktcfg_fuzz" not in " ".join((binary, *args)) for binary, args in calls)
    assert outcome.confirmed is True
    assert outcome.fuzzing_report["mode"] == "NOT_RUN"
    assert outcome.fuzzing_report["executions"] == 0
    assert outcome.finding is not None
    assert outcome.finding.discovery_method == "REPLAYED_REPRODUCER"
    assert outcome.finding.replay_source == "artifact://reproducer/crash-literal-tab.bin"
    assert outcome.reproducer is not None
    assert outcome.reproducer.replay_attempts == 5
    assert outcome.reproducer.replay_successes == 5
    assert events[0]["type"] == "STAGE_COMPLETED"
    assert "SKIPPED" in events[0]["message"]
    assert events[0]["payload"]["report"]["mode"] == "NOT_RUN"
    assert [event["type"] for event in events[1:]] == [
        "FINDING_RECORDED",
        "REPRODUCER_RECORDED",
    ]


@pytest.mark.slow
def test_committed_crash_reproducer_replays_five_of_five(
    tmp_path: Path, pktcfg_source: Path
) -> None:
    outcome = run_replay_stage("mission-replay-real", pktcfg_source, tmp_path / "workspace")
    events = emit_replay_events(outcome)

    assert outcome.confirmed is True
    assert outcome.replay_attempts == 5
    assert outcome.replay_successes == 5
    assert outcome.fuzzing_report["mode"] == "NOT_RUN"
    assert outcome.fuzzing_report["executions"] == 0
    assert outcome.finding is not None
    assert outcome.finding.discovery_method == "REPLAYED_REPRODUCER"
    assert outcome.finding.category == "HEAP_BUFFER_OVERFLOW"
    assert outcome.finding.function == "emit_tab"
    if outcome.finding.file_path != "<unknown>":
        assert Path(outcome.finding.file_path).name == "decode.c"
        assert outcome.finding.line == 43
    else:
        assert outcome.finding.line is None
    assert outcome.reproducer is not None
    assert outcome.reproducer.artifact["sha256"]
    assert outcome.reproducer.artifact["size_bytes"] > 0
    assert [event["type"] for event in events] == [
        "STAGE_COMPLETED",
        "FINDING_RECORDED",
        "REPRODUCER_RECORDED",
    ]
    assert events[0]["payload"]["report"]["mode"] == "NOT_RUN"
    assert "FUZZING_CAMPAIGN" not in str(outcome.as_dict())
