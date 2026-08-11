"""Sanitizer report parsing, pinned against real captured ASan/UBSan transcripts."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from adapters.cpp.pipeline import run_reproducer, run_variant
from adapters.cpp.sanitizer import parse_sanitizer_output
from adapters.cpp.variants import Variant, spec_for
from packages.sandbox import Jail, JailPolicy

# Captured verbatim from `./build-asan/pktcfg_replay crash/crash-literal-tab.bin 5` during
# development (AppleClang 21 / macOS arm64). Frame addresses vary by run; the grammar this
# parser depends on — the ERROR header, numbered `#N` frames, and the SUMMARY line — does
# not.
_REAL_ASAN_CAPTURE = """\
==78383==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x6020000000f4 at pc 0x000102ac8cf8 bp 0x00016d339b20 sp 0x00016d339b18
WRITE of size 1 at 0x6020000000f4 thread T0
    #0 0x000102ac8cf4 in emit_tab decode.c:43
    #1 0x000102ac88f0 in pkt_decode_into decode.c:148
    #2 0x000102ac6afc in pkt_parse parse.c:126
    #3 0x000102ac9c28 in pktcfg_fuzz_one_input fuzz_entry.c:26
    #4 0x000102ac5628 in main pktcfg_replay.c:68

0x6020000000f4 is located 0 bytes after 4-byte region [0x6020000000f0,0x6020000000f4)
allocated by thread T0 here:
    #0 0x000103341164 in malloc+0x78 (libclang_rt.asan_osx_dynamic.dylib:arm64e+0x41164)
    #1 0x000102ac6898 in pkt_parse parse.c:120

SUMMARY: AddressSanitizer: heap-buffer-overflow decode.c:43 in emit_tab
"""

# Captured from a minimal signed-overflow probe (`cc -fsanitize=undefined`), whose SUMMARY
# line has no "in <function>" suffix — the grammar this parser must fall back to the stack
# frame for.
_REAL_UBSAN_CAPTURE = """\
ub.c:2:31: runtime error: signed integer overflow: 2147483647 + 1 cannot be represented in type 'int'
    #0 0x000102d9063c in trigger ub.c:2
    #1 0x000102d90668 in main ub.c:4

SUMMARY: UndefinedBehaviorSanitizer: undefined-behavior ub.c:2:31
"""


def test_asan_heap_buffer_overflow_is_parsed_structurally() -> None:
    findings = parse_sanitizer_output(_REAL_ASAN_CAPTURE)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.tool == "ADDRESS_SANITIZER"
    assert finding.kind == "heap-buffer-overflow"
    assert finding.function == "emit_tab"
    assert finding.file == "decode.c"
    assert finding.line == 43
    assert finding.stack[0].function == "emit_tab"
    assert finding.stack[1].function == "pkt_decode_into"
    # The "allocated by" trace must not bleed into the primary stack.
    assert all(frame.function != "malloc" for frame in finding.stack)


def test_ubsan_falls_back_to_the_stack_frame_when_summary_has_no_function() -> None:
    findings = parse_sanitizer_output(_REAL_UBSAN_CAPTURE)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.tool == "UNDEFINED_BEHAVIOUR_SANITIZER"
    assert finding.function == "trigger"
    assert finding.file == "ub.c"
    assert finding.line == 2
    assert "signed integer overflow" in finding.message


@pytest.mark.parametrize(
    "clean_output",
    ["", "all 8 tests passed, no issues", "test_header: 13 checks, 0 failure(s)\n"],
)
def test_clean_output_produces_no_fabricated_finding(clean_output: str) -> None:
    """Injected violation check, inverted: confirm the parser does NOT invent a finding
    from ordinary output. A parser that always returns something on non-empty input would
    pass every positive test above by coincidence; this is what rules that out."""
    assert parse_sanitizer_output(clean_output) == ()


@pytest.mark.slow
def test_the_seeded_defect_is_confirmed_end_to_end(tmp_path: Path, pktcfg_source: Path) -> None:
    """The full pipeline, real cmake/clang, real crash file: builds ASAN_UBSAN, replays
    the committed reproducer, and confirms the exact finding documented in
    demo/repositories/pktcfg/README.md's defect table.

    Regression test for a real CI failure: this passed locally on macOS and failed on
    the Linux runner with `test_header` reporting a genuine (not phantom) CTest failure.
    Root cause, reproduced directly in a `ubuntu:24.04` container: `packages.sandbox.Jail`
    applies `RLIMIT_AS` from its policy unconditionally, `RLIMIT_AS` is not enforced on
    Darwin at all (masking the bug locally) but is on Linux, and AddressSanitizer's
    shadow-memory reservation (~28 TiB measured) blows through the jail's 2 GiB default —
    every sanitizer-instrumented process aborted at startup. See
    `adapters/cpp/variants.py`'s `MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS` for the full
    explanation; this is the fix, not a workaround around a still-broken policy."""
    spec = spec_for(Variant.ASAN_UBSAN)
    assert spec.min_jail_memory_bytes is not None, "ASAN_UBSAN must set a memory floor"
    policy = JailPolicy(memory_bytes=spec.min_jail_memory_bytes)
    with Jail.create(policy, parent=tmp_path) as jail:
        result = run_variant(pktcfg_source, jail, Variant.ASAN_UBSAN)
        # #27's other half: the baseline must stay green under sanitizers — no ctest
        # case trips the defect on its own.
        assert result.ctest.all_passed is True

        crash_file = pktcfg_source / "crash" / "crash-literal-tab.bin"
        # run_reproducer needs result.build_dir, which only exists while `jail` is open —
        # both calls stay inside this `with` block. See pipeline.py's module docstring.
        repro = run_reproducer(
            jail, result.build_dir / "pktcfg_replay", (str(crash_file), "5"), spec=spec
        )
    assert repro.crashed is True
    assert len(repro.findings) == 1
    finding = repro.findings[0]
    assert finding.tool == "ADDRESS_SANITIZER"
    assert finding.kind == "heap-buffer-overflow"
    assert finding.function == "emit_tab"
    # Basename, not exact match: a real toolchain's SUMMARY line embeds whatever path
    # the compiler was invoked with — Apple clang on macOS produced a bare `decode.c` in
    # earlier manual runs, gcc on Linux embeds the full absolute compile path
    # (`.../src/decode.c`). Both are legitimate; `finding.file` was never a documented
    # "bare filename" contract, only this test's original, single-platform assumption
    # was. Caught running the real suite in a Linux container (python:3.12-slim).
    assert finding.file is not None
    assert Path(finding.file).name == "decode.c", finding.file
    assert finding.line == 43


@pytest.mark.slow
def test_the_corrected_patch_produces_no_crash(tmp_path: Path, candidate_a_source: Path) -> None:
    """Injected-violation check on the fix itself: replaying the same crash input through
    the correctly patched binary must produce zero findings."""
    spec = spec_for(Variant.ASAN_UBSAN)
    assert spec.min_jail_memory_bytes is not None, "ASAN_UBSAN must set a memory floor"
    policy = JailPolicy(memory_bytes=spec.min_jail_memory_bytes)
    with Jail.create(policy, parent=tmp_path) as jail:
        result = run_variant(candidate_a_source, jail, Variant.ASAN_UBSAN)
        assert result.ctest.all_passed is True

        crash_file = candidate_a_source / "crash" / "crash-literal-tab.bin"
        repro = run_reproducer(
            jail, result.build_dir / "pktcfg_replay", (str(crash_file), "5"), spec=spec
        )
    assert repro.crashed is False
    assert repro.findings == ()


@pytest.mark.slow
@pytest.mark.skipif(
    sys.platform == "darwin",
    reason="RLIMIT_AS is not enforced on Darwin at all, so this regression cannot "
    "reproduce here — it is Linux-only by construction, the same way "
    "packages/sandbox/tests/test_jail.py::test_memory_limit_stops_an_allocator is. "
    "Confirmed reproducing in a ubuntu:24.04 Docker container while diagnosing it.",
)
def test_the_jails_default_memory_policy_cannot_run_asan(
    tmp_path: Path, pktcfg_source: Path
) -> None:
    """Injected violation, pinning the actual CI regression: build ASAN_UBSAN inside a
    `Jail` using the *default* `JailPolicy` (2 GiB `RLIMIT_AS`) rather than
    `MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS`. Every sanitizer-instrumented test process
    must fail to even start — proving the fix in the two tests above is load-bearing and
    not incidentally passing for some other reason."""
    with Jail.create(parent=tmp_path) as jail:  # no memory_bytes override — the bug
        result = run_variant(pktcfg_source, jail, Variant.ASAN_UBSAN)
    assert result.ctest.all_passed is False
    assert result.ctest.total == 8
    assert result.ctest.passed == 0, (
        "every test should fail to even start under the default 2 GiB RLIMIT_AS"
    )
    failure_output = " ".join(t.output for t in result.ctest.tests)
    assert "AddressSanitizer failed to allocate" in failure_output or "ulimit" in failure_output
