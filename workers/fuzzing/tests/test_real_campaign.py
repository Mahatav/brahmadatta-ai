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

#: Unlike `needs_real_fuzz_run`, this does NOT require the opt-in env var: it needs a
#: reachable docker daemon but never builds an image or runs a campaign — `docker run`
#: against a nonexistent image reference fails in well under a second, so this is exactly
#: the "cheap enough for a default `pytest` invocation" case the module docstring
#: describes `needs_real_fuzz_run` itself as NOT being.
needs_docker = pytest.mark.skipif(
    not HAS_DOCKER,
    reason=f"no {RUNTIME!r} daemon reachable on this host — skipped, not silently passed "
    f"(HAS_DOCKER={HAS_DOCKER})",
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


def _write_non_pktcfg_synthetic_target(root: Path, *, with_leak_harness: bool = False) -> None:
    """A tiny, real CMake C project with option/target names deliberately unrelated to
    pktcfg's — `SYNTH_SANITIZE`/`SYNTH_FUZZ`/`synth_fuzz`, mirroring exactly the
    dogfooding repro this session hit against `stb_image` (`STB_SANITIZE`/`STB_FUZZ`/
    `stb_fuzz`) and LAVA-M base64. Before #288's fix, `run_libfuzzer_campaign` always
    emitted the literal `-DPKTCFG_SANITIZE=ON -DPKTCFG_FUZZ=ON`, which CMake silently
    no-ops for a project that has no such option — `synth_fuzz` never gets built, and
    `cmake --build ... --target synth_fuzz` fails with "No rule to make target".

    `with_leak_harness` adds a second fuzz executable, `synth_leak_fuzz`, whose
    `LLVMFuzzerTestOneInput` unconditionally leaks 64 bytes on every single input,
    regardless of content — deterministic, real LeakSanitizer bait for #289's own
    regression proof, independent of #288's harness-generalization proof.
    """
    (root / "fuzz").mkdir(parents=True, exist_ok=True)
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "corpus").mkdir(parents=True, exist_ok=True)
    (root / "corpus" / "seed").write_bytes(b"hello")

    cmakelists = """
cmake_minimum_required(VERSION 3.16)
project(synth C)
set(CMAKE_C_STANDARD 11)

option(SYNTH_SANITIZE "Build with ASan/UBSan" OFF)
option(SYNTH_FUZZ "Build the libFuzzer harness(es)" OFF)

add_library(synth STATIC src/lib.c)
target_include_directories(synth PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/src)

if(SYNTH_SANITIZE)
  set(SYNTH_SAN_FLAGS -fsanitize=address,undefined -fno-omit-frame-pointer -g)
  target_compile_options(synth PUBLIC ${SYNTH_SAN_FLAGS})
  target_link_options(synth PUBLIC ${SYNTH_SAN_FLAGS})
endif()

if(SYNTH_FUZZ)
  target_compile_options(synth PRIVATE -fsanitize=fuzzer-no-link)

  add_executable(synth_fuzz fuzz/harness.c)
  target_link_libraries(synth_fuzz PRIVATE synth)
  target_compile_options(synth_fuzz PRIVATE -fsanitize=fuzzer)
  target_link_options(synth_fuzz PRIVATE -fsanitize=fuzzer)
"""
    if with_leak_harness:
        cmakelists += """
  add_executable(synth_leak_fuzz fuzz/leak_harness.c)
  target_link_libraries(synth_leak_fuzz PRIVATE synth)
  target_compile_options(synth_leak_fuzz PRIVATE -fsanitize=fuzzer)
  target_link_options(synth_leak_fuzz PRIVATE -fsanitize=fuzzer)
"""
    cmakelists += "endif()\n"
    (root / "CMakeLists.txt").write_text(cmakelists)

    (root / "src" / "lib.c").write_text(
        "#include <stddef.h>\n"
        "#include <stdint.h>\n"
        "int synth_process(const uint8_t *data, size_t size) {\n"
        "    (void)data;\n"
        "    return (int)size;\n"
        "}\n"
    )
    (root / "fuzz" / "harness.c").write_text(
        "#include <stddef.h>\n"
        "#include <stdint.h>\n"
        "int synth_process(const uint8_t *data, size_t size);\n"
        "int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {\n"
        "    synth_process(data, size);\n"
        "    return 0;\n"
        "}\n"
    )
    if with_leak_harness:
        (root / "fuzz" / "leak_harness.c").write_text(
            "#include <stddef.h>\n"
            "#include <stdint.h>\n"
            "#include <stdlib.h>\n"
            "int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {\n"
            "    (void)data;\n"
            "    (void)size;\n"
            "    // Deliberate, unconditional leak — real LeakSanitizer bait, on every\n"
            "    // single input, independent of #288's harness-generalization proof.\n"
            "    volatile void *leaked = malloc(64);\n"
            "    (void)leaked;\n"
            "    return 0;\n"
            "}\n"
        )


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


@needs_real_fuzz_run
def test_real_campaign_crash_bytes_survive_the_jails_own_teardown(
    fuzz_image: str, tmp_path
) -> None:
    """D-106's actual proof: the real crash-artifact bytes a live campaign discovers
    against pktcfg's seeded heap-buffer-overflow are still on disk, still readable,
    still non-empty, after `run_fuzzing_stage` returns — i.e. after
    `adapters.cpp.fuzzing.run_libfuzzer_campaign`'s own `ContainerJail` has already
    `shutil.rmtree`d its ephemeral worktree. This is the exact gap D-098/D-105 both
    hit live: before D-106, nothing survived this point for any caller to persist.
    """
    policy = ContainerJailPolicy(
        image=fuzz_image,
        memory_mb=2048,
        cpu_limit=2.0,
        wall_clock_seconds=180.0,
    )
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    outcome = run_fuzzing_stage(
        "test-d106-durable-copy",
        PKTCFG_SOURCE,
        policy=policy,
        budget_seconds=90,
        workspace_root=workspace_root,
    )

    assert outcome.mode == "LIVE_CAMPAIGN", (
        f"expected a real campaign, got mode={outcome.mode!r} "
        f"failure={outcome.failure.as_dict() if outcome.failure else None}"
    )
    assert outcome.unique_crashes >= 1, "no crash found against the seeded defect"
    assert outcome.durable_artifacts, (
        "a crash was found but no durable copy survived the ContainerJail's own "
        "teardown — the exact D-106 gap this test exists to prove closed"
    )

    for artifact in outcome.durable_artifacts:
        host_path = Path(artifact.host_path)
        assert host_path.is_file(), f"{host_path} does not exist after run_fuzzing_stage returned"
        assert host_path.stat().st_size > 0
        assert host_path.stat().st_size == artifact.size_bytes
        # Durable really does mean "outside the jail": it lives under workspace_root,
        # never under any path this test itself created inside a jail worktree.
        assert workspace_root.resolve() in host_path.resolve().parents


@needs_docker
@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG filed by qa-engineer against PR #192 (2026-08-17): "
        "packages.sandbox.errors.ContainerUnavailableError is not one of the exception "
        "types workers.fuzzing.run.run_fuzzing_stage catches (only StepFailure, "
        "AdapterError, ValueError from adapters.cpp.errors) — every OTHER failure mode "
        "in this module (unpinned image string, CONFIGURE/BUILD/PROBE_TOOLCHAIN step "
        "failure) is caught and shaped into a clean mode='NOT_RUN' FuzzingOutcome with a "
        "FuzzFailure, but a syntactically valid, digest-pinned SANDBOX_FUZZ_IMAGE that "
        "Docker cannot find or pull raises ContainerUnavailableError straight out of "
        "run_fuzzing_stage instead. This is a real, live operational failure mode (a "
        "stale pinned digest, a registry outage, a host that never ran "
        "build-fuzz-image.sh) — not a hypothetical. xfail(strict=True) so this flips to a "
        "hard failure (and needs un-xfailing) the moment it's fixed, rather than staying "
        "silently green."
    ),
)
def test_run_fuzzing_stage_reports_cleanly_when_the_pinned_image_cannot_be_found() -> None:
    """The image itself failing to build/pull is a distinct failure mode from everything
    `test_run_fuzzing.py`'s mocked `test_run_fuzzing_stage_reports_toolchain_blocker`
    covers (an unpinned image *string*, rejected by `require_pinned` before Docker is
    ever invoked) and from `test_libfuzzer_campaign_requires_a_digest_pinned_image`
    (same). A digest-pinned reference that is syntactically valid but does not exist in
    this daemon's image store/no registry can supply it is a real thing that happens
    (stale pin, registry outage, a fresh host that has not run `build-fuzz-image.sh`
    yet) — and #189/#192's whole point is that `SANDBOX_FUZZ_IMAGE` is a real, external,
    digest-pinned dependency now, not a hypothetical. This calls the real
    `run_fuzzing_stage` -> real `ContainerJail` -> a real `docker run` against a real
    daemon (no monkeypatching) with a made-up-but-validly-formatted digest, and checks
    that the failure is reported the same way every other failure in this module is:
    a shaped `FuzzingOutcome`, not an uncaught exception.
    """
    nonexistent_but_validly_pinned_image = "brahmadatta-fuzz-toolchain@sha256:" + "b" * 64
    policy = ContainerJailPolicy(
        image=nonexistent_but_validly_pinned_image,
        memory_mb=512,
        cpu_limit=1.0,
        wall_clock_seconds=30.0,
    )

    outcome = run_fuzzing_stage(
        "test-192-missing-image",
        PKTCFG_SOURCE,
        policy=policy,
        budget_seconds=10,
    )

    assert outcome.mode == "NOT_RUN"
    assert outcome.failure is not None
    assert outcome.ran is False


# ---------------------------------------------------------------------------------
# #288/#289 — the same real, non-mocked path as the pktcfg tests above, driven against
# a target that is deliberately NOT pktcfg (its own option/target names), the actual
# proof this session's four-target dogfooding run asked for.
# ---------------------------------------------------------------------------------


@needs_real_fuzz_run
def test_real_campaign_drives_a_non_pktcfg_target_and_reports_its_own_harness(
    fuzz_image: str, tmp_path: Path
) -> None:
    """#288's real, end-to-end regression proof: a target whose CMake cache options and
    fuzz target are named nothing like pktcfg's builds and runs successfully through the
    exact same `run_fuzzing_stage` entry point pktcfg uses, and the reported harness
    label matches what actually ran — never pktcfg's own default.

    Before this fix, this call would have silently forced `-DPKTCFG_SANITIZE=ON
    -DPKTCFG_FUZZ=ON` onto this project's configure step (which defines no such
    options), so `cmake --build ... --target synth_fuzz` would fail with "No rule to
    make target 'synth_fuzz'" — the exact `gmake: *** No rule to make target
    'pktcfg_fuzz'`-shaped failure this session's stb_image dogfooding run hit.
    """
    synthetic_source = tmp_path / "synth-target"
    synthetic_source.mkdir()
    _write_non_pktcfg_synthetic_target(synthetic_source)

    policy = ContainerJailPolicy(
        image=fuzz_image, memory_mb=1024, cpu_limit=2.0, wall_clock_seconds=90.0
    )

    outcome = run_fuzzing_stage(
        "test-288-non-pktcfg-target",
        synthetic_source,
        policy=policy,
        harness_target="synth_fuzz",
        harness_binary="synth_fuzz",
        cache_entries={"SYNTH_SANITIZE": "ON", "SYNTH_FUZZ": "ON"},
        budget_seconds=10,
    )

    assert outcome.mode == "LIVE_CAMPAIGN", (
        f"expected a real campaign against the synthetic target, got mode="
        f"{outcome.mode!r} failure={outcome.failure.as_dict() if outcome.failure else None}"
    )
    assert outcome.executions > 0, "libFuzzer reported zero executions against the synthetic target"
    assert outcome.harness == "synth_fuzz", (
        "a non-pktcfg target's reported harness must be its own, never pktcfg's default "
        "(#288)"
    )


@needs_real_fuzz_run
def test_real_campaign_suppresses_a_deliberate_leak_when_sanitizer_env_disables_it(
    fuzz_image: str, tmp_path: Path
) -> None:
    """#289's real, end-to-end regression proof: a harness that leaks memory on every
    single input (no real memory-safety crash anywhere in it) is, by default, reported
    as `sanitizer_confirmed`-shaped evidence (a real `leak-*` artifact with its own
    `SUMMARY: LeakSanitizer:` line) — and once leak detection is suppressed via
    `sanitizer_env`, the identical harness runs clean for the same budget: no crash, no
    artifact, `sanitizer_confirmed` is impossible to construct as True from this outcome.
    """
    synthetic_source = tmp_path / "synth-leak-target"
    synthetic_source.mkdir()
    _write_non_pktcfg_synthetic_target(synthetic_source, with_leak_harness=True)

    policy = ContainerJailPolicy(
        image=fuzz_image, memory_mb=1024, cpu_limit=2.0, wall_clock_seconds=90.0
    )

    # First: leak detection NOT suppressed — the leak is real and must be found, proving
    # this is a genuine LeakSanitizer bait, not a scenario that never triggers at all.
    unsuppressed = run_fuzzing_stage(
        "test-289-leak-unsuppressed",
        synthetic_source,
        policy=policy,
        harness_target="synth_leak_fuzz",
        harness_binary="synth_leak_fuzz",
        cache_entries={"SYNTH_SANITIZE": "ON", "SYNTH_FUZZ": "ON"},
        budget_seconds=30,
    )
    assert unsuppressed.mode == "LIVE_CAMPAIGN", (
        f"expected a real campaign, got mode={unsuppressed.mode!r} "
        f"failure={unsuppressed.failure.as_dict() if unsuppressed.failure else None}"
    )
    assert unsuppressed.unique_crashes >= 1, (
        "the deliberate leak was not detected at all — this harness is not a valid "
        "LeakSanitizer regression fixture (adjust the budget/allocation, not the "
        "assertion)"
    )
    assert "LeakSanitizer" in unsuppressed.run_output_excerpt

    # Second: identical harness, `sanitizer_env` suppresses leak detection (#289's own
    # fix) — the same leak must now report clean, no false "sanitizer_confirmed".
    suppressed = run_fuzzing_stage(
        "test-289-leak-suppressed",
        synthetic_source,
        policy=policy,
        harness_target="synth_leak_fuzz",
        harness_binary="synth_leak_fuzz",
        cache_entries={"SYNTH_SANITIZE": "ON", "SYNTH_FUZZ": "ON"},
        budget_seconds=15,
        sanitizer_env={"ASAN_OPTIONS": "detect_leaks=0"},
    )
    assert suppressed.mode == "LIVE_CAMPAIGN", (
        f"expected a real campaign, got mode={suppressed.mode!r} "
        f"failure={suppressed.failure.as_dict() if suppressed.failure else None}"
    )
    assert suppressed.unique_crashes == 0, (
        "a leak-only harness must report zero crashes once leak detection is "
        "suppressed via sanitizer_env (#289)"
    )
    assert suppressed.crashes_found == 0
    assert not suppressed.artifact_refs
    sanitizer_confirmed = suppressed.ran and suppressed.crashes_found > 0 and bool(suppressed.sanitizers)
    assert sanitizer_confirmed is False, (
        "the D5 gate formula (workers/fuzzing/cli.py::build_fuzzing_record) must not be "
        "constructible as sanitizer_confirmed=True from a suppressed leak"
    )
