"""D-106's own named end-to-end proof: a real `FUZZ` campaign discovers pktcfg's
seeded heap-buffer-overflow, persists a real `Reproducer` row (no fixture, no
monkeypatch), and a subsequent real `VERIFY` run against that same finding reaches a
genuine `VERIFIED` verdict for `candidate-a-correct-bounds-fix.patch` — the exact gap
D-098/D-105 both hit live, twice: `REPRODUCER_ELIMINATED` always `NOT_RUN` because no
code path ever wrote a `Reproducer` row for a self-discovered finding.

Opt-in and skip-loud, mirroring `workers/fuzzing/tests/test_real_campaign.py`'s own
gating exactly (a real `docker run` against the real
`infrastructure/compose/images/fuzz-toolchain.Dockerfile` image, ~400MB on a cold
cache, cached after): needs a reachable docker daemon AND
`BRAHMADATTA_RUN_REAL_FUZZ_CAMPAIGN=1`. `VERIFY`'s own half needs `cmake`/`ctest` on
PATH, same skip `test_verify_dispatch.py`'s real-toolchain tests already use.

    BRAHMADATTA_RUN_REAL_FUZZ_CAMPAIGN=1 pytest \\
        orchestrator/tests/test_fuzz_to_verify_real_e2e.py -v -s
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest
from django.test import override_settings
from django.utils import timezone

from contracts.enums import MissionState, PatchProvenance, Verdict
from missions.models import (
    Finding,
    FuzzingReport,
    Job,
    JobKind,
    JobState,
    Reproducer,
    VerificationRecord,
)
from orchestrator import candidates, transitions
from orchestrator.executors import ExecutorContext, JobOutcome, executor_for, transition_policy_for
from orchestrator.tests.conftest import CANDIDATE_A, NOW, TRACE, walk_to
from orchestrator.verify_dispatch import _resolve_reproducer_path

pytestmark = pytest.mark.django_db(transaction=True)

REPO_ROOT = Path(__file__).resolve().parents[4]
BUILD_SCRIPT = REPO_ROOT / "infrastructure" / "scripts" / "build-fuzz-image.sh"
DEMO_REPOSITORY = CANDIDATE_A.parents[1]

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
OPTED_IN = os.environ.get("BRAHMADATTA_RUN_REAL_FUZZ_CAMPAIGN") == "1"

needs_real_fuzz_run = pytest.mark.skipif(
    not (HAS_DOCKER and OPTED_IN),
    reason=(
        "real FUZZ-to-VERIFY end-to-end test skipped: needs a reachable docker daemon "
        "AND BRAHMADATTA_RUN_REAL_FUZZ_CAMPAIGN=1 (opt-in — builds a real image and "
        f"runs a real container). HAS_DOCKER={HAS_DOCKER} OPTED_IN={OPTED_IN}."
    ),
)


def _extend_authorization(mission) -> None:
    mission.authorizations.update(expires_at=timezone.now() + timedelta(days=1))


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


def _fuzz_job(mission) -> Job:
    return Job.objects.create(
        mission=mission,
        kind=JobKind.FUZZ,
        state=JobState.RUNNING,
        attempt=1,
        max_attempts=2,
        run_after=NOW,
        deadline_at=NOW + timedelta(minutes=30),
    )


def _verify_job(mission, patch_id) -> Job:
    return Job.objects.create(
        mission=mission,
        kind=JobKind.VERIFY,
        payload={"patch_id": str(patch_id)},
        attempt=1,
        max_attempts=1,
        run_after=NOW,
        deadline_at=NOW,
    )


@needs_real_fuzz_run
@pytest.mark.skipif(shutil.which("cmake") is None, reason="cmake not installed")
@pytest.mark.skipif(shutil.which("ctest") is None, reason="ctest not installed")
@pytest.mark.skipif(not DEMO_REPOSITORY.is_dir(), reason="demo target not present")
def test_a_real_fuzz_campaign_reaches_a_genuine_verified_verdict(
    mission, fuzz_image: str, tmp_path, settings
):
    """The whole point of D-106, driven end to end with no shortcuts:

    1. A real `FUZZ` job (real `ContainerJail`, real libFuzzer campaign against the
       real `pktcfg` target) discovers the seeded heap-buffer-overflow and — this is
       the actual fix — persists a real `Reproducer` row, not just a `Finding`.
    2. `orchestrator.verify_dispatch._resolve_reproducer_path` (the function `VERIFY`'s
       `REPRODUCER_ELIMINATED` gate actually calls) resolves that row to real,
       readable bytes.
    3. A real `VERIFY` job for `candidate-a-correct-bounds-fix.patch` — real
       `git apply`/`cmake`/`ctest`/`pktcfg_replay`, no scripted gate matrix — reaches
       `REPRODUCER_ELIMINATED: PASS` (not `NOT_RUN`) and an overall `VERIFIED`
       verdict, for the first time in this project's history against a
       self-discovered finding.
    """
    settings.SANDBOX_FUZZ_IMAGE = fuzz_image
    artifact_root = tmp_path / "artifacts"

    with override_settings(ARTIFACT_ROOT=artifact_root):
        walk_to(mission, MissionState.STRESS_TEST)

        fuzz_ctx = ExecutorContext(
            job=_fuzz_job(mission),
            mission=mission,
            source_dir=DEMO_REPOSITORY,
            workspace_root=tmp_path / "fuzz-workspace",
            trace_id=TRACE,
            cancel_requested=lambda: False,
        )
        fuzz_result = executor_for(JobKind.FUZZ)(fuzz_ctx)
        assert fuzz_result.outcome is JobOutcome.SUCCEEDED, fuzz_result.detail
        assert fuzz_result.result["unique_crashes"] >= 1, (
            "no crash found against pktcfg's seeded heap-buffer-overflow — either the "
            "toolchain regressed or the campaign never reached the defect"
        )

        report = FuzzingReport.objects.get(mission=mission)
        assert report.unique_crashes >= 1

        finding = Finding.objects.filter(mission=mission).first()
        assert finding is not None, "FUZZ found a crash but recorded no Finding"

        reproducer = Reproducer.objects.filter(finding=finding).first()
        assert reproducer is not None, (
            "D-106's own gap: FUZZ found a crash but recorded no Reproducer row — "
            "REPRODUCER_ELIMINATED would still resolve to NOT_RUN"
        )
        assert reproducer.minimized is False

        # The exact function VERIFY's gate calls, proving the row is not just present
        # but actually resolvable to real bytes on disk.
        fake_ctx = ExecutorContext(
            job=fuzz_ctx.job,
            mission=mission,
            source_dir=DEMO_REPOSITORY,
            workspace_root=tmp_path / "verify-workspace",
            trace_id=TRACE,
            cancel_requested=lambda: False,
        )
        from types import SimpleNamespace

        resolved = _resolve_reproducer_path(fake_ctx, SimpleNamespace(finding=finding))
        assert resolved.is_file()
        assert resolved.stat().st_size > 0

        # Drive the FUZZ job to a terminal state and let the real transition policy
        # move the mission forward, the same way the orchestrator loop would.
        job = fuzz_ctx.job
        job.state = JobState.SUCCEEDED
        job.finished_at = timezone.now()
        job.save(update_fields=["state", "finished_at"])
        next_state = transition_policy_for(JobKind.FUZZ)(job, mission)
        assert next_state is not None
        transitions.transition(mission.id, next_state, trace_id=TRACE, now=NOW)
        mission.refresh_from_db()
        assert mission.state_enum is MissionState.CORRELATE

        transitions.transition(mission.id, MissionState.PATCH, trace_id=TRACE, now=NOW)
        candidate = candidates.record_patch_candidate(
            mission.id,
            finding_id=finding.id,
            provenance=PatchProvenance.OPERATOR_SUPPLIED,
            diff=CANDIDATE_A.read_text(),
            files_changed=1,
            lines_changed=len(
                [line for line in CANDIDATE_A.read_text().splitlines() if line[:1] in "+-"]
            ),
            trace_id=TRACE,
            now=NOW,
        )
        transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)
        _extend_authorization(mission)

        verify_ctx = ExecutorContext(
            job=_verify_job(mission, candidate.id),
            mission=mission,
            source_dir=DEMO_REPOSITORY,
            workspace_root=tmp_path / "verify-workspace-2",
            trace_id=TRACE,
            cancel_requested=lambda: False,
        )
        verify_result = executor_for(JobKind.VERIFY)(verify_ctx)
        assert verify_result.outcome is JobOutcome.SUCCEEDED, verify_result.detail

        record = VerificationRecord.objects.get(mission=mission, patch_id=candidate.id)
        assert record.gates["reproducer_eliminated"]["status"] == "PASS", record.gates[
            "reproducer_eliminated"
        ]
        assert record.verdict == Verdict.VERIFIED.value, record.gates
