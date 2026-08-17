"""Business logic behind all seven mission-lifecycle routers (#154).

Split across two engineers per D-060 §4, landing in this one module rather than two:
`create_mission`/`list_missions`/`get_mission` are one slice, `preflight_mission`/
`start_mission`/`pause_mission`/`cancel_mission` the other. Both follow
`authorization.service`'s shape, because that module's docstring is the pattern for
this whole area of the codebase.

## create_mission / list_missions / get_mission

1. There is no existing row to lock for a create — it has nothing to check the
   request against except the schema's own constraints, which `StrictSchema` and the
   field constraints on `MissionCreateRequest` already enforce before this function
   runs (D-060 §1). `repository_ref` is recorded as the operator's claim and is
   deliberately **not** checked against the snapshot-source allowlist here — that
   check belongs to `authorization.service._materialize_source`, at the point bytes
   are actually resolved, not at create time.
2. Write the new row.
3. Idempotency is the one piece of `create_mission` that is genuinely new work
   (D-060 §2): `idempotency_key` had no backing column and nothing consumed it before
   #154. Two concurrent creates carrying the *same* key must produce exactly one
   `Mission` row and both callers must see it — this is the literal race #154 asks
   about, and it is closed the same way `create_mission_snapshot` closes the
   `Artifact` race in `authorization/service.py`: attempt the insert inside a
   savepoint, catch the unique-constraint `IntegrityError`, and return the winning
   row rather than a raw 500 or a check-then-act read. Two creates with **no** key,
   or two different keys, are just two different missions — nothing to serialize.

`list_missions` and `get_mission` have no authorization scoping beyond role
(D-060 §3): `Mission` carries no owner/tenant field, and `api.auth`'s own docstring
states this is "one named operator, one machine, a fourteen-day project." Any
principal holding a read role may read any mission; `require_role` in the router is
the whole authorization surface for both.

## preflight_mission / start_mission / pause_mission / cancel_mission

Three of the four are almost embarrassingly thin, on purpose: `start_mission`,
`pause_mission` and `cancel_mission` each do nothing but call
`orchestrator.transitions.transition`, which is the only place a mission's lifecycle
fields may move (SEC-16) and the only place that takes `SELECT ... FOR UPDATE` on the
mission row. Opening a second lock here — or fetching the mission's current state to
decide what to do before calling `transition` — would reopen the exact check-then-act
window SEC-15 closed on PR #110: `transition` reads `current` *after* the lock, not from
anything a caller fetched earlier, and two concurrent calls on the same mission
serialize on that lock rather than racing. See `orchestrator.transitions.transition`'s
own docstring, and `api/tests/test_mission_lifecycle.py`'s two concurrent-pause/cancel
tests for the test that demonstrates it under real Postgres locking.

`preflight_mission` is the one exception, and is not thin for a structural reason
rather than an oversight: it is *non-mutating* (D-060 §1) and therefore never reaches
`transition`, which is the only place in this module that would otherwise take the row
lock. To read a consistent view — the same row `start_mission` would lock, evaluated
against the same guards `contracts.state_machine.assert_transition` runs — it takes its
own `SELECT ... FOR UPDATE` for the lifetime of a read-only transaction, through
`_lock_mission` below. That is not a "second lock" in the sense the rule above forbids:
no other function in this request also locks the row, and nothing here calls
`transition`.

`get_mission` also resolves the mission by id, but never under a lock: it is a plain
read with no write to make consistent against, so `Mission.objects.get` (not
`_lock_mission`) is the right call there — two different needs, two different
functions, not a discrepancy.
"""

from __future__ import annotations

import uuid
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Max, Sum
from django.utils import timezone

from api import sse
from authorization.errors import MissionNotFoundError
from contracts.enums import (
    ErrorCode,
    LanguageAdapter,
    MissionState,
    PatchProvenance,
    Verdict,
    posture_for,
)
from contracts.errors import ContractError
from contracts.schemas.common import Acknowledgement, Page, ResourceUsage
from contracts.schemas.evidence import CandidateVerdict, MissionVerdictSummary
from contracts.schemas.missions import (
    CancelRequest,
    MissionCounts,
    MissionCreateRequest,
    MissionDetail,
    MissionPolicy,
    MissionProgress,
    MissionSummary,
    PauseRequest,
    PreflightCheck,
    PreflightReport,
    SnapshotRecord,
    StartRequest,
)
from contracts.state_machine import (
    STAGE_FOR_STATE,
    STATE_SEQUENCE,
    VERDICT_FOR_STATE,
    allowed_transitions,
    assert_resume,
    assert_stage_can_run,
    assert_verdict_is_evidenced,
)
from contracts.verdict import derive_mission_verdict
from missions.models import (
    BaselineReport,
    Finding,
    Mission,
    MissionEvent,
    PatchCandidate,
    ResourceSample,
    VerificationRecord,
)
from orchestrator import repository, transitions

#: States a verdict has already been evidenced for (`orchestrator.transitions` only
#: ever sets `Mission.verdict` on the way into one of these). "100% done" for the
#: progress bar even though they are not members of the happy-path sequence below.
#: CANCELLING/CANCELLED/FAILED are left unmapped on purpose: an aborted run has no
#: honest position on a completion bar, and `MissionProgress.percent_complete` is
#: optional precisely so a state that cannot honestly report one can say nothing
#: rather than fabricate a number.
_VERDICT_STATE_SET = frozenset(VERDICT_FOR_STATE.keys())

#: The one transition `start_mission` can ever request. `TRANSITIONS[SNAPSHOTTED]` in
#: `contracts.state_machine` has exactly one non-abort member, so this is not a policy
#: choice made here — it is the frozen transition table's only answer, restated so
#: `preflight_mission` and `start_mission` can share it without importing a private
#: name. See `start_mission`'s docstring for the naming tension this produces with
#: `EventType.PREFLIGHT_COMPLETED` and why it is not a bug.
_START_TARGET = MissionState.VALIDATING


def create_mission(payload: MissionCreateRequest, *, now=None) -> MissionSummary:
    """Insert a mission draft in `CREATED`, replaying an `idempotency_key` collision.

    Creating a mission in `CREATED` is the one lifecycle write that does not go
    through `orchestrator.transitions.transition`: `Mission.save()`'s own guard
    (SEC-16) exempts a row that is still being added, since `CREATED` is not a state
    any transition guard would have refused.
    """
    now = now or timezone.now()
    fields = dict(
        name=payload.name,
        repository_ref=payload.repository_ref,
        adapter=payload.adapter.value,
        policy=payload.policy.model_dump(mode="json"),
    )

    if payload.idempotency_key is None:
        mission = Mission.objects.create(**fields)
        return _mission_summary(mission, now)

    # The race #154 asks about. A savepoint (nested `atomic()`) rather than a plain
    # `create()`, for the same reason given at length in
    # `authorization.service.create_mission_snapshot`'s `Artifact` insert: on
    # Postgres an `IntegrityError` poisons the *enclosing* transaction for every
    # statement that follows, even once caught in Python. Wrapping just the insert
    # keeps that poisoning scoped to a rollback-able savepoint instead of the whole
    # request, and keeps this function safe to call from inside a future caller's
    # own `atomic()` block without re-deriving this reasoning there.
    try:
        with transaction.atomic():
            mission = Mission.objects.create(
                idempotency_key=payload.idempotency_key, **fields
            )
    except IntegrityError:
        # Someone else's create for this key won the race. Its fields may not match
        # what this request asked for — idempotency here is key-based, not the
        # content-hash comparison `create_mission_snapshot` uses for the archive
        # digest (D-060 §2 is explicit that this is new, simpler semantics, not a
        # reuse of that one) — but the contract is "replaying a create with the same
        # key returns the same mission," and the winner's row is that mission.
        mission = Mission.objects.get(idempotency_key=payload.idempotency_key)

    return _mission_summary(mission, now)


def list_missions(*, limit: int, offset: int, now=None) -> Page[MissionSummary]:
    """Every mission, newest first (`Mission.Meta.ordering`), no scoping beyond role.

    D-060 §3: `Mission` has no owner/tenant column, so there is nothing to filter by
    beyond the `READ_ROLES` check the router already performs.
    """
    now = now or timezone.now()
    queryset = Mission.objects.all()
    total = queryset.count()
    rows = list(queryset[offset : offset + limit])
    return Page[MissionSummary](
        items=[_mission_summary(row, now) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def get_mission(mission_id: uuid.UUID, *, now=None) -> MissionDetail:
    """The full mission record. No scoping beyond role (D-060 §3), same as `list`.

    Plain `Mission.objects.get`, never `_lock_mission` below: this is a read with
    nothing to write afterward, so there is nothing a row lock would make consistent
    that a normal read does not already give it.
    """
    now = now or timezone.now()
    try:
        mission = Mission.objects.get(pk=mission_id)
    except Mission.DoesNotExist as exc:
        raise MissionNotFoundError(
            "No mission with that id.", details={"mission_id": str(mission_id)}
        ) from exc
    return _mission_detail(mission, now)


def _lock_mission(mission_id: UUID) -> Mission:
    """`SELECT ... FOR UPDATE`, or `MissionNotFoundError`. Must run inside a transaction.

    Used only by `preflight_mission` below — the one function in this module that
    reads the mission row without also calling `orchestrator.transitions.transition`
    (which takes this same lock itself for `start_mission`/`pause_mission`/
    `cancel_mission`). A second, small definition of the same four lines as
    `authorization.service._lock_mission` — that function is private to a different
    domain module, and importing a `_`-prefixed helper across an app boundary is worse
    than the duplication.
    """
    try:
        return Mission.objects.select_for_update().get(pk=mission_id)
    except Mission.DoesNotExist as exc:
        raise MissionNotFoundError(
            "No mission with that id.", details={"mission_id": str(mission_id)}
        ) from exc


def preflight_mission(mission_id: UUID, *, now=None) -> PreflightReport:
    """Report whether `start_mission` would succeed right now, without moving anything.

    D-060 §1: reads the locked mission and its active authorization and runs the same
    guards `contracts.state_machine.assert_transition` runs for `current -> VALIDATING`
    — the only transition `start_mission` can ever request — decomposed into named
    checks so a caller learns *every* guard that would refuse, not only the first one
    `assert_transition` itself would stop at. Each check calls the same public guard
    function the real transition calls; nothing here re-derives a guard's logic, so a
    check can only disagree with `start_mission`'s outcome if the row changed between
    the two calls — which the row lock, held for this whole read, is what limits.

    Never calls `orchestrator.transitions.transition`. Returns `200` with `passed`
    telling the story, not a `4xx` — a mission that is not ready to start is the normal
    answer this endpoint exists to give, not a failure of the request.
    """
    now = now or timezone.now()
    target = _START_TARGET

    with transaction.atomic():
        mission = _lock_mission(mission_id)
        current = mission.state_enum
        paused_from = mission.paused_from_enum
        authorization = repository.load_active_authorization(mission, now)
        snapshot_sha256 = repository.latest_snapshot_sha256(mission)
        verifications = repository.load_verifications(mission.id)

        checks: list[PreflightCheck] = []
        blocking_codes: list[str] = []

        def record(name: str, *, passed: bool, detail: str = "", code: str = "") -> None:
            checks.append(PreflightCheck(name=name, passed=passed, detail=detail))
            if not passed and code:
                blocking_codes.append(code)

        if target in allowed_transitions(current, paused_from):
            record("legal_transition", passed=True)
        else:
            record(
                "legal_transition",
                passed=False,
                detail=(
                    f"{current} -> {target} is not a legal transition from this "
                    f"mission's current state."
                ),
                code=str(ErrorCode.INVALID_STATE_TRANSITION),
            )

        try:
            assert_resume(current, target, paused_from)
            record("resume_origin", passed=True)
        except ContractError as exc:
            record(
                "resume_origin", passed=False, detail=exc.message, code=str(exc.code)
            )

        try:
            assert_verdict_is_evidenced(
                current, target, verifications, mission_id=mission.id
            )
            record("verdict_evidenced", passed=True)
        except ContractError as exc:
            record(
                "verdict_evidenced",
                passed=False,
                detail=exc.message,
                code=str(exc.code),
            )

        # `target` is fixed to VALIDATING, which is neither exempt from the
        # authorization requirement nor a stage-less (terminal-verdict) target — see
        # `contracts.state_machine._AUTHORIZATION_EXEMPT_TARGETS` and
        # `assert_transition`'s dispatch. `STAGE_FOR_STATE[VALIDATING]` is always
        # `MissionStage.INGEST`, never `None`, so `assert_stage_can_run` is always the
        # right call here — this does not need to reimplement `assert_transition`'s
        # general branch for every other possible target, only the one this function
        # ever asks about.
        stage = STAGE_FOR_STATE[target]
        assert stage is not None  # narrowed by the comment above: VALIDATING -> INGEST
        try:
            assert_stage_can_run(stage, authorization, now, snapshot_sha256)
            record("authorization_and_stage", passed=True)
        except ContractError as exc:
            record(
                "authorization_and_stage",
                passed=False,
                detail=exc.message,
                code=str(exc.code),
            )

        return PreflightReport(
            mission_id=mission.id,
            passed=all(check.passed for check in checks),
            checks=checks,
            checked_at=now,
            blocking_codes=blocking_codes,
        )


def start_mission(
    mission_id: UUID, payload: StartRequest, *, trace_id: str, now=None
) -> Acknowledgement:
    """Move `SNAPSHOTTED -> VALIDATING` — the one transition this action can request.

    `StartRequest.confirm_authorized` is typed `Literal[True]`; pydantic already
    refuses a request that does not carry it, so there is nothing left to check here.
    `StartRequest.idempotency_key` is accepted by the schema but not consumed: D-060
    scoped new idempotency infrastructure to `create_mission` only (its
    `Mission.idempotency_key` migration and conditional-unique-constraint pattern), and
    nothing analogous exists for `start`. A retried `start` call today reaches
    `transition` a second time and gets a clean `InvalidStateTransitionError` (409),
    not corruption and not a silent no-op — see
    `test_starting_a_mission_twice_is_a_clean_409_not_a_double_transition`. Flagged in
    the handoff as a gap, not built around silently.

    The only mutating call in this module that does not target `PAUSED` or
    `CANCELLING`. `EventType.PREFLIGHT_COMPLETED` fires on entry to `VALIDATING`
    (`orchestrator.transitions._EVENT_TYPE_BY_STATE`) — which reads oddly attached to
    an action named "start" rather than to `preflight_mission`, and D-060 §2 names this
    exact tension as the one place in the brief with "a plausible counter-reading".
    It resolves without a real choice, though: `contracts.state_machine.TRANSITIONS
    [SNAPSHOTTED]` has exactly one non-abort member (`VALIDATING`), so there is no
    other state `start_mission` could target without changing the frozen transition
    table, which is out of this endpoint's authority to do. `preflight_mission` staying
    non-mutating and `start_mission` being the one call that reaches `VALIDATING` are
    therefore the same conclusion looked at from either endpoint.
    """
    now = now or timezone.now()
    result = transitions.transition(
        mission_id,
        _START_TARGET,
        trace_id=trace_id,
        reason="operator confirmed start",
        now=now,
    )
    return Acknowledgement(
        mission_id=str(result.mission_id),
        accepted=True,
        trace_id=trace_id,
        message=f"{result.from_state} -> {result.to_state}",
    )


def pause_mission(
    mission_id: UUID, payload: PauseRequest, *, trace_id: str, now=None
) -> Acknowledgement:
    """Move the mission to `PAUSED`. No pre-fetch: `transition` decides from the state
    it reads under its own lock, never from anything read here first (#110)."""
    now = now or timezone.now()
    result = transitions.transition(
        mission_id,
        MissionState.PAUSED,
        trace_id=trace_id,
        reason=payload.reason,
        now=now,
    )
    return Acknowledgement(
        mission_id=str(result.mission_id),
        accepted=True,
        trace_id=trace_id,
        message=f"{result.from_state} -> {result.to_state}",
    )


def cancel_mission(
    mission_id: UUID, payload: CancelRequest, *, trace_id: str, now=None
) -> Acknowledgement:
    """Move the mission to `CANCELLING`, which schedules teardown on commit
    (`orchestrator.transitions._requires_teardown`). Same no-pre-fetch shape as
    `pause_mission`, for the same reason."""
    now = now or timezone.now()
    result = transitions.transition(
        mission_id,
        MissionState.CANCELLING,
        trace_id=trace_id,
        reason=payload.reason,
        now=now,
    )
    return Acknowledgement(
        mission_id=str(result.mission_id),
        accepted=True,
        trace_id=trace_id,
        message=f"{result.from_state} -> {result.to_state}",
    )


# --- schema assembly ---------------------------------------------------------------


def _mission_summary(mission: Mission, now) -> MissionSummary:
    return MissionSummary(
        id=mission.id,
        name=mission.name,
        state=mission.state_enum,
        posture=posture_for(mission.state_enum),
        adapter=LanguageAdapter(mission.adapter),
        repository_ref=mission.repository_ref,
        authorized=repository.load_active_authorization(mission, now) is not None,
        verdict=Verdict(mission.verdict) if mission.verdict else None,
        created_at=mission.created_at,
        updated_at=mission.updated_at,
    )


def _mission_detail(mission: Mission, now) -> MissionDetail:
    authorization_record = repository.load_active_authorization(mission, now)
    snapshot_row = mission.snapshots.order_by("-created_at").first()
    last_event_row = mission.events.order_by("-sequence").first()
    verdict_summary = _verdict_summary(mission)

    return MissionDetail(
        id=mission.id,
        name=mission.name,
        state=mission.state_enum,
        posture=posture_for(mission.state_enum),
        adapter=LanguageAdapter(mission.adapter),
        repository_ref=mission.repository_ref,
        policy=MissionPolicy.model_validate(mission.policy or {}),
        authorization=authorization_record,
        snapshot=(
            SnapshotRecord.model_validate(snapshot_row) if snapshot_row else None
        ),
        progress=_mission_progress(mission, last_event_row),
        counts=_mission_counts(mission),
        resource_usage=_resource_usage(mission),
        verdict=Verdict(mission.verdict) if mission.verdict else None,
        verdict_summary=verdict_summary,
        allowed_transitions=sorted(
            allowed_transitions(mission.state_enum, mission.paused_from_enum),
            key=str,
        ),
        last_event=sse.to_schema(last_event_row) if last_event_row else None,
        created_at=mission.created_at,
        updated_at=mission.updated_at,
    )


def _mission_progress(mission: Mission, last_event_row: MissionEvent | None) -> MissionProgress:
    state = mission.state_enum
    stage = STAGE_FOR_STATE[state]

    # Every stage a persisted transition has actually reached for this mission,
    # ordered by the happy-path sequence — read from `MissionEvent.stage`, which
    # `orchestrator.transitions.transition` stamps with `STAGE_FOR_STATE[target]` on
    # every transition (see that module). This reads what happened, rather than
    # re-deriving "what should have happened" from the state machine a second time.
    reached = set(
        mission.events.exclude(stage__isnull=True)
        .exclude(stage="")
        .values_list("stage", flat=True)
    )
    stages_completed = [
        candidate_stage
        for candidate_stage in dict.fromkeys(
            STAGE_FOR_STATE[candidate_state]
            for candidate_state in STATE_SEQUENCE
            if STAGE_FOR_STATE[candidate_state] is not None
        )
        if str(candidate_stage) in reached
    ]

    return MissionProgress(
        stage=stage,
        stages_completed=stages_completed,
        percent_complete=_percent_complete(mission),
        last_event_sequence=last_event_row.sequence if last_event_row else 0,
    )


def _percent_complete(mission: Mission) -> float | None:
    """Position on the happy path, or `None` where that would not be an honest number.

    Not specified by the frozen contract beyond "optional float 0-100" — this is a
    backend-developer default (CLAUDE.md's "no decorative fake metrics" rule read the
    humbler way): a real position in the documented happy-path sequence for a mission
    still on it, 100 once a verdict has actually been evidenced, and `None` — not a
    guess — for a paused, cancelling, cancelled or failed mission, where "percent
    complete" has no honest meaning.
    """
    state = mission.state_enum
    if state in _VERDICT_STATE_SET:
        return 100.0
    try:
        index = STATE_SEQUENCE.index(state)
    except ValueError:
        return None
    return round((index + 1) / len(STATE_SEQUENCE) * 100, 2)


def _mission_counts(mission: Mission) -> MissionCounts:
    findings = Finding.objects.filter(mission=mission)
    baseline: BaselineReport | None = getattr(mission, "baseline", None)
    return MissionCounts(
        findings=findings.count(),
        reproducible_findings=findings.filter(reproducible=True).count(),
        patch_candidates=PatchCandidate.objects.filter(mission=mission).count(),
        verifications=VerificationRecord.objects.filter(mission=mission).count(),
        tests_passed=baseline.tests_passed if baseline else 0,
        tests_failed=baseline.tests_failed if baseline else 0,
    )


def _resource_usage(mission: Mission) -> ResourceUsage:
    """Summed/peaked across every sample this mission recorded. Zero rows -> zeros,
    never estimated (P0-14's own rule, applied to "no samples yet" too)."""
    totals = ResourceSample.objects.filter(mission=mission).aggregate(
        cpu_seconds=Sum("cpu_seconds"),
        peak_memory_mb=Max("peak_memory_mb"),
        wall_seconds=Sum("wall_seconds"),
        sandbox_count=Max("sandbox_count"),
        gpu_seconds=Sum("gpu_seconds"),
    )
    return ResourceUsage(
        cpu_seconds=totals["cpu_seconds"] or 0.0,
        peak_memory_mb=totals["peak_memory_mb"] or 0.0,
        wall_seconds=totals["wall_seconds"] or 0.0,
        sandbox_count=totals["sandbox_count"] or 0,
        gpu_seconds=totals["gpu_seconds"] or 0.0,
    )


def _verdict_summary(mission: Mission) -> MissionVerdictSummary | None:
    """`None` until the candidate set has at least one verification record.

    Built directly from this mission's own `VerificationRecord` rows — not from
    `mission.verdict` — so the per-candidate breakdown is always self-consistent
    with `mission_verdict`, which `MissionVerdictSummary`'s own validator re-checks
    on construction.
    """
    records = list(
        VerificationRecord.objects.filter(mission=mission)
        .select_related("patch")
        .order_by("started_at")
    )
    if not records:
        return None

    candidates = [
        CandidateVerdict(
            patch_id=record.patch_id,
            verification_id=record.id,
            verdict=Verdict(record.verdict),
            provenance=PatchProvenance(record.patch.provenance),
        )
        for record in records
    ]
    verdicts = [candidate.verdict for candidate in candidates]
    return MissionVerdictSummary(
        mission_verdict=derive_mission_verdict(verdicts),
        candidates=candidates,
        verified_count=sum(1 for v in verdicts if v is Verdict.VERIFIED),
        rejected_count=sum(1 for v in verdicts if v is Verdict.REJECTED),
        human_review_count=sum(
            1 for v in verdicts if v is Verdict.HUMAN_REVIEW_REQUIRED
        ),
    )
