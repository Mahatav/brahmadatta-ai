from __future__ import annotations

from pathlib import Path

import pytest

from adapters.cpp.fuzzing import parse_libfuzzer_metrics, run_libfuzzer_campaign
from packages.sandbox.container import ContainerJailPolicy


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
