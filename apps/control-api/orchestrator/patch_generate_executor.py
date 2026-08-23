"""`JobKind.PATCH_GENERATE` executor and transition policy (#168, T4 / T4-lite).

## Scope: T4-lite, per D-062

D-061 §4's literal brief for T4 included finishing D-026's package relocation
(`services/model-gateway/` → `apps/control-api/gateway/`). D-062 (`.project/
decisions.md`) de-scoped that: this module wires `JobKind.PATCH_GENERATE` against the
gateway package **at its current location**, `services/model-gateway/gateway/`, and
does not move it. The relocation is a fast-follow after 2026-08-20, tracked
separately — not this module's job, and nothing here assumes the move has happened.

## Why nothing in this module imports `gateway.*` at the top level

`missions.apps.MissionsConfig.ready()` imports this module (for its
`@register_executor`/`@register_transition_policy` side effects) on **every** process
that touches the `Job`/`Mission` models — `manage.py check`, `runserver`, the ASGI
process, and `run_worker`/`run_orchestrator` alike (see that file's own docstring).
D-028/C5 (`tests/architecture/test_import_direction.py::
test_importing_the_asgi_app_does_not_load_the_gateway`) requires that `gateway.*`
never load inside the ASGI process — it is the one package permitted to hold an
inference client, and the whole point of the two-process split (worker holds
repository content and a route to the model; control-api does not) collapses the
moment an import edge connects them. `orchestrator/model_host.py` and
`orchestrator/transitions.py` already use the same discipline for a different
reason (compose/subprocess); here it is load-bearing for a security invariant, not
just tidiness. Every `from gateway...` import in this module is therefore inside a
function body, never at module scope, and `_ensure_gateway_importable()` (the one
thing that touches `sys.path`) is the only module-scope side effect, and it mutates
nothing until it is actually called — which only happens from inside this module's
own executor function, which only `run_worker`'s claim loop ever invokes.

## The fan-out: one `Job`, N generations internally

Architecture spec §3.4: `PATCH_GENERATE` is `"1 job, N attempts internally."` T0's
`orchestrator/queue.py::ensure_jobs_enqueued` confirms this is the ratified, later
design (it postdates D-061 §3's own text): *"PATCH_GENERATE/VERIFY are one job each
with fan-out *inside* them"* — and `MAX_ATTEMPTS_BY_KIND[JobKind.PATCH_GENERATE]` is
`1` (`missions/models.py`), so there is no job-level retry to speak of; a lease
timeout on this job goes straight to `FAILED` (`reap_expired_leases`), never back to
`QUEUED`. D-061 §3's own text names `PATCH_GENERATE` as the one exception to "check
your stage's terminal artifact before doing real work," phrased as "using the job's
attempt field" — read literally that cannot mean `Job.attempt` (constant at `1` for
this kind for the reasons above); it means the *internal* generation-attempt index,
which is what `_patch_generate_executor` below actually keys its within-run
idempotency on: before generating attempt *i*, it has already recorded
`i - 1` candidates for this mission this run, and a genuine re-entry into this
function (there is no code path that produces one today, but nothing prevents a
future caller) resumes from `PatchCandidate.objects.filter(mission=...).count()`
rather than re-fanning-out from zero.

## The degradation ladder (architecture spec §6.4)

Per fan-out attempt, in order: (1) the call as configured; (2) one transport retry
with the same context — `services/model-gateway`'s own HTTP layer
(`gateway/client.py`) has no retry of its own, so this lives here, not in the
gateway package, consistent with T4-lite leaving that package's internals alone;
(3) one context-reduction retry (`_reduced_code_slice` — the spec's "±40-line slice
instead of ±120," approximated as the middle third of `Finding.code_slice`'s lines,
since T3/CORRELATE — not yet merged to this branch — is what would define an exact
line-window convention and this module cannot assume one exists); then the attempt
is recorded as failed (`ErrorCode.MODEL_CAPACITY_UNAVAILABLE`) and the run moves to
the next attempt, never retrying the whole ladder. `gateway.errors.
LiveBackendUnavailableError` (no live backend configured at all — a build-time fact,
not a transient one) skips the ladder outright; retrying or reducing context cannot
change it.

## The one rule this module exists to keep clean

CLAUDE.md: "A patch is never accepted on model confidence alone." This module
GENERATES candidates and hands every one of them — accepted or not — to
`orchestrator.candidates.record_patch_candidate`, which runs the actual policy gate
(`orchestrator.patch_policy.evaluate_patch_policy`) and persists the real, computed
`policy_status`. Nothing here reads `PatchCandidate.confidence`/`ModelProvenance.
confidence` to decide anything — it is recorded because the schema records it, never
branched on.
"""

from __future__ import annotations

import sys
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from contracts.enums import (
    ErrorCode,
    EventStatus,
    EventType,
    MissionStage,
    MissionState,
    PatchPolicyStatus,
    PatchProvenance,
    Severity,
)
from contracts.errors import CandidateSetFrozenError
from contracts.schemas.evidence import ModelProvenance
from contracts.schemas.missions import MissionPolicy
from missions.models import Finding, Job, JobKind, JobState, Mission, PatchCandidate
from orchestrator import candidates as candidates_module
from orchestrator import events
from orchestrator.executors import (
    ExecutorContext,
    ExecutorResult,
    JobOutcome,
    register_executor,
    register_transition_policy,
)

__all__: list[str] = []

#: `_reduced_code_slice`'s ratio target — the spec's "±40-line slice instead of
#: ±120" is 1/3. See this module's docstring, "The degradation ladder."
_REDUCED_SLICE_RATIO = 3


# ---------------------------------------------------------------------------------
# Lazy gateway access — see this module's docstring for why none of this runs at
# import time.
# ---------------------------------------------------------------------------------


def _model_gateway_root() -> Path:
    """Directory containing the importable `gateway` package.

    D-100 (`.project/decisions.md`): this used to compute the path itself —
    `Path(__file__).resolve().parents[3] / "services" / "model-gateway"` — which
    assumed a bare-metal checkout depth (`repo_root/apps/control-api/orchestrator/
    file.py`, 4 parent levels to repo root) that neither compose profile's flattened
    container layout has (`/app/orchestrator/file.py`, 2 real parent levels).
    `parents[3]` raised `IndexError` the instant PATCH_GENERATE's live-model path
    actually ran inside either container — found live, #50 D7 gate rehearsal run 4
    (D-098).

    Delegated to `settings.MODEL_GATEWAY_ROOT` instead, the same shape
    `SNAPSHOT_SOURCE_ROOT` already established (`config/settings/base.py`) for the
    identical class of problem (`demo/repositories`'s bare-metal-only default):
    correct by default on bare metal, explicitly overridden by each compose profile
    for its own container layout rather than guessed at here. Reading `django.conf.
    settings` (not `gateway.*`) is fine at any point in this module — the import
    discipline this module's own docstring describes is specifically about the
    gateway package itself, not Django settings.
    """
    from django.conf import settings

    return Path(settings.MODEL_GATEWAY_ROOT)


def _ensure_gateway_importable() -> None:
    """Put `services/model-gateway` on `sys.path`, once, lazily, in this process only.

    Deliberately not done in `config/settings/base.py`, which puts `REPO_ROOT` on
    `sys.path` for *every* process including the ASGI one — doing the same here
    would make `import gateway` resolvable (though still unimported) from a request
    handler, which is a smaller version of the same mistake this module's docstring
    is about. This function is only ever called from inside `_patch_generate_executor`
    or a test that says so explicitly.
    """
    root = str(_model_gateway_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def _build_gateway_settings():
    """`gateway.settings.GatewaySettings`, bridged from this process's own env names.

    The gateway package's own `from_environment()` reads `MODEL_ENDPOINT`; the
    control API's existing convention (`config/settings/base.py::MODEL_ENDPOINTS`,
    predating this module) is `SMALL_MODEL_BASE_URL`. Nothing before this task wired
    the two together (checked directly: neither name appears in the other's
    settings module). Rather than silently renaming either — `SMALL_MODEL_BASE_URL`
    is ml-infra-engineer's name, `MODEL_ENDPOINT` is the gateway's own, and picking
    one is a naming call outside this task's authority — `MODEL_ENDPOINT` wins if an
    operator has set it explicitly, and `SMALL_MODEL_BASE_URL` is the fallback so a
    deployment that only set the control API's own variable still works. Flagged as
    a real naming split for ml-infra-engineer to resolve, not decided here.
    """
    import os

    from gateway.settings import from_environment

    env = dict(os.environ)
    if not env.get("MODEL_ENDPOINT"):
        fallback = env.get("SMALL_MODEL_BASE_URL", "")
        if fallback:
            env["MODEL_ENDPOINT"] = fallback
    return from_environment(env)


def _build_live_backend(settings):
    """`gateway.ollama.OllamaCodeLlamaBackend`, pointed at the configured endpoint.

    The only live backend this codebase has (D5, #35/#36) — constructed here, not
    imported at module scope, for the same reason as everything else in this
    section.

    `bearer_token=settings.model_host_bearer_token` is D-075/SEC-50, threaded through
    the same way `OllamaCodeLlamaBackend`'s own docstring names this exact scenario:
    the compose `model-host-auth` sidecar (`network_mode: "service:model-host"`)
    rejects every request without it once the `model` profile is in use. Found live,
    #50 D7 gate rehearsal run 5 (D-105, `.project/decisions.md`) — `GatewaySettings.
    model_host_bearer_token` was already computed correctly by `from_environment()`
    and `OllamaCodeLlamaBackend.bearer_token` was already a real field; this call site
    simply never connected the two, so every live-model `PATCH_GENERATE` call got a
    real `401` back from the sidecar instead of ever reaching Ollama.

    `timeout_sec=settings.model_host_timeout_seconds` is D-123: this backend's own
    dataclass default and the nginx sidecar's `proxy_read_timeout`/`proxy_send_timeout`
    used to be two independently hardcoded `300s` literals that only matched by
    coincidence. Threading the settings-derived value through here (rather than
    leaving this call site on the dataclass's own default) is what makes
    `MODEL_HOST_TIMEOUT_SECONDS` the actual single source of truth for the live
    `PATCH_GENERATE` path specifically, not just in principle.
    """
    from gateway.ollama import DEFAULT_OLLAMA_ENDPOINT, OllamaCodeLlamaBackend

    return OllamaCodeLlamaBackend(
        endpoint=settings.endpoint or DEFAULT_OLLAMA_ENDPOINT,
        bearer_token=settings.model_host_bearer_token,
        timeout_sec=settings.model_host_timeout_seconds,
    )


def _build_gateway(settings):
    from gateway.service import build_gateway
    from gateway.settings import GatewayMode

    live_backend = _build_live_backend(settings) if settings.mode is GatewayMode.LIVE else None
    return build_gateway(settings, live_backend=live_backend, capture_note="#168 T4")


# ---------------------------------------------------------------------------------
# Finding -> gateway context
# ---------------------------------------------------------------------------------


def _select_finding(mission: Mission) -> Finding | None:
    """The finding CORRELATE bound this mission to.

    T3/CORRELATE (not yet merged to this branch) is what will eventually stamp a
    single finding onto the mission or the job payload. Until then, the same
    selection any reader of `Finding` in this codebase already uses
    (`orchestrator/evidence_repository.py::list_findings`:
    `order_by("detected_at", "id")`), preferring a `reproducible` one — P0's own
    rule that only a reproduced finding is worth patching.
    """
    findings = Finding.objects.filter(mission=mission).order_by("detected_at", "id")
    reproducible = findings.filter(reproducible=True).first()
    return reproducible or findings.first()


def _context_finding(finding: Finding, mission: Mission):
    from gateway.context import ContextFinding

    reproducer = finding.reproducers.order_by("-created_at").first()
    reproducer_uri = None
    reproducer_sha256 = None
    if reproducer is not None:
        artifact = reproducer.artifact or {}
        reproducer_uri = artifact.get("uri")
        reproducer_sha256 = artifact.get("sha256")

    return ContextFinding(
        mission_id=str(mission.id),
        finding_id=str(finding.id),
        title=finding.title,
        category=str(finding.category),
        severity=str(finding.severity),
        file_path=finding.file_path,
        function=finding.function or None,
        sanitizer_report=finding.sanitizer_report or "",
        code_slice=finding.code_slice or "",
        reproducer_uri=reproducer_uri,
        reproducer_sha256=reproducer_sha256,
    )


def _context_policy(mission_policy: MissionPolicy):
    from gateway.context import ContextPolicy, PatchPolicyContext

    return ContextPolicy(
        patch=PatchPolicyContext(
            allowed_paths=tuple(mission_policy.patch.allowed_paths),
            max_files_changed=mission_policy.patch.max_files_changed,
            max_lines_changed=mission_policy.patch.max_lines_changed,
        ),
        reproducer_replay_attempts=mission_policy.reproducer_replay_attempts,
    )


def _reduced_code_slice(code_slice: str) -> str:
    """Rung 2 of the degradation ladder: a narrower code window, declared in
    advance. See this module's docstring, "The degradation ladder," for why this is
    a proportional reduction rather than a literal line-count match to the spec's
    ±40/±120 example."""
    lines = code_slice.splitlines()
    if len(lines) <= _REDUCED_SLICE_RATIO:
        return code_slice
    width = max(1, len(lines) // _REDUCED_SLICE_RATIO)
    start = (len(lines) - width) // 2
    return "\n".join(lines[start : start + width])


# ---------------------------------------------------------------------------------
# One fan-out attempt, with its own degradation ladder
# ---------------------------------------------------------------------------------


def _generate_once(gateway, context_finding, context_policy, *, reduced: bool):
    from gateway.context import build_context, request_patch

    finding_for_call = context_finding
    if reduced:
        finding_for_call = context_finding.model_copy(
            update={"code_slice": _reduced_code_slice(context_finding.code_slice)}
        )
    package = build_context(finding_for_call, context_policy)
    return request_patch(package, context_policy, gateway)


def _generate_with_ladder(gateway, context_finding, context_policy):
    """Rungs 1-3 of architecture spec §6.4 for one fan-out attempt.

    Returns `(GatewayResponse, degraded: bool)`. Raises the gateway's own error
    once every rung is exhausted; the caller records that as one failed attempt and
    moves on to the next fan-out index, never retries the whole ladder again for
    the same attempt.
    """
    from gateway.errors import GatewayError, LiveBackendUnavailableError

    last_exc: GatewayError | None = None
    for reduced in (False, False, True):
        try:
            return _generate_once(gateway, context_finding, context_policy, reduced=reduced), reduced
        except LiveBackendUnavailableError:
            # Rung 1 fact, not a transient one — nothing about a retry or a smaller
            # prompt changes "no live backend is configured." Fail this attempt now.
            raise
        except GatewayError as exc:  # three iterations, not a hot loop
            last_exc = exc
            continue
    assert last_exc is not None  # pragma: no cover - loop always assigns or returns
    raise last_exc


# ---------------------------------------------------------------------------------
# Recording one attempt's outcome
# ---------------------------------------------------------------------------------


def _record_generated_candidate(
    mission: Mission, finding: Finding, response, *, trace_id: str
) -> PatchCandidate:
    provenance = PatchProvenance(response.provenance.contract_patch_provenance())
    model = None
    if provenance is PatchProvenance.MODEL_GENERATED:
        model = ModelProvenance(**response.provenance.to_contract_dict())
    return candidates_module.record_patch_candidate(
        mission.id,
        finding_id=finding.id,
        provenance=provenance,
        diff=response.candidate.diff,
        trace_id=trace_id,
        model=model,
        rationale=response.candidate.rationale,
    )


def _emit_attempt_progress(
    mission: Mission, *, attempt: int, attempts_target: int, detail: str, trace_id: str, now
) -> None:
    with transaction.atomic():
        locked = Mission.objects.select_for_update().get(pk=mission.id)
        events.emit(
            locked,
            EventType.STAGE_PROGRESS,
            detail,
            {
                "kind": "stage_progress",
                "stage": str(MissionStage.PATCH),
                "percent_complete": round(100 * attempt / attempts_target, 1),
                "detail": detail,
            },
            trace_id=trace_id,
            stage=MissionStage.PATCH,
            state=locked.state_enum,
            timestamp=now,
        )


def _emit_attempt_failed(
    mission: Mission, *, attempt: int, detail: str, trace_id: str, now
) -> None:
    with transaction.atomic():
        locked = Mission.objects.select_for_update().get(pk=mission.id)
        events.emit(
            locked,
            EventType.LOG,
            detail,
            {"kind": "log", "text": detail},
            trace_id=trace_id,
            stage=MissionStage.PATCH,
            state=locked.state_enum,
            severity=Severity.MEDIUM,
            metrics={"patch_generation_attempt_failed": 1.0, "attempt": float(attempt)},
            timestamp=now,
        )


# ---------------------------------------------------------------------------------
# The executor
# ---------------------------------------------------------------------------------


@register_executor(JobKind.PATCH_GENERATE)
def _patch_generate_executor(ctx: ExecutorContext) -> ExecutorResult:
    now = timezone.now()
    mission = ctx.mission
    mission_policy = MissionPolicy.model_validate(mission.policy or {})
    attempts_target = mission_policy.patch_generation_attempts

    finding = _select_finding(mission)
    if finding is None:
        return ExecutorResult(
            outcome=JobOutcome.FAILED,
            detail="No Finding exists for this mission; PATCH_GENERATE has nothing "
            "to patch. This indicates a pipeline gap upstream (CORRELATE should not "
            "have transitioned a mission into PATCH without one), not a model or "
            "policy outcome.",
            result={"infra_failure": True, "reason": "no_finding"},
            error_code=ErrorCode.INTERNAL_ERROR,
        )

    # D-061 §3's exception for this kind: resume from however many candidates this
    # mission already has, rather than re-fanning-out from zero. See this module's
    # docstring, "The fan-out."
    already = PatchCandidate.objects.filter(mission=mission).count()
    if already >= attempts_target:
        return _summarize(
            mission, finding, attempts_target=attempts_target, already_recorded=True
        )

    if ctx.cancel_requested():
        return ExecutorResult(
            outcome=JobOutcome.CANCELLED,
            detail="Cancellation requested before patch generation started.",
            result={"cancelled_before_start": True, "candidates_recorded": already},
        )

    _ensure_gateway_importable()
    try:
        settings = _build_gateway_settings()
        gateway = _build_gateway(settings)
    except Exception as exc:  # a config fault, not a generation result
        from gateway.errors import GatewayError

        if not isinstance(exc, GatewayError):
            raise
        detail = f"model gateway misconfigured, no attempt was made: {exc}"
        with transaction.atomic():
            locked = Mission.objects.select_for_update().get(pk=mission.id)
            events.emit(
                locked,
                EventType.LOG,
                detail,
                {"kind": "log", "text": detail},
                trace_id=ctx.trace_id,
                stage=MissionStage.PATCH,
                state=locked.state_enum,
                status=EventStatus.FAILED,
                severity=Severity.HIGH,
                metrics={"model_gateway_misconfigured": 1.0},
                timestamp=now,
            )
        return ExecutorResult(
            outcome=JobOutcome.FAILED,
            detail=detail,
            result={"infra_failure": True, "reason": "gateway_misconfigured"},
            error_code=ErrorCode.MODEL_CAPACITY_UNAVAILABLE,
        )

    context_finding = _context_finding(finding, mission)
    context_policy = _context_policy(mission_policy)

    generation_failures = 0
    degraded_attempts = 0
    cancelled_early = False

    for attempt in range(already + 1, attempts_target + 1):
        if ctx.cancel_requested():
            cancelled_early = True
            break

        try:
            response, degraded = _generate_with_ladder(gateway, context_finding, context_policy)
        except Exception as exc:  # recorded, not swallowed
            from gateway.errors import GatewayError

            if not isinstance(exc, GatewayError):
                raise
            generation_failures += 1
            detail = f"attempt {attempt}/{attempts_target}: {type(exc).__name__}: {exc}"
            _emit_attempt_failed(mission, attempt=attempt, detail=detail, trace_id=ctx.trace_id, now=now)
            continue

        if degraded:
            degraded_attempts += 1
        try:
            _record_generated_candidate(mission, finding, response, trace_id=ctx.trace_id)
        except CandidateSetFrozenError:
            # Verification started while this job was still fanning out. Stop; the
            # candidates already recorded are what VERIFY will see.
            break

        _emit_attempt_progress(
            mission,
            attempt=attempt,
            attempts_target=attempts_target,
            detail=f"patch generation attempt {attempt}/{attempts_target}",
            trace_id=ctx.trace_id,
            now=now,
        )

    result = _summarize(
        mission,
        finding,
        attempts_target=attempts_target,
        already_recorded=False,
    ).result
    result["generation_failures"] = generation_failures
    result["degraded_attempts"] = degraded_attempts
    result["cancelled_early"] = cancelled_early

    total_recorded = result["candidates_recorded"]
    accepted = result["accepted_count"]

    if accepted > 0:
        return ExecutorResult(
            outcome=JobOutcome.SUCCEEDED,
            detail=f"{accepted}/{total_recorded} policy-accepted candidate(s) of "
            f"{attempts_target} attempts.",
            result=result,
        )

    if cancelled_early and total_recorded == 0:
        return ExecutorResult(
            outcome=JobOutcome.CANCELLED,
            detail="Cancellation requested mid-run before any candidate was recorded.",
            result=result,
        )

    error_code = (
        ErrorCode.MODEL_CAPACITY_UNAVAILABLE
        if generation_failures > 0
        else ErrorCode.PATCH_POLICY_REJECTED
    )
    return ExecutorResult(
        outcome=JobOutcome.FAILED,
        detail=f"0/{total_recorded} policy-accepted candidates of {attempts_target} "
        f"attempts ({generation_failures} generation failure(s)).",
        result=result,
        error_code=error_code,
    )


def _summarize(
    mission: Mission, finding: Finding, *, attempts_target: int, already_recorded: bool
) -> ExecutorResult:
    rows = PatchCandidate.objects.filter(mission=mission)
    accepted = rows.filter(policy_status=PatchPolicyStatus.ACCEPTED.value).count()
    total = rows.count()
    return ExecutorResult(
        outcome=JobOutcome.SUCCEEDED if accepted else JobOutcome.FAILED,
        result={
            "finding_id": str(finding.id),
            "attempts_target": attempts_target,
            "candidates_recorded": total,
            "accepted_count": accepted,
            "candidate_ids": [str(row_id) for row_id in rows.values_list("id", flat=True)],
            "already_recorded": already_recorded,
        },
    )


# ---------------------------------------------------------------------------------
# The transition policy
# ---------------------------------------------------------------------------------


@register_transition_policy(JobKind.PATCH_GENERATE)
def _patch_generate_transition_policy(job: Job, mission: Mission) -> MissionState | None:
    """A terminal `PATCH_GENERATE` job routes `PATCH -> VERIFY` once at least one
    policy-accepted candidate exists; otherwise `PATCH -> HUMAN_REVIEW` unless the
    job's own result names a genuine infrastructure fault (`result["infra_failure"]`
    — no `Finding` to patch, or the gateway itself was unusable before a single
    attempt could run), which routes `PATCH -> FAILED` instead. This mirrors
    `_fuzz_transition_policy`'s `infra_failure` convention (this module's sibling in
    `orchestrator/executors.py`) rather than inventing a second one.

    `TRANSITIONS[MissionState.PATCH]` (`contracts/state_machine.py`) is `{VERIFY,
    PAUSED, HUMAN_REVIEW, CANCELLING, FAILED}` — every target this policy returns is
    legal directly from `PATCH`, unlike the `STRESS_TEST -> HUMAN_REVIEW` trap D-061
    §2 documents for `FUZZ`; there is no equivalent indirection needed here.

    A `CANCELLED` job returns `None` — the mission-level cancel already in flight
    owns that transition, same reasoning as `_baseline_transition_policy`.
    """
    if job.state == JobState.CANCELLED:
        return None
    if job.state == JobState.SUCCEEDED and int(job.result.get("accepted_count", 0)) > 0:
        return MissionState.VERIFY
    if bool(job.result.get("infra_failure")):
        return MissionState.FAILED
    return MissionState.HUMAN_REVIEW
