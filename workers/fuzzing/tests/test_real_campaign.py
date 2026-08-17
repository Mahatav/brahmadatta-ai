"""A REAL (not mocked) libFuzzer campaign against pktcfg's seeded crash — #189.

Issue #189's own gap statement: "Every existing test mocks `run_fuzzing_stage` rather
than running a real campaign." `test_run_fuzzing.py` in this same directory
`monkeypatch.setattr("workers.fuzzing.run.run_libfuzzer_campaign", fake_run)` in both of
its tests — useful for `FuzzingOutcome`'s own shaping logic, but it cannot and does not
prove a real container can build and run the harness. This file is the other half: no
monkeypatch, no fake result — `run_fuzzing_stage` calls the real
`adapters.cpp.fuzzing.run_libfuzzer_campaign`, which calls the real
`packages.sandbox.container.ContainerJail`, which runs the real
`infrastructure/compose/images/fuzz-toolchain.Dockerfile` image via a real `docker run`
with the full D-024 flag set (`--network none --cap-drop ALL --user 10001:10001
--read-only ...| unchanged from what `ContainerJailPolicy` always emits).

Opt-in and skip-loud, not part of the default `pytest` collection budget
------------------------------------------------------------------------
Building the image (~20s first run, cached after) and running a real fuzzing campaign is
exactly the kind of "real infra, real time" check `.github/workflows/ci.yml`'s own header
comment describes for `finale-egress-evidence.sh`: "the right test and the wrong cadence"
for every PR. This mirrors that precedent rather than inventing a new one: skipped unless
BOTH a container runtime is reachable (same `needs_docker` shape as
`packages/sandbox/tests/test_container_jail.py`) AND the operator opts in explicitly,
because unlike that file's `PROBE_IMAGE` (a pre-existing pinned `python` image, pulled in
under a second), this test's first run also builds a ~400 MB toolchain image from
upstream Ubuntu package mirrors — real network time on a cold cache, not appropriate as a
silent default for every `pytest` invocation in this repository.

    BRAHMADATTA_RUN_REAL_FUZZ_CAMPAIGN=1 pytest workers/fuzzing/tests/test_real_campaign.py -v -s

Rerunning is fast: the image build is cached by Docker's layer cache and this test's own
session fixture reuses one built image across every test in the file.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from packages.sandbox.container import ContainerJailPolicy
from workers.fuzzing.run import run_fuzzing_stage

REPO_ROOT = Path(__file__).resolve().parents[3]
BUILD_SCRIPT = REPO_ROOT / "infrastructure" / "scripts" / "build-fuzz-image.sh"
PKTCFG_SOURCE = REPO_ROOT / "demo" / "repositories" / "pktcfg"

RUNTIME = "docker"
HAS_RUNTIME = shutil.which(RUNTIME) is not None


def _daemon_responds() -> bool:
    if not HAS_RUNTIME:
        return False
    try:
        return (
            subprocess.run([RUNTIME, "info"], capture_output=True, timeout=10).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


HAS_DOCKER = _daemon_responds()
OPTED_IN = os.environ.get("BRAHMADATTA_RUN_REAL_FUZZ_CAMPAIGN") == "1"

needs_real_fuzz_run = pytest.mark.skipif(
    not (HAS_DOCKER and OPTED_IN),
    reason=(
        "real fuzzing-campaign test skipped: needs a reachable docker daemon AND "
        "BRAHMADATTA_RUN_REAL_FUZZ_CAMPAIGN=1 (opt-in — this builds a real image and runs "
        "a real container). Not silently passed, not silently dropped: "
        f"HAS_DOCKER={HAS_DOCKER} OPTED_IN={OPTED_IN}."
    ),
)


@pytest.fixture(scope="session")
def fuzz_image() -> str:
    """Build `infrastructure/compose/images/fuzz-toolchain.Dockerfile` for real via the
    same script an operator runs, and return the pinned `name@sha256:...` digest
    `build-fuzz-image.sh` resolves it to. Session-scoped so every test in this file (were
    more than one to be added later) reuses the same build.
    """
    result = subprocess.run(
        [str(BUILD_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        pytest.fail(
            "build-fuzz-image.sh failed — the fuzzing-toolchain image could not be "
            f"built:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    digest = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    if "@sha256:" not in digest:
        pytest.fail(
            f"build-fuzz-image.sh did not print a pinned digest on stdout; got {digest!r}. "
            f"stderr:\n{result.stderr}"
        )
    return digest


@needs_real_fuzz_run
def test_real_libfuzzer_campaign_finds_the_seeded_heap_overflow(fuzz_image: str) -> None:
    """The end-to-end path #189 exists to prove: a real pinned image, run through the
    real `ContainerJail`, building and executing pktcfg's actual libFuzzer harness,
    genuinely finds the seeded heap-buffer-overflow — no mock, no fixture standing in for
    a crash.
    """
    policy = ContainerJailPolicy(
        image=fuzz_image,
        memory_mb=2048,
        cpu_limit=2.0,
        wall_clock_seconds=180.0,
    )

    outcome = run_fuzzing_stage(
        "test-189-real-campaign",
        PKTCFG_SOURCE,
        policy=policy,
        budget_seconds=90,
    )

    assert outcome.mode == "LIVE_CAMPAIGN", (
        f"expected a real campaign, got mode={outcome.mode!r} "
        f"failure={outcome.failure.as_dict() if outcome.failure else None}"
    )
    assert outcome.toolchain is not None
    assert outcome.toolchain.image == fuzz_image
    assert outcome.toolchain.as_dict()["pinned"] is True
    assert outcome.executions > 0, "libFuzzer reported zero executions"

    # The actual acceptance criterion: a real crash, on the real seeded defect.
    assert outcome.unique_crashes >= 1, (
        "no crash found against pktcfg's seeded heap-buffer-overflow — either the "
        "toolchain regressed or the campaign never reached the defect"
    )
    assert outcome.artifact_refs, "a crash was reported but no artifact path was recorded"
    assert "address" in outcome.sanitizers
    assert "AddressSanitizer: heap-buffer-overflow" in outcome.run_output_excerpt, (
        "expected ASan's own heap-buffer-overflow summary line in the captured output"
    )
