"""CLI for the D5 live libFuzzer campaign."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any, TextIO

from packages.sandbox.container import ContainerJailPolicy
from workers.fuzzing.run import FuzzingOutcome, emit_fuzzing_events, run_fuzzing_stage

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = REPO_ROOT / "demo" / "repositories" / "pktcfg"


def main(argv: list[str] | None = None, *, stdout: TextIO = sys.stdout, stderr: TextIO = sys.stderr) -> int:
    args = _parser().parse_args(argv)

    try:
        outcome = run_fuzzing_stage(
            args.mission_id,
            args.source,
            policy=ContainerJailPolicy(
                image=args.image,
                runtime=args.runtime,
                wall_clock_seconds=args.wall_clock_seconds,
                memory_mb=args.memory_mb,
                cpu_limit=args.cpu_limit,
            ),
            budget_seconds=args.budget_seconds,
        )
    except Exception as exc:
        print(f"D5 fuzzing gate failed to run: {exc}", file=stderr)
        return 2

    record = build_fuzzing_record(outcome, include_events=args.events)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(_json(record, pretty=args.pretty) + "\n", encoding="utf-8")
    print(_json(record, pretty=args.pretty), file=stdout)

    if not record["gate"]["passed"]:
        print(_failure_message(record), file=stderr)
        return 1
    return 0


def build_fuzzing_record(outcome: FuzzingOutcome, *, include_events: bool = False) -> dict[str, Any]:
    sanitizer_confirmed = outcome.ran and outcome.crashes_found > 0 and bool(outcome.sanitizers)
    gate = {
        "name": "D5_LIVE_LIBFUZZER_SANITIZER_CRASH",
        "passed": sanitizer_confirmed,
        "sanitizer_confirmed": sanitizer_confirmed,
        "mode": outcome.mode,
        "executions": outcome.executions,
        "crashes_found": outcome.crashes_found,
        "unique_crashes": outcome.unique_crashes,
        "runtime_seconds": outcome.runtime_seconds,
        "artifact_refs": list(outcome.artifact_refs),
    }
    record: dict[str, Any] = {
        "schema": "brahmadatta.d5_fuzzing_gate.v1",
        "mission_id": outcome.mission_id,
        "recorded_at": outcome.recorded_at.isoformat(),
        "gate": gate,
        "fuzzing": outcome.as_dict(),
    }
    if include_events:
        record["events"] = emit_fuzzing_events(outcome)
    return record


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m workers.fuzzing",
        description="Run the D5 live libFuzzer campaign and emit JSON evidence.",
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="C/C++ target root.")
    parser.add_argument("--image", required=True, help="Pinned container image, name@sha256:<digest>.")
    parser.add_argument("--runtime", default="docker", help="Container runtime CLI.")
    parser.add_argument("--budget-seconds", type=int, default=1800, help="libFuzzer wall-clock budget.")
    parser.add_argument("--wall-clock-seconds", type=float, default=5400.0, help="Container wall-clock limit.")
    parser.add_argument("--memory-mb", type=int, default=8192, help="Container memory limit.")
    parser.add_argument("--cpu-limit", type=float, default=4.0, help="Container CPU limit.")
    parser.add_argument(
        "--mission-id",
        default=f"d5-fuzzing-gate-{uuid.uuid4()}",
        help="Mission id to stamp into the evidence record.",
    )
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON evidence output path.")
    parser.add_argument("--events", action="store_true", help="Include mission events.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser


def _json(record: dict[str, Any], *, pretty: bool) -> str:
    return json.dumps(record, indent=2 if pretty else None, sort_keys=True)


def _failure_message(record: dict[str, Any]) -> str:
    gate = record["gate"]
    return (
        "D5 fuzzing gate failed: "
        f"mode={gate['mode']} "
        f"sanitizer_confirmed={gate['sanitizer_confirmed']} "
        f"crashes_found={gate['crashes_found']}"
    )
