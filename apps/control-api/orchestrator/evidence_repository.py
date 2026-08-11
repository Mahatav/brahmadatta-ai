"""Read-side evidence queries for the control API (#32).

The database stores rows; the API and orchestrator consume frozen contract schemas.
Keeping the conversion here prevents endpoints from learning table quirks and keeps
artifact handling honest: callers receive hash-addressed pointers, never artifact
content.
"""

from __future__ import annotations

from uuid import UUID

from django.http import Http404

from contracts.schemas.common import ArtifactRef
from contracts.schemas.evidence import (
    BaselineReport as BaselineSchema,
    FindingDetail,
    FindingSummary,
    FuzzingReport as FuzzingSchema,
    PatchCandidate as PatchSchema,
    ReproducerRecord,
    VerificationRecord as VerificationSchema,
)
from missions.models import (
    BaselineReport,
    Finding,
    FuzzingReport,
    PatchCandidate,
    Reproducer,
    VerificationRecord,
)


def list_findings(
    mission_id: UUID, *, limit: int, offset: int
) -> tuple[list[FindingSummary], int]:
    rows = Finding.objects.filter(mission_id=mission_id).order_by("detected_at", "id")
    total = rows.count()
    return [_finding_summary(row) for row in rows[offset : offset + limit]], total


def get_finding_detail(mission_id: UUID, finding_id: UUID) -> FindingDetail:
    row = _finding_for_mission(mission_id, finding_id)
    reproducers = list(row.reproducers.order_by("created_at", "id"))
    primary_reproducer = reproducers[0] if reproducers else None
    artifacts = [_artifact_ref(reproducer.artifact) for reproducer in reproducers]
    return FindingDetail(
        summary=_finding_summary(row),
        sanitizer_report=row.sanitizer_report,
        code_slice=row.code_slice,
        reproducer=(
            _reproducer_record(primary_reproducer) if primary_reproducer else None
        ),
        related_finding_ids=[],
        artifacts=artifacts,
    )


def get_baseline_report(mission_id: UUID) -> BaselineSchema:
    try:
        row = BaselineReport.objects.get(mission_id=mission_id)
    except BaselineReport.DoesNotExist as exc:
        raise Http404("baseline not found") from exc
    return BaselineSchema(
        mission_id=row.mission_id,
        configure_ok=row.configure_ok,
        build_ok=row.build_ok,
        tests_total=row.tests_total,
        tests_passed=row.tests_passed,
        tests_failed=row.tests_failed,
        duration_seconds=row.duration_seconds,
        adapter=row.adapter,
        recorded_at=row.recorded_at,
        log_ref=_artifact_ref(row.log_ref) if row.log_ref else None,
    )


def get_fuzzing_report(mission_id: UUID) -> FuzzingSchema:
    row = (
        FuzzingReport.objects.filter(mission_id=mission_id)
        .order_by("-recorded_at", "-id")
        .first()
    )
    if row is None:
        raise Http404("fuzzing report not found")
    return FuzzingSchema(
        mission_id=row.mission_id,
        mode=row.mode,
        harness=row.harness,
        engine=row.engine,
        runtime_seconds=row.runtime_seconds,
        executions=row.executions,
        crashes_found=row.crashes_found,
        unique_crashes=row.unique_crashes,
        corpus_size=row.corpus_size,
        sanitizers=row.sanitizers,
        finding_ids=list(
            row.mission.findings.order_by("detected_at", "id").values_list("id", flat=True)
        ),
        replay_source=row.replay_source,
        recorded_at=row.recorded_at,
    )


def list_patch_candidates(
    mission_id: UUID, *, limit: int, offset: int
) -> tuple[list[PatchSchema], int]:
    rows = PatchCandidate.objects.filter(mission_id=mission_id).order_by(
        "created_at", "id"
    )
    total = rows.count()
    return [_patch_candidate(row) for row in rows[offset : offset + limit]], total


def get_patch_verification(mission_id: UUID, patch_id: UUID) -> VerificationSchema:
    try:
        row = VerificationRecord.objects.get(mission_id=mission_id, patch_id=patch_id)
    except VerificationRecord.DoesNotExist as exc:
        raise Http404("verification not found") from exc
    return _verification_record(row)


def _finding_for_mission(mission_id: UUID, finding_id: UUID) -> Finding:
    try:
        return Finding.objects.get(mission_id=mission_id, id=finding_id)
    except Finding.DoesNotExist as exc:
        raise Http404("finding not found") from exc


def _finding_summary(row: Finding) -> FindingSummary:
    return FindingSummary(
        id=row.id,
        mission_id=row.mission_id,
        category=row.category,
        severity=row.severity,
        tool=row.tool,
        discovery_method=row.discovery_method,
        replay_source=row.replay_source,
        location={
            "file_path": row.file_path,
            "line": row.line,
            "function": row.function,
        },
        fingerprint=row.fingerprint,
        reproducible=row.reproducible,
        detected_at=row.detected_at,
        title=row.title,
    )


def _reproducer_record(row: Reproducer) -> ReproducerRecord:
    return ReproducerRecord(
        id=row.id,
        finding_id=row.finding_id,
        minimized=row.minimized,
        replay_attempts=row.replay_attempts,
        replay_successes=row.replay_successes,
        test_command=row.test_command,
        artifact=_artifact_ref(row.artifact),
        created_at=row.created_at,
    )


def _patch_candidate(row: PatchCandidate) -> PatchSchema:
    return PatchSchema(
        id=row.id,
        mission_id=row.mission_id,
        finding_id=row.finding_id,
        provenance=row.provenance,
        model=row.model_provenance,
        diff=row.diff,
        files_changed=row.files_changed,
        lines_changed=row.lines_changed,
        policy_status=row.policy_status,
        policy_detail=row.policy_detail,
        rationale=row.rationale,
        created_at=row.created_at,
    )


def _verification_record(row: VerificationRecord) -> VerificationSchema:
    return VerificationSchema(
        id=row.id,
        mission_id=row.mission_id,
        patch_id=row.patch_id,
        gates=row.gates,
        verdict=row.verdict,
        started_at=row.started_at,
        finished_at=row.finished_at,
        worktree_sha256=row.worktree_sha256,
        resource_usage=row.resource_usage,
    )


def _artifact_ref(value: dict) -> ArtifactRef:
    return ArtifactRef(**value)
