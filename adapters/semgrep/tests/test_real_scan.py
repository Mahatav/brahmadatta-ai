"""A REAL (not mocked) Semgrep scan against `demo/repositories/pktcfg` (#22, D-144).

Mirrors `workers/fuzzing/tests/test_real_campaign.py`'s own shape and reasoning —
see that file's module docstring for the "opt-in and skip-loud" rationale, restated
here rather than re-derived. `test_parser.py` in this same directory proves the
parsing logic against real *captured* JSON; this file proves the whole path end to
end: `run_semgrep_scan` -> a real `ContainerJail` -> a real
`infrastructure/compose/images/analyze-toolchain.Dockerfile` image -> a real
`docker run` with the full D-024 flag set -> real Semgrep -> real findings against
`demo/repositories/pktcfg`'s real source.

    BRAHMADATTA_RUN_REAL_ANALYZE_SCAN=1 pytest adapters/semgrep/tests/test_real_scan.py -v -s
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from adapters.semgrep.run_semgrep import run_semgrep_scan
from packages.sandbox.container import ContainerJailPolicy

REPO_ROOT = Path(__file__).resolve().parents[3]
BUILD_SCRIPT = REPO_ROOT / "infrastructure" / "scripts" / "build-analyze-image.sh"
PKTCFG_SOURCE = REPO_ROOT / "demo" / "repositories" / "pktcfg"
RULES_DIR = REPO_ROOT / "adapters" / "semgrep" / "rules"

RUNTIME = "docker"
HAS_RUNTIME = shutil.which(RUNTIME) is not None


def _daemon_responds() -> bool:
    if not HAS_RUNTIME:
        return False
    try:
        return (
            subprocess.run([RUNTIME, "info"], capture_output=True, timeout=10).returncode == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


HAS_DOCKER = _daemon_responds()
OPTED_IN = os.environ.get("BRAHMADATTA_RUN_REAL_ANALYZE_SCAN") == "1"

needs_real_analyze_run = pytest.mark.skipif(
    not (HAS_DOCKER and OPTED_IN),
    reason=(
        "real Semgrep-scan test skipped: needs a reachable docker daemon AND "
        "BRAHMADATTA_RUN_REAL_ANALYZE_SCAN=1 (opt-in — this builds a real image and "
        f"runs a real container). HAS_DOCKER={HAS_DOCKER} OPTED_IN={OPTED_IN}."
    ),
)


@pytest.fixture(scope="session")
def analyze_image() -> str:
    result = subprocess.run([str(BUILD_SCRIPT)], capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        pytest.fail(
            "build-analyze-image.sh failed — the analyze-toolchain image could not be "
            f"built:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    digest = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    if "@sha256:" not in digest:
        pytest.fail(
            f"build-analyze-image.sh did not print a pinned digest on stdout; got "
            f"{digest!r}. stderr:\n{result.stderr}"
        )
    return digest


@needs_real_analyze_run
def test_real_semgrep_scan_finds_real_matches_in_pktcfg(analyze_image: str) -> None:
    """The end-to-end proof: a real pinned image, a real `--network none` container,
    genuinely finds the two real Semgrep matches this session confirmed exist in
    `demo/repositories/pktcfg` (`src/parse.c:114` memcpy, `src/parse.c:120` malloc
    arithmetic) — no mock, no fixture standing in for a scan.
    """
    policy = ContainerJailPolicy(
        image=analyze_image,
        memory_mb=1024,
        cpu_limit=2.0,
        wall_clock_seconds=120.0,
        extra_env={"HOME": "/tmp"},
    )

    result = run_semgrep_scan(
        PKTCFG_SOURCE, policy, rules_dir=RULES_DIR, mission_ref="test-22-real-scan"
    )

    assert result.report.ok, f"scan-level errors: {result.report.tool_errors}"
    assert result.report.tool_version == "1.173.0"
    assert result.image_digest == analyze_image
    assert len(result.report.scanned_files) == 7
    assert set(result.report.scanned_files) >= {"src/parse.c"}

    by_rule = {m.rule_id: m for m in result.report.matches}
    assert "brahmadatta-c-memcpy-review-bounds" in by_rule
    assert "brahmadatta-c-malloc-arithmetic-size" in by_rule

    memcpy_match = by_rule["brahmadatta-c-memcpy-review-bounds"]
    assert memcpy_match.file_path == "src/parse.c"
    assert memcpy_match.start_line == 114
    # Never the "requires login" placeholder Semgrep's OSS engine reports for
    # extra.lines — this must be the real matched source line, read off disk.
    assert "requires login" not in memcpy_match.code_snippet
    assert "memcpy(entry->name, name, name_len)" in memcpy_match.code_snippet

    malloc_match = by_rule["brahmadatta-c-malloc-arithmetic-size"]
    assert malloc_match.file_path == "src/parse.c"
    assert malloc_match.start_line == 120
    assert "malloc(need + 1)" in malloc_match.code_snippet

    # Rules that do NOT match this target are a true negative, not a bug — every
    # vendored rule loaded and ran; only two actually fired against real code.
    assert "brahmadatta-c-dangerous-string-copy" not in by_rule
    assert "brahmadatta-c-command-injection" not in by_rule


@needs_real_analyze_run
def test_real_scan_never_touches_the_network(analyze_image: str) -> None:
    """`ContainerJailPolicy.network` is hardcoded `"none"` regardless of what this
    test passes — this asserts the scan still completes successfully under it (no
    silent dependency on a registry fetch this adapter's own docstring claims does
    not exist)."""
    policy = ContainerJailPolicy(
        image=analyze_image,
        memory_mb=512,
        cpu_limit=1.0,
        wall_clock_seconds=60.0,
        extra_env={"HOME": "/tmp"},
    )
    assert policy.network == "none"  # not configurable — this is the whole point

    result = run_semgrep_scan(
        PKTCFG_SOURCE, policy, rules_dir=RULES_DIR, mission_ref="test-22-no-network"
    )
    assert result.report.ok
    assert result.exit_code == 0
