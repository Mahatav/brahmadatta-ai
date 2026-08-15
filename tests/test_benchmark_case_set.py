from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = REPO_ROOT / ".project" / "evidence" / "d8-benchmark-case-set.json"
PKTCFG = REPO_ROOT / "demo" / "repositories" / "pktcfg"
PERFORMANCE_DOC = REPO_ROOT / "docs" / "03-technical" / "29-performance-requirements.md"
MASTER_DOC = REPO_ROOT / "docs" / "Brahmadatta-AI-Master-MVP-Documentation.md"


def _benchmark() -> dict:
    return json.loads(BENCHMARK.read_text(encoding="utf-8"))


def test_benchmark_case_set_records_all_issue_61_cases() -> None:
    case_ids = {case["id"] for case in _benchmark()["cases"]}

    assert {
        "BD-001",
        "BD-001-A",
        "BD-001-B",
        "BD-001-P",
        "BD-001-C",
        "BD-001-M",
        "BD-002",
        "BD-003",
        "BD-004",
    } <= case_ids


def test_candidate_patch_artifacts_exist() -> None:
    for case in _benchmark()["cases"]:
        patch = case.get("patch")
        if patch:
            assert (REPO_ROOT / patch).is_file(), patch


def test_new_benchmark_candidate_patches_are_applyable_diffs() -> None:
    for patch in [
        PKTCFG / "patches" / "candidate-p-policy-rejected-out-of-scope.patch",
        PKTCFG / "patches" / "candidate-c-compile-failure.patch",
    ]:
        result = subprocess.run(
            ["git", "apply", "--check", str(patch)],
            cwd=PKTCFG,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert result.returncode == 0, result.stderr


def test_metrics_are_not_published_as_measured_percentages() -> None:
    statuses = {
        row["metric"]: row["status"]
        for row in _benchmark()["metric_publication_status"]
    }

    assert statuses["Confirmed-finding precision on chosen benchmarks"] == "target - not measured"
    assert statuses["Verified patch rate on selected solvable cases"] == "target - not measured"


def test_issue_54_measurement_conditions_are_recorded() -> None:
    status = _benchmark()["issue_54_status"]

    assert status["benchmark_run"] == "not run"
    assert "target - not measured" in status["reason"]
    conditions = status["measurement_conditions_recorded_for_audit"]
    for key in ["host", "node", "npm", "python", "docker", "command_center"]:
        assert conditions[key]


def test_performance_tables_cannot_publish_unmeasured_targets() -> None:
    for path in [PERFORMANCE_DOC, MASTER_DOC]:
        text = path.read_text(encoding="utf-8")
        assert "Publication status" in text, path
        assert "Target - not measured" in text, path
        assert "Runtime deadlines in code come" in text, path
