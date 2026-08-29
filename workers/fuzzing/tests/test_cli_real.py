"""A REAL (not mocked) CLI run proving #292's fix: a discovered crash artifact survives
`ContainerJail.close()` when driven through `workers/fuzzing/cli.py::main` end to end.

Companion to `test_real_campaign.py::test_real_campaign_crash_bytes_survive_the_jails_own_
teardown`, which proves the same thing one layer down (calling `run_fuzzing_stage`
directly with `workspace_root=`). This file proves the actual CLI entry point — the one
#292 found never passed `workspace_root` through at all — does the same thing for real,
with no monkeypatching of `run_fuzzing_stage`/`run_libfuzzer_campaign`.

Same opt-in, skip-loud discipline as `test_real_campaign.py` (see that module's own
docstring): reuses its `fuzz_image` session fixture and `needs_real_fuzz_run` marker
rather than duplicating the image-build machinery.

    BRAHMADATTA_RUN_REAL_FUZZ_CAMPAIGN=1 pytest workers/fuzzing/tests/test_cli_real.py -v -s
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from workers.fuzzing import cli
from workers.fuzzing.tests.test_real_campaign import (
    PKTCFG_SOURCE,
    fuzz_image,  # noqa: F401 - re-exported fixture, pytest resolves it by name
    needs_real_fuzz_run,
)


@needs_real_fuzz_run
def test_cli_e2e_crash_artifact_survives_containerjail_close(
    fuzz_image: str, tmp_path: Path
) -> None:
    """#292's own reproduction, closed: before this fix, `cli.main()` never passed
    `workspace_root` to `run_fuzzing_stage`, so `ContainerJail.close()`'s
    `shutil.rmtree` deleted the discovered crash artifact the instant the real campaign
    returned — even though the CLI's own JSON `artifact_refs` claimed one existed. This
    drives the actual `python -m workers.fuzzing` entry point (via `cli.main`, no
    monkeypatching) against pktcfg's real seeded heap-buffer-overflow and checks the
    artifact bytes `artifact_refs` names are still on disk, under `--workspace-root`,
    after `main()` has already returned (i.e. after the sandbox is long gone)."""
    workspace_root = tmp_path / "cli-workspace"
    output_path = tmp_path / "fuzzing.json"

    stdout = io.StringIO()
    stderr = io.StringIO()
    code = cli.main(
        [
            "--source",
            str(PKTCFG_SOURCE),
            "--image",
            fuzz_image,
            "--budget-seconds",
            "90",
            "--wall-clock-seconds",
            "180",
            "--memory-mb",
            "2048",
            "--cpu-limit",
            "2.0",
            "--workspace-root",
            str(workspace_root),
            "--output",
            str(output_path),
            "--mission-id",
            "test-292-cli-e2e",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    record = json.loads(output_path.read_text())
    assert record["fuzzing"]["mode"] == "LIVE_CAMPAIGN", (
        f"expected a real campaign, got: {record['fuzzing']}"
    )
    assert record["gate"]["crashes_found"] >= 1, (
        "no crash found against pktcfg's seeded heap-buffer-overflow — cannot prove "
        "artifact survival without a real discovered artifact"
    )
    assert code == 0, f"D5 gate unexpectedly failed: {stderr.getvalue()}"

    artifact_refs = record["gate"]["artifact_refs"]
    assert artifact_refs, "a crash was reported but no artifact_refs were recorded"

    # The actual #292 proof: real bytes, still on disk, under workspace_root, after
    # cli.main() (and therefore the campaign's own ContainerJail.close()) has returned.
    durable_dir = workspace_root / "test-292-cli-e2e-fuzz-artifacts"
    assert durable_dir.is_dir(), (
        f"{durable_dir} does not exist — the CLI still is not wiring workspace_root "
        f"through to run_fuzzing_stage (#292)"
    )
    durable_files = list(durable_dir.glob("*"))
    assert durable_files, f"{durable_dir} exists but is empty"
    for durable_file in durable_files:
        assert durable_file.stat().st_size > 0, f"{durable_file} exists but is empty"
