"""CLI for the D5 live libFuzzer campaign.

#292: this CLI never passed `workspace_root` through to `run_fuzzing_stage`, so
`ContainerJail.close()`'s own `shutil.rmtree` deleted any discovered crash artifact the
instant the campaign returned — even though this CLI's own JSON `artifact_refs` output
claimed one existed. `--workspace-root` (default `DEFAULT_WORKSPACE`, mirroring
`workers/replay/cli.py`'s identical `--workspace`/`DEFAULT_WORKSPACE` pattern) fixes the
one-call-site wiring gap; `run_fuzzing_stage`/`run_libfuzzer_campaign` already handled a
supplied `workspace_root` correctly (D-106) — nothing else needed to change.

#301: `--harness-target`/`--harness-binary`/`--cache-entry`/`--sanitizer-env` expose
`run_fuzzing_stage`'s own same-named parameters (already real since #296/#288/#289) to
an operator running this CLI directly against a non-pktcfg target — before this, the
only way to drive a second target through this stage at all was to bypass this CLI and
call `run_fuzzing_stage` from a one-off script, exactly what the #301 dogfooding session
had to do. Every one of these flags defaults to pktcfg's own values (unset
`--cache-entry`/`--sanitizer-env` mean "use `run_libfuzzer_campaign`'s own default /
no extra env," not an empty override), so a pktcfg invocation with none of these flags
is completely unaffected."""

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
DEFAULT_WORKSPACE = REPO_ROOT / ".d5-fuzz-workspace"
DEFAULT_HARNESS_TARGET = "pktcfg_fuzz"
DEFAULT_HARNESS_BINARY = "pktcfg_fuzz"


def _parse_kv_pairs(pairs: list[str] | None, *, flag: str) -> dict[str, str]:
    """Parse repeated `KEY=VALUE` arguments into a dict, in the order given (a later
    duplicate key wins, matching how `dict()` construction already behaves for
    `MissionPolicy.fuzz_cache_entries`/`fuzz_sanitizer_env`, #301)."""
    result: dict[str, str] = {}
    for pair in pairs or ():
        if "=" not in pair:
            raise argparse.ArgumentTypeError(f"{flag} expects KEY=VALUE, got: {pair!r}")
        key, _, value = pair.partition("=")
        if not key:
            raise argparse.ArgumentTypeError(f"{flag} expects a non-empty KEY, got: {pair!r}")
        result[key] = value
    return result


def main(argv: list[str] | None = None, *, stdout: TextIO = sys.stdout, stderr: TextIO = sys.stderr) -> int:
    args = _parser().parse_args(argv)

    try:
        cache_entries = _parse_kv_pairs(args.cache_entry, flag="--cache-entry") or None
        sanitizer_env = _parse_kv_pairs(args.sanitizer_env, flag="--sanitizer-env") or None
    except argparse.ArgumentTypeError as exc:
        print(str(exc), file=stderr)
        return 2

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
            harness_target=args.harness_target,
            harness_binary=args.harness_binary,
            cache_entries=cache_entries,
            budget_seconds=args.budget_seconds,
            workspace_root=args.workspace_root,
            sanitizer_env=sanitizer_env,
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
    parser.add_argument(
        "--harness-target",
        default=DEFAULT_HARNESS_TARGET,
        help=(
            "#301: the CMake target name to build (`cmake --build ... --target "
            "<this>`). Default is pktcfg's own target name — unset, this flag "
            "changes nothing about the pktcfg invocation."
        ),
    )
    parser.add_argument(
        "--harness-binary",
        default=DEFAULT_HARNESS_BINARY,
        help=(
            "#301: the built executable's bare file name inside the FUZZ build "
            "directory. Default is pktcfg's own binary name."
        ),
    )
    parser.add_argument(
        "--cache-entry",
        action="append",
        metavar="KEY=VALUE",
        help=(
            "#301: a CMake `-D<KEY>=<VALUE>` cache entry for the target's own "
            "sanitizer/fuzz-enable options (repeatable). Omitted entirely (the "
            "default), `run_libfuzzer_campaign` uses its own `DEFAULT_CACHE_ENTRIES` "
            "— pktcfg's `PKTCFG_SANITIZE=ON`/`PKTCFG_FUZZ=ON` — unchanged. Example: "
            "--cache-entry STB_SANITIZE=ON --cache-entry STB_FUZZ=ON"
        ),
    )
    parser.add_argument(
        "--sanitizer-env",
        action="append",
        metavar="KEY=VALUE",
        help=(
            "#301: sanitizer runtime environment for the live campaign (repeatable), "
            "e.g. --sanitizer-env ASAN_OPTIONS=detect_leaks=0. Omitted entirely (the "
            "default) adds nothing, matching pktcfg's prior behaviour."
        ),
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=DEFAULT_WORKSPACE,
        help=(
            "Host-side scratch space (D-106) that survives the campaign's own "
            "ContainerJail teardown, so a discovered crash artifact's bytes are still "
            "readable after this command returns (#292 — without this, the JSON "
            "output's artifact_refs point at bytes ContainerJail.close() already deleted)."
        ),
    )
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
