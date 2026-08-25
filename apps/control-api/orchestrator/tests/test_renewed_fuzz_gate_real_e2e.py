"""#40 real, non-mocked proof: renewed fuzzing against a real patched build.

Mirrors `orchestrator/tests/test_fuzz_to_verify_real_e2e.py` and
`workers/fuzzing/tests/test_real_campaign.py`'s own opt-in shape exactly — no
`campaign_runner=` injection, no `ScriptedRunner`: a real `git apply`, a real
`packages.sandbox.Jail`-driven `cmake`/`ctest`, and a real
`packages.sandbox.container.ContainerJail`-driven libFuzzer campaign
(`adapters.cpp.fuzzing.run_libfuzzer_campaign`) against the real
`infrastructure/compose/images/fuzz-toolchain.Dockerfile` image, run through
`orchestrator.verification.run_verification` end to end.

Two cases, both against the real demo target (`demo/repositories/pktcfg`):

* `candidate-a-correct-bounds-fix.patch` — the genuinely correct fix. Every gate,
  including the real renewed-fuzz campaign, must PASS: `Verified`.
* `candidate-d-overfit-single-input-fix.patch` (#40) — teaches the sizing pass about a
  literal tab, but only for the exact byte length of the one reproducer it was fit to.
  Passes COMPILE, REPRODUCER_ELIMINATED and REGRESSION_PRESERVED (the three-gate
  matrix this product shipped with before #40 would have called it `Verified`) — the
  renewed-fuzz campaign is what actually catches it, by rediscovering the same class
  of crash at a different literal-tab length, and the mission verdict must be
  `Rejected`, not `Verified`.

Opt-in and skip-loud, not part of the default `pytest` collection budget — same
`BRAHMADATTA_RUN_REAL_FUZZ_CAMPAIGN=1` gate as the two files above:

    BRAHMADATTA_RUN_REAL_FUZZ_CAMPAIGN=1 pytest \\
        orchestrator/tests/test_renewed_fuzz_gate_real_e2e.py -v -s
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from contracts.enums import GateStatus, Verdict
from contracts.verdict import derive_verdict
from orchestrator.tests.conftest import CANDIDATE_A, DEMO_ROOT
from orchestrator.verification import RenewedFuzzConfig, VerificationBaseline, run_verification
from packages.sandbox.container import ContainerJailPolicy

REPO_ROOT = Path(__file__).resolve().parents[4]
BUILD_SCRIPT = REPO_ROOT / "infrastructure" / "scripts" / "build-fuzz-image.sh"
DEMO_REPOSITORY = CANDIDATE_A.parents[1]
CRASH = DEMO_REPOSITORY / "crash" / "crash-literal-tab.bin"
CANDIDATE_D = DEMO_ROOT / "candidate-d-overfit-single-input-fix.patch"
BASELINE = VerificationBaseline(expected_regression_tests=8)

RUNTIME = "docker"
HAS_RUNTIME = shutil.which(RUNTIME) is not None


def _daemon_responds() -> bool:
    if not HAS_RUNTIME:
        return False
    try:
        return subprocess.run([RUNTIME, "info"], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


HAS_DOCKER = _daemon_responds()
OPTED_IN = os.environ.get("BRAHMADATTA_RUN_REAL_FUZZ_CAMPAIGN") == "1"

needs_real_fuzz_run = pytest.mark.skipif(
    not (HAS_DOCKER and OPTED_IN),
    reason=(
        "real renewed-fuzz gate test skipped: needs a reachable docker daemon AND "
        "BRAHMADATTA_RUN_REAL_FUZZ_CAMPAIGN=1 (opt-in — builds a real image and runs a "
        f"real container). HAS_DOCKER={HAS_DOCKER} OPTED_IN={OPTED_IN}."
    ),
)


@pytest.fixture(scope="module")
def fuzz_image() -> str:
    result = subprocess.run([str(BUILD_SCRIPT)], capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        pytest.fail(
            "build-fuzz-image.sh failed:\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    digest = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    if "@sha256:" not in digest:
        pytest.fail(f"build-fuzz-image.sh did not print a pinned digest; got {digest!r}")
    return digest


def _renewed_fuzz_config(image: str, *, budget_seconds: int = 120) -> RenewedFuzzConfig:
    return RenewedFuzzConfig(
        container_policy=ContainerJailPolicy(
            image=image,
            wall_clock_seconds=float(budget_seconds) + 180.0,
        ),
        budget_seconds=budget_seconds,
        mission_ref="renewed-fuzz-real-e2e",
    )


@needs_real_fuzz_run
@pytest.mark.skipif(shutil.which("cmake") is None, reason="cmake not installed")
@pytest.mark.skipif(shutil.which("ctest") is None, reason="ctest not installed")
@pytest.mark.skipif(not DEMO_REPOSITORY.is_dir(), reason="demo target not present")
def test_the_correct_patch_survives_a_real_renewed_fuzz_campaign(fuzz_image: str):
    """(a) A genuinely correct patch: every gate, including a real bounded libFuzzer
    campaign against its own real patched+sanitizer build, PASSes."""
    gates = run_verification(
        DEMO_REPOSITORY,
        CANDIDATE_A.read_text(),
        CRASH,
        BASELINE,
        renewed_fuzz=_renewed_fuzz_config(fuzz_image),
    )

    assert gates.compile.status is GateStatus.PASS, gates.compile.detail
    assert gates.reproducer_eliminated.status is GateStatus.PASS, gates.reproducer_eliminated.detail
    assert gates.regression_preserved.status is GateStatus.PASS, gates.regression_preserved.detail
    assert gates.renewed_fuzzing.status is GateStatus.PASS, gates.renewed_fuzzing.detail
    assert derive_verdict(gates) is Verdict.VERIFIED


@needs_real_fuzz_run
@pytest.mark.skipif(shutil.which("cmake") is None, reason="cmake not installed")
@pytest.mark.skipif(shutil.which("ctest") is None, reason="ctest not installed")
@pytest.mark.skipif(not DEMO_REPOSITORY.is_dir(), reason="demo target not present")
def test_an_overfit_patch_is_caught_by_a_real_renewed_fuzz_campaign(fuzz_image: str):
    """(b) The deliberately-bad patch: passes every pre-#40 gate (compile, the
    *original* reproducer, and regression — the literal-tab path has no unit test at
    baseline, see demo/repositories/pktcfg/README.md), because it special-cases the
    exact byte length of the one reproducer it was fit to. A real renewed-fuzz
    campaign against its own real patched build rediscovers the same bug class at a
    different length and the gate FAILs — flipping the verdict away from Verified."""
    assert CANDIDATE_D.is_file(), f"missing fixture: {CANDIDATE_D}"

    gates = run_verification(
        DEMO_REPOSITORY,
        CANDIDATE_D.read_text(),
        CRASH,
        BASELINE,
        renewed_fuzz=_renewed_fuzz_config(fuzz_image),
    )

    assert gates.compile.status is GateStatus.PASS, gates.compile.detail
    assert gates.reproducer_eliminated.status is GateStatus.PASS, (
        "candidate D should still eliminate the *original* reproducer — that is the "
        f"whole point of the overfit: {gates.reproducer_eliminated.detail}"
    )
    assert gates.regression_preserved.status is GateStatus.PASS, (
        "candidate D should still pass the regression suite — the literal-tab path "
        f"has no baseline unit test: {gates.regression_preserved.detail}"
    )
    assert gates.renewed_fuzzing.status is GateStatus.FAIL, (
        "a real renewed-fuzz campaign against candidate D's own patched build should "
        f"rediscover the literal-tab overflow at a different length: {gates.renewed_fuzzing.detail}"
    )
    assert derive_verdict(gates) is Verdict.REJECTED, (
        "three gates PASSing plus a real new crash from renewed fuzzing must still "
        "reject the candidate, not call it Verified"
    )
