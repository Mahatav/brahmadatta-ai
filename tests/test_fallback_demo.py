from __future__ import annotations

import json
from pathlib import Path

from tools import fallback_demo


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_and_check_offline_fallback_demo(tmp_path: Path) -> None:
    d5_fuzzing = tmp_path / "d5-live-fuzzing.json"
    d5_replay = tmp_path / "d5-reproducer-gate.json"
    d6_loop = tmp_path / "d6-verdict-loop-gate.json"
    html = tmp_path / "fallback-demo.html"
    manifest = tmp_path / "fallback-demo-manifest.json"

    _write_json(
        d5_fuzzing,
        {"gate": {"runtime_seconds": 0.4, "crashes_found": 1}},
    )
    _write_json(
        d5_replay,
        {"gate": {"replay_successes": 5, "replay_attempts": 5}},
    )
    _write_json(
        d6_loop,
        {
            "gate": {"consecutive_runs": 2},
            "runs": [
                {
                    "verifications": [
                        {
                            "verdict": "VERIFIED",
                            "gates": {
                                "compile": {"status": "PASS", "detail": "ok"},
                                "reproducer_eliminated": {"status": "PASS", "detail": "ok"},
                                "regression_preserved": {"status": "PASS", "detail": "ok"},
                                "static_delta": {"status": "NOT_RUN", "detail": "cut"},
                                "renewed_fuzzing": {"status": "NOT_RUN", "detail": "cut"},
                            },
                        },
                        {
                            "verdict": "REJECTED",
                            "gates": {
                                "compile": {"status": "PASS", "detail": "ok"},
                                "reproducer_eliminated": {"status": "PASS", "detail": "ok"},
                                "regression_preserved": {"status": "FAIL", "detail": "failed"},
                                "static_delta": {"status": "NOT_RUN", "detail": "cut"},
                                "renewed_fuzzing": {"status": "NOT_RUN", "detail": "cut"},
                            },
                        },
                    ]
                }
            ],
        },
    )

    assert (
        fallback_demo.main(
            [
                "build",
                "--d5-fuzzing",
                str(d5_fuzzing),
                "--d5-replay",
                str(d5_replay),
                "--d6-loop",
                str(d6_loop),
                "--output",
                str(html),
                "--manifest",
                str(manifest),
            ]
        )
        == fallback_demo.EXIT_OK
    )
    assert fallback_demo.main(["check", "--manifest", str(manifest)]) == fallback_demo.EXIT_OK

    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["artifact"]["playable_offline"] is True
    assert payload["scope"]["d6_steps_1_to_7_with_both_verdicts"] is True
    assert payload["claim"] == "offline playable evidence replay"
    assert "D6 Gate Matrices" in html.read_text(encoding="utf-8")
