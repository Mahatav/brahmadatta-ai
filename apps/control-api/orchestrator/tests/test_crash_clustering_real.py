"""#30's acceptance criterion, exercised against a REAL multi-crash run: "Tested
against a real multi-crash run."

Every `SanitizerFinding` this file asserts on comes from a real subprocess -- either
pktcfg's real ASan/UBSan-instrumented `pktcfg_replay` binary, built for real from
`demo/repositories/pktcfg` by the same `adapters.cpp.pipeline.run_variant` +
`packages.sandbox.Jail` pair `workers/replay/run.py` uses in production, or (for the
one genuinely distinct crash class, see below) a standalone `-fsanitize=undefined`
probe compiled and run for real by this test. Nothing here hand-writes a sanitizer
report string.

## Why the "same root cause, many raw crashes" side uses crafted PKTC packets rather
than a real libFuzzer campaign

`adapters.cpp.fuzzing.run_libfuzzer_campaign` runs the harness once and libFuzzer's
own default behaviour is to abort at the first crash it finds -- this project's
harness invocation (`run_argv` in that module) does not pass `-keep_going` or
`-fork`, so one campaign realistically discovers at most one unique crash today (see
`.project/decisions.md`, #30's entry). Rather than fabricate a multi-crash campaign
result that does not reflect what the pipeline can actually produce, this test
instead replays several distinct, genuinely crash-triggering byte sequences directly
through the same built binary -- the same relationship a real corpus of many crashing
inputs (from retried campaigns, a future `-fork`-mode run, or a stored crash corpus
replayed in batch) would have to `record_finding`'s clustering. What #30 changes is
downstream of "a crash happened": `_fingerprint`'s stack signature and `Finding.
crash_count` -- and that is exactly what this test proves against real crash bytes.

## Why the "genuinely distinct root cause" side does not use a second pktcfg bug

`demo/repositories/pktcfg` is a controlled fixture with exactly one seeded defect
(its own module header on every source file: "It contains a SEEDED heap-buffer-
overflow on purpose"; confirmed directly by reading `src/decode.c`, `src/parse.c`,
`src/config.c` -- no second real memory-safety bug exists to crash it with, and
adding one would mean mutating a shared demo fixture other work depends on (the
seeded git-history/bisect answer, #5), out of this task's scope). This test instead
follows the exact precedent `adapters/cpp/tests/test_sanitizer.py` already
established for its own second fixture ("Captured from a minimal signed-overflow
probe (`cc -fsanitize=undefined`)") -- except captured fresh, in-process, rather than
hand-pasted, so it is a real report from a real compiler on this machine, not a
string that could silently drift from what `-fsanitize=undefined` actually emits.
"""

from __future__ import annotations

import shutil
import subprocess
import textwrap
from datetime import UTC, datetime
from pathlib import Path

import pytest

from adapters.cpp.pipeline import run_reproducer, run_variant
from adapters.cpp.sanitizer import parse_sanitizer_output
from adapters.cpp.variants import Variant, spec_for
from contracts.enums import MissionState
from missions.models import Finding, Mission
from orchestrator import findings
from orchestrator.tests.conftest import TRACE, walk_to
from packages.sandbox import Jail, JailPolicy
from workers.fuzzing.dispatch import _finding_kwargs_from_sanitizer

pytestmark = pytest.mark.django_db(transaction=True)

REPO_ROOT = Path(__file__).resolve().parents[4]
PKTCFG_SOURCE = REPO_ROOT / "demo" / "repositories" / "pktcfg"
_NOW = datetime.now(UTC)

needs_toolchain = pytest.mark.skipif(
    not PKTCFG_SOURCE.is_dir()
    or shutil.which("cmake") is None
    or shutil.which("ctest") is None
    or shutil.which("cc") is None,
    reason="demo/repositories/pktcfg or the local C toolchain (cmake/ctest/cc) is "
    "not available in this checkout",
)


def _pktc_packet(name: bytes, value: bytes) -> bytes:
    """Build one real, well-formed PKTC packet with a single entry -- same layout
    `demo/repositories/pktcfg/tests/packet_builder.h` builds for the target's own
    C tests, reimplemented here in Python so the test body can craft many distinct
    byte sequences without shelling out. `flags=0` (unescaped): the seeded defect
    (`src/decode.c`'s own header comment) fires on a *literal* tab byte in the value
    regardless of the escaped flag -- `pkt_decode_into`'s `if (c == '\\t')` branch is
    unconditional.
    """
    assert 1 <= len(name) <= 63
    assert len(value) <= 0xFFFF
    header = b"PKTC" + bytes([1, 1, 0, 0])
    entry_header = bytes([len(name), 0, len(value) & 0xFF, (len(value) >> 8) & 0xFF])
    return header + entry_header + name + value


#: Five genuinely distinct raw byte sequences -- different names, different values,
#: different tab positions and counts -- that all reach the same root cause: the
#: literal-tab length mismatch between `pkt_decoded_length` and `pkt_decode_into`.
#:
#: Verified directly (not assumed) that all five make the fault land *inside*
#: `emit_tab` itself rather than a few bytes later, in the plain byte-copy line of
#: `pkt_decode_into`: since `pkt_decoded_length` only undercounts by
#: `PKT_TAB_WIDTH - 1` bytes per literal tab, whether the resulting out-of-bounds
#: write is observed inside `emit_tab`'s own write loop or on a later ordinary byte
#: depends on exactly how much buffer headroom is left when each tab is expanded --
#: an incidental fact about *where* the fault is first observed, not a different
#: root cause. A value like `"\tfast"` (tab first, four ordinary bytes after, in a
#: 6-byte buffer) manifests the overflow two bytes later, in `pkt_decode_into`'s
#: generic copy line -- a real illustration of exactly why a naive crash-site-only
#: fingerprint under-clusters, and exactly the kind of noise `_stack_signature`
#: exists to average over. Avoided here by keeping a tab as the last byte written
#: (or followed only by more tabs), which reliably keeps the fault inside
#: `emit_tab` -- the shape a real fuzzer's discoveries of this bug overwhelmingly
#: take too (`crash/crash-literal-tab.bin`, `_REAL_ASAN_CAPTURE` in
#: `test_fuzz_executor.py`, both `emit_tab`).
_SAME_ROOT_CAUSE_PACKETS = [
    _pktc_packet(b"columns", b"a\tb"),
    _pktc_packet(b"mode", b"fast\t"),
    _pktc_packet(b"x", b"12\t34\t56"),
    _pktc_packet(b"a-much-longer-key", b"\t"),
    _pktc_packet(b"k", b"z" * 40 + b"\t"),
]


def _real_ubsan_finding(tmp_path: Path):
    """Compile and run a minimal `-fsanitize=undefined` probe for real, and
    structurally parse its own real crash report. A wholly separate binary from
    pktcfg -- proves the "distinct root cause" side of clustering against a report
    this test did not hand-write, mirroring `adapters/cpp/tests/test_sanitizer.py`'s
    own "captured from a minimal signed-overflow probe" fixture, captured fresh here
    instead of pasted.
    """
    probe_source = tmp_path / "overflow_probe.c"
    probe_source.write_text(
        textwrap.dedent(
            """\
            int add(int a, int b) { return a + b; }
            int main(void) {
                volatile int x = 2147483647;
                volatile int y = 1;
                return add(x, y);
            }
            """
        )
    )
    probe_binary = tmp_path / "overflow_probe"
    compile_result = subprocess.run(
        ["cc", "-fsanitize=undefined", "-g", "-O0", str(probe_source), "-o", str(probe_binary)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert compile_result.returncode == 0, (
        f"probe failed to compile: {compile_result.stderr}"
    )

    run_result = subprocess.run(
        [str(probe_binary)], capture_output=True, text=True, timeout=10
    )
    captured = run_result.stdout + "\n" + run_result.stderr
    parsed = parse_sanitizer_output(captured)
    assert parsed, f"expected a real UBSAN report from the probe, got: {captured!r}"
    return parsed[0]


@pytest.fixture(scope="module")
def _pktcfg_replay_binary(tmp_path_factory) -> Path:
    """Build pktcfg's real ASan/UBSan-instrumented `pktcfg_replay` binary once,
    exactly the way `workers/replay/run.py::run_replay_stage` does in production
    (`run_variant(source, jail, Variant.ASAN_UBSAN)`), and hand back a binary path
    plus the still-open jail it lives in. Module-scoped: the build itself is not what
    #30 is testing, and it is the slow part.
    """
    workspace = tmp_path_factory.mktemp("crash-clustering-workspace")
    spec = spec_for(Variant.ASAN_UBSAN)
    policy = JailPolicy(memory_bytes=spec.min_jail_memory_bytes)
    jail_cm = Jail.create(policy, parent=workspace)
    jail = jail_cm.__enter__()
    build = run_variant(PKTCFG_SOURCE, jail, Variant.ASAN_UBSAN)
    binary = build.build_dir / "pktcfg_replay"
    assert binary.is_file(), f"pktcfg_replay was not built at {binary}"
    yield jail, binary, spec
    jail_cm.__exit__(None, None, None)


@pytest.mark.slow
@needs_toolchain
def test_many_raw_crashes_from_the_same_root_cause_cluster_into_one_finding_with_an_accurate_count(
    mission: Mission, tmp_path: Path, _pktcfg_replay_binary
) -> None:
    jail, binary, spec = _pktcfg_replay_binary
    walk_to(mission, MissionState.STRESS_TEST)

    crash_dir = tmp_path / "crashes"
    crash_dir.mkdir()

    finding_rows: list[Finding] = []
    for i, packet in enumerate(_SAME_ROOT_CAUSE_PACKETS):
        crash_file = crash_dir / f"crash-{i}.bin"
        crash_file.write_bytes(packet)

        result = run_reproducer(jail, binary, (str(crash_file), "1"), spec=spec)
        assert result.findings, (
            f"crash-{i}.bin did not crash the real ASan-instrumented binary: "
            f"exit_code={result.exit_code} stderr={result.captured_stderr!r}"
        )
        sanitizer_finding = result.findings[0]
        assert sanitizer_finding.function == "emit_tab"
        assert sanitizer_finding.kind == "heap-buffer-overflow"

        kwargs = _finding_kwargs_from_sanitizer(sanitizer_finding)
        kwargs["detected_at"] = _NOW
        row = findings.record_finding(mission.id, trace_id=TRACE, **kwargs)
        finding_rows.append(row)

    # The actual acceptance criterion: five genuinely distinct raw crash inputs, one
    # Finding row, an accurate cluster count.
    ids = {row.id for row in finding_rows}
    assert len(ids) == 1, f"expected one clustered finding, got {len(ids)} distinct rows"
    assert Finding.objects.filter(mission=mission).count() == 1

    clustered = Finding.objects.get(mission=mission)
    assert clustered.crash_count == len(_SAME_ROOT_CAUSE_PACKETS)
    assert clustered.function == "emit_tab"
    assert clustered.file_path == "decode.c"
    assert clustered.line == 43


@pytest.mark.slow
@needs_toolchain
def test_a_genuinely_distinct_crash_gets_its_own_finding_and_does_not_join_the_cluster(
    mission: Mission, tmp_path: Path, _pktcfg_replay_binary
) -> None:
    jail, binary, spec = _pktcfg_replay_binary
    walk_to(mission, MissionState.STRESS_TEST)

    # First: the same-root-cause cluster from the other test, replayed here too, so
    # this test is self-contained rather than depending on execution order.
    crash_dir = tmp_path / "crashes"
    crash_dir.mkdir()
    for i, packet in enumerate(_SAME_ROOT_CAUSE_PACKETS[:3]):
        crash_file = crash_dir / f"crash-{i}.bin"
        crash_file.write_bytes(packet)
        result = run_reproducer(jail, binary, (str(crash_file), "1"), spec=spec)
        assert result.findings
        kwargs = _finding_kwargs_from_sanitizer(result.findings[0])
        kwargs["detected_at"] = _NOW
        findings.record_finding(mission.id, trace_id=TRACE, **kwargs)

    # Then: a real, distinct crash class (see this module's docstring for why this
    # is a standalone UBSAN probe rather than a second pktcfg bug).
    distinct = _real_ubsan_finding(tmp_path)
    distinct_kwargs = _finding_kwargs_from_sanitizer(distinct)
    distinct_kwargs["detected_at"] = _NOW
    distinct_row = findings.record_finding(mission.id, trace_id=TRACE, **distinct_kwargs)

    assert Finding.objects.filter(mission=mission).count() == 2

    clustered = Finding.objects.get(mission=mission, function="emit_tab")
    assert clustered.crash_count == 3
    assert clustered.fingerprint != distinct_row.fingerprint

    distinct_row.refresh_from_db()
    assert distinct_row.crash_count == 1
    assert distinct_row.tool == "UNDEFINED_BEHAVIOUR_SANITIZER"
