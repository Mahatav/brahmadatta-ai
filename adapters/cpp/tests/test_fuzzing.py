from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from adapters.cpp.fuzzing import (
    DEFAULT_CACHE_ENTRIES,
    FUZZ_ARTIFACT_DIR,
    FuzzToolchainRecord,
    _copy_crash_artifacts_durably,
    parse_libfuzzer_metrics,
    run_libfuzzer_campaign,
)
from packages.sandbox import LimitKind
from packages.sandbox.container import ContainerJail, ContainerJailPolicy, ContainerJailResult

PINNED_IMAGE = "llvm-fuzzer@sha256:" + "b" * 64


def _sandbox(tmp_path: Path) -> ContainerJail:
    """A `ContainerJail` built directly against a real temp directory, bypassing
    `.create()` (which needs no daemon, but this skips even the `mkdtemp` indirection)
    — enough to exercise `_copy_crash_artifacts_durably`'s own copy-out logic against
    real files without a container runtime."""
    root = tmp_path / "sandbox-root"
    root.mkdir()
    return ContainerJail(root, ContainerJailPolicy(image=PINNED_IMAGE), "test-mission")


class _RecordingRuns:
    """Stands in for `ContainerJail.run` so `run_libfuzzer_campaign`'s configure/build/
    run argv can be inspected directly, without a real `docker` daemon (#288's own
    regression coverage needs to prove the *argv this module constructs*, which does not
    require actually invoking cmake/clang) — `adapters/cpp/tests/test_real_campaign.py`-
    style tests are the companion opt-in real-container proof for the same fix.
    """

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], *, raise_on_limit: bool = False) -> ContainerJailResult:
        self.calls.append(list(argv))
        return ContainerJailResult(
            argv=tuple(argv),
            exit_code=0,
            stdout="",
            stderr="",
            stdout_truncated=False,
            stderr_truncated=False,
            wall_seconds=0.001,
            limit_hit=LimitKind.NONE,
        )


def _patch_container_run(monkeypatch: pytest.MonkeyPatch) -> _RecordingRuns:
    recorder = _RecordingRuns()
    monkeypatch.setattr(ContainerJail, "run", lambda self, argv, **kw: recorder(argv, **kw))
    monkeypatch.setattr(
        "adapters.cpp.fuzzing._probe_fuzz_toolchain",
        lambda sandbox, image: FuzzToolchainRecord(image=image, isolation_mode="TEST", tools=()),
    )
    return recorder


def test_default_cache_entries_are_pktcfgs_own_options() -> None:
    """#288's whole "pktcfg keeps working identically" requirement, pinned as a value,
    not just an assertion about source text."""
    assert dict(DEFAULT_CACHE_ENTRIES) == {"PKTCFG_SANITIZE": "ON", "PKTCFG_FUZZ": "ON"}


def test_run_libfuzzer_campaign_configures_pktcfgs_own_options_by_default(
    monkeypatch: pytest.MonkeyPatch, pktcfg_source: Path
) -> None:
    """D5 gate evidence needs an ASan/UBSan stack, not only libFuzzer coverage — and
    (#288) pktcfg's own build must keep getting exactly the options it always got when
    no caller passes `cache_entries`."""
    recorder = _patch_container_run(monkeypatch)

    result = run_libfuzzer_campaign(
        pktcfg_source, ContainerJailPolicy(image=PINNED_IMAGE), budget_seconds=1
    )

    configure_argv = recorder.calls[0]
    assert "-DPKTCFG_SANITIZE=ON" in configure_argv
    assert "-DPKTCFG_FUZZ=ON" in configure_argv
    build_argv = recorder.calls[1]
    assert build_argv[:2] == ["cmake", "--build"]
    assert "pktcfg_fuzz" in build_argv
    assert result.harness == "pktcfg_fuzz"


def test_run_libfuzzer_campaign_drives_a_non_pktcfg_targets_own_cache_entries_and_harness(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """#288's actual regression proof: a target that names its own CMake options and
    fuzz target completely differently from pktcfg — reproducing the real
    `stb_image`/LAVA-M dogfooding failure this session (`STB_SANITIZE`/`STB_FUZZ`/
    `stb_fuzz`, not `PKTCFG_*`) — is driven correctly end-to-end by
    `run_libfuzzer_campaign`, and the reported harness label matches what was actually
    configured/built/run, never a hardcoded pktcfg default.

    Before this fix, this call always emitted the literal `-DPKTCFG_SANITIZE=ON
    -DPKTCFG_FUZZ=ON` regardless of `cache_entries`, which is exactly the failure this
    session's dogfooding hit against a real, differently-named target: CMake silently
    no-ops an unrecognised `-D` cache variable, so the harness target never gets built.
    """
    synthetic_source = tmp_path / "synthetic-target"
    synthetic_source.mkdir()
    (synthetic_source / "CMakeLists.txt").write_text("# synthetic non-pktcfg fixture\n")

    recorder = _patch_container_run(monkeypatch)

    result = run_libfuzzer_campaign(
        synthetic_source,
        ContainerJailPolicy(image=PINNED_IMAGE),
        harness_target="stb_fuzz",
        harness_binary="stb_fuzz",
        cache_entries={"STB_SANITIZE": "ON", "STB_FUZZ": "ON"},
        budget_seconds=1,
    )

    configure_argv = recorder.calls[0]
    assert "-DSTB_SANITIZE=ON" in configure_argv
    assert "-DSTB_FUZZ=ON" in configure_argv
    assert not any("PKTCFG" in arg for arg in configure_argv), (
        "a non-pktcfg target's configure step must never carry pktcfg's own literal "
        "cache-entry names (#288)"
    )
    build_argv = recorder.calls[1]
    assert "stb_fuzz" in build_argv
    run_argv = recorder.calls[3]
    assert run_argv[0].endswith("/stb_fuzz")
    assert result.harness == "stb_fuzz", (
        "the reported harness must reflect what was actually configured/run, never a "
        "hardcoded pktcfg default (#288)"
    )


def test_run_libfuzzer_campaign_sanitizer_env_is_opt_in_and_merges_with_policy_env(
    monkeypatch: pytest.MonkeyPatch, pktcfg_source: Path
) -> None:
    """#289: `sanitizer_env` layers onto whatever `policy.extra_env` a caller already
    set, without mutating the caller's own (frozen) policy object, and does nothing at
    all when omitted — pktcfg's prior behaviour (no extra env) is unchanged by default.
    """
    _patch_container_run(monkeypatch)
    captured_policy: list[ContainerJailPolicy] = []
    real_create = ContainerJail.create

    def _capturing_create(policy: ContainerJailPolicy, **kw: Any) -> ContainerJail:
        captured_policy.append(policy)
        return real_create(policy, **kw)

    monkeypatch.setattr(ContainerJail, "create", staticmethod(_capturing_create))

    base_policy = ContainerJailPolicy(image=PINNED_IMAGE, extra_env={"EXISTING": "1"})
    run_libfuzzer_campaign(
        pktcfg_source,
        base_policy,
        budget_seconds=1,
        sanitizer_env={"ASAN_OPTIONS": "detect_leaks=0"},
    )

    assert captured_policy[0].extra_env == {
        "EXISTING": "1",
        "ASAN_OPTIONS": "detect_leaks=0",
    }
    # The caller's own policy object is never mutated (frozen dataclass, replaced not
    # patched) — still exactly what the caller constructed.
    assert base_policy.extra_env == {"EXISTING": "1"}


def test_parse_libfuzzer_metrics_from_crashing_run() -> None:
    output = """
INFO: Running with entropic power schedule (0xFF, 100).
#8      INITED cov: 22 ft: 24 corp: 7/139b exec/s: 0 rss: 31Mb
#1024   NEW    cov: 41 ft: 66 corp: 8/178b lim: 21 exec/s: 512 rss: 33Mb
==17==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x602000000033
SUMMARY: AddressSanitizer: heap-buffer-overflow decode.c:31 in emit_tab
Test unit written to /workspace/fuzz-artifacts/crash-a90fd31ab2
stat::number_of_executed_units: 1088
"""
    metrics = parse_libfuzzer_metrics(output, corpus_size=7)

    assert metrics.executions == 1088
    assert metrics.coverage == 41
    assert metrics.crashes_found == 1
    assert metrics.unique_crashes == 1
    assert metrics.corpus_size == 7
    assert metrics.artifact_paths == ("fuzz-artifacts/crash-a90fd31ab2",)
    assert metrics.sanitizers == ("address",)


def test_parse_libfuzzer_metrics_uses_artifact_directory_listing() -> None:
    output = "#12 DONE   cov: 9 ft: 11 corp: 3/44b lim: 4 exec/s: 12 rss: 29Mb"
    metrics = parse_libfuzzer_metrics(
        output,
        corpus_size=3,
        artifact_paths=("fuzz-artifacts/crash-abc", "fuzz-artifacts/crash-def"),
    )

    assert metrics.executions == 12
    assert metrics.coverage == 9
    assert metrics.crashes_found == 2
    assert metrics.unique_crashes == 2


def test_parse_libfuzzer_metrics_deduplicates_absolute_and_relative_artifacts() -> None:
    output = (
        "SUMMARY: AddressSanitizer: heap-buffer-overflow decode.c:31 in emit_tab\n"
        "Test unit written to /workspace/fuzz-artifacts/crash-a90fd31ab2\n"
    )
    metrics = parse_libfuzzer_metrics(
        output,
        corpus_size=3,
        artifact_paths=("fuzz-artifacts/crash-a90fd31ab2",),
    )

    assert metrics.crashes_found == 1
    assert metrics.unique_crashes == 1
    assert metrics.artifact_paths == ("fuzz-artifacts/crash-a90fd31ab2",)


# ---------------------------------------------------------------------------------
# #291: `slow-unit`/`timeout`/`oom` artifacts are resource-limit findings, never a
# sanitizer-confirmed crash — reproducing the real stb_image dogfooding failure this
# session (a `slow-unit-*` algorithmic-hang artifact reported as `sanitizer_confirmed`).
# ---------------------------------------------------------------------------------


def test_parse_libfuzzer_metrics_slow_unit_artifact_is_never_counted_as_a_crash() -> None:
    """The exact stb_image repro: a `slow-unit-*` artifact with no `SUMMARY:
    ...Sanitizer:` line anywhere — a real CWE-400-shaped algorithmic hang, not a
    memory-safety defect — must never inflate `crashes_found`/`unique_crashes` or
    populate `sanitizers`."""
    output = (
        "==17== ERROR: libFuzzer: timeout after 25 seconds\n"
        "Test unit written to /workspace/fuzz-artifacts/slow-unit-8481f00d\n"
        "stat::number_of_executed_units: 4021\n"
    )
    metrics = parse_libfuzzer_metrics(output, corpus_size=5)

    assert metrics.crashes_found == 0
    assert metrics.unique_crashes == 0
    assert metrics.sanitizers == ()
    # Still real, visible evidence — just not a "crash".
    assert metrics.artifact_paths == ("fuzz-artifacts/slow-unit-8481f00d",)


def test_parse_libfuzzer_metrics_timeout_artifact_ignores_unrelated_sanitizer_text() -> None:
    """A `timeout-*` artifact must stay unconfirmed even when the session's *combined*
    output happens to carry a genuine `SUMMARY: ...Sanitizer:` line from something other
    than the artifact that actually stopped the run (#291's own "not tied to the
    specific artifact that stopped the run" gap statement) — e.g. informational ASan
    boilerplate the toolchain prints on startup, unrelated to why libFuzzer stopped."""
    output = (
        "SUMMARY: AddressSanitizer: heap-buffer-overflow unrelated-startup-check.c:1\n"
        "==17== ERROR: libFuzzer: timeout after 25 seconds\n"
        "Test unit written to /workspace/fuzz-artifacts/timeout-deadbeef\n"
    )
    metrics = parse_libfuzzer_metrics(output, corpus_size=5)

    assert metrics.crashes_found == 0
    assert metrics.unique_crashes == 0
    assert metrics.sanitizers == (), (
        "sanitizers must only be populated when the artifact that actually stopped the "
        "run has its own SUMMARY line, not from stray sanitizer text elsewhere in the "
        "captured session output"
    )


def test_parse_libfuzzer_metrics_oom_artifact_is_never_sanitizer_confirmed() -> None:
    output = (
        "==17== ERROR: libFuzzer: out-of-memory (malloc(4294967296))\n"
        "Test unit written to /workspace/fuzz-artifacts/oom-cafebabe\n"
    )
    metrics = parse_libfuzzer_metrics(output, corpus_size=1)

    assert metrics.crashes_found == 0
    assert metrics.unique_crashes == 0
    assert metrics.sanitizers == ()
    assert metrics.artifact_paths == ("fuzz-artifacts/oom-cafebabe",)


def test_parse_libfuzzer_metrics_real_crash_is_still_confirmed_alongside_a_hang() -> None:
    """A genuine sanitizer crash must still be reported correctly even in a session that
    also mentions a resource-limit artifact — the fix narrows what counts as a crash, it
    does not stop recognising a real one."""
    output = (
        "SUMMARY: AddressSanitizer: heap-buffer-overflow decode.c:31 in emit_tab\n"
        "Test unit written to /workspace/fuzz-artifacts/crash-a90fd31ab2\n"
    )
    metrics = parse_libfuzzer_metrics(
        output,
        corpus_size=3,
        artifact_paths=("fuzz-artifacts/slow-unit-earlier-run",),
    )

    assert metrics.crashes_found == 1
    assert metrics.unique_crashes == 1
    assert metrics.sanitizers == ("address",)
    assert metrics.artifact_paths == (
        "fuzz-artifacts/crash-a90fd31ab2",
        "fuzz-artifacts/slow-unit-earlier-run",
    )


def test_libfuzzer_campaign_requires_a_digest_pinned_image(pktcfg_source: Path) -> None:
    policy = ContainerJailPolicy(image="llvm-fuzzer:latest")

    with pytest.raises(Exception, match="not pinned"):
        run_libfuzzer_campaign(pktcfg_source, policy, budget_seconds=1)


# ---------------------------------------------------------------------------------
# D-106: `_copy_crash_artifacts_durably` — the copy-out this fix adds, and the two
# safeguards a fuzzer-controlled artifact directory needs that a trusted log does not.
# ---------------------------------------------------------------------------------


def test_copy_crash_artifacts_durably_copies_real_bytes_out(tmp_path: Path) -> None:
    sandbox = _sandbox(tmp_path)
    artifact_dir = sandbox.root / FUZZ_ARTIFACT_DIR
    artifact_dir.mkdir()
    (artifact_dir / "crash-abc123").write_bytes(b"crashing input bytes")

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    durable = _copy_crash_artifacts_durably(
        sandbox, ("fuzz-artifacts/crash-abc123",), workspace_root, "mission-1"
    )

    assert len(durable) == 1
    assert durable[0].relative_path == "fuzz-artifacts/crash-abc123"
    assert durable[0].size_bytes == len(b"crashing input bytes")
    host_path = Path(durable[0].host_path)
    assert host_path.is_file()
    assert host_path.read_bytes() == b"crashing input bytes"
    # Durable means outside the sandbox root — survives independently of it.
    assert workspace_root.resolve() in host_path.resolve().parents

    # The bytes really do survive the sandbox's own teardown, the entire point.
    sandbox.close()
    assert host_path.is_file()
    assert host_path.read_bytes() == b"crashing input bytes"


def test_copy_crash_artifacts_durably_refuses_a_symlink(tmp_path: Path) -> None:
    """A fuzzed target that plants a symlink where a crash artifact is expected must
    never have that symlink followed — D-106's own named cybersecurity-review target."""
    sandbox = _sandbox(tmp_path)
    artifact_dir = sandbox.root / FUZZ_ARTIFACT_DIR
    artifact_dir.mkdir()

    secret = tmp_path / "outside-the-sandbox-secret.txt"
    secret.write_bytes(b"should never be readable through the copy-out path")
    (artifact_dir / "crash-symlink").symlink_to(secret)

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    durable = _copy_crash_artifacts_durably(
        sandbox, ("fuzz-artifacts/crash-symlink",), workspace_root, "mission-1"
    )

    assert durable == ()
    assert list(workspace_root.rglob("*")) == []


def test_copy_crash_artifacts_durably_refuses_a_symlinked_escape_via_relative_target(
    tmp_path: Path,
) -> None:
    """A relative symlink target that resolves outside `sandbox.root` (not just an
    absolute one) is refused the same way."""
    sandbox = _sandbox(tmp_path)
    artifact_dir = sandbox.root / FUZZ_ARTIFACT_DIR
    artifact_dir.mkdir()

    secret = tmp_path / "another-secret.txt"
    secret.write_bytes(b"nope")
    (artifact_dir / "crash-relative-escape").symlink_to(os.path.relpath(secret, artifact_dir))

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    durable = _copy_crash_artifacts_durably(
        sandbox, ("fuzz-artifacts/crash-relative-escape",), workspace_root, "mission-1"
    )

    assert durable == ()


def test_copy_crash_artifacts_durably_enforces_a_size_ceiling(tmp_path: Path) -> None:
    """A corrupted or hostile oversized crash artifact must not be copied whole, or
    left half-written — D-106's other named cybersecurity-review target."""
    sandbox = _sandbox(tmp_path)
    artifact_dir = sandbox.root / FUZZ_ARTIFACT_DIR
    artifact_dir.mkdir()
    (artifact_dir / "crash-huge").write_bytes(b"x" * 1000)

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    durable = _copy_crash_artifacts_durably(
        sandbox,
        ("fuzz-artifacts/crash-huge",),
        workspace_root,
        "mission-1",
        max_bytes=100,
    )

    assert durable == ()
    # No partial file left behind under the destination directory.
    leftover = list((workspace_root / "mission-1-fuzz-artifacts").glob("*")) if (
        workspace_root / "mission-1-fuzz-artifacts"
    ).is_dir() else []
    assert leftover == []


def test_copy_crash_artifacts_durably_skips_a_vanished_artifact(tmp_path: Path) -> None:
    """Discovered by `run_libfuzzer_campaign`'s own glob, then vanished before the
    copy — must be skipped, not raise past this function (this module's own "a
    hostile or corrupted crash artifact must not take down an otherwise-real fuzzing
    outcome" discipline)."""
    sandbox = _sandbox(tmp_path)
    (sandbox.root / FUZZ_ARTIFACT_DIR).mkdir()

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    durable = _copy_crash_artifacts_durably(
        sandbox, ("fuzz-artifacts/crash-never-existed",), workspace_root, "mission-1"
    )

    assert durable == ()


def test_copy_crash_artifacts_durably_copies_multiple_artifacts_in_order(tmp_path: Path) -> None:
    sandbox = _sandbox(tmp_path)
    artifact_dir = sandbox.root / FUZZ_ARTIFACT_DIR
    artifact_dir.mkdir()
    (artifact_dir / "crash-a").write_bytes(b"aaa")
    (artifact_dir / "crash-b").write_bytes(b"bbbb")

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    durable = _copy_crash_artifacts_durably(
        sandbox,
        ("fuzz-artifacts/crash-a", "fuzz-artifacts/crash-b"),
        workspace_root,
        "mission-1",
    )

    assert [d.relative_path for d in durable] == [
        "fuzz-artifacts/crash-a",
        "fuzz-artifacts/crash-b",
    ]
    assert Path(durable[0].host_path).read_bytes() == b"aaa"
    assert Path(durable[1].host_path).read_bytes() == b"bbbb"
