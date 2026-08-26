"""`workers.static_analysis.run.run_analyze_stage` — the mission-facing wrapper
(#22, D-144). `run_semgrep_scan` mocked here; the real end-to-end path is
`adapters/semgrep/tests/test_real_scan.py`.
"""

from __future__ import annotations

import pytest

from adapters.semgrep.errors import UnpinnedToolchain
from adapters.semgrep.parser import SemgrepMatch, SemgrepScanReport
from adapters.semgrep.run_semgrep import SemgrepRunResult
from packages.sandbox.container import ContainerJailPolicy

PINNED_IMAGE = "brahmadatta-analyze-toolchain@sha256:" + "a" * 64


def _match(rule_id: str = "brahmadatta-c-memcpy-review-bounds") -> SemgrepMatch:
    return SemgrepMatch(
        rule_id=rule_id,
        raw_check_id=f"rules.c.{rule_id}",
        file_path="src/parse.c",
        start_line=114,
        end_line=114,
        message="review bounds",
        tool_severity="INFO",
        cwe="CWE-787",
        category="security",
        brahmadatta_category="OTHER",
        brahmadatta_severity="LOW",
        code_snippet="memcpy(entry->name, name, name_len);",
    )


def test_run_analyze_stage_shapes_a_live_scan(monkeypatch: pytest.MonkeyPatch, tmp_path):
    def fake_scan(*args, **kwargs) -> SemgrepRunResult:
        return SemgrepRunResult(
            report=SemgrepScanReport(
                tool_version="1.173.0",
                matches=(_match(),),
                scanned_files=("src/parse.c",),
                tool_errors=(),
                ok=True,
            ),
            image_digest=PINNED_IMAGE,
            ruleset_version="brahmadatta-c-cpp-2026-08-24",
            exit_code=0,
            limit_hit="NONE",
            runtime_seconds=1.2,
            stdout_truncated=False,
            stderr_excerpt="",
        )

    monkeypatch.setattr("workers.static_analysis.run.run_semgrep_scan", fake_scan)

    outcome = run_analyze_stage_helper(tmp_path, fake_scan)
    assert outcome.mode == "LIVE_SCAN"
    assert outcome.ran is True
    assert len(outcome.matches) == 1
    assert outcome.files_scanned == 1
    assert outcome.ruleset_version == "brahmadatta-c-cpp-2026-08-24"
    assert outcome.as_dict()["matches_found"] == 1
    assert "code_snippet" not in outcome.as_dict()  # never raw content in the summary


def test_run_analyze_stage_reports_a_clean_zero_match_scan(monkeypatch: pytest.MonkeyPatch, tmp_path):
    def fake_scan(*args, **kwargs) -> SemgrepRunResult:
        return SemgrepRunResult(
            report=SemgrepScanReport(
                tool_version="1.173.0",
                matches=(),
                scanned_files=("a.c", "b.c"),
                tool_errors=(),
                ok=True,
            ),
            image_digest=PINNED_IMAGE,
            ruleset_version="brahmadatta-c-cpp-2026-08-24",
            exit_code=0,
            limit_hit="NONE",
            runtime_seconds=0.5,
            stdout_truncated=False,
            stderr_excerpt="",
        )

    monkeypatch.setattr("workers.static_analysis.run.run_semgrep_scan", fake_scan)
    outcome = run_analyze_stage_helper(tmp_path, fake_scan)

    assert outcome.mode == "LIVE_SCAN"
    assert outcome.ran is True
    assert outcome.matches == ()
    assert outcome.files_scanned == 2


def test_run_analyze_stage_reports_unpinned_image_as_not_run(monkeypatch: pytest.MonkeyPatch, tmp_path):
    def fake_scan(*args, **kwargs):
        raise UnpinnedToolchain("image reference is not pinned to a digest: 'x:latest'")

    monkeypatch.setattr("workers.static_analysis.run.run_semgrep_scan", fake_scan)
    outcome = run_analyze_stage_helper(tmp_path, fake_scan)

    assert outcome.mode == "NOT_RUN"
    assert outcome.ran is False
    assert "not pinned" in (outcome.failure_reason or "")


def test_run_analyze_stage_reports_a_scan_level_error_as_not_run(monkeypatch: pytest.MonkeyPatch, tmp_path):
    def fake_scan(*args, **kwargs) -> SemgrepRunResult:
        return SemgrepRunResult(
            report=SemgrepScanReport(
                tool_version="1.173.0",
                matches=(),
                scanned_files=(),
                tool_errors=("unable to find a config",),
                ok=False,
            ),
            image_digest=PINNED_IMAGE,
            ruleset_version="unknown",
            exit_code=0,
            limit_hit="NONE",
            runtime_seconds=0.1,
            stdout_truncated=False,
            stderr_excerpt="",
        )

    monkeypatch.setattr("workers.static_analysis.run.run_semgrep_scan", fake_scan)
    outcome = run_analyze_stage_helper(tmp_path, fake_scan)

    assert outcome.mode == "NOT_RUN"
    assert outcome.ran is False
    assert outcome.tool_errors == ("unable to find a config",)


def run_analyze_stage_helper(tmp_path, _fake_scan):
    """Import here (not at module top) so `monkeypatch.setattr` on the string target
    above always lands before `run_analyze_stage` resolves its own module-level
    reference — mirrors the exact pattern `test_run_fuzzing.py` uses for
    `run_libfuzzer_campaign`."""
    from workers.static_analysis.run import run_analyze_stage

    return run_analyze_stage(
        "mission-1",
        tmp_path,
        policy=ContainerJailPolicy(image=PINNED_IMAGE),
        rules_dir=tmp_path,
    )
