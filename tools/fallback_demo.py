"""Build and verify the #49 offline fallback demonstration artifact."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "fallback-demo/1"
EXIT_OK = 0
EXIT_BAD_INPUT = 5
DEFAULT_D5_FUZZING = ".project/evidence/d5-live-fuzzing.json"
DEFAULT_D5_REPLAY = ".project/evidence/d5-reproducer-gate.json"
DEFAULT_D6_LOOP = ".project/evidence/d6-verdict-loop-gate.json"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - root python3 is 3.9.


def _cmd_build(args: argparse.Namespace) -> int:
    d5_fuzzing = _load(args.d5_fuzzing)
    d5_replay = _load(args.d5_replay)
    d6_loop = _load(args.d6_loop)

    html_path = Path(args.output)
    manifest_path = Path(args.manifest)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    html_path.write_text(_render_html(d5_fuzzing, d5_replay, d6_loop), encoding="utf-8")
    manifest = _manifest_payload(
        html_path,
        d5_fuzzing,
        d5_replay,
        d6_loop,
        source_paths=[args.d5_fuzzing, args.d5_replay, args.d6_loop],
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sys.stdout.write(f"wrote {html_path}\n")
    sys.stdout.write(f"wrote {manifest_path}\n")
    return EXIT_OK


def _cmd_check(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact = manifest_path.parent / manifest["artifact"]["path"]
    if not artifact.is_file():
        raise FileNotFoundError(f"{artifact} is not a file")
    digest = _sha256_file(artifact)
    if digest != manifest["artifact"]["sha256"]:
        raise ValueError(f"{artifact} sha256 mismatch: {digest}")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("fallback manifest schema_version mismatch")
    if manifest.get("claim") != "offline playable evidence replay":
        raise ValueError("fallback manifest does not declare its evidence-replay claim")
    if not manifest.get("captions"):
        raise ValueError("fallback manifest has no captions")
    sys.stdout.write(f"fallback demo ok: {artifact} sha256:{digest}\n")
    return EXIT_OK


def _manifest_payload(
    html_path: Path,
    d5_fuzzing: dict[str, Any],
    d5_replay: dict[str, Any],
    d6_loop: dict[str, Any],
    *,
    source_paths: list[str],
) -> dict[str, Any]:
    rel = html_path.name
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "fallback-demonstration",
        "claim": "offline playable evidence replay",
        "recorded_at": _now(),
        "artifact": {
            "path": rel,
            "sha256": _sha256_file(html_path),
            "bytes": html_path.stat().st_size,
            "media_type": "text/html",
            "playable_offline": True,
            "network_dependency": False,
        },
        "source_evidence": [
            {"path": path, "sha256": _sha256_file(Path(path))}
            for path in source_paths
        ],
        "scope": {
            "d5_steps_1_to_4": True,
            "d6_steps_1_to_7_with_both_verdicts": _d6_has_both_verdicts(d6_loop),
            "d7_all_nine_steps": False,
            "not_staged_or_reshot": True,
        },
        "captions": _captions(d5_fuzzing, d5_replay, d6_loop),
    }


def _captions(
    d5_fuzzing: dict[str, Any],
    d5_replay: dict[str, Any],
    d6_loop: dict[str, Any],
) -> list[str]:
    fuzz_gate = d5_fuzzing.get("gate", {})
    replay_gate = d5_replay.get("gate", {})
    d6_gate = d6_loop.get("gate", {})
    return [
        "D5 live libFuzzer campaign produced a sanitizer-confirmed crash.",
        (
            f"Fuzzing ran {fuzz_gate.get('runtime_seconds', 'unknown')} seconds and "
            f"found {fuzz_gate.get('crashes_found', 'unknown')} crash."
        ),
        (
            "The minimized reproducer replayed "
            f"{replay_gate.get('replay_successes', 'unknown')} of "
            f"{replay_gate.get('replay_attempts', 'unknown')} times from a clean build."
        ),
        (
            "D6 verdict loop produced both verdicts twice consecutively: "
            f"{d6_gate.get('consecutive_runs', 'unknown')} runs recorded."
        ),
        "Static delta and renewed fuzzing are disclosed as NOT_RUN where cut by plan.",
    ]


def _d6_has_both_verdicts(d6_loop: dict[str, Any]) -> bool:
    runs = d6_loop.get("runs", [])
    if not isinstance(runs, list) or not runs:
        return False
    for run in runs:
        verifications = run.get("verifications", []) if isinstance(run, dict) else []
        verdicts = {item.get("verdict") for item in verifications if isinstance(item, dict)}
        if not {"VERIFIED", "REJECTED"} <= verdicts:
            return False
    return True


def _render_html(
    d5_fuzzing: dict[str, Any],
    d5_replay: dict[str, Any],
    d6_loop: dict[str, Any],
) -> str:
    captions = _captions(d5_fuzzing, d5_replay, d6_loop)
    runs = d6_loop.get("runs", [])
    gate_rows = []
    for run in runs if isinstance(runs, list) else []:
        for record in run.get("verifications", []):
            gates = record.get("gates", {})
            gate_rows.append(
                "<tr>"
                f"<td>{html.escape(str(record.get('verdict', 'unknown')))}</td>"
                + "".join(
                    f"<td>{html.escape(str(gates.get(name, {}).get('status', 'NOT_RUN')))}"
                    f"<small>{html.escape(str(gates.get(name, {}).get('detail', '')))}</small></td>"
                    for name in (
                        "compile",
                        "reproducer_eliminated",
                        "regression_preserved",
                        "static_delta",
                        "renewed_fuzzing",
                    )
                )
                + "</tr>"
            )
    return f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>Brahmadatta D5/D6 Fallback Evidence Replay</title>
<style>
body {{ margin: 0; background: #161f99; color: #fff; font: 16px ui-monospace, SFMono-Regular, Menlo, monospace; }}
main {{ min-height: 100vh; display: grid; grid-template-columns: 360px 1fr; gap: 24px; padding: 32px; box-sizing: border-box; }}
h1 {{ margin: 0 0 16px; font: 700 46px Georgia, serif; }}
h2 {{ margin: 0 0 10px; font-size: 15px; letter-spacing: .12em; text-transform: uppercase; color: #bfc7ff; }}
section {{ border-top: 2px solid rgba(255,255,255,.72); padding-top: 18px; }}
ol {{ margin: 0; padding-left: 22px; line-height: 1.7; color: #dde2ff; }}
table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
th,td {{ border: 1px solid rgba(255,255,255,.35); padding: 10px; vertical-align: top; }}
small {{ display: block; margin-top: 6px; color: #b8c0ee; }}
.badge {{ display: inline-block; margin-top: 12px; border: 1px solid #fff; padding: 8px 10px; }}
</style>
<main>
  <aside>
    <h1>Brahmadatta Fallback</h1>
    <section>
      <h2>Captions</h2>
      <ol>{"".join(f"<li>{html.escape(line)}</li>" for line in captions)}</ol>
      <span class="badge">offline playable evidence replay</span>
    </section>
  </aside>
  <section>
    <h2>D6 Gate Matrices</h2>
    <table>
      <thead><tr><th>Verdict</th><th>Compile</th><th>Reproducer</th><th>Regression</th><th>Static</th><th>Fuzzing</th></tr></thead>
      <tbody>{"".join(gate_rows)}</tbody>
    </table>
  </section>
</main>
</html>
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build or check the #49 fallback demo artifact.")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--d5-fuzzing", default=DEFAULT_D5_FUZZING)
    build.add_argument("--d5-replay", default=DEFAULT_D5_REPLAY)
    build.add_argument("--d6-loop", default=DEFAULT_D6_LOOP)
    build.add_argument("--output", default=".project/evidence/fallback-demo-d6.html")
    build.add_argument("--manifest", default=".project/evidence/fallback-demo-d6-manifest.json")
    check = sub.add_parser("check")
    check.add_argument("--manifest", default=".project/evidence/fallback-demo-d6-manifest.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return {"build": _cmd_build, "check": _cmd_check}[args.command](args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return EXIT_BAD_INPUT


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
