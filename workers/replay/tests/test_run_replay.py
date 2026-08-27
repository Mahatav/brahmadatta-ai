"""Stored-reproducer replay stage (#83)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from adapters.cpp.pipeline import ReproducerResult
from adapters.cpp.sanitizer import SanitizerFinding
from workers.replay import run as replay_run
from workers.replay.run import emit_replay_events, run_replay_stage

# A fabricated, obviously-fake credential value for #246's regression test — distinct
# from `hunter2`/`DATABASE_URL=postgresql://svc_user:hunter2@...` already used by
# `apps/control-api/orchestrator/tests/test_sanitizer_report_redaction.py` and
# `test_fuzz_executor.py`'s own #191 regression test, so this test cannot pass by
# accidentally matching a pattern tuned for that other value.
_FAKE_TEST_TOKEN = "sk-FAKE-TEST-TOKEN-not-a-real-secret-88221"
_FAKE_SECRET_PROJECT_PATH = "/Users/replaytestuser/fake-secret-project/pktcfg/src/decode.c"

_POISONED_STDERR = (
    "==99999==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x602000000abc\n"
    f"API_TOKEN={_FAKE_TEST_TOKEN}\n"
    f"    #0 0x1 in emit_tab {_FAKE_SECRET_PROJECT_PATH}:43\n"
    f"SUMMARY: AddressSanitizer: heap-buffer-overflow {_FAKE_SECRET_PROJECT_PATH}:43 in emit_tab\n"
)


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


def test_finding_sanitizer_report_is_redacted_before_it_is_stored(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, pktcfg_source: Path
) -> None:
    """#246 (following #191/D-125): `ReplayFinding.sanitizer_report` must never carry
    the raw, unredacted captured stderr — redaction has to happen at the point the
    field is populated (`_finding_from_sanitizer`), not deferred to a display layer
    that (today) does not even exist for this worker.
    """

    def fake_run_variant(source_dir, jail, variant):  # noqa: ANN001
        return SimpleNamespace(build_dir=tmp_path / "build-asan-ubsan")

    def fake_run_reproducer(jail, binary_path, args, *, spec):  # noqa: ANN001
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
                    raw=_POISONED_STDERR,
                ),
            ),
            timed_out=False,
            captured_stdout="",
            captured_stderr=_POISONED_STDERR,
        )

    monkeypatch.setattr(replay_run, "run_variant", fake_run_variant)
    monkeypatch.setattr(replay_run, "run_reproducer", fake_run_reproducer)

    outcome = run_replay_stage("mission-replay-redaction", pktcfg_source, tmp_path / "workspace")

    assert outcome.finding is not None
    report = outcome.finding.sanitizer_report
    assert _FAKE_TEST_TOKEN not in report, "fake credential leaked through unredacted"
    assert _FAKE_SECRET_PROJECT_PATH not in report, "absolute path leaked through unredacted"

    # Not over-redacted: the crash signature stays useful to an operator.
    assert "AddressSanitizer: heap-buffer-overflow" in report
    assert "emit_tab" in report
    assert "SUMMARY: AddressSanitizer: heap-buffer-overflow" in report

    # The same guarantee holds for the JSON shape the CLI/event stream emits, once
    # `sanitizer_report` is added to it (see `ReplayFinding.as_summary_dict`'s own
    # docstring/#246 issue for why it is not there yet).
    assert _FAKE_TEST_TOKEN not in str(outcome.as_dict())
    assert _FAKE_SECRET_PROJECT_PATH not in str(outcome.as_dict())


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
