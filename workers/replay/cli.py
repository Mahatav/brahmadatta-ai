"""CLI for the D4/D5 stored-reproducer gate.

The worker already owns the real path. This module makes it operable: one command builds the
sanitized target, replays the committed reproducer five times from a clean workspace, and emits
the evidence-shaped JSON record the Command Center/API can display later.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any, TextIO

from workers.replay.run import ReplayOutcome, emit_replay_events, run_replay_stage

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = REPO_ROOT / "demo" / "repositories" / "pktcfg"
DEFAULT_WORKSPACE = REPO_ROOT / ".d4-d5-workspace"


def main(argv: list[str] | None = None, *, stdout: TextIO = sys.stdout, stderr: TextIO = sys.stderr) -> int:
    args = _parser().parse_args(argv)

    try:
        outcome = run_replay_stage(
            args.mission_id,
            args.source,
            args.workspace,
            reproducer_path=args.reproducer,
            replay_attempts=args.attempts,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary: report any gate blocker.
        print(f"D4/D5 gate failed to run: {exc}", file=stderr)
        return 2

    record = build_gate_record(outcome, include_events=args.events)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(_json(record, pretty=args.pretty) + "\n", encoding="utf-8")
    print(_json(record, pretty=args.pretty), file=stdout)

    if not record["gate"]["passed"]:
        print(_failure_message(record), file=stderr)
        return 1
    return 0


def build_gate_record(outcome: ReplayOutcome, *, include_events: bool = False) -> dict[str, Any]:
    finding = outcome.finding.as_summary_dict() if outcome.finding else None
    reproducer = outcome.reproducer.as_dict() if outcome.reproducer else None
    sanitizer_confirmed = finding is not None and bool(finding.get("tool"))
    clean_replay_passed = (
        outcome.replay_attempts > 0 and outcome.replay_successes == outcome.replay_attempts
    )
    minimized = bool(reproducer and reproducer.get("minimized"))
    gate = {
        "name": "D5_SANITIZER_REPRODUCER_5_OF_5",
        "passed": sanitizer_confirmed and clean_replay_passed and minimized,
        "sanitizer_confirmed": sanitizer_confirmed,
        "clean_replay_passed": clean_replay_passed,
        "replay_attempts": outcome.replay_attempts,
        "replay_successes": outcome.replay_successes,
        "minimized_reproducer": minimized,
        "fuzzing_mode": outcome.fuzzing_report["mode"],
        "discovery_method": finding["discovery_method"] if finding else None,
    }
    record: dict[str, Any] = {
        "schema": "brahmadatta.d4_d5_gate.v1",
        "mission_id": outcome.mission_id,
        "recorded_at": outcome.recorded_at.isoformat(),
        "source_dir": outcome.source_dir,
        "build_variant": outcome.build_variant,
        "gate": gate,
        "fuzzing": outcome.fuzzing_report,
        "finding": finding,
        "reproducer": reproducer,
        "duration_seconds": outcome.duration_seconds,
    }
    if include_events:
        record["events"] = emit_replay_events(outcome)
    return record


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m workers.replay",
        description="Run the D4/D5 sanitizer replay gate and emit JSON evidence.",
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="C/C++ target root.")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=DEFAULT_WORKSPACE,
        help="Scratch workspace for the isolated clean build.",
    )
    parser.add_argument("--reproducer", type=Path, default=None, help="Stored reproducer path.")
    parser.add_argument("--attempts", type=int, default=5, help="Independent replay attempts.")
    parser.add_argument(
        "--mission-id",
        default=f"d4-d5-gate-{uuid.uuid4()}",
        help="Mission id to stamp into the evidence record.",
    )
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON evidence output path.")
    parser.add_argument("--events", action="store_true", help="Include replay mission events.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser


def _json(record: dict[str, Any], *, pretty: bool) -> str:
    return json.dumps(record, indent=2 if pretty else None, sort_keys=True)


def _failure_message(record: dict[str, Any]) -> str:
    gate = record["gate"]
    return (
        "D5 gate failed: "
        f"sanitizer_confirmed={gate['sanitizer_confirmed']} "
        f"clean_replay_passed={gate['clean_replay_passed']} "
        f"minimized_reproducer={gate['minimized_reproducer']}"
    )
