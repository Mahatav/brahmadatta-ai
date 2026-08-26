"""Parse Semgrep's `--json` output into a structured, defensive shape.

## Why `extra.lines`/`extra.fingerprint` are never trusted

Checked directly in this session, not assumed: Semgrep 1.173.0's OSS engine reports
the *literal string* `"requires login"` for both `results[].extra.lines` (the
matched source snippet) and `results[].extra.fingerprint` when not authenticated
against Semgrep Cloud — this adapter never authenticates (`--metrics=off`, no
`SEMGREP_APP_TOKEN`, matching the project's "repository content never sent to an
external inference API" rule, and there is no network path to reach it from inside
`--network none` regardless). Relying on either field would silently store the
string `"requires login"` as if it were real matched code or a real fingerprint.
Neither is read here: `SemgrepMatch.code_snippet` starts empty and is filled in by
`run_semgrep.py` from the checked-out source directly (still host-readable inside
`ContainerJail.root` before the jail tears down), and `orchestrator.findings`'
fingerprint is computed by the caller from `(rule_id, file_path, start_line)`, the
same "derive it ourselves" pattern `workers/fuzzing/dispatch.py::_fingerprint`
already uses for ASan/UBSan findings.

## Why a nonzero process exit code is not the failure signal

Checked directly: Semgrep exits `0` even when real findings are present (any
severity, including `ERROR`) — `--json`'s own `errors` array, not the process exit
code, is where a genuine scan-level fault (an unreadable ruleset, a target path that
does not exist) is reported, also with exit code `0`. `parse_semgrep_json` treats
"nothing was scanned and at least one error was reported" as the actual failure
signal (`ok` on `SemgrepScanReport`); a per-file parse warning on an otherwise
successful scan (`paths.scanned` non-empty) is surfaced in `tool_errors` but does not
by itself make the scan a failure — the real findings from every file that DID parse
are not fabricated by discarding them over one bad file elsewhere in the tree.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

__all__ = ["SemgrepMatch", "SemgrepScanReport", "parse_semgrep_json"]

#: Every vendored rule id in `adapters/semgrep/rules/` carries this literal prefix
#: (see that directory's own YAML). Semgrep's `check_id` is namespaced by the
#: filesystem path it was loaded from (e.g. `workspace.rules.c.brahmadatta-c-...`
#: inside the container, `adapters.semgrep.rules.c.brahmadatta-c-...` from a host-side
#: run) — this regex strips whatever prefix that path produced and keeps only the
#: rule's own `id:` field, regardless of where the ruleset directory was mounted.
_RULE_ID_RE = re.compile(r"(brahmadatta-[a-z0-9-]+)$")

#: Semgrep's own three severities. `metadata.brahmadatta_severity` (set on every
#: vendored rule) is preferred when present; this is the fallback for a rule that
#: forgets to set it.
_SEVERITY_FALLBACK: dict[str, str] = {"ERROR": "HIGH", "WARNING": "MEDIUM", "INFO": "LOW"}


@dataclass(frozen=True, slots=True)
class SemgrepMatch:
    """One real Semgrep match, before `Finding` construction.

    `file_path` is relative to the scan root (`scan_root` prefix already stripped)
    — never an absolute container path, so nothing under `/workspace/...` ever
    reaches a `Finding.file_path` column. `code_snippet` starts empty; `run_semgrep.
    run_semgrep_scan` fills it in from the host-readable checkout before the jail
    tears down (see this module's docstring).
    """

    rule_id: str
    raw_check_id: str
    file_path: str
    start_line: int
    end_line: int
    message: str
    tool_severity: str
    cwe: str | None
    category: str
    brahmadatta_category: str
    brahmadatta_severity: str
    code_snippet: str = ""


@dataclass(frozen=True, slots=True)
class SemgrepScanReport:
    """The whole parsed scan: real matches, plus anything Semgrep itself reported as
    an error, plus whether the scan is trustworthy at all (`ok`)."""

    tool_version: str
    matches: tuple[SemgrepMatch, ...]
    scanned_files: tuple[str, ...]
    tool_errors: tuple[str, ...]
    ok: bool


def _strip_root(path: str, scan_root: str) -> str:
    if path.startswith(scan_root):
        return path[len(scan_root):].lstrip("/")
    return path


def _rule_id_from_check_id(check_id: str) -> str:
    match = _RULE_ID_RE.search(check_id)
    return match.group(1) if match else check_id


def _severity_for(metadata: dict, tool_severity: str) -> str:
    value = metadata.get("brahmadatta_severity")
    if isinstance(value, str) and value:
        return value.upper()
    return _SEVERITY_FALLBACK.get(tool_severity.upper(), "MEDIUM")


def _one_match(raw: dict, *, scan_root: str) -> SemgrepMatch | None:
    """Defensive: a single malformed result entry is skipped (returns `None`), never
    allowed to abort parsing the rest of a real scan's real findings."""
    try:
        check_id = str(raw["check_id"])
        path = str(raw["path"])
        start_line = int(raw["start"]["line"])
        end_line = int(raw["end"]["line"])
        extra = raw.get("extra") or {}
        message = str(extra.get("message") or "")
        tool_severity = str(extra.get("severity") or "INFO")
        metadata = extra.get("metadata") or {}
    except (KeyError, TypeError, ValueError):
        return None

    brahmadatta_category = metadata.get("brahmadatta_category")
    if not isinstance(brahmadatta_category, str) or not brahmadatta_category:
        brahmadatta_category = "OTHER"

    cwe = metadata.get("cwe")
    cwe_str = cwe if isinstance(cwe, str) and cwe else None

    category = metadata.get("category")
    category_str = category if isinstance(category, str) and category else "security"

    return SemgrepMatch(
        rule_id=_rule_id_from_check_id(check_id),
        raw_check_id=check_id,
        file_path=_strip_root(path, scan_root),
        start_line=start_line,
        end_line=max(end_line, start_line),
        message=message,
        tool_severity=tool_severity.upper(),
        cwe=cwe_str,
        category=category_str,
        brahmadatta_category=brahmadatta_category.upper(),
        brahmadatta_severity=_severity_for(metadata, tool_severity),
    )


def parse_semgrep_json(raw_stdout: str, *, scan_root: str) -> SemgrepScanReport:
    """Parse one `semgrep --json` stdout capture. Never raises: a completely
    unparseable payload (empty stdout, a crash before any JSON was printed) comes
    back as `SemgrepScanReport(ok=False, ...)` with the raw text (capped) recorded
    as the one `tool_errors` entry, exactly like `adapters.cpp.errors.StepFailure`
    reports an infrastructure-shaped failure rather than raising past its own
    executor.
    """
    if not raw_stdout:
        return SemgrepScanReport(
            tool_version="unknown",
            matches=(),
            scanned_files=(),
            tool_errors=("semgrep produced no output at all (empty stdout)",),
            ok=False,
        )
    try:
        payload = json.loads(raw_stdout)
    except json.JSONDecodeError:
        excerpt = raw_stdout[:2000]
        return SemgrepScanReport(
            tool_version="unknown",
            matches=(),
            scanned_files=(),
            tool_errors=(f"semgrep produced no parseable JSON output: {excerpt}",),
            ok=False,
        )

    tool_version = str(payload.get("version") or "unknown")
    scanned = tuple(
        _strip_root(str(p), scan_root) for p in (payload.get("paths") or {}).get("scanned", [])
    )
    raw_errors = payload.get("errors") or []
    tool_errors = tuple(
        str(err.get("message", err)) if isinstance(err, dict) else str(err) for err in raw_errors
    )

    # See this module's docstring: "nothing was scanned and at least one error was
    # reported" is the real failure signal, not the process exit code.
    ok = bool(scanned) or not tool_errors

    matches: list[SemgrepMatch] = []
    for raw in payload.get("results") or []:
        if not isinstance(raw, dict):
            continue
        parsed = _one_match(raw, scan_root=scan_root)
        if parsed is not None:
            matches.append(parsed)

    return SemgrepScanReport(
        tool_version=tool_version,
        matches=tuple(matches),
        scanned_files=scanned,
        tool_errors=tool_errors,
        ok=ok,
    )
