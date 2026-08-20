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
5. Gateway misconfiguration: the real `_build_gateway_settings`/`_build_gateway` path
   (not the `_patch_gateway` scripted stand-in), against a real
   `ExternalInferenceBlockedError` (an out-of-boundary `MODEL_ENDPOINT`) and a real
   `GatewayConfigurationError` (an unset `MODEL_GATEWAY_MODE`) — the fail-closed
   behaviour cybersecurity's PR #196 review reproduced by hand (LOW finding: "no unit
   test exercises the gateway-misconfiguration/`infra_failure` path"). Confirms
   `infra_failure`/`gateway_misconfigured` is set, the job fails closed, and no
   repository content is ever built for the model (`_context_finding` must not be
   called).
6. End to end through `orchestrator.queue.dispatch_terminal_jobs` — real `claim_job`/
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
from gateway.ollama import OllamaCodeLlamaBackend  # noqa: E402
from gateway.schemas import GenerationRequest  # noqa: E402
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
# 0. `_model_gateway_root()` — D-100 (`.project/decisions.md`)
# --------------------------------------------------------------------------------
#
# #50 D7 gate rehearsal run 4 (D-098): `_model_gateway_root()` used to be
# `Path(__file__).resolve().parents[3] / "services" / "model-gateway"` — bare-metal
# only. `IndexError` inside either compose profile's container, live, both times
# PATCH_GENERATE's live-model path actually ran.


def test_the_old_relative_parent_indexing_would_fail_inside_either_container():
    """Documents the exact failure mechanism D-098 reproduced live, independent of
    however `_model_gateway_root()` is implemented today: `parents[3]` assumed a
    bare-metal checkout depth (`repo_root/apps/control-api/orchestrator/file.py`, 4
    parent levels to repo root) that neither compose profile's flattened container
    layout has (`/app/orchestrator/file.py` — `/app/orchestrator`, `/app`, `/` is the
    whole chain, only 3 entries, indices 0-2)."""
    container_module_path = Path("/app/orchestrator/patch_generate_executor.py")
    with pytest.raises(IndexError):
        container_module_path.resolve().parents[3]


def test_model_gateway_root_is_driven_by_django_settings_not_file_depth(settings, tmp_path):
    """The fix: `_model_gateway_root()` reads `settings.MODEL_GATEWAY_ROOT`, which
    each compose profile now sets explicitly (`infrastructure/compose/docker-
    compose*.yml`), rather than deriving anything from `__file__`'s own location.
    Proven by pointing the setting at a directory with zero relationship to this
    module's path on disk — if `_model_gateway_root()` still touched `__file__`
    depth in any way, it could not possibly return this exact, unrelated path.

    This is the test that would have caught the original bug: against the pre-D-100
    code (`Path(__file__).resolve().parents[3] / "services" / "model-gateway"`),
    `MODEL_GATEWAY_ROOT` was never read at all, so this assertion would have failed
    (the old code returns the bare-metal repo-relative path regardless of what this
    setting says) well before ever reaching the container-only `IndexError` case
    covered by the test above.
    """
    custom_root = tmp_path / "wherever" / "gateway-happens-to-live"
    settings.MODEL_GATEWAY_ROOT = str(custom_root)

    assert pge._model_gateway_root() == custom_root


def test_model_gateway_root_default_resolves_to_the_real_importable_package():
    """Sanity check for the bare-metal default this checkout actually runs under
    pytest: `config.settings.base.MODEL_GATEWAY_ROOT`'s own `REPO_ROOT`-relative
    default (unset `MODEL_GATEWAY_ROOT` env var, the common case) must land on the
    real `services/model-gateway/gateway` package — not merely some path — so
    `_ensure_gateway_importable`'s `sys.path` insert actually makes `import gateway`
    resolve, exactly as this test module's own `pge._ensure_gateway_importable()`
    call (module scope, above) already relies on."""
    root = pge._model_gateway_root()
    assert (root / "gateway" / "__init__.py").is_file()


# --------------------------------------------------------------------------------
# 0.5. `_build_live_backend` threads the D-075/SEC-50 bearer token (D-105/D-106)
#
# #50 D7 gate rehearsal run 5 (D-105, `.project/decisions.md`): `_build_live_backend`
# constructed `OllamaCodeLlamaBackend(endpoint=...)` without `bearer_token=settings.
# model_host_bearer_token`, even though `GatewaySettings.model_host_bearer_token` was
# already computed correctly from `MODEL_HOST_BEARER_TOKEN` and `OllamaCodeLlamaBackend.
# bearer_token` was already a real field — the two were simply never connected. Every
# live-model `PATCH_GENERATE` call against the compose `model` profile's `model-host-
# auth` sidecar got a real `HTTP 401` instead of ever reaching Ollama.
# --------------------------------------------------------------------------------


def test_build_live_backend_threads_the_bearer_token_from_settings():
    """Narrow regression: the field must actually be passed through, not merely
    exist on both sides."""
    settings = GatewaySettings(
        mode=GatewayMode.LIVE,
        endpoint="http://model-host:11434",
        resolve_endpoint=False,
        model_host_bearer_token="s3cr3t-sidecar-token",
    )

    backend = pge._build_live_backend(settings)

    assert backend.bearer_token == "s3cr3t-sidecar-token"


def test_build_live_backend_defaults_to_no_bearer_token(monkeypatch):
    """The other half of the same regression: an unconfigured token must not become
    a non-empty one by accident (e.g. `None` -> the literal string `"None"`), the
    same "blank is legal, send nothing" contract `OllamaCodeLlamaBackend`'s own
    docstring describes for a bare loopback `ollama serve`."""
    settings = GatewaySettings(
        mode=GatewayMode.LIVE,
        endpoint="http://127.0.0.1:11434",
        resolve_endpoint=False,
    )

    backend = pge._build_live_backend(settings)

    assert backend.bearer_token == ""


def _fake_sidecar_urlopen(seen: dict, *, required_token: str):
    """Stand-in for the real `model-host-auth` nginx sidecar (D-075/SEC-50): reject
    any request whose `Authorization` header isn't exactly `Bearer <required_token>`
    with the same `HTTPError(401)` `urllib` itself raises for a real `401` response,
    accept everything else. Mirrors `services/model-gateway/gateway/tests/
    test_ollama_backend.py::_make_fake_urlopen`'s shape; faking the sidecar's one
    decision here is the same pattern that module already uses to fake Ollama
    itself, and standing up a real nginx sidecar in a unit test is neither practical
    nor how the rest of this suite tests the gateway boundary.
    """
    import io
    import json
    import urllib.error

    def fake_urlopen(request, timeout):
        seen["authorization"] = request.get_header("Authorization")
        if seen["authorization"] != f"Bearer {required_token}":
            raise urllib.error.HTTPError(
                request.full_url, 401, "Unauthorized", hdrs=None, fp=io.BytesIO(b"")
            )
        body = json.dumps(
            {
                "message": {
                    "content": json.dumps(
                        {
                            "diff": CANDIDATE_A_DIFF,
                            "rationale": "sidecar-authenticated",
                            "touched_files": ["src/parse.c"],
                            "confidence": 0.6,
                        }
                    )
                },
                "eval_count": 7,
            }
        ).encode("utf-8")

        class _FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return body

        return _FakeResponse()

    return fake_urlopen


def test_live_backend_built_by_this_module_gets_401_from_the_sidecar_without_the_fix(
    monkeypatch,
):
    """Reproduces the original bug directly: a backend built with no bearer token
    (the pre-fix call shape) against a fake sidecar that requires one fails with the
    exact `HTTPError(401)` #50 D7 gate rehearsal run 5 hit live."""
    import urllib.error

    seen: dict = {}
    monkeypatch.setattr(
        "gateway.client.urlopen",
        _fake_sidecar_urlopen(seen, required_token="s3cr3t-sidecar-token"),
    )

    settings = GatewaySettings(
        mode=GatewayMode.LIVE,
        endpoint="http://model-host:11434/api",
        resolve_endpoint=False,
        # No model_host_bearer_token — irrelevant here: the point of this test is
        # the pre-fix *call site*, which never read the field at all.
    )
    # The exact pre-fix call shape (`_build_live_backend` before D-106): no
    # `bearer_token=` kwarg reaches `OllamaCodeLlamaBackend` at all.
    backend = OllamaCodeLlamaBackend(endpoint=settings.endpoint)

    request = GenerationRequest(
        mission_id="m-0001",
        prompt="Fix the off-by-one.",
        prompt_version="patch-prompt/3",
    )

    with pytest.raises(urllib.error.HTTPError) as excinfo:
        backend.generate(request)
    assert excinfo.value.code == 401


def test_live_backend_built_by_this_module_authenticates_through_the_sidecar(monkeypatch):
    """The fix, end to end: `_build_live_backend` (this module's real call site, not
    a hand-rolled stand-in) against the same fake sidecar now succeeds, because the
    backend it constructs actually carries and sends the configured token."""
    seen: dict = {}
    monkeypatch.setattr(
        "gateway.client.urlopen",
        _fake_sidecar_urlopen(seen, required_token="s3cr3t-sidecar-token"),
    )

    settings = GatewaySettings(
        mode=GatewayMode.LIVE,
        endpoint="http://model-host:11434/api",
        resolve_endpoint=False,
        model_host_bearer_token="s3cr3t-sidecar-token",
    )
    backend = pge._build_live_backend(settings)

    request = GenerationRequest(
        mission_id="m-0001",
        prompt="Fix the off-by-one.",
        prompt_version="patch-prompt/3",
    )
    candidate, _wall_time_ms, _output_tokens = backend.generate(request)

    assert seen["authorization"] == "Bearer s3cr3t-sidecar-token"
    assert candidate.rationale == "sidecar-authenticated"


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
# 4. Gateway misconfiguration: fails closed, before any repository content is built.
#
# Unlike every test above, these two do NOT use `_patch_gateway` — that helper
# replaces `_build_gateway_settings`/`_build_gateway` with a scripted stand-in
# precisely so tests don't hit the real settings-validation path. Here that path is
# the thing under test: the real `gateway.settings.from_environment` /
# `gateway.endpoint_policy.classify` boundary check, exercised end to end through
# the executor's own `except GatewayError` branch.
# --------------------------------------------------------------------------------


def test_endpoint_outside_the_boundary_fails_closed_before_any_content_is_sent(
    mission: Mission, finding, monkeypatch
):
    """`MODEL_ENDPOINT` pointed at a known hosted inference provider must raise
    `ExternalInferenceBlockedError` (a `GatewayError`) out of the real
    `gateway.settings.from_environment` -> `gateway.endpoint_policy.classify` path,
    and the executor must catch it, record `infra_failure`/`gateway_misconfigured`,
    and never build repository content for the model. This is the exact scenario
    cybersecurity's PR #196 review reproduced by hand (LOW finding: no unit test
    covered it) — see `gateway/endpoint_policy.py::_KNOWN_HOSTED_INFERENCE_HOSTS`.
    """
    walk_to(mission, MissionState.PATCH)
    monkeypatch.setenv("MODEL_GATEWAY_MODE", "live")
    monkeypatch.setenv("MODEL_ENDPOINT", "https://api.openai.com/v1")
    monkeypatch.delenv("SMALL_MODEL_BASE_URL", raising=False)

    def _must_not_be_called(*_a, **_kw):  # pragma: no cover - assertion by side effect
        raise AssertionError(
            "no repository content may be built once the gateway is misconfigured"
        )

    monkeypatch.setattr(pge, "_context_finding", _must_not_be_called)

    job = _job(mission)
    result = pge._patch_generate_executor(_ctx(mission, job))

    assert result.outcome is JobOutcome.FAILED
    assert result.error_code is ErrorCode.MODEL_CAPACITY_UNAVAILABLE
    assert result.result["infra_failure"] is True
    assert result.result["reason"] == "gateway_misconfigured"
    assert "api.openai.com" in result.detail
    assert PatchCandidate.objects.filter(mission=mission).count() == 0


def test_unset_gateway_mode_fails_closed_before_any_content_is_sent(
    mission: Mission, finding, monkeypatch
):
    """`MODEL_GATEWAY_MODE` unset is a `GatewayConfigurationError` (also a
    `GatewayError`, per `gateway/settings.py::from_environment`'s own docstring), not
    a live/replay ambiguity resolved silently. Same fail-closed contract as the
    boundary-violation case above, different exception type."""
    walk_to(mission, MissionState.PATCH)
    monkeypatch.delenv("MODEL_GATEWAY_MODE", raising=False)
    monkeypatch.delenv("MODEL_ENDPOINT", raising=False)
    monkeypatch.delenv("SMALL_MODEL_BASE_URL", raising=False)

    def _must_not_be_called(*_a, **_kw):  # pragma: no cover - assertion by side effect
        raise AssertionError(
            "no repository content may be built once the gateway is misconfigured"
        )

    monkeypatch.setattr(pge, "_context_finding", _must_not_be_called)

    job = _job(mission)
    result = pge._patch_generate_executor(_ctx(mission, job))

    assert result.outcome is JobOutcome.FAILED
    assert result.error_code is ErrorCode.MODEL_CAPACITY_UNAVAILABLE
    assert result.result["infra_failure"] is True
    assert result.result["reason"] == "gateway_misconfigured"
    assert PatchCandidate.objects.filter(mission=mission).count() == 0


# --------------------------------------------------------------------------------
# 5. Transition-policy unit tests
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
# 6. End to end through the real dispatcher
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
