"""`adapters.semgrep.parser` — pure parsing logic, no Docker, no Django (#22, D-144).

Every fixture JSON shape here is drawn from real `semgrep --json` output this session
actually captured against `demo/repositories/pktcfg` with the vendored ruleset
(`adapters/semgrep/rules/c/dangerous-functions.yaml`) — see this file's own docstrings
for which real run each shape is copied from, rather than invented.
"""

from __future__ import annotations

import json
from typing import Any

from adapters.semgrep.parser import parse_semgrep_json

#: Copied verbatim (structure, not every byte) from a real
#: `docker run --network none --user 10001:10001 --cap-drop ALL --security-opt
#: no-new-privileges --read-only --tmpfs /tmp:size=64m -e HOME=/tmp
#: brahmadatta-analyze-toolchain@sha256:... semgrep --config /workspace/rules --json
#: --quiet --metrics=off /workspace/source` against `demo/repositories/pktcfg`, run in
#: this session — two real findings, `src/parse.c:114` (memcpy) and `src/parse.c:120`
#: (malloc arithmetic size). `extra.lines`/`extra.fingerprint` are the real literal
#: string Semgrep 1.173.0's OSS engine returns when not authenticated — see `parser.py`
#: module docstring for why neither is trusted.
_REAL_PKTCFG_OUTPUT: dict[str, Any] = {
    "version": "1.173.0",
    "results": [
        {
            "check_id": "workspace.rules.c.brahmadatta-c-memcpy-review-bounds",
            "path": "/workspace/source/src/parse.c",
            "start": {"line": 114, "col": 9, "offset": 3102},
            "end": {"line": 114, "col": 44, "offset": 3137},
            "extra": {
                "message": "memcpy()/memmove() call. Not a defect by itself...",
                "metadata": {
                    "cwe": "CWE-787",
                    "category": "security",
                    "confidence": "LOW",
                    "brahmadatta_category": "OTHER",
                    "brahmadatta_severity": "LOW",
                },
                "severity": "INFO",
                "fingerprint": "requires login",
                "lines": "requires login",
                "validation_state": "NO_VALIDATOR",
                "engine_kind": "OSS",
            },
        },
        {
            "check_id": "workspace.rules.c.brahmadatta-c-malloc-arithmetic-size",
            "path": "/workspace/source/src/parse.c",
            "start": {"line": 120, "col": 24, "offset": 3350},
            "end": {"line": 120, "col": 35, "offset": 3361},
            "extra": {
                "message": "malloc()/calloc() sized from an arithmetic expression...",
                "metadata": {
                    "cwe": "CWE-190",
                    "category": "security",
                    "confidence": "MEDIUM",
                    "brahmadatta_category": "INTEGER_OVERFLOW",
                    "brahmadatta_severity": "MEDIUM",
                },
                "severity": "WARNING",
                "fingerprint": "requires login",
                "lines": "requires login",
                "validation_state": "NO_VALIDATOR",
                "engine_kind": "OSS",
            },
        },
    ],
    "paths": {"scanned": [f"/workspace/source/{p}" for p in (
        "fuzz/pktcfg_fuzz.c",
        "include/pktcfg/pktcfg.h",
        "src/config.c",
        "src/decode.c",
        "src/fuzz_entry.c",
        "src/parse.c",
        "tools/pktcfg_replay.c",
    )]},
    "errors": [],
}

#: Real shape (structure) of a `semgrep --json` invocation against a missing/invalid
#: `--config` path, captured in this session: `errors` populated, `paths.scanned`
#: empty, process exit code still 0.
_REAL_CONFIG_ERROR_OUTPUT: dict[str, Any] = {
    "version": "1.173.0",
    "results": [],
    "errors": [
        {
            "code": 2,
            "level": "error",
            "type": "SemgrepError",
            "message": "unable to find a config; path `/nonexistent` does not exist",
        },
        {"code": 7, "level": "error", "type": "SemgrepError", "message": "invalid configuration file found"},
    ],
    "paths": {"scanned": []},
}


def test_real_pktcfg_output_parses_into_two_matches():
    report = parse_semgrep_json(
        json.dumps(_REAL_PKTCFG_OUTPUT), scan_root="/workspace/source"
    )

    assert report.ok is True
    assert report.tool_version == "1.173.0"
    assert len(report.scanned_files) == 7
    assert len(report.matches) == 2

    memcpy_match, malloc_match = report.matches
    assert memcpy_match.rule_id == "brahmadatta-c-memcpy-review-bounds"
    assert memcpy_match.file_path == "src/parse.c"  # scan_root stripped
    assert memcpy_match.start_line == 114
    assert memcpy_match.brahmadatta_category == "OTHER"
    assert memcpy_match.brahmadatta_severity == "LOW"
    assert memcpy_match.cwe == "CWE-787"

    assert malloc_match.rule_id == "brahmadatta-c-malloc-arithmetic-size"
    assert malloc_match.brahmadatta_category == "INTEGER_OVERFLOW"
    assert malloc_match.brahmadatta_severity == "MEDIUM"


def test_never_trusts_extra_lines_or_fingerprint():
    """The literal `"requires login"` string Semgrep's OSS engine returns for both
    fields must never leak into a parsed `SemgrepMatch` as if it were real content —
    see `parser.py`'s own module docstring."""
    report = parse_semgrep_json(
        json.dumps(_REAL_PKTCFG_OUTPUT), scan_root="/workspace/source"
    )
    for match in report.matches:
        assert match.code_snippet == ""  # filled in later, by run_semgrep.py, from disk
        assert "requires login" not in match.code_snippet


def test_config_error_with_nothing_scanned_is_not_ok():
    report = parse_semgrep_json(
        json.dumps(_REAL_CONFIG_ERROR_OUTPUT), scan_root="/workspace/source"
    )
    assert report.ok is False
    assert report.scanned_files == ()
    assert report.matches == ()
    assert len(report.tool_errors) == 2
    assert "unable to find a config" in report.tool_errors[0]


def test_partial_per_file_error_with_real_results_is_still_ok():
    """`paths.scanned` non-empty means real work happened — a per-file parse warning
    elsewhere in the tree must not discard the real findings that DID come back."""
    payload = dict(_REAL_PKTCFG_OUTPUT)
    payload["errors"] = [{"code": 3, "level": "warn", "type": "PartialParsing", "message": "could not fully parse one file"}]
    report = parse_semgrep_json(json.dumps(payload), scan_root="/workspace/source")

    assert report.ok is True
    assert len(report.matches) == 2
    assert len(report.tool_errors) == 1


def test_unparseable_stdout_is_reported_not_raised():
    report = parse_semgrep_json("not json at all {{{", scan_root="/workspace/source")
    assert report.ok is False
    assert report.matches == ()
    assert len(report.tool_errors) == 1
    assert "no parseable JSON" in report.tool_errors[0]


def test_empty_stdout_is_reported_not_raised():
    report = parse_semgrep_json("", scan_root="/workspace/source")
    assert report.ok is False
    assert report.matches == ()


def test_a_single_malformed_result_entry_is_skipped_not_fatal():
    payload = {
        "version": "1.173.0",
        "results": [
            {"check_id": "x.brahmadatta-c-dangerous-string-copy"},  # missing path/start/end
            _REAL_PKTCFG_OUTPUT["results"][0],
        ],
        "paths": {"scanned": ["/workspace/source/src/parse.c"]},
        "errors": [],
    }
    report = parse_semgrep_json(json.dumps(payload), scan_root="/workspace/source")
    assert report.ok is True
    assert len(report.matches) == 1
    assert report.matches[0].rule_id == "brahmadatta-c-memcpy-review-bounds"


def test_rule_id_extraction_strips_whatever_path_prefix_the_container_used():
    for prefix in ("workspace.rules.c", "adapters.semgrep.rules.c", "rules.c"):
        payload = {
            "version": "1.173.0",
            "results": [
                {
                    "check_id": f"{prefix}.brahmadatta-c-command-injection",
                    "path": "/workspace/source/tools/x.c",
                    "start": {"line": 1},
                    "end": {"line": 1},
                    "extra": {"message": "m", "severity": "ERROR", "metadata": {}},
                }
            ],
            "paths": {"scanned": ["/workspace/source/tools/x.c"]},
            "errors": [],
        }
        report = parse_semgrep_json(json.dumps(payload), scan_root="/workspace/source")
        assert report.matches[0].rule_id == "brahmadatta-c-command-injection"


def test_missing_metadata_falls_back_to_severity_derived_from_tool_severity():
    payload = {
        "version": "1.173.0",
        "results": [
            {
                "check_id": "rules.c.brahmadatta-c-dangerous-string-copy",
                "path": "/workspace/source/a.c",
                "start": {"line": 5},
                "end": {"line": 5},
                "extra": {"message": "m", "severity": "ERROR"},
            }
        ],
        "paths": {"scanned": ["/workspace/source/a.c"]},
        "errors": [],
    }
    report = parse_semgrep_json(json.dumps(payload), scan_root="/workspace/source")
    match = report.matches[0]
    assert match.brahmadatta_category == "OTHER"  # no metadata at all -> fallback
    assert match.brahmadatta_severity == "HIGH"  # ERROR -> HIGH fallback
