"""`orchestrator.redaction.redact_sanitizer_report` — #191 (SEC-50 per that issue's own
title; see `orchestrator/redaction.py`'s module comment on that number already being
assigned to a different, closed finding).

Mirrors `test_evidence_export.py`'s own methodology for `sanitize_detail`: poison a
realistic captured report with the two leak classes named by `FindingDetail.
sanitizer_report`'s own field docstring ("Absolute paths and environment values are
stripped before it reaches here"), assert they are gone, and assert the report is
still useful — crash type, stack frames, offending function all survive.
"""

from __future__ import annotations

import pytest

from orchestrator.redaction import redact_sanitizer_report

# A realistic ASan transcript, built on the same real captured grammar
# `adapters/cpp/tests/test_sanitizer.py` pins (`decode.c:43` in `emit_tab`), but with an
# absolute path standing in for what a developer's own local build would actually emit
# (an out-of-tree build directory bakes the *building* machine's absolute path into the
# binary's debug info) and an injected environment-variable line standing in for the
# `DATABASE_URL=postgresql://...`-shaped leak class SEC-44/45/48 already named.
_POISONED_ASAN_REPORT = """\
==78383==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x6020000000f4 at pc 0x000102ac8cf8 bp 0x00016d339b20 sp 0x00016d339b18
WRITE of size 1 at 0x6020000000f4 thread T0
DATABASE_URL=postgresql://svc_user:hunter2@db.internal:5432/missions
    #0 0x000102ac8cf4 in emit_tab /Users/someone/secret-project/pktcfg/src/decode.c:43
    #1 0x000102ac88f0 in pkt_decode_into /Users/someone/secret-project/pktcfg/src/decode.c:148
    #2 0x000102ac6afc in pkt_parse /Users/someone/secret-project/pktcfg/src/parse.c:126

0x6020000000f4 is located 0 bytes after 4-byte region [0x6020000000f0,0x6020000000f4)
allocated by thread T0 here:
    #0 0x000103341164 in malloc+0x78 (libclang_rt.asan_osx_dynamic.dylib:arm64e+0x41164)
    #1 0x000102ac6898 in pkt_parse /Users/someone/secret-project/pktcfg/src/parse.c:120

SUMMARY: AddressSanitizer: heap-buffer-overflow /Users/someone/secret-project/pktcfg/src/decode.c:43 in emit_tab
"""

_SECRET_SPANS = [
    "/Users/someone/secret-project",
    "DATABASE_URL=postgresql://svc_user:hunter2@db.internal:5432/missions",
    "hunter2",
]

_USEFUL_SPANS = [
    "AddressSanitizer: heap-buffer-overflow",
    "emit_tab",
    "pkt_decode_into",
    "pkt_parse",
    "SUMMARY: AddressSanitizer: heap-buffer-overflow",
    "0x6020000000f4",
]


def test_redacts_absolute_paths_and_env_assignment_lines():
    redacted = redact_sanitizer_report(_POISONED_ASAN_REPORT)
    for secret in _SECRET_SPANS:
        assert secret not in redacted, f"{secret!r} leaked through unredacted"


@pytest.mark.parametrize("useful", _USEFUL_SPANS)
def test_keeps_the_crash_signature_and_stack_frames(useful):
    redacted = redact_sanitizer_report(_POISONED_ASAN_REPORT)
    assert useful in redacted, f"{useful!r} was lost — over-redaction, not a fix"


def test_redaction_placeholders_are_present_where_the_secrets_were():
    redacted = redact_sanitizer_report(_POISONED_ASAN_REPORT)
    assert "[redacted absolute path]" in redacted
    assert "[redacted: line removed" in redacted


def test_empty_report_passes_through_unchanged():
    assert redact_sanitizer_report("") == ""


def test_benign_report_with_only_relative_paths_is_untouched():
    benign = (
        "SUMMARY: AddressSanitizer: heap-buffer-overflow decode.c:43 in emit_tab\n"
        "    #0 0x000102ac8cf4 in emit_tab decode.c:43\n"
    )
    assert redact_sanitizer_report(benign) == benign


def test_idempotent():
    once = redact_sanitizer_report(_POISONED_ASAN_REPORT)
    twice = redact_sanitizer_report(once)
    assert once == twice


def test_windows_style_absolute_path_is_also_redacted():
    report = (
        "SUMMARY: UndefinedBehaviorSanitizer: undefined-behavior in main\n"
        "    #0 0x1 in main C:\\Users\\someone\\secret-project\\src\\main.c:10\n"
    )
    redacted = redact_sanitizer_report(report)
    assert "secret-project" not in redacted
    assert "SUMMARY: UndefinedBehaviorSanitizer: undefined-behavior in main" in redacted
