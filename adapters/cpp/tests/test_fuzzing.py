from __future__ import annotations

import os
from pathlib import Path

import pytest

from adapters.cpp.fuzzing import (
    FUZZ_ARTIFACT_DIR,
    _copy_crash_artifacts_durably,
    parse_libfuzzer_metrics,
    run_libfuzzer_campaign,
)
from packages.sandbox.container import ContainerJail, ContainerJailPolicy

PINNED_IMAGE = "llvm-fuzzer@sha256:" + "b" * 64


def _sandbox(tmp_path: Path) -> ContainerJail:
    """A `ContainerJail` built directly against a real temp directory, bypassing
    `.create()` (which needs no daemon, but this skips even the `mkdtemp` indirection)
    — enough to exercise `_copy_crash_artifacts_durably`'s own copy-out logic against
    real files without a container runtime."""
    root = tmp_path / "sandbox-root"
    root.mkdir()
    return ContainerJail(root, ContainerJailPolicy(image=PINNED_IMAGE), "test-mission")


def test_fuzzing_configure_enables_sanitizers() -> None:
    """D5 gate evidence needs an ASan/UBSan stack, not only libFuzzer coverage."""
    import inspect

    from adapters.cpp import fuzzing

    source = inspect.getsource(fuzzing.run_libfuzzer_campaign)

    assert "-DPKTCFG_FUZZ=ON" in source
    assert "-DPKTCFG_SANITIZE=ON" in source


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
