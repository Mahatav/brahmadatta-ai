from __future__ import annotations

import json
from pathlib import Path

from tools import verdict_report


def test_render_and_check_d6_verdict_report(tmp_path: Path) -> None:
    source = tmp_path / "d6.json"
    report = tmp_path / "d6.md"
    source.write_text(
        json.dumps(
            {
                "recorded_at": "2026-08-13T04:07:24Z",
                "gate": {
                    "name": "D6_TWO_VERDICTS_FROM_ONE_ACTION_TWICE",
                    "passed": True,
                    "consecutive_runs": 2,
                    "model_generation_attempts": {
                    "completed": 0,
                    "required": 10,
                    "status": "blocked - model unavailable",
                    "artifact": ".project/evidence/d6-model-generation-attempts.json",
                },
                },
                "runs": [
                    _run(1),
                    _run(2),
                ],
            }
        ),
        encoding="utf-8",
    )

    assert (
        verdict_report.main(
            ["render", "--input", str(source), "--output", str(report)]
        )
        == verdict_report.EXIT_OK
    )
    assert verdict_report.main(["check", "--report", str(report)]) == verdict_report.EXIT_OK

    text = report.read_text(encoding="utf-8")
    assert "D6_TWO_VERDICTS_FROM_ONE_ACTION_TWICE" in text
    assert text.count("VERIFIED") >= 2
    assert text.count("REJECTED") >= 2
    assert "blocked - model unavailable" in text
    assert ".project/evidence/d6-model-generation-attempts.json" in text


def _run(number: int) -> dict:
    return {
        "run_number": number,
        "mission_id": f"m-{number}",
        "elapsed_ms": 1.2,
        "summary": {
            "mission_verdict": "VERIFIED",
            "verified_count": 1,
            "rejected_count": 1,
        },
        "verifications": [
            _verification("VERIFIED", "p-good", "PASS"),
            _verification("REJECTED", "p-bad", "FAIL"),
        ],
    }


def _verification(verdict: str, patch_id: str, regression: str) -> dict:
    return {
        "patch_id": patch_id,
        "verdict": verdict,
        "gates": {
            "compile": {"status": "PASS", "detail": "compiled"},
            "reproducer_eliminated": {"status": "PASS", "detail": "gone"},
            "regression_preserved": {"status": regression, "detail": "regression result"},
            "static_delta": {"status": "NOT_RUN", "detail": "cut"},
            "renewed_fuzzing": {"status": "NOT_RUN", "detail": "cut"},
        },
    }
