"""`JobKind.FUZZ`'s executor, and `JobKind.MINIMIZE`'s honest-blocked one (#168, T2).

`workers.fuzzing.dispatch` is imported for its registration side effect the same way
`test_baseline_executor.py` does it for `workers.baseline.dispatch` — see that
file's own header comment. `_fuzz_transition_policy` itself (the
`STRESS_TEST -> CORRELATE` routing) is T0's, already tested end-to-end in
`test_stress_test_routing.py`; nothing here re-tests that policy, only the
executor that produces the `job.result` it reads.

Four shapes of test:

1. Idempotency / cancellation (D-061 §3 rule 2) —
   `test_existing_report_short_circuits_no_double_run`,
   `test_cancel_requested_before_start_short_circuits`.
2. The sandbox layer: unconfigured image, and a genuine `JailError` from
   `run_fuzzing_stage` — both `infra_failure`, distinguished from a harness build
   failure, which is not.
3. Outcome classification: a clean campaign (crash or not) succeeds; zero
   executions is treated as a stall and retried once; a real crash persists a
   `FuzzingReport` and a `Finding`.
4. `JobKind.MINIMIZE`'s executor and transition policy, proving they are real,
   registered, and honest about the structural blocker rather than absent.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from adapters.cpp.fuzzing import DurableArtifact, FuzzFailure
from contracts.enums import ErrorCode, MissionState
from missions.models import Finding, FuzzingReport, Job, JobKind, JobState, Mission, Reproducer
from orchestrator.executors import ExecutorContext, JobOutcome, executor_for, transition_policy_for
from orchestrator.tests.conftest import NOW, TRACE, walk_to
from packages.sandbox.errors import ContainerUnavailableError
from workers.fuzzing import dispatch
from workers.fuzzing.run import FuzzingOutcome

pytestmark = pytest.mark.django_db(transaction=True)

# A real captured ASan transcript for pktcfg's seeded defect — pinned in
# adapters/cpp/tests/test_sanitizer.py as "captured verbatim ... during
# development." Reused here rather than hand-written so this test's expectations
# are checked against the same real grammar `parse_sanitizer_output` is proven
# against elsewhere, not a fixture invented for this file alone.
_REAL_ASAN_CAPTURE = """\
==78383==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x6020000000f4 at pc 0x000102ac8cf8 bp 0x00016d339b20 sp 0x00016d339b18
WRITE of size 1 at 0x6020000000f4 thread T0
    #0 0x000102ac8cf4 in emit_tab decode.c:43
    #1 0x000102ac88f0 in pkt_decode_into decode.c:148
    #2 0x000102ac6afc in pkt_parse parse.c:126
    #3 0x000102ac9c28 in pktcfg_fuzz_one_input fuzz_entry.c:26
    #4 0x000102ac5628 in main pktcfg_replay.c:68

0x6020000000f4 is located 0 bytes after 4-byte region [0x6020000000f0,0x6020000000f4)
allocated by thread T0 here:
    #0 0x000103341164 in malloc+0x78 (libclang_rt.asan_osx_dynamic.dylib:arm64e+0x41164)
    #1 0x000102ac6898 in pkt_parse parse.c:120

SUMMARY: AddressSanitizer: heap-buffer-overflow decode.c:43 in emit_tab
"""


def _job(mission: Mission, *, state: str = JobState.RUNNING, attempt: int = 1) -> Job:
    return Job.objects.create(
        mission=mission,
        kind=JobKind.FUZZ,
        state=state,
        attempt=attempt,
        max_attempts=2,
        run_after=NOW,
        deadline_at=NOW + timedelta(minutes=30),
    )


def _ctx(mission: Mission, job: Job, *, cancelled: bool = False) -> ExecutorContext:
    return ExecutorContext(
        job=job,
        mission=mission,
        source_dir=Path("/does/not/matter"),
        workspace_root=Path("/does/not/matter/either"),
        trace_id=TRACE,
        cancel_requested=lambda: cancelled,
    )


def _clean_outcome(
    *,
    executions: int = 4096,
    crashes: int = 0,
    excerpt: str = "",
    artifact_refs: tuple[str, ...] = (),
    durable_artifacts: tuple[DurableArtifact, ...] = (),
) -> FuzzingOutcome:
    return FuzzingOutcome(
        mission_id="whatever",
        mode="LIVE_CAMPAIGN",
        harness="pktcfg_fuzz_one_input",
        engine="libFuzzer",
        runtime_seconds=12.5,
        executions=executions,
        crashes_found=crashes,
        unique_crashes=crashes,
        corpus_size=8,
        sanitizers=("address", "undefined"),
        recorded_at=datetime.now(UTC),
        run_output_excerpt=excerpt,
        artifact_refs=artifact_refs,
        durable_artifacts=durable_artifacts,
    )


@pytest.fixture(autouse=True)
def _fuzz_image(settings):
    settings.SANDBOX_FUZZ_IMAGE = "llvm-fuzzer@sha256:" + "b" * 64


# ---------------------------------------------------------------------------------
# 1. Idempotency / cancellation
# ---------------------------------------------------------------------------------


def test_existing_report_short_circuits_no_double_run(mission: Mission, monkeypatch):
    walk_to(mission, MissionState.STRESS_TEST)
    FuzzingReport.objects.create(
        mission=mission,
        mode="LIVE_CAMPAIGN",
        harness="pktcfg_fuzz_one_input",
        engine="libFuzzer",
        runtime_seconds=9.0,
        executions=2048,
        crashes_found=1,
        unique_crashes=1,
        corpus_size=8,
        sanitizers=["address"],
        recorded_at=NOW,
    )

    def _must_not_run(*args, **kwargs):
        raise AssertionError("run_fuzzing_stage was called despite an existing FuzzingReport")

    monkeypatch.setattr(dispatch, "run_fuzzing_stage", _must_not_run)

    job = _job(mission)
    result = executor_for(JobKind.FUZZ)(_ctx(mission, job))

    assert result.outcome == JobOutcome.SUCCEEDED
    assert result.result["already_recorded"] is True
    assert result.result["unique_crashes"] == 1
    assert FuzzingReport.objects.filter(mission=mission).count() == 1


def test_cancel_requested_before_start_short_circuits(mission: Mission, monkeypatch):
    def _must_not_run(*args, **kwargs):
        raise AssertionError("run_fuzzing_stage was called despite cancel_requested()")

    monkeypatch.setattr(dispatch, "run_fuzzing_stage", _must_not_run)

    job = _job(mission)
    result = executor_for(JobKind.FUZZ)(_ctx(mission, job, cancelled=True))

    assert result.outcome == JobOutcome.CANCELLED
    assert FuzzingReport.objects.filter(mission=mission).count() == 0


# ---------------------------------------------------------------------------------
# 2. Sandbox layer: unconfigured image, genuine infra fault
# ---------------------------------------------------------------------------------


def test_unconfigured_image_is_an_infra_failure_not_a_crash(mission: Mission, settings, monkeypatch):
    settings.SANDBOX_FUZZ_IMAGE = ""

    def _must_not_run(*args, **kwargs):
        raise AssertionError("run_fuzzing_stage was called with no image configured")

    monkeypatch.setattr(dispatch, "run_fuzzing_stage", _must_not_run)

    job = _job(mission)
    result = executor_for(JobKind.FUZZ)(_ctx(mission, job))

    assert result.outcome == JobOutcome.FAILED
    assert result.result["infra_failure"] is True
    assert result.error_code == ErrorCode.SANDBOX_UNAVAILABLE
    assert result.retry is False


def test_a_genuine_jail_error_is_an_infra_failure_and_may_retry(mission: Mission, monkeypatch):
    """SEC-42 (#176) / D-086: `job_mission_kind_unique` makes a second literal `Job`
    row for `(mission, FUZZ)` impossible, matching production reality — a retry
    reuses the *same* row with `attempt` incremented in place (`orchestrator.queue.
    retry_job`), it never gets a new row. The second attempt below mutates `job` in
    place instead of the pre-fix version's separately created `job2`."""

    def _raise_unavailable(*args, **kwargs):
        raise ContainerUnavailableError("docker daemon did not respond")

    monkeypatch.setattr(dispatch, "run_fuzzing_stage", _raise_unavailable)

    job = _job(mission, attempt=1)
    result = executor_for(JobKind.FUZZ)(_ctx(mission, job))

    assert result.outcome == JobOutcome.FAILED
    assert result.result["infra_failure"] is True
    assert result.error_code == ErrorCode.SANDBOX_UNAVAILABLE
    assert result.retry is True  # attempt 1 < max_attempts 2

    job.attempt = 2
    job.state = JobState.RUNNING
    job.save(update_fields=["attempt", "state"])
    result2 = executor_for(JobKind.FUZZ)(_ctx(mission, job))
    assert result2.retry is False  # attempts exhausted


# ---------------------------------------------------------------------------------
# 3. Outcome classification
# ---------------------------------------------------------------------------------


def test_a_harness_build_failure_is_not_an_infra_failure(mission: Mission, monkeypatch):
    outcome = FuzzingOutcome(
        mission_id=str(mission.id),
        mode="NOT_RUN",
        harness="pktcfg_fuzz_one_input",
        engine="libFuzzer",
        runtime_seconds=0.0,
        executions=0,
        crashes_found=0,
        unique_crashes=0,
        corpus_size=0,
        sanitizers=(),
        recorded_at=NOW,
        failure=FuzzFailure(
            step="BUILD",
            command=("cmake", "--build", "build-libfuzzer"),
            exit_code=2,
            first_error="undefined reference to pktcfg_fuzz_one_input",
        ),
    )
    monkeypatch.setattr(dispatch, "run_fuzzing_stage", lambda *a, **k: outcome)

    job = _job(mission)
    result = executor_for(JobKind.FUZZ)(_ctx(mission, job))

    assert result.outcome == JobOutcome.FAILED
    assert result.result["infra_failure"] is False
    assert result.error_code is None
    assert FuzzingReport.objects.filter(mission=mission).count() == 0


def test_a_toolchain_probe_failure_is_an_infra_failure(mission: Mission, monkeypatch):
    outcome = FuzzingOutcome(
        mission_id=str(mission.id),
        mode="NOT_RUN",
        harness="pktcfg_fuzz_one_input",
        engine="libFuzzer",
        runtime_seconds=0.0,
        executions=0,
        crashes_found=0,
        unique_crashes=0,
        corpus_size=0,
        sanitizers=(),
        recorded_at=NOW,
        failure=FuzzFailure(
            step="PROBE_TOOLCHAIN",
            command=(),
            exit_code=-1,
            first_error="image reference is not pinned to a digest",
        ),
    )
    monkeypatch.setattr(dispatch, "run_fuzzing_stage", lambda *a, **k: outcome)

    job = _job(mission)
    result = executor_for(JobKind.FUZZ)(_ctx(mission, job))

    assert result.outcome == JobOutcome.FAILED
    assert result.result["infra_failure"] is True
    assert result.error_code == ErrorCode.SANDBOX_UNAVAILABLE


def test_zero_executions_is_treated_as_a_stall_and_may_retry(mission: Mission, monkeypatch):
    outcome = _clean_outcome(executions=0, crashes=0)
    monkeypatch.setattr(dispatch, "run_fuzzing_stage", lambda *a, **k: outcome)

    job = _job(mission, attempt=1)
    result = executor_for(JobKind.FUZZ)(_ctx(mission, job))

    assert result.outcome == JobOutcome.FAILED
    assert result.result["stalled"] is True
    assert result.result["infra_failure"] is False
    assert result.retry is True
    assert FuzzingReport.objects.filter(mission=mission).count() == 0


def test_a_clean_campaign_with_no_crashes_succeeds(mission: Mission, monkeypatch):
    outcome = _clean_outcome(executions=100_000, crashes=0)
    monkeypatch.setattr(dispatch, "run_fuzzing_stage", lambda *a, **k: outcome)

    job = _job(mission)
    result = executor_for(JobKind.FUZZ)(_ctx(mission, job))

    assert result.outcome == JobOutcome.SUCCEEDED
    assert result.result["crashes_found"] == 0
    report = FuzzingReport.objects.get(mission=mission)
    assert report.unique_crashes == 0
    assert Finding.objects.filter(mission=mission).count() == 0


def test_a_real_crash_persists_a_report_and_a_structured_finding(mission: Mission, monkeypatch):
    outcome = _clean_outcome(executions=4096, crashes=1, excerpt=_REAL_ASAN_CAPTURE)
    monkeypatch.setattr(dispatch, "run_fuzzing_stage", lambda *a, **k: outcome)

    job = _job(mission)
    result = executor_for(JobKind.FUZZ)(_ctx(mission, job))

    assert result.outcome == JobOutcome.SUCCEEDED
    assert result.result["crashes_found"] == 1

    report = FuzzingReport.objects.get(mission=mission)
    assert report.unique_crashes == 1

    finding = Finding.objects.get(mission=mission)
    assert finding.category == "HEAP_BUFFER_OVERFLOW"
    assert finding.tool == "ADDRESS_SANITIZER"
    assert finding.discovery_method == "FUZZING_CAMPAIGN"
    assert finding.file_path == "decode.c"
    assert finding.line == 43
    assert finding.function == "emit_tab"
    assert finding.reproducible is False  # see module docstring: MINIMIZE is blocked
    assert finding.replay_source is None


def test_a_real_crash_s_sanitizer_report_is_redacted_before_it_is_stored(
    mission: Mission, monkeypatch
):
    """#191 (SEC-50 per that issue's title): `Finding.sanitizer_report` must never
    carry the raw sandboxed-process capture verbatim — `FindingDetail.
    sanitizer_report`'s own field docstring promises absolute paths and environment
    values are stripped, and `api/routers/evidence.py`'s module docstring promises
    "never raw tool output" for exactly this endpoint's response
    (`GET /missions/{id}/findings/{finding_id}`). Poisons the same real captured
    ASan grammar `test_a_real_crash_persists_a_report_and_a_structured_finding`
    already exercises with an absolute path and an injected
    `DATABASE_URL=postgresql://...`-shaped line — the concrete leak class SEC-44/45/
    48 already named — and asserts the persisted row lost neither its usefulness nor
    its safety.
    """
    # Poison only the `#0` frame line's path (not the `SUMMARY:` line) — this test
    # is about `sanitizer_report`, not `Finding.file_path`/`.line`/`.function`
    # (parsed separately from the `SUMMARY:` line by `adapters.cpp.sanitizer`, out
    # of scope for #191, which names `sanitizer_report` specifically) — so the
    # structured columns stay independently verifiable below, unperturbed by this
    # fixture's own edit.
    poisoned_capture = _REAL_ASAN_CAPTURE.replace(
        "#0 0x000102ac8cf4 in emit_tab decode.c:43",
        "#0 0x000102ac8cf4 in emit_tab /Users/someone/secret-project/pktcfg/src/decode.c:43",
        1,
    ).replace(
        "WRITE of size 1 at 0x6020000000f4 thread T0",
        "WRITE of size 1 at 0x6020000000f4 thread T0\n"
        "DATABASE_URL=postgresql://svc_user:hunter2@db.internal:5432/missions",
        1,
    )
    assert "/Users/someone/secret-project" in poisoned_capture  # the fixture is doing its job
    assert "hunter2" in poisoned_capture

    outcome = _clean_outcome(executions=4096, crashes=1, excerpt=poisoned_capture)
    monkeypatch.setattr(dispatch, "run_fuzzing_stage", lambda *a, **k: outcome)

    job = _job(mission)
    result = executor_for(JobKind.FUZZ)(_ctx(mission, job))
    assert result.outcome == JobOutcome.SUCCEEDED

    finding = Finding.objects.get(mission=mission)

    # The leak this issue names: gone.
    assert "/Users/someone/secret-project" not in finding.sanitizer_report
    assert "DATABASE_URL=postgresql://" not in finding.sanitizer_report
    assert "hunter2" not in finding.sanitizer_report

    # The report is still useful: crash type, stack frames, offending function.
    assert "AddressSanitizer: heap-buffer-overflow" in finding.sanitizer_report
    assert "emit_tab" in finding.sanitizer_report
    assert "pkt_decode_into" in finding.sanitizer_report
    assert "pkt_parse" in finding.sanitizer_report

    # The structured columns (parsed separately, not from this free-text field)
    # still carry the real crash location — this fix does not touch them.
    assert finding.file_path == "decode.c"
    assert finding.line == 43
    assert finding.function == "emit_tab"


# ---------------------------------------------------------------------------------
# D-106: a durably-copied crash artifact becomes a real Reproducer row, and the row
# is what VERIFY's own resolver actually reads back — this is the fix for the exact
# gap D-098/D-105 hit live, twice: REPRODUCER_ELIMINATED always NOT_RUN.
# ---------------------------------------------------------------------------------


def test_a_real_crash_with_a_durable_artifact_persists_a_reproducer(
    mission: Mission, monkeypatch, tmp_path, settings
):
    from django.test import override_settings

    from orchestrator.verify_dispatch import _resolve_reproducer_path

    crash_bytes = b"a real, faulting crash input"
    source = tmp_path / "crash-abc123"
    source.write_bytes(crash_bytes)
    artifact_root = tmp_path / "artifacts"

    outcome = _clean_outcome(
        executions=4096,
        crashes=1,
        excerpt=_REAL_ASAN_CAPTURE,
        durable_artifacts=(
            DurableArtifact(
                relative_path="fuzz-artifacts/crash-abc123",
                host_path=str(source),
                size_bytes=len(crash_bytes),
            ),
        ),
    )
    monkeypatch.setattr(dispatch, "run_fuzzing_stage", lambda *a, **k: outcome)

    with override_settings(ARTIFACT_ROOT=artifact_root):
        job = _job(mission)
        result = executor_for(JobKind.FUZZ)(_ctx(mission, job))

        assert result.outcome == JobOutcome.SUCCEEDED
        finding = Finding.objects.get(mission=mission)
        reproducer = Reproducer.objects.get(finding=finding)

        assert reproducer.minimized is False
        assert reproducer.artifact["size_bytes"] == len(crash_bytes)
        sha256 = reproducer.artifact["sha256"]
        assert (artifact_root / sha256[:2] / sha256).read_bytes() == crash_bytes

        # The actual acceptance criterion: VERIFY's own resolver finds real bytes.
        fake_patch = SimpleNamespace(finding=finding)
        fake_ctx = SimpleNamespace(workspace_root=tmp_path / "workspace")

        resolved = _resolve_reproducer_path(fake_ctx, fake_patch)
        assert resolved.is_file()
        assert resolved.read_bytes() == crash_bytes


def test_no_reproducer_when_no_durable_artifact_survived(mission: Mission, monkeypatch, settings):
    """The honest case: `run_fuzzing_stage` found a crash but no durable copy came
    back (no `workspace_root` given, or `_copy_crash_artifacts_durably` rejected
    every candidate). A `Finding` is still recorded — `VERIFY`'s
    `REPRODUCER_ELIMINATED` gate stays `NOT_RUN`, not a fabricated pass."""
    outcome = _clean_outcome(executions=4096, crashes=1, excerpt=_REAL_ASAN_CAPTURE)
    monkeypatch.setattr(dispatch, "run_fuzzing_stage", lambda *a, **k: outcome)

    job = _job(mission)
    result = executor_for(JobKind.FUZZ)(_ctx(mission, job))

    assert result.outcome == JobOutcome.SUCCEEDED
    finding = Finding.objects.get(mission=mission)
    assert Reproducer.objects.filter(finding=finding).count() == 0


def test_no_reproducer_when_durable_artifact_count_does_not_match_findings(
    mission: Mission, monkeypatch, tmp_path, settings
):
    """Two findings (structured + unstructured, forced via two artifact refs with no
    sanitizer text) but only one durable artifact — an ambiguous mapping this
    module's own docstring says must not guess. No Reproducer for either finding."""
    source = tmp_path / "crash-only-one"
    source.write_bytes(b"one artifact")

    outcome = _clean_outcome(
        executions=4096,
        crashes=1,
        excerpt="",
        artifact_refs=("fuzz-artifacts/crash-a", "fuzz-artifacts/crash-b"),
        durable_artifacts=(
            DurableArtifact(
                relative_path="fuzz-artifacts/crash-a", host_path=str(source), size_bytes=12
            ),
        ),
    )
    monkeypatch.setattr(dispatch, "run_fuzzing_stage", lambda *a, **k: outcome)

    job = _job(mission)
    result = executor_for(JobKind.FUZZ)(_ctx(mission, job))

    assert result.outcome == JobOutcome.SUCCEEDED
    assert Finding.objects.filter(mission=mission).count() == 2
    assert Reproducer.objects.count() == 0


def test_a_crash_with_no_parseable_sanitizer_report_still_records_a_finding(
    mission: Mission, monkeypatch
):
    """No structural ASan/UBSan grammar match (e.g. truncated excerpt, plain crash) —
    the crash must not be silently dropped."""
    outcome = _clean_outcome(
        executions=4096, crashes=1, excerpt="", artifact_refs=("fuzz-artifacts/crash-abc123",)
    )
    monkeypatch.setattr(dispatch, "run_fuzzing_stage", lambda *a, **k: outcome)

    job = _job(mission)
    result = executor_for(JobKind.FUZZ)(_ctx(mission, job))

    assert result.outcome == JobOutcome.SUCCEEDED
    finding = Finding.objects.get(mission=mission)
    assert finding.category == "OTHER"
    assert finding.tool == "LIBFUZZER"
    assert "crash-abc123" in finding.title


def test_re_running_a_completed_campaign_does_not_duplicate_findings(mission: Mission, monkeypatch):
    """A worker that crashed after `_persist_outcome` committed but before its `Job`
    reached SUCCEEDED must not double the evidence on restart — proven end to end
    through the executor, not just `record_finding` in isolation.

    SEC-42 (#176) / D-086: `job_mission_kind_unique` makes a second literal `Job` row
    for `(mission, FUZZ)` impossible, matching production reality — a worker that
    crashed mid-job and gets re-claimed re-runs the executor against the *same* `Job`
    row (still not yet terminal), it never gets a new one. The restart below reuses
    `job` instead of the pre-fix version's separately created `job2`.
    """
    outcome = _clean_outcome(executions=4096, crashes=1, excerpt=_REAL_ASAN_CAPTURE)
    monkeypatch.setattr(dispatch, "run_fuzzing_stage", lambda *a, **k: outcome)

    job = _job(mission)
    executor_for(JobKind.FUZZ)(_ctx(mission, job))
    assert Finding.objects.filter(mission=mission).count() == 1
    assert FuzzingReport.objects.filter(mission=mission).count() == 1

    def _must_not_run_again(*args, **kwargs):
        raise AssertionError("run_fuzzing_stage was called despite an existing FuzzingReport")

    monkeypatch.setattr(dispatch, "run_fuzzing_stage", _must_not_run_again)

    result2 = executor_for(JobKind.FUZZ)(_ctx(mission, job))
    assert result2.outcome == JobOutcome.SUCCEEDED
    assert Finding.objects.filter(mission=mission).count() == 1
    assert FuzzingReport.objects.filter(mission=mission).count() == 1


# ---------------------------------------------------------------------------------
# 4. JobKind.MINIMIZE — real, registered, honest about being structurally blocked
# ---------------------------------------------------------------------------------


def test_minimize_executor_is_real_not_a_not_implemented_stub(mission: Mission):
    job = Job.objects.create(
        mission=mission,
        kind=JobKind.MINIMIZE,
        state=JobState.RUNNING,
        attempt=1,
        max_attempts=1,
        run_after=NOW,
        deadline_at=NOW + timedelta(minutes=30),
    )
    result = executor_for(JobKind.MINIMIZE)(_ctx(mission, job))

    assert result.outcome == JobOutcome.FAILED
    assert result.result["infra_failure"] is True
    assert result.result["blocked_reason"] == "minimize_not_implemented"
    assert result.retry is False


def test_minimize_transition_policy_never_transitions_the_mission():
    policy = transition_policy_for(JobKind.MINIMIZE)
    job = Job(kind=JobKind.MINIMIZE, state=JobState.FAILED, result={})
    assert policy(job, Mission()) is None
