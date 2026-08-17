"""Evidence API.

`GET /missions/{id}/git-bisect` from the API specification is deliberately absent:
automated bisect is CUT (P1-1, D-014). Adding it back is a scope decision, not a
backend one.

Every response here is sanitized by construction — the schemas carry summaries,
diffs and artifact *pointers*, never raw archives, raw tool output, or credentials
(`21-api-specification.md`, API rules).
"""

from __future__ import annotations

from uuid import UUID

from django.http import HttpRequest
from ninja import Query, Router, Status

from api.auth import OPERATOR_ROLES, READ_ROLES, require_role
from api.errors import ERROR_RESPONSES
from contracts.schemas.common import Page
from contracts.schemas.evidence import (
    BaselineReport,
    EvidenceBundle,
    ExportReceipt,
    ExportRequest,
    FindingDetail,
    FindingSummary,
    FuzzingReport,
    PatchCandidate,
    VerificationRecord,
)
from orchestrator import evidence_bundle, evidence_export, evidence_repository

router = Router(tags=["evidence"])

VERIFICATION_ISSUE = "#28 (verification gates)"


@router.get(
    "/missions/{mission_id}/findings",
    response={200: Page[FindingSummary], **ERROR_RESPONSES},
    summary="Findings recorded for a mission",
    operation_id="listFindings",
)
def list_findings(
    request: HttpRequest,
    mission_id: UUID,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    require_role(request, *READ_ROLES)
    items, total = evidence_repository.list_findings(mission_id, limit=limit, offset=offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/missions/{mission_id}/findings/{finding_id}",
    response={200: FindingDetail, **ERROR_RESPONSES},
    summary="One finding, with sanitized sanitizer report and reproducer",
    operation_id="getFinding",
)
def get_finding(request: HttpRequest, mission_id: UUID, finding_id: UUID):
    require_role(request, *READ_ROLES)
    return evidence_repository.get_finding_detail(mission_id, finding_id)


@router.get(
    "/missions/{mission_id}/baseline",
    response={200: BaselineReport, **ERROR_RESPONSES},
    summary="Baseline build and regression-test counts",
    description=(
        "Added to the specification during the D1 freeze. P0-5 makes the baseline "
        "counts the denominator for 'regression preserved', and the D3 gate is stated "
        "in terms of them, so the Command Center needs them addressable on their own "
        "rather than only inside the full evidence bundle."
    ),
    operation_id="getBaseline",
)
def get_baseline(request: HttpRequest, mission_id: UUID):
    require_role(request, *READ_ROLES)
    return evidence_repository.get_baseline_report(mission_id)


@router.get(
    "/missions/{mission_id}/fuzzing",
    response={200: FuzzingReport, **ERROR_RESPONSES},
    summary="Fuzzing campaign summary",
    operation_id="getFuzzingReport",
)
def get_fuzzing(request: HttpRequest, mission_id: UUID):
    require_role(request, *READ_ROLES)
    return evidence_repository.get_fuzzing_report(mission_id)


@router.get(
    "/missions/{mission_id}/patches",
    response={200: Page[PatchCandidate], **ERROR_RESPONSES},
    summary="Patch candidates, with provenance and policy status",
    operation_id="listPatchCandidates",
)
def list_patches(
    request: HttpRequest,
    mission_id: UUID,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    require_role(request, *READ_ROLES)
    items, total = evidence_repository.list_patch_candidates(mission_id, limit=limit, offset=offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/missions/{mission_id}/patches/{patch_id}/verification",
    response={200: VerificationRecord, **ERROR_RESPONSES},
    summary="Verdict and the deterministic gate matrix behind it",
    description=(
        "The verdict in this response is re-derived from the gate matrix before it "
        "is serialized. A record whose verdict does not follow from its gates cannot "
        "be returned — see contracts.schemas.evidence.VerificationRecord."
    ),
    operation_id="getPatchVerification",
)
def get_verification(request: HttpRequest, mission_id: UUID, patch_id: UUID):
    require_role(request, *READ_ROLES)
    return evidence_repository.get_patch_verification(mission_id, patch_id)


@router.get(
    "/missions/{mission_id}/evidence",
    response={200: EvidenceBundle, **ERROR_RESPONSES},
    summary="The complete evidence bundle for a mission",
    operation_id="getEvidenceBundle",
)
def get_evidence(request: HttpRequest, mission_id: UUID):
    require_role(request, *READ_ROLES)
    return evidence_bundle.assemble_evidence_bundle(mission_id)


@router.post(
    "/missions/{mission_id}/export",
    response={202: ExportReceipt, **ERROR_RESPONSES},
    summary="Export the Markdown/JSON evidence report",
    description=(
        "Exportable from any mission state (architecture spec §5.3: 'export is a "
        "side-effect and an endpoint, not a privilege of the happy path'). Each call "
        "is a fresh export (a new export_id/generated_at); the pipeline-driven "
        "JobKind.EXPORT job that runs on entry to EXPORTING reuses a mission's "
        "existing bundle instead of re-rendering one — see "
        "orchestrator.evidence_export's module docstring for why the two callers "
        "differ on that point, and the known gap around `idempotency_key` not yet "
        "being persisted."
    ),
    operation_id="exportEvidence",
)
def export_evidence(request: HttpRequest, mission_id: UUID, payload: ExportRequest):
    require_role(request, *OPERATOR_ROLES)
    outcome = evidence_export.export_mission(
        mission_id,
        formats=payload.formats,
        include_artifacts=payload.include_artifacts,
        reuse_existing=False,
    )
    return Status(202, outcome.receipt)
