"""Render the D6 verdict-loop evidence as a judge-readable Markdown report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_BAD_INPUT = 5
DEFAULT_INPUT = ".project/evidence/d6-verdict-loop-gate.json"
DEFAULT_OUTPUT = ".project/evidence/d6-verdict-loop-report.md"
GATE_ORDER = (
    "compile",
    "reproducer_eliminated",
    "regression_preserved",
    "static_delta",
    "renewed_fuzzing",
)


def _cmd_render(args: argparse.Namespace) -> int:
    source = Path(args.input)
    payload = json.loads(source.read_text(encoding="utf-8"))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_render_markdown(payload, source), encoding="utf-8")
    sys.stdout.write(f"wrote {output}\n")
    return EXIT_OK


def _cmd_check(args: argparse.Namespace) -> int:
    report = Path(args.report)
    text = report.read_text(encoding="utf-8")
    required = [
        "## Run 1",
        "## Run 2",
        "VERIFIED",
        "REJECTED",
        "| Gate | Status | Detail |",
        "NOT_RUN",
    ]
    missing = [item for item in required if item not in text]
    if missing:
        raise ValueError(f"{report} is missing: {', '.join(missing)}")
    sys.stdout.write(f"verdict report ok: {report}\n")
    return EXIT_OK


def _render_markdown(payload: dict[str, Any], source: Path) -> str:
    gate = payload.get("gate", {})
    lines = [
        "# D6 Verdict Loop Report",
        "",
        f"Source evidence: `{source}`",
        f"Recorded at: `{payload.get('recorded_at', 'unknown')}`",
        "",
        "## Gate",
        "",
        f"- Name: `{gate.get('name', 'unknown')}`",
        f"- Consecutive runs: `{gate.get('consecutive_runs', 'unknown')}`",
        f"- Passed: `{gate.get('passed', 'unknown')}`",
        f"- Model generation attempts: `{_model_attempts(gate)}`",
        "",
    ]
    for run in payload.get("runs", []):
        lines.extend(_render_run(run))
    return "\n".join(lines).rstrip() + "\n"


def _render_run(run: dict[str, Any]) -> list[str]:
    lines = [
        f"## Run {run.get('run_number', 'unknown')}",
        "",
        f"- Mission: `{run.get('mission_id', 'unknown')}`",
        f"- Elapsed ms: `{run.get('elapsed_ms', 'unknown')}`",
        "",
    ]
    summary = run.get("summary", {})
    if isinstance(summary, dict):
        lines.extend(
            [
                "### Verdict Summary",
                "",
                f"- Mission verdict: `{summary.get('mission_verdict', 'unknown')}`",
                f"- Verified candidates: `{summary.get('verified_count', 'unknown')}`",
                f"- Rejected candidates: `{summary.get('rejected_count', 'unknown')}`",
                "",
            ]
        )
    for record in run.get("verifications", []):
        lines.extend(_render_verification(record))
    return lines


def _render_verification(record: dict[str, Any]) -> list[str]:
    lines = [
        f"### Candidate `{record.get('patch_id', 'unknown')}`",
        "",
        f"Verdict: `{record.get('verdict', 'unknown')}`",
        "",
        "| Gate | Status | Detail |",
        "|---|---|---|",
    ]
    gates = record.get("gates", {})
    for gate_name in GATE_ORDER:
        gate = gates.get(gate_name, {}) if isinstance(gates, dict) else {}
        lines.append(
            "| "
            f"{gate_name} | "
            f"{gate.get('status', 'NOT_RUN')} | "
            f"{_escape_table(str(gate.get('detail', 'reason unavailable')))} |"
        )
    lines.append("")
    return lines


def _model_attempts(gate: dict[str, Any]) -> str:
    attempts = gate.get("model_generation_attempts")
    if not isinstance(attempts, dict):
        return "not recorded"
    text = (
        f"{attempts.get('completed', 'unknown')} of "
        f"{attempts.get('required', 'unknown')} - "
        f"{attempts.get('status', 'unknown')}"
    )
    artifact = attempts.get("artifact")
    if isinstance(artifact, str) and artifact:
        text += f" ({artifact})"
    return text


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render/check the D6 verdict-loop report.")
    sub = parser.add_subparsers(dest="command", required=True)
    render = sub.add_parser("render")
    render.add_argument("--input", default=DEFAULT_INPUT)
    render.add_argument("--output", default=DEFAULT_OUTPUT)
    check = sub.add_parser("check")
    check.add_argument("--report", default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return {"render": _cmd_render, "check": _cmd_check}[args.command](args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return EXIT_BAD_INPUT


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
