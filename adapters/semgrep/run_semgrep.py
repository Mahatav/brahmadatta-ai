"""Run a real Semgrep scan inside a `ContainerJail` against a vendored ruleset.

## Why a vendored ruleset, not `--config=p/c` / `--config=auto`

`packages.sandbox.container.ContainerJailPolicy.network` is hardcoded to `"none"` —
`__post_init__` refuses anything else (D-024 condition 1) — and
`docs/03-technical/23-security-plan.md` states the same policy at the project level:
"Outbound network denied by default." Semgrep's registry shorthands (`p/...`, `r/...`,
`auto`) resolve over HTTPS to `semgrep.dev`; there is no reachable network from inside
this sandbox to do that, by design, and there should not be — this project's own rule
is that repository content is never sent to an external service (see `CLAUDE.md`,
"Repository content is never sent to an external inference API"), and an outbound
config-resolution request is a real network call even though it is not an inference
call. `adapters/semgrep/rules/` is a small, hand-authored, pinned C/C++ ruleset
checked into this repository instead (see that directory's own YAML for the rules and
`adapters/semgrep/rules/VERSION` for the pin) — copied into the sandboxed worktree
alongside the target source (this module, below) and referenced by a local
`--config` path, which needs no network at all. Verified directly in this session,
not assumed: a real `docker run --network none --user 10001:10001 --cap-drop ALL
--security-opt no-new-privileges --read-only --tmpfs /tmp:size=64m` container, built
from `infrastructure/compose/images/analyze-toolchain.Dockerfile`, produced the
identical two real findings against `demo/repositories/pktcfg` that an unsandboxed
run produced (`src/parse.c:114` memcpy, `src/parse.c:120` malloc arithmetic) — see
this PR's handoff for the full transcript.

## `HOME=/tmp` — the one non-obvious flag this adapter needs

Checked directly: Semgrep's CLI tries to write a settings file to `~/.semgrep/`
*before* it does anything else, even on a scan that never touches the network for
config resolution — under D-024's `--read-only` root filesystem, `/home/analyzer` is
not writable and every invocation crashes with `OSError: [Errno 30] Read-only file
system: '/home/analyzer/.semgrep'` before printing any JSON at all. `ContainerJail`
already mounts a sized, writable tmpfs at `/tmp` (D-024 condition 5); pointing `HOME`
there (`_analyze_container_policy` in `workers/static_analysis/dispatch.py` sets
`extra_env={"HOME": "/tmp"}`) gives Semgrep a real writable location without loosening
`--read-only` anywhere. Confirmed fixed in this session's real container run above —
the identical command without this env var reproduces the crash.

## What this module does not do

Mirrors `adapters/cpp/fuzzing.py::run_libfuzzer_campaign`'s own boundary: it does not
build the target image (an already-pinned `ContainerJailPolicy.image` is required),
and it does not decide what a `Finding` looks like — `SemgrepMatch`/`SemgrepScanReport`
(`adapters/semgrep/parser.py`) are the raw, structural shape; `workers.static_analysis.
dispatch` is where redaction (`orchestrator.redaction.redact_sanitizer_report`) and
`Finding` construction happen, the same layering FUZZ uses.
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, replace
from pathlib import Path

from packages.sandbox.container import ContainerJail, ContainerJailPolicy

from .errors import ToolchainError, require_pinned
from .parser import SemgrepScanReport, parse_semgrep_json

__all__ = ["SemgrepRunResult", "run_semgrep_scan"]

#: Bytes of matched-line context read back from the checked-out source per match,
#: before any redaction. Generous for a handful of matched lines, far short of
#: `Finding.code_slice`'s own 20000-char field ceiling (`missions/models.py`) once
#: `orchestrator.redaction.redact_sanitizer_report` and truncation are applied on top
#: by the caller.
_MAX_SNIPPET_CHARS = 4000

#: How many lines of leading/trailing context to include around a match's own
#: start/end line — 0 keeps the snippet to exactly the matched span, which is what
#: every vendored rule in `adapters/semgrep/rules/` matches on a single call
#: expression, not a multi-statement block.
_SNIPPET_CONTEXT_LINES = 0


@dataclass(frozen=True, slots=True)
class SemgrepRunResult:
    """What `run_semgrep_scan` hands back — the parsed report plus run metadata
    `workers.static_analysis.dispatch` needs for `StageToolRun` (tool version,
    image digest, ruleset version) and for deciding `ExecutorResult.outcome`."""

    report: SemgrepScanReport
    image_digest: str
    ruleset_version: str
    exit_code: int
    limit_hit: str
    runtime_seconds: float
    stdout_truncated: bool
    stderr_excerpt: str


def _read_ruleset_version(rules_dir: Path) -> str:
    version_file = rules_dir / "VERSION"
    if not version_file.is_file():
        return "unknown"
    return version_file.read_text(encoding="utf-8", errors="replace").strip() or "unknown"


def _read_snippet(source_root: Path, relative_path: str, start_line: int, end_line: int) -> str:
    """Read the matched span directly off the checked-out source (still host-
    readable inside `sandbox.root` before the jail tears down) — see this module's
    docstring for why Semgrep's own `extra.lines` is never trusted instead.
    Never raises: a vanished file, an out-of-range line, or a path that would
    resolve outside `source_root` (defence against a crafted target repo naming a
    match at a path like `../../etc/passwd`) all return an empty snippet rather than
    failing the whole scan over one cosmetic field."""
    try:
        resolved_root = source_root.resolve(strict=True)
        candidate = (source_root / relative_path).resolve()
        candidate.relative_to(resolved_root)
        if not candidate.is_file():
            return ""
        lines = candidate.read_text(encoding="utf-8", errors="replace").splitlines()
    except (OSError, ValueError):
        return ""

    lo = max(1, start_line - _SNIPPET_CONTEXT_LINES) - 1
    hi = min(len(lines), end_line + _SNIPPET_CONTEXT_LINES)
    snippet = "\n".join(lines[lo:hi])
    return snippet[:_MAX_SNIPPET_CHARS]


def run_semgrep_scan(
    source_dir: Path | str,
    policy: ContainerJailPolicy,
    *,
    rules_dir: Path | str,
    mission_ref: str = "analyze",
) -> SemgrepRunResult:
    """Copy `source_dir` and the vendored ruleset into a fresh `ContainerJail`, run
    Semgrep offline against them, and return the parsed, snippet-enriched result.

    Raises `adapters.semgrep.errors.ToolchainError` for a caller-supplied-argument
    problem (missing source/ruleset directory, unpinned image) — a configuration
    fault, not a per-mission one. `packages.sandbox.errors.JailError` (raised by
    `ContainerJail`/`sandbox.run` when the container itself cannot start) is
    deliberately NOT caught here — mirrors `run_libfuzzer_campaign`'s own boundary;
    `workers.static_analysis.dispatch`'s executor is where that becomes an
    `infra_failure` result, exactly like `workers/fuzzing/dispatch.py`'s.
    """
    started = time.monotonic()
    image = require_pinned(policy.image)
    source = Path(source_dir).resolve()
    if not source.is_dir():
        raise ToolchainError(f"source directory does not exist: {source}")
    rules_root = Path(rules_dir).resolve()
    if not rules_root.is_dir():
        raise ToolchainError(f"vendored ruleset directory does not exist: {rules_root}")
    ruleset_version = _read_ruleset_version(rules_root)

    with ContainerJail.create(policy, mission_ref=mission_ref) as sandbox:
        target_source = sandbox.root / "source"
        shutil.copytree(
            source,
            target_source,
            ignore=shutil.ignore_patterns("build", "build-*", ".git"),
        )
        target_rules = sandbox.root / "rules"
        shutil.copytree(rules_root, target_rules)

        scan = sandbox.run(
            [
                "semgrep",
                "--config",
                "/workspace/rules",
                "--json",
                "--quiet",
                "--metrics=off",
                "--disable-version-check",
                "/workspace/source",
            ]
        )

        report = parse_semgrep_json(scan.stdout, scan_root="/workspace/source")
        enriched = tuple(
            replace(
                match,
                code_snippet=_read_snippet(
                    target_source, match.file_path, match.start_line, match.end_line
                ),
            )
            for match in report.matches
        )
        report = replace(report, matches=enriched)

    return SemgrepRunResult(
        report=report,
        image_digest=image,
        ruleset_version=ruleset_version,
        exit_code=scan.exit_code,
        limit_hit=str(scan.limit_hit),
        runtime_seconds=time.monotonic() - started,
        stdout_truncated=scan.stdout_truncated,
        stderr_excerpt=scan.stderr[-2000:] if scan.stderr else "",
    )
