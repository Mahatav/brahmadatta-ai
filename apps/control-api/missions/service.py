"""Business logic behind `POST /missions`, `GET /missions` and `GET /missions/{id}`
(#154, one of two halves — the other is `orchestrator.transitions` wired directly
into `preflight`/`start`/`pause`/`cancel`, a separate PR).

`create_mission` follows the same shape as `authorization.service`'s two functions,
because that module's docstring is the pattern for this whole area of the codebase:

1. There is no existing row to lock — a create has nothing to check the request
   against except the schema's own constraints, which `StrictSchema` and the field
   constraints on `MissionCreateRequest` already enforce before this function runs
   (D-060 §1). `repository_ref` is recorded as the operator's claim and is
   deliberately **not** checked against the snapshot-source allowlist here — that
   check belongs to `authorization.service._materialize_source`, at the point bytes
   are actually resolved, not at create time.
2. Write the new row.
3. Idempotency is the one piece of this endpoint that is genuinely new work
   (D-060 §2): `idempotency_key` had no backing column and nothing consumed it
   before #154. Two concurrent creates carrying the *same* key must produce exactly
   one `Mission` row and both callers must see it — this is the literal race #154
   asks about, and it is closed the same way `create_mission_snapshot` closes the
   `Artifact` race in `authorization/service.py`: attempt the insert inside a
   savepoint, catch the unique-constraint `IntegrityError`, and return the winning
   row rather than a raw 500 or a check-then-act read. Two creates with **no** key,
   or two different keys, are just two different missions — nothing to serialize.

`list_missions` and `get_mission` have no authorization scoping beyond role
(D-060 §3): `Mission` carries no owner/tenant field, and `api.auth`'s own docstring
states this is "one named operator, one machine, a fourteen-day project." Any
principal holding a read role may read any mission; `require_role` in the router is
the whole authorization surface for both.
"""

from __future__ import annotations

import uuid

from django.db import IntegrityError, transaction
from django.db.models import Max, Sum
from django.utils import timezone

from api import sse
from authorization.errors import MissionNotFoundError
from contracts.enums import LanguageAdapter, PatchProvenance, Verdict, posture_for
from contracts.schemas.common import Page, ResourceUsage
from contracts.schemas.evidence import CandidateVerdict, MissionVerdictSummary
from contracts.schemas.missions import (
    MissionCounts,
    MissionCreateRequest,
    MissionDetail,
    MissionPolicy,
    MissionProgress,
    MissionSummary,
    SnapshotRecord,
)
from contracts.state_machine import (
    STAGE_FOR_STATE,
    STATE_SEQUENCE,
    VERDICT_FOR_STATE,
    allowed_transitions,
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
from orchestrator import repository

#: States a verdict has already been evidenced for (`orchestrator.transitions` only
#: ever sets `Mission.verdict` on the way into one of these). "100% done" for the
#: progress bar even though they are not members of the happy-path sequence below.
#: CANCELLING/CANCELLED/FAILED are left unmapped on purpose: an aborted run has no
#: honest position on a completion bar, and `MissionProgress.percent_complete` is
#: optional precisely so a state that cannot honestly report one can say nothing
#: rather than fabricate a number.
_VERDICT_STATE_SET = frozenset(VERDICT_FOR_STATE.keys())


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
    """The full mission record. No scoping beyond role (D-060 §3), same as `list`."""
    now = now or timezone.now()
    try:
        mission = Mission.objects.get(pk=mission_id)
    except Mission.DoesNotExist as exc:
        raise MissionNotFoundError(
            "No mission with that id.", details={"mission_id": str(mission_id)}
        ) from exc
    return _mission_detail(mission, now)


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
