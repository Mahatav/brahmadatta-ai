from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path

from adapters.cpp.fuzzing import FuzzFailure
from workers.fuzzing import cli
from workers.fuzzing.run import FuzzingOutcome

PINNED_IMAGE = "llvm-fuzzer@sha256:" + "b" * 64


def test_cli_passes_a_workspace_root_to_run_fuzzing_stage_by_default(monkeypatch) -> None:
    """#292: the CLI never passed `workspace_root` through to `run_fuzzing_stage`, so
    `ContainerJail.close()`'s own `shutil.rmtree` deleted any discovered crash artifact
    the instant a real campaign returned — even though this CLI's JSON `artifact_refs`
    claimed one existed. A default (non-`None`) `workspace_root` must always be passed,
    with no extra flag required."""
    captured_kwargs: dict[str, object] = {}

    def fake_run_fuzzing_stage(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured_kwargs.update(kwargs)
        return _outcome(crashes=0)

    monkeypatch.setattr(cli, "run_fuzzing_stage", fake_run_fuzzing_stage)

    cli.main(["--image", PINNED_IMAGE], stdout=io.StringIO(), stderr=io.StringIO())

    assert "workspace_root" in captured_kwargs
    assert captured_kwargs["workspace_root"] is not None


def test_cli_workspace_root_flag_overrides_the_default(monkeypatch, tmp_path: Path) -> None:
    captured_kwargs: dict[str, object] = {}

    def fake_run_fuzzing_stage(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured_kwargs.update(kwargs)
        return _outcome(crashes=0)

    monkeypatch.setattr(cli, "run_fuzzing_stage", fake_run_fuzzing_stage)
    custom_workspace = tmp_path / "custom-workspace"

    cli.main(
        ["--image", PINNED_IMAGE, "--workspace-root", str(custom_workspace)],
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )

    assert captured_kwargs["workspace_root"] == custom_workspace


def test_cli_writes_d5_fuzzing_gate_evidence(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "fuzzing.json"

    monkeypatch.setattr(cli, "run_fuzzing_stage", lambda *args, **kwargs: _outcome(crashes=1))

    stdout = io.StringIO()
    stderr = io.StringIO()
    code = cli.main(
        ["--image", PINNED_IMAGE, "--output", str(output), "--events"],
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 0
    record = json.loads(output.read_text())
    streamed = json.loads(stdout.getvalue())
    assert record == streamed
    assert record["schema"] == "brahmadatta.d5_fuzzing_gate.v1"
    assert record["gate"]["passed"] is True
    assert record["gate"]["sanitizer_confirmed"] is True
    assert record["gate"]["mode"] == "LIVE_CAMPAIGN"
    assert record["gate"]["crashes_found"] == 1
    assert "AddressSanitizer" in record["fuzzing"]["run_output_excerpt"]
    assert [event["type"] for event in record["events"]] == ["STAGE_STARTED", "STAGE_COMPLETED"]
    assert stderr.getvalue() == ""


def test_cli_fails_when_fuzzer_finds_no_crash(monkeypatch) -> None:
    monkeypatch.setattr(cli, "run_fuzzing_stage", lambda *args, **kwargs: _outcome(crashes=0))

    stdout = io.StringIO()
    stderr = io.StringIO()
    code = cli.main(["--image", PINNED_IMAGE], stdout=stdout, stderr=stderr)

    assert code == 1
    record = json.loads(stdout.getvalue())
    assert record["gate"]["passed"] is False
    assert "D5 fuzzing gate failed" in stderr.getvalue()


def test_cli_reports_gate_runner_blockers(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise RuntimeError("container runtime is unavailable")

    monkeypatch.setattr(cli, "run_fuzzing_stage", fail)

    stdout = io.StringIO()
    stderr = io.StringIO()
    code = cli.main(["--image", PINNED_IMAGE], stdout=stdout, stderr=stderr)

    assert code == 2
    assert stdout.getvalue() == ""
    assert "container runtime is unavailable" in stderr.getvalue()


# ---------------------------------------------------------------------------------
# #301: --harness-target/--harness-binary/--cache-entry/--sanitizer-env expose
# run_fuzzing_stage's own (already real, #296/#288/#289) generalization to this CLI.
# ---------------------------------------------------------------------------------


def test_cli_defaults_reproduce_pktcfgs_own_behaviour_unchanged(monkeypatch) -> None:
    """No new flag passed at all: `run_fuzzing_stage` must be called with exactly
    pktcfg's own harness identity and no extra cache entries/sanitizer env — the "byte
    for byte unaffected" requirement #301's fix direction names explicitly."""
    captured_kwargs: dict[str, object] = {}

    def fake_run_fuzzing_stage(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured_kwargs.update(kwargs)
        return _outcome(crashes=0)

    monkeypatch.setattr(cli, "run_fuzzing_stage", fake_run_fuzzing_stage)

    cli.main(["--image", PINNED_IMAGE], stdout=io.StringIO(), stderr=io.StringIO())

    assert captured_kwargs["harness_target"] == "pktcfg_fuzz"
    assert captured_kwargs["harness_binary"] == "pktcfg_fuzz"
    assert captured_kwargs["cache_entries"] is None
    assert captured_kwargs["sanitizer_env"] is None


def test_cli_drives_a_synthetic_non_pktcfg_target_end_to_end_through_the_real_cli(
    monkeypatch,
) -> None:
    """#301's actual regression proof: a synthetic target that names its own harness,
    CMake options, and sanitizer env completely differently from pktcfg is driven
    correctly through the REAL CLI entry point (`cli.main`, not a raw function call to
    `run_fuzzing_stage`) — proving the product surface this issue names as missing now
    actually exists."""
    captured_kwargs: dict[str, object] = {}

    def fake_run_fuzzing_stage(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured_kwargs.update(kwargs)
        return _outcome(crashes=1)

    monkeypatch.setattr(cli, "run_fuzzing_stage", fake_run_fuzzing_stage)

    code = cli.main(
        [
            "--image",
            PINNED_IMAGE,
            "--harness-target",
            "njson_fuzz",
            "--harness-binary",
            "njson_fuzz",
            "--cache-entry",
            "NJSON_SANITIZE=ON",
            "--cache-entry",
            "NJSON_FUZZ=ON",
            "--sanitizer-env",
            "ASAN_OPTIONS=detect_leaks=0",
        ],
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )

    assert code == 0
    assert captured_kwargs["harness_target"] == "njson_fuzz"
    assert captured_kwargs["harness_binary"] == "njson_fuzz"
    assert captured_kwargs["cache_entries"] == {"NJSON_SANITIZE": "ON", "NJSON_FUZZ": "ON"}
    assert captured_kwargs["sanitizer_env"] == {"ASAN_OPTIONS": "detect_leaks=0"}


def test_cli_cache_entry_value_may_itself_contain_an_equals_sign(monkeypatch) -> None:
    """`--sanitizer-env ASAN_OPTIONS=detect_leaks=0` must split on the FIRST `=` only,
    since a real sanitizer option string routinely contains one itself."""
    captured_kwargs: dict[str, object] = {}
    monkeypatch.setattr(
        cli,
        "run_fuzzing_stage",
        lambda *a, **kw: (captured_kwargs.update(kw), _outcome(crashes=0))[1],
    )

    cli.main(
        ["--image", PINNED_IMAGE, "--sanitizer-env", "ASAN_OPTIONS=detect_leaks=0:halt_on_error=1"],
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )

    assert captured_kwargs["sanitizer_env"] == {"ASAN_OPTIONS": "detect_leaks=0:halt_on_error=1"}


def test_cli_rejects_a_malformed_cache_entry(monkeypatch) -> None:
    monkeypatch.setattr(cli, "run_fuzzing_stage", lambda *a, **kw: _outcome(crashes=0))

    stdout = io.StringIO()
    stderr = io.StringIO()
    code = cli.main(
        ["--image", PINNED_IMAGE, "--cache-entry", "not-a-key-value-pair"],
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 2
    assert stdout.getvalue() == ""
    assert "--cache-entry expects KEY=VALUE" in stderr.getvalue()


def _outcome(*, crashes: int) -> FuzzingOutcome:
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    return FuzzingOutcome(
        mission_id="mission-fuzzing",
        mode="LIVE_CAMPAIGN",
        harness="pktcfg_fuzz_one_input",
        engine="libFuzzer",
        runtime_seconds=2.5,
        executions=2048,
        crashes_found=crashes,
        unique_crashes=crashes,
        corpus_size=8,
        sanitizers=("address",),
        recorded_at=now,
        coverage=44,
        artifact_refs=("fuzz-artifacts/crash-abc",) if crashes else (),
        run_output_excerpt=(
            "SUMMARY: AddressSanitizer: heap-buffer-overflow src/decode.c:43 in emit_tab"
            if crashes
            else "#2048 DONE cov: 44"
        ),
        failure=None
        if crashes
        else FuzzFailure(
            step="RUN",
            command=("pktcfg_fuzz",),
            exit_code=0,
            first_error="no crash found",
        ),
    )
