"""`JobKind.PATCH_GENERATE` executor + transition policy (#168, T4 / T4-lite).

Five shapes of test, mirroring the assignment and `test_cancelling_dispatch.py`'s own
precedent for "exercise the transition through the real dispatcher, not just the policy
function" (the class of gap PR #173's review found for `TEARDOWN`):

1. Registration against the shared contract.
2. The attempt-scoped idempotency property that is `PATCH_GENERATE`'s one named
   exception to D-061 §3 rule 2 (resume from however many candidates already exist,
   not "does one exist at all").
3. The degradation ladder (architecture spec §6.4): a transport retry, then a
   context-reduction retry, before an attempt is recorded as failed.
4. Transition-policy unit tests: `infra_failure` -> `FAILED`, a `CANCELLED` job ->
   `None`, cross-checked against the real state machine.
5. End to end through `orchestrator.queue.dispatch_terminal_jobs` — real `claim_job`/
   `mark_running`/`complete_job`, the real executor, the real dispatcher — for both the
   success path (`PATCH -> VERIFY`) and the all-attempts-exhausted path
   (`PATCH -> HUMAN_REVIEW`).

Every test that needs the gateway package itself uses `FakeLiveBackend`-shaped stand-ins
against the *real* `gateway.service.ModelGateway`/`gateway.context.build_context`/
`request_patch` code path — the same pattern `services/model-gateway/gateway/tests/
conftest.py` already uses for its own suite — rather than mocking this module's own
gateway calls away. Only the HTTP layer (`gateway.ollama.OllamaCodeLlamaBackend`) is
replaced; `record_patch_candidate`, the patch policy, and every Django write are real.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

import pytest

from contracts.enums import ErrorCode, MissionState
from missions.models import Job, JobKind, JobState, Mission, PatchCandidate
from orchestrator import candidates as candidates_module
from orchestrator import executors, queue, transitions
from orchestrator import patch_generate_executor as pge
from orchestrator.executors import ExecutorContext, JobOutcome
from orchestrator.tests.conftest import CANDIDATE_A, CANDIDATE_P, NOW, TRACE, walk_to

pytestmark = pytest.mark.django_db(transaction=True)

pge._ensure_gateway_importable()

from gateway.errors import LiveGenerationError  # noqa: E402
from gateway.schemas import PatchCandidate as GatewayPatchCandidate  # noqa: E402
from gateway.service import build_gateway  # noqa: E402
from gateway.settings import GatewayMode, GatewaySettings  # noqa: E402

CANDIDATE_A_DIFF = CANDIDATE_A.read_text()
CANDIDATE_P_DIFF = CANDIDATE_P.read_text()


@dataclass
class ScriptedBackend:
    """A stand-in for a served model — real `LiveBackend` protocol, scripted
    outcomes. Mirrors `services/model-gateway/gateway/tests/conftest.py`'s
    `FakeLiveBackend`/`ExplodingLiveBackend`, combined so a single instance can
    script a mixed sequence (fail, fail, succeed) across the degradation ladder.
    """

    model_name: str = "fake-code-model"
    model_revision: str = "test"
    model_artifact_sha256: str = "c" * 64
    served_from: str = "http://127.0.0.1:8080/v1"
    #: One entry consumed per call. An `Exception` instance is raised; anything else
    #: is treated as the diff text for a successful `PatchCandidate`.
    script: list[object] = field(default_factory=lambda: [CANDIDATE_A_DIFF])
    calls: list[str] = field(default_factory=list)

    def generate(self, request):
        self.calls.append(request.prompt_sha256)
        index = min(len(self.calls) - 1, len(self.script) - 1)
        outcome = self.script[index]
        if isinstance(outcome, Exception):
            raise outcome
        candidate = GatewayPatchCandidate(diff=outcome, rationale="scripted", confidence=0.5)
        return candidate, 10, 8


def _gateway(backend: ScriptedBackend):
    settings = GatewaySettings(mode=GatewayMode.LIVE, endpoint="", resolve_endpoint=False)
    return build_gateway(settings, live_backend=backend)


def _patch_gateway(monkeypatch, backend: ScriptedBackend) -> None:
    # `_build_gateway_settings` reads `MODEL_GATEWAY_MODE` from the real environment,
    # which the test process never sets (see .env.example — it has no default on
    # purpose). Every test that scripts a backend patches both halves so the
    # scripted backend is what actually answers, not a settings failure.
    monkeypatch.setattr(pge, "_build_gateway_settings", lambda: None)
    monkeypatch.setattr(pge, "_build_gateway", lambda settings: _gateway(backend))


def _job(mission: Mission, *, state: str = JobState.RUNNING, result: dict | None = None) -> Job:
    return Job.objects.create(
        mission=mission,
        kind=JobKind.PATCH_GENERATE,
        state=state,
        result=result or {},
        attempt=1,
        max_attempts=1,
        run_after=NOW,
        deadline_at=NOW + timedelta(minutes=30),
    )


def _ctx(mission: Mission, job: Job, *, cancelled: bool = False) -> ExecutorContext:
    return ExecutorContext(
        job=job,
        mission=mission,
        source_dir=Path("/tmp/unused-source"),
        workspace_root=Path("/tmp/unused-workspace"),
        trace_id=TRACE,
        cancel_requested=lambda: cancelled,
    )


def _small_attempts(mission: Mission, n: int) -> None:
    policy = dict(mission.policy or {})
    policy["patch_generation_attempts"] = n
    mission.policy = policy
    mission.save(update_fields=["policy"])


# --------------------------------------------------------------------------------
# 1. Registration
# --------------------------------------------------------------------------------


def test_patch_generate_is_registered_against_the_shared_contract():
    assert executors.executor_for(JobKind.PATCH_GENERATE) is pge._patch_generate_executor
    assert (
        executors.transition_policy_for(JobKind.PATCH_GENERATE)
        is pge._patch_generate_transition_policy
    )


# --------------------------------------------------------------------------------
# 2. Attempt-scoped idempotency (D-061 §3's named exception for this kind)
# --------------------------------------------------------------------------------


def test_executor_resumes_from_already_recorded_candidates_not_from_zero(
    mission: Mission, finding, monkeypatch
):
    """Two `PatchCandidate` rows already exist for this mission (a prior partial
    run). `attempts_target=3`, so the executor must make exactly one more call, not
    three — the "did this attempt already produce a candidate" check working."""
    walk_to(mission, MissionState.PATCH)
    _small_attempts(mission, 3)
    mission.refresh_from_db()

    candidates_module.record_patch_candidate(
        mission.id,
        finding_id=finding.id,
        provenance="OPERATOR_SUPPLIED",
        diff=CANDIDATE_A_DIFF,
        trace_id=TRACE,
        now=NOW,
    )
    candidates_module.record_patch_candidate(
        mission.id,
        finding_id=finding.id,
        provenance="OPERATOR_SUPPLIED",
        diff=CANDIDATE_A_DIFF,
        trace_id=TRACE,
        now=NOW,
    )
    assert PatchCandidate.objects.filter(mission=mission).count() == 2

    backend = ScriptedBackend(script=[CANDIDATE_A_DIFF])
    _patch_gateway(monkeypatch, backend)

    job = _job(mission)
    result = pge._patch_generate_executor(_ctx(mission, job))

    assert len(backend.calls) == 1  # not 3 — resumed from the existing 2
    assert result.outcome is JobOutcome.SUCCEEDED
    assert result.result["candidates_recorded"] == 3
    assert result.result["already_recorded"] is False


def test_executor_short_circuits_when_the_target_is_already_met(mission: Mission, finding, monkeypatch):
    walk_to(mission, MissionState.PATCH)
    _small_attempts(mission, 1)
    mission.refresh_from_db()

    candidates_module.record_patch_candidate(
        mission.id,
        finding_id=finding.id,
        provenance="OPERATOR_SUPPLIED",
        diff=CANDIDATE_A_DIFF,
        trace_id=TRACE,
        now=NOW,
    )

    def _must_not_be_called(*_a, **_kw):  # pragma: no cover - assertion by side effect
        raise AssertionError("the gateway must not be built when the target is already met")

    monkeypatch.setattr(pge, "_build_gateway", _must_not_be_called)

    job = _job(mission)
    result = pge._patch_generate_executor(_ctx(mission, job))

    assert result.outcome is JobOutcome.SUCCEEDED
    assert result.result["already_recorded"] is True


# --------------------------------------------------------------------------------
# 3. The degradation ladder
# --------------------------------------------------------------------------------


def test_a_transient_failure_recovers_on_the_transport_retry(mission: Mission, finding, monkeypatch):
    walk_to(mission, MissionState.PATCH)
    _small_attempts(mission, 1)
    mission.refresh_from_db()

    backend = ScriptedBackend(script=[LiveGenerationError("timeout"), CANDIDATE_A_DIFF])
    _patch_gateway(monkeypatch, backend)

    job = _job(mission)
    result = pge._patch_generate_executor(_ctx(mission, job))

    assert len(backend.calls) == 2
    assert result.outcome is JobOutcome.SUCCEEDED
    assert result.result["degraded_attempts"] == 0
    assert result.result["generation_failures"] == 0


def test_a_failure_that_survives_the_transport_retry_recovers_on_reduced_context(
    mission: Mission, finding, monkeypatch
):
    walk_to(mission, MissionState.PATCH)
    _small_attempts(mission, 1)
    mission.refresh_from_db()
    finding.code_slice = "\n".join(f"line {i}" for i in range(30))
    finding.save(update_fields=["code_slice"])

    backend = ScriptedBackend(
        script=[LiveGenerationError("timeout"), LiveGenerationError("timeout"), CANDIDATE_A_DIFF]
    )
    _patch_gateway(monkeypatch, backend)

    job = _job(mission)
    result = pge._patch_generate_executor(_ctx(mission, job))

    assert len(backend.calls) == 3
    assert result.outcome is JobOutcome.SUCCEEDED
    assert result.result["degraded_attempts"] == 1


def test_every_rung_failing_records_one_generation_failure_and_moves_on(
    mission: Mission, finding, monkeypatch
):
    walk_to(mission, MissionState.PATCH)
    _small_attempts(mission, 2)
    mission.refresh_from_db()

    backend = ScriptedBackend(
        script=[
            LiveGenerationError("down"),
            LiveGenerationError("down"),
            LiveGenerationError("down"),
            CANDIDATE_A_DIFF,
        ]
    )
    _patch_gateway(monkeypatch, backend)

    job = _job(mission)
    result = pge._patch_generate_executor(_ctx(mission, job))

    assert len(backend.calls) == 4  # 3 rungs for attempt 1, 1 call for attempt 2
    assert result.outcome is JobOutcome.SUCCEEDED
    assert result.result["generation_failures"] == 1
    assert result.result["accepted_count"] == 1


def test_policy_rejected_diffs_are_recorded_but_do_not_count_as_accepted(
    mission: Mission, finding, monkeypatch
):
    walk_to(mission, MissionState.PATCH)
    _small_attempts(mission, 1)
    mission.refresh_from_db()

    backend = ScriptedBackend(script=[CANDIDATE_P_DIFF])
    _patch_gateway(monkeypatch, backend)

    job = _job(mission)
    result = pge._patch_generate_executor(_ctx(mission, job))

    assert result.outcome is JobOutcome.FAILED
    assert result.error_code is ErrorCode.PATCH_POLICY_REJECTED
    assert result.result["candidates_recorded"] == 1
    assert result.result["accepted_count"] == 0


# --------------------------------------------------------------------------------
# Cancellation
# --------------------------------------------------------------------------------


def test_cancel_requested_before_start_short_circuits(mission: Mission, finding, monkeypatch):
    def _must_not_be_called(*_a, **_kw):  # pragma: no cover
        raise AssertionError("the gateway must not be built after a pre-flight cancel")

    monkeypatch.setattr(pge, "_build_gateway", _must_not_be_called)
    walk_to(mission, MissionState.PATCH)

    job = _job(mission)
    result = pge._patch_generate_executor(_ctx(mission, job, cancelled=True))

    assert result.outcome is JobOutcome.CANCELLED
    assert PatchCandidate.objects.filter(mission=mission).count() == 0


# --------------------------------------------------------------------------------
# 4. Transition-policy unit tests
# --------------------------------------------------------------------------------


def test_transition_policy_routes_infra_failure_to_failed(mission: Mission):
    walk_to(mission, MissionState.PATCH)
    job = _job(mission, state=JobState.FAILED, result={"infra_failure": True})

    target = pge._patch_generate_transition_policy(job, mission)

    assert target is MissionState.FAILED
    transitions.transition(mission.id, target, trace_id=TRACE, now=NOW)
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.FAILED


def test_transition_policy_routes_zero_accepted_to_human_review(mission: Mission):
    walk_to(mission, MissionState.PATCH)
    job = _job(mission, state=JobState.FAILED, result={"accepted_count": 0})

    target = pge._patch_generate_transition_policy(job, mission)

    assert target is MissionState.HUMAN_REVIEW
    transitions.transition(mission.id, target, trace_id=TRACE, now=NOW)
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.HUMAN_REVIEW


def test_transition_policy_defers_on_a_cancelled_job(mission: Mission):
    walk_to(mission, MissionState.PATCH)
    job = _job(mission, state=JobState.CANCELLED, result={})

    assert pge._patch_generate_transition_policy(job, mission) is None


# --------------------------------------------------------------------------------
# 5. End to end through the real dispatcher
# --------------------------------------------------------------------------------


def _run_real_patch_generate_job(job: Job, mission: Mission) -> Job:
    claimed = queue.claim_job("test-worker-1", now=NOW)
    assert claimed is not None and claimed.id == job.id
    assert queue.mark_running(claimed.id, "test-worker-1", now=NOW)

    executor = executors.executor_for(JobKind.PATCH_GENERATE)
    result = executor(_ctx(mission, claimed))

    job_state = JobState.SUCCEEDED if result.outcome is JobOutcome.SUCCEEDED else JobState.FAILED
    assert queue.complete_job(claimed.id, "test-worker-1", job_state, result=result.result, now=NOW)
    claimed.refresh_from_db()
    return claimed


def test_a_successful_generation_walks_from_patch_to_verify_through_the_real_dispatcher(
    mission: Mission, finding, monkeypatch
):
    walk_to(mission, MissionState.PATCH)
    _small_attempts(mission, 1)
    mission.refresh_from_db()

    backend = ScriptedBackend(script=[CANDIDATE_A_DIFF])
    _patch_gateway(monkeypatch, backend)

    enqueued = queue.ensure_jobs_enqueued(now=NOW)
    assert [j.mission_id for j in enqueued] == [mission.id]
    job = Job.objects.get(mission=mission, kind=JobKind.PATCH_GENERATE)

    completed = _run_real_patch_generate_job(job, mission)
    assert completed.state == JobState.SUCCEEDED

    advanced = queue.dispatch_terminal_jobs(trace_id=TRACE, now=NOW)

    assert advanced == [mission.id]
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.VERIFY
    row = PatchCandidate.objects.get(mission=mission)
    assert row.provenance == "MODEL_GENERATED"
    assert row.model_provenance["model_name"] == "fake-code-model"
    assert row.policy_status == "ACCEPTED"


def test_exhausting_every_attempt_walks_from_patch_to_human_review_through_the_real_dispatcher(
    mission: Mission, finding, monkeypatch
):
    walk_to(mission, MissionState.PATCH)
    _small_attempts(mission, 1)
    mission.refresh_from_db()

    backend = ScriptedBackend(script=[LiveGenerationError("model host unreachable")])
    _patch_gateway(monkeypatch, backend)

    queue.ensure_jobs_enqueued(now=NOW)
    job = Job.objects.get(mission=mission, kind=JobKind.PATCH_GENERATE)

    completed = _run_real_patch_generate_job(job, mission)
    assert completed.state == JobState.FAILED
    assert completed.result["accepted_count"] == 0
    assert completed.result["generation_failures"] == 1

    advanced = queue.dispatch_terminal_jobs(trace_id=TRACE, now=NOW)

    assert advanced == [mission.id]
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.HUMAN_REVIEW
    assert PatchCandidate.objects.filter(mission=mission).count() == 0


def test_a_missing_finding_walks_from_patch_to_failed_through_the_real_dispatcher(
    mission: Mission, monkeypatch
):
    """No `Finding` row at all — a pipeline gap upstream, not a model or policy
    outcome — routes to `Mission.FAILED`, never `HUMAN_REVIEW`."""
    walk_to(mission, MissionState.PATCH)

    def _must_not_be_called(*_a, **_kw):  # pragma: no cover
        raise AssertionError("the gateway must not be built with no finding to patch")

    monkeypatch.setattr(pge, "_build_gateway", _must_not_be_called)

    queue.ensure_jobs_enqueued(now=NOW)
    job = Job.objects.get(mission=mission, kind=JobKind.PATCH_GENERATE)

    completed = _run_real_patch_generate_job(job, mission)
    assert completed.state == JobState.FAILED
    assert completed.result["infra_failure"] is True

    advanced = queue.dispatch_terminal_jobs(trace_id=TRACE, now=NOW)

    assert advanced == [mission.id]
    mission.refresh_from_db()
    assert mission.state_enum is MissionState.FAILED


# --------------------------------------------------------------------------------
# Deadline: the queue-level override this task added
# --------------------------------------------------------------------------------


def test_default_deadline_seconds_scales_with_the_attempts_target():
    from orchestrator.queue import default_deadline_seconds

    assert default_deadline_seconds(JobKind.PATCH_GENERATE, {}) == max(1800, 10 * 360)
    assert (
        default_deadline_seconds(JobKind.PATCH_GENERATE, {"patch_generation_attempts": 2})
        == 1800  # floor, not 2 * 360
    )
    assert (
        default_deadline_seconds(JobKind.PATCH_GENERATE, {"patch_generation_attempts": 20})
        == 20 * 360
    )
