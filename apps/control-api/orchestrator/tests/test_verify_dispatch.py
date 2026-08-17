"""`JobKind.VERIFY` executor + transition policy (#168, T5).

Two layers of coverage, deliberately:

* Routing/idempotency/guard-clause behaviour is exercised with `run_verification`
  monkeypatched to a scripted `GateMatrix` — fast, and it is what actually decides
  `MissionState`, not the toolchain underneath it.
* `test_the_real_pktcfg_pair_reaches_export_through_the_real_executor` runs the real
  demo target (#74) through the real `run_verification` (real `cmake`/`ctest`/
  `git apply`, no scripted runner) via the real executor and the real transition
  policy — the actual gate-matrix scenario this project's pitch is built on: one
  candidate that correctly bounds the tab-expansion write, one that "fixes" the crash
  by breaking the regression suite. Skipped if the toolchain is not installed, same
  guard `packages/sandbox/tests/test_baseline_in_jail.py` uses.
"""

from __future__ import annotations

import shutil
from datetime import timedelta
from uuid import uuid4

import pytest
from django.test import override_settings
from django.utils import timezone

from authorization.store import ingest_from_path
from contracts.enums import (
    GateStatus,
    LanguageAdapter,
    MissionState,
    PatchPolicyStatus,
    PatchProvenance,
    Verdict,
)
from missions.models import (
    Authorization,
    BaselineReport,
    Job,
    JobKind,
    Mission,
    PatchCandidate,
    Reproducer,
    Snapshot,
    VerificationRecord,
)
from orchestrator import candidates, transitions
from orchestrator.executors import ExecutorContext, JobOutcome, executor_for, transition_policy_for
from orchestrator.tests.conftest import (
    CANDIDATE_A,
    CANDIDATE_B,
    CANDIDATE_C,
    NOW,
    SNAPSHOT_SHA,
    TRACE,
    gate_matrix,
    walk_to,
)
from orchestrator.verify_dispatch import _verify_executor, _verify_transition_policy

pytestmark = pytest.mark.django_db(transaction=True)

DEMO_REPOSITORY = CANDIDATE_A.parents[1]
CRASH = DEMO_REPOSITORY / "crash" / "crash-literal-tab.bin"


def _other_mission() -> Mission:
    """A second, independent mission — same shape as `conftest.mission`, so it can
    walk the state machine on its own. Not a fixture from `conftest.py` because only
    one test in this file needs a second mission."""
    row = Mission.objects.create(
        name="other mission",
        repository_ref="file:///demo/repositories/other",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    Authorization.objects.create(
        mission=row,
        statement="I am authorized to test this repository on behalf of the owner.",
        granted_by="Mahatav Arora",
        granted_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(hours=8),
        repository_ref="file:///demo/repositories/other",
    )
    Snapshot.objects.create(
        mission=row,
        commit_sha="1" * 40,
        archive_sha256=SNAPSHOT_SHA,
        file_count=31,
        bytes_total=120_000,
    )
    return row


def _extend_authorization(mission: Mission) -> None:
    """The shared `mission` fixture's `Authorization` expires 8h after `conftest`'s
    fixed `NOW` — fine for callers that pass an explicit `now=` to every write (every
    other test in this package does), wrong for a test that exercises the real
    executor, which reads real wall-clock time via `django.utils.timezone.now()`
    inside `record_verification`. Extending the expiry here keeps `conftest.py`'s
    shared fixture untouched for tests that do not need this."""
    mission.authorizations.update(expires_at=timezone.now() + timedelta(days=1))


# --------------------------------------------------------------------------------
# Shared fixtures/helpers
# --------------------------------------------------------------------------------


def _job(mission: Mission, *, patch_id, attempt: int = 1) -> Job:
    return Job.objects.create(
        mission=mission,
        kind=JobKind.VERIFY,
        payload={"patch_id": str(patch_id)},
        attempt=attempt,
        max_attempts=1,
        run_after=NOW,
        deadline_at=NOW,
    )


def _ctx(job: Job, mission: Mission, tmp_path, source_dir=None) -> ExecutorContext:
    return ExecutorContext(
        job=job,
        mission=mission,
        source_dir=source_dir or tmp_path,
        workspace_root=tmp_path / "workspace",
        trace_id=TRACE,
        cancel_requested=lambda: False,
    )


def _accepted_candidate(mission: Mission, finding, diff: str) -> PatchCandidate:
    return candidates.record_patch_candidate(
        mission.id,
        finding_id=finding.id,
        provenance=PatchProvenance.OPERATOR_SUPPLIED,
        diff=diff,
        files_changed=1,
        lines_changed=len([line for line in diff.splitlines() if line[:1] in "+-"]),
        policy_status=PatchPolicyStatus.ACCEPTED,
        trace_id=TRACE,
        now=NOW,
    )


def _mark_job_terminal(job: Job, state: str) -> Job:
    job.state = state
    job.finished_at = NOW
    job.save(update_fields=["state", "finished_at"])
    return job


# --------------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------------


def test_verify_is_registered_for_both_registries():
    assert executor_for(JobKind.VERIFY) is _verify_executor
    assert transition_policy_for(JobKind.VERIFY) is _verify_transition_policy


# --------------------------------------------------------------------------------
# Executor: guard clauses (no toolchain needed — these never reach run_verification)
# --------------------------------------------------------------------------------


def test_missing_patch_id_is_an_infra_failure(mission, tmp_path):
    walk_to(mission, MissionState.VERIFY)
    job = Job.objects.create(
        mission=mission,
        kind=JobKind.VERIFY,
        payload={},
        run_after=NOW,
        deadline_at=NOW,
    )
    result = _verify_executor(_ctx(job, mission, tmp_path))

    assert result.outcome is JobOutcome.FAILED
    assert result.result["infra_failure"] is True
    assert VerificationRecord.objects.count() == 0


def test_nonexistent_patch_id_is_an_infra_failure(mission, tmp_path):
    walk_to(mission, MissionState.VERIFY)
    job = _job(mission, patch_id=uuid4())
    result = _verify_executor(_ctx(job, mission, tmp_path))

    assert result.outcome is JobOutcome.FAILED
    assert result.result["infra_failure"] is True


def test_a_candidate_from_another_mission_is_refused(mission, finding, tmp_path):
    """Mirrors SEC-15 (`test_cross_mission_evidence.py`) at the executor boundary: a
    `Job.payload["patch_id"]` naming a candidate that is not this mission's own must
    never reach `run_verification`, let alone `record_verification`."""
    other = _other_mission()
    walk_to(other, MissionState.PATCH)
    foreign_candidate = _accepted_candidate(other, finding, CANDIDATE_A.read_text())

    walk_to(mission, MissionState.VERIFY)
    job = _job(mission, patch_id=foreign_candidate.id)
    result = _verify_executor(_ctx(job, mission, tmp_path))

    assert result.outcome is JobOutcome.FAILED
    assert result.result["infra_failure"] is True
    assert VerificationRecord.objects.count() == 0


def test_a_policy_rejected_candidate_is_refused_not_silently_verified(
    mission, finding, tmp_path
):
    walk_to(mission, MissionState.PATCH)
    candidate = candidates.record_patch_candidate(
        mission.id,
        finding_id=finding.id,
        provenance=PatchProvenance.OPERATOR_SUPPLIED,
        diff=CANDIDATE_A.read_text(),
        files_changed=99,
        lines_changed=999,
        policy_status=PatchPolicyStatus.REJECTED_TOO_MANY_FILES,
        trace_id=TRACE,
        now=NOW,
    )
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)
    job = _job(mission, patch_id=candidate.id)
    result = _verify_executor(_ctx(job, mission, tmp_path))

    assert result.outcome is JobOutcome.FAILED
    assert result.result["infra_failure"] is True
    assert VerificationRecord.objects.count() == 0


def test_idempotent_on_a_candidate_already_verified(mission, finding, tmp_path):
    """D-061 §3, scoped to the candidate (see `verify_dispatch`'s module docstring):
    a restart must not retry into `VerificationRecord.patch`'s unique constraint."""
    walk_to(mission, MissionState.PATCH)
    candidate = _accepted_candidate(mission, finding, CANDIDATE_A.read_text())
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)

    existing = candidates.record_verification(
        mission.id,
        patch_id=candidate.id,
        gates=gate_matrix(),
        started_at=NOW,
        finished_at=NOW,
        trace_id=TRACE,
        now=NOW,
    )

    job = _job(mission, patch_id=candidate.id)
    result = _verify_executor(_ctx(job, mission, tmp_path))

    assert result.outcome is JobOutcome.SUCCEEDED
    assert result.result["already_verified"] is True
    assert result.result["verification_id"] == str(existing.id)
    # No second row, no IntegrityError.
    assert VerificationRecord.objects.filter(patch_id=candidate.id).count() == 1


def test_an_exception_inside_run_verification_is_an_infra_failure_not_a_verdict(
    mission, finding, tmp_path, monkeypatch
):
    walk_to(mission, MissionState.PATCH)
    candidate = _accepted_candidate(mission, finding, CANDIDATE_A.read_text())
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)

    def _boom(*args, **kwargs):
        raise OSError("sandbox host unreachable")

    monkeypatch.setattr("orchestrator.verify_dispatch.run_verification", _boom)

    job = _job(mission, patch_id=candidate.id)
    result = _verify_executor(_ctx(job, mission, tmp_path))

    assert result.outcome is JobOutcome.FAILED
    assert result.result["infra_failure"] is True
    assert VerificationRecord.objects.count() == 0


def test_record_verification_refusal_is_an_infra_failure_not_a_verdict(
    mission, finding, tmp_path, monkeypatch
):
    """The gates ran fine; the write was refused (mission not in VERIFY). Still not a
    verdict — nothing this mission can stand behind was recorded."""
    walk_to(mission, MissionState.PATCH)
    candidate = _accepted_candidate(mission, finding, CANDIDATE_A.read_text())
    # Deliberately NOT walking to VERIFY — `record_verification` requires it.

    monkeypatch.setattr(
        "orchestrator.verify_dispatch.run_verification",
        lambda *a, **k: gate_matrix(),
    )

    job = _job(mission, patch_id=candidate.id)
    result = _verify_executor(_ctx(job, mission, tmp_path))

    assert result.outcome is JobOutcome.FAILED
    assert result.result["infra_failure"] is True
    assert VerificationRecord.objects.count() == 0


def test_a_verified_candidate_is_recorded_and_the_gate_matrix_is_persisted(
    mission, finding, tmp_path, monkeypatch
):
    walk_to(mission, MissionState.PATCH)
    candidate = _accepted_candidate(mission, finding, CANDIDATE_A.read_text())
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)
    _extend_authorization(mission)

    monkeypatch.setattr(
        "orchestrator.verify_dispatch.run_verification",
        lambda *a, **k: gate_matrix(),
    )

    job = _job(mission, patch_id=candidate.id)
    result = _verify_executor(_ctx(job, mission, tmp_path))

    assert result.outcome is JobOutcome.SUCCEEDED
    assert result.result["verdict"] == Verdict.VERIFIED.value
    record = VerificationRecord.objects.get(patch_id=candidate.id)
    assert record.verdict == Verdict.VERIFIED.value

    gate_matrix_ref = tmp_path / "workspace" / "verify" / f"{candidate.id}.json"
    assert gate_matrix_ref.is_file()
    assert result.result["gate_matrix_ref"] == str(gate_matrix_ref)


def test_a_rejected_candidate_is_still_a_succeeded_job(mission, finding, tmp_path, monkeypatch):
    """D-061 §2: a legitimate REJECTED verdict is a `SUCCEEDED` job, never `FAILED` —
    conflating 'the patch was bad' with 'our system broke' is exactly the bug this
    executor must not have."""
    walk_to(mission, MissionState.PATCH)
    candidate = _accepted_candidate(mission, finding, CANDIDATE_B.read_text())
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)
    _extend_authorization(mission)

    monkeypatch.setattr(
        "orchestrator.verify_dispatch.run_verification",
        lambda *a, **k: gate_matrix(regression=GateStatus.FAIL),
    )

    job = _job(mission, patch_id=candidate.id)
    result = _verify_executor(_ctx(job, mission, tmp_path))

    assert result.outcome is JobOutcome.SUCCEEDED
    assert result.result["verdict"] == Verdict.REJECTED.value
    assert "infra_failure" not in result.result


def test_baseline_report_supplies_the_regression_denominator(
    mission, finding, tmp_path, monkeypatch
):
    """P0-5: `BaselineReport.tests_total` is the denominator for 'regression
    preserved'. This proves it actually reaches `VerificationBaseline`, not just that
    the field exists."""
    walk_to(mission, MissionState.PATCH)
    candidate = _accepted_candidate(mission, finding, CANDIDATE_A.read_text())
    BaselineReport.objects.create(
        mission=mission,
        configure_ok=True,
        build_ok=True,
        tests_total=8,
        tests_passed=8,
        tests_failed=0,
        duration_seconds=1.0,
        adapter="C_CMAKE_CTEST",
        recorded_at=NOW,
    )
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)
    _extend_authorization(mission)

    seen = {}

    def _capture(worktree, diff, reproducer, baseline, **kwargs):
        seen["expected_regression_tests"] = baseline.expected_regression_tests
        return gate_matrix()

    monkeypatch.setattr("orchestrator.verify_dispatch.run_verification", _capture)

    job = _job(mission, patch_id=candidate.id)
    result = _verify_executor(_ctx(job, mission, tmp_path))

    assert result.outcome is JobOutcome.SUCCEEDED, result.detail
    assert seen["expected_regression_tests"] == 8


def test_missing_reproducer_resolves_to_a_sentinel_path_not_a_crash(
    mission, finding, tmp_path, monkeypatch
):
    """No `Reproducer` row exists for this finding — `run_verification` itself turns a
    missing file into a disclosed `NOT_RUN` gate (see `_run_reproducer`); the executor
    must hand it a real, nonexistent `Path`, never raise."""
    walk_to(mission, MissionState.PATCH)
    candidate = _accepted_candidate(mission, finding, CANDIDATE_A.read_text())
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)
    _extend_authorization(mission)

    seen = {}

    def _capture(worktree, diff, reproducer, baseline, **kwargs):
        seen["reproducer"] = reproducer
        return gate_matrix()

    monkeypatch.setattr("orchestrator.verify_dispatch.run_verification", _capture)

    job = _job(mission, patch_id=candidate.id)
    result = _verify_executor(_ctx(job, mission, tmp_path))

    assert result.outcome is JobOutcome.SUCCEEDED, result.detail
    assert not seen["reproducer"].exists()


def test_reproducer_artifact_resolves_through_the_content_addressed_store(
    mission, finding, tmp_path, monkeypatch
):
    artifact_root = tmp_path / "artifacts"
    with override_settings(ARTIFACT_ROOT=artifact_root):
        ingest = ingest_from_path(artifact_root, CRASH, max_bytes=10_000_000)
        Reproducer.objects.create(
            finding=finding,
            minimized=True,
            replay_attempts=1,
            replay_successes=1,
            test_command="pktcfg_replay crash-literal-tab.bin",
            artifact={
                "uri": f"artifact://{mission.id}/reproducer/{ingest.sha256}",
                "kind": "reproducer_input",
                "sha256": ingest.sha256,
                "size_bytes": ingest.bytes_written,
            },
            created_at=NOW,
        )

        walk_to(mission, MissionState.PATCH)
        candidate = _accepted_candidate(mission, finding, CANDIDATE_A.read_text())
        transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)
        _extend_authorization(mission)

        seen = {}

        def _capture(worktree, diff, reproducer, baseline, **kwargs):
            seen["reproducer"] = reproducer
            return gate_matrix()

        monkeypatch.setattr("orchestrator.verify_dispatch.run_verification", _capture)

        job = _job(mission, patch_id=candidate.id)
        result = _verify_executor(_ctx(job, mission, tmp_path))

    assert result.outcome is JobOutcome.SUCCEEDED, result.detail
    assert seen["reproducer"] == ingest.path
    assert seen["reproducer"].read_bytes() == CRASH.read_bytes()


# --------------------------------------------------------------------------------
# Transition policy
# --------------------------------------------------------------------------------


def test_failed_job_routes_to_failed(mission, finding):
    walk_to(mission, MissionState.PATCH)
    candidate = _accepted_candidate(mission, finding, CANDIDATE_A.read_text())
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)

    job = _job(mission, patch_id=candidate.id)
    _mark_job_terminal(job, "FAILED")

    assert _verify_transition_policy(job, mission) is MissionState.FAILED


def test_timed_out_job_routes_to_failed_rather_than_stalling_forever(mission, finding):
    """The exact shape of #168: MAX_ATTEMPTS_BY_KIND[VERIFY] == 1, so a TIMED_OUT job
    has no retry coming — the mission must not be left in VERIFY forever."""
    walk_to(mission, MissionState.PATCH)
    candidate = _accepted_candidate(mission, finding, CANDIDATE_A.read_text())
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)

    job = _job(mission, patch_id=candidate.id)
    _mark_job_terminal(job, "TIMED_OUT")

    assert _verify_transition_policy(job, mission) is MissionState.FAILED


def test_cancelled_job_defers_to_the_mission_level_cancel_path(mission, finding):
    walk_to(mission, MissionState.PATCH)
    candidate = _accepted_candidate(mission, finding, CANDIDATE_A.read_text())
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)

    job = _job(mission, patch_id=candidate.id)
    _mark_job_terminal(job, "CANCELLED")

    assert _verify_transition_policy(job, mission) is None


def test_succeeded_job_waits_for_sibling_candidates_before_routing_onward(
    mission, finding
):
    walk_to(mission, MissionState.PATCH)
    candidate_a = _accepted_candidate(mission, finding, CANDIDATE_A.read_text())
    candidate_b = _accepted_candidate(mission, finding, CANDIDATE_B.read_text())
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)

    candidates.record_verification(
        mission.id,
        patch_id=candidate_a.id,
        gates=gate_matrix(),
        started_at=NOW,
        finished_at=NOW,
        trace_id=TRACE,
        now=NOW,
    )
    job_a = _job(mission, patch_id=candidate_a.id)
    _mark_job_terminal(job_a, "SUCCEEDED")

    # candidate_b has not been verified yet — this terminal job must not fire the
    # VERIFY -> EXPORTING transition on its own.
    assert _verify_transition_policy(job_a, mission) is None

    candidates.record_verification(
        mission.id,
        patch_id=candidate_b.id,
        gates=gate_matrix(regression=GateStatus.FAIL),
        started_at=NOW,
        finished_at=NOW,
        trace_id=TRACE,
        now=NOW,
    )
    job_b = _job(mission, patch_id=candidate_b.id)
    _mark_job_terminal(job_b, "SUCCEEDED")

    assert _verify_transition_policy(job_b, mission) is MissionState.EXPORTING


def test_transition_policy_never_returns_human_review_directly(mission, finding):
    """The `VERIFY`-shaped mirror of the `STRESS_TEST -> HUMAN_REVIEW` trap
    (`orchestrator/executors.py`'s docstring): `TRANSITIONS[VERIFY]` legally allows
    `HUMAN_REVIEW`, but this policy must never choose it — `EXPORTING`'s own
    transition-out derives it from the whole candidate set."""
    walk_to(mission, MissionState.PATCH)
    candidate = _accepted_candidate(mission, finding, CANDIDATE_A.read_text())
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)

    candidates.record_verification(
        mission.id,
        patch_id=candidate.id,
        gates=gate_matrix(
            compile_=GateStatus.PASS,
            reproducer=GateStatus.NOT_RUN,
            regression=GateStatus.NOT_RUN,
        ),
        started_at=NOW,
        finished_at=NOW,
        trace_id=TRACE,
        now=NOW,
    )
    job = _job(mission, patch_id=candidate.id)
    _mark_job_terminal(job, "SUCCEEDED")

    # This candidate's own verdict is HUMAN_REVIEW_REQUIRED (a required gate NOT_RUN),
    # and it is the mission's only candidate — the strongest possible pull toward
    # answering HUMAN_REVIEW directly. The policy must still say EXPORTING.
    record = VerificationRecord.objects.get(patch_id=candidate.id)
    assert record.verdict == Verdict.HUMAN_REVIEW_REQUIRED.value
    assert _verify_transition_policy(job, mission) is MissionState.EXPORTING


def test_zero_accepted_candidates_does_not_force_a_transition(mission):
    """Defensive: should not happen on the happy path (PATCH's own policy routes to
    HUMAN_REVIEW before VERIFY if nothing was accepted), but a dispatch bug must not
    crash straight into EXPORTING with an empty candidate set."""
    walk_to(mission, MissionState.VERIFY)
    job = _job(mission, patch_id=uuid4())
    _mark_job_terminal(job, "SUCCEEDED")

    assert _verify_transition_policy(job, mission) is None


# --------------------------------------------------------------------------------
# Real toolchain, real demo target: the actual pktcfg gate-matrix scenario
# --------------------------------------------------------------------------------


@pytest.mark.skipif(not DEMO_REPOSITORY.is_dir(), reason="demo target not present")
@pytest.mark.skipif(shutil.which("cmake") is None, reason="cmake not installed")
@pytest.mark.skipif(shutil.which("ctest") is None, reason="ctest not installed")
def test_the_real_pktcfg_pair_reaches_export_through_the_real_executor(
    mission, finding, tmp_path
):
    """No `ScriptedRunner`, no monkeypatch: the real `git apply` / `cmake` / `ctest` /
    `pktcfg_replay` against the real demo target, through the real executor and the
    real transition policy, for both the D6 kill-criterion candidates. This is what
    "verification is deterministic, never confidence-based" means end to end for
    this stage.
    """
    artifact_root = tmp_path / "artifacts"
    with override_settings(ARTIFACT_ROOT=artifact_root):
        ingest = ingest_from_path(artifact_root, CRASH, max_bytes=10_000_000)
        Reproducer.objects.create(
            finding=finding,
            minimized=True,
            replay_attempts=1,
            replay_successes=1,
            test_command="pktcfg_replay crash-literal-tab.bin",
            artifact={
                "uri": f"artifact://{mission.id}/reproducer/{ingest.sha256}",
                "kind": "reproducer_input",
                "sha256": ingest.sha256,
                "size_bytes": ingest.bytes_written,
            },
            created_at=NOW,
        )

        walk_to(mission, MissionState.PATCH)
        candidate_a = _accepted_candidate(mission, finding, CANDIDATE_A.read_text())
        candidate_b = _accepted_candidate(mission, finding, CANDIDATE_B.read_text())
        transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)
        _extend_authorization(mission)

        def _run(candidate) -> None:
            job = _job(mission, patch_id=candidate.id)
            ctx = ExecutorContext(
                job=job,
                mission=mission,
                source_dir=DEMO_REPOSITORY,
                workspace_root=tmp_path / "workspace",
                trace_id=TRACE,
                cancel_requested=lambda: False,
            )
            result = _verify_executor(ctx)
            assert result.outcome is JobOutcome.SUCCEEDED, result.detail
            _mark_job_terminal(job, "SUCCEEDED")
            next_state = _verify_transition_policy(job, mission)
            if next_state is not None:
                transitions.transition(mission.id, next_state, trace_id=TRACE, now=NOW)

        _run(candidate_a)
        mission.refresh_from_db()
        assert mission.state_enum is MissionState.VERIFY  # candidate_b still pending

        _run(candidate_b)
        mission.refresh_from_db()
        assert mission.state_enum is MissionState.EXPORTING

    records = {
        record.patch_id: record.verdict
        for record in VerificationRecord.objects.filter(mission=mission)
    }
    assert records[candidate_a.id] == Verdict.VERIFIED.value
    assert records[candidate_b.id] == Verdict.REJECTED.value

    transitions.transition(mission.id, MissionState.VERIFIED, trace_id=TRACE, now=NOW)
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.VERIFIED
    assert mission.verdict == Verdict.VERIFIED.value

    for candidate in (candidate_a, candidate_b):
        assert (tmp_path / "workspace" / "verify" / f"{candidate.id}.json").is_file()


@pytest.mark.skipif(not DEMO_REPOSITORY.is_dir(), reason="demo target not present")
@pytest.mark.skipif(shutil.which("cmake") is None, reason="cmake not installed")
@pytest.mark.skipif(shutil.which("ctest") is None, reason="ctest not installed")
def test_the_real_compile_failure_candidate_is_a_succeeded_job_with_a_rejected_verdict(
    mission, finding, tmp_path
):
    """D-061 §2's own named example, run for real: VERIFY's compile-gate failure is a
    legitimate REJECTED verdict, never a FAILED job."""
    walk_to(mission, MissionState.PATCH)
    candidate = _accepted_candidate(mission, finding, CANDIDATE_C.read_text())
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)
    _extend_authorization(mission)

    job = _job(mission, patch_id=candidate.id)
    ctx = ExecutorContext(
        job=job,
        mission=mission,
        source_dir=DEMO_REPOSITORY,
        workspace_root=tmp_path / "workspace",
        trace_id=TRACE,
        cancel_requested=lambda: False,
    )
    result = _verify_executor(ctx)

    assert result.outcome is JobOutcome.SUCCEEDED, result.detail
    assert result.result["verdict"] == Verdict.REJECTED.value
    record = VerificationRecord.objects.get(patch_id=candidate.id)
    assert record.verdict == Verdict.REJECTED.value
