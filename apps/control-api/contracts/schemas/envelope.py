"""The event envelope.

Everything the Command Center ever renders arrives as one of these. The UI
reconstructs mission state from the ordered stream plus periodic summary snapshots
(`docs/03-technical/16-system-architecture-document.md`, "UI event model"), so this
schema is the widest part of the contract and the part most worth freezing.

`payload` is a discriminated union on `kind`, one variant per family of event. That
matters for the frontend: `openapi-typescript` renders it as a discriminated union in
TypeScript, so a `switch` over `payload.kind` is exhaustively checked at build time.
Adding a payload variant without regenerating types breaks the Astro build, which is
the intended failure mode.

## SSE framing

`GET /api/v1/missions/{id}/events` streams these as:

    id: <sequence>
    event: <type>
    data: <MissionEvent as JSON>

Reconnect with `Last-Event-ID`, or replay explicitly through
`GET /api/v1/missions/{id}/events/replay?since_sequence=N`. `sequence` is a
gap-free per-mission counter, so a client can always tell whether it missed one.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import Field

from contracts.enums import (
    ErrorCode,
    EventStatus,
    EventType,
    MissionPosture,
    MissionStage,
    MissionState,
    Severity,
)
from contracts.schemas.common import ResourceUsage, StrictSchema
from contracts.schemas.evidence import (
    BaselineReport,
    ExportReceipt,
    FindingSummary,
    FuzzingReport,
    MissionVerdictSummary,
    PatchCandidate,
    ReproducerRecord,
    VerificationRecord,
)


class StateChangedPayload(StrictSchema):
    kind: Literal["state_changed"] = "state_changed"
    from_state: MissionState | None = None
    to_state: MissionState
    posture: MissionPosture
    reason: str = Field(default="", max_length=1000)


class StageProgressPayload(StrictSchema):
    kind: Literal["stage_progress"] = "stage_progress"
    stage: MissionStage
    percent_complete: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Null when the stage genuinely cannot report progress. The UI "
        "shows an indeterminate indicator rather than inventing a number.",
    )
    detail: str = Field(default="", max_length=1000)


class SnapshotPayload(StrictSchema):
    kind: Literal["snapshot"] = "snapshot"
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    commit_sha: str | None = Field(default=None, max_length=64)
    file_count: int = Field(ge=0)
    bytes_total: int = Field(ge=0)


class BaselinePayload(StrictSchema):
    kind: Literal["baseline"] = "baseline"
    report: BaselineReport


class FindingPayload(StrictSchema):
    kind: Literal["finding"] = "finding"
    finding: FindingSummary


class ReproducerPayload(StrictSchema):
    kind: Literal["reproducer"] = "reproducer"
    reproducer: ReproducerRecord


class FuzzingPayload(StrictSchema):
    kind: Literal["fuzzing"] = "fuzzing"
    report: FuzzingReport


class PatchCandidatePayload(StrictSchema):
    kind: Literal["patch_candidate"] = "patch_candidate"
    patch: PatchCandidate


class VerificationPayload(StrictSchema):
    kind: Literal["verification"] = "verification"
    verification: VerificationRecord


class MissionVerdictPayload(StrictSchema):
    """The mission verdict and every candidate verdict behind it.

    Emitted once, when the mission reaches a terminal verdict state. The Command
    Center renders the candidates side by side from this — the `Verified` and the
    `Rejected` together — rather than reducing them to one badge.
    """

    kind: Literal["mission_verdict"] = "mission_verdict"
    summary: MissionVerdictSummary


class EvidenceExportPayload(StrictSchema):
    kind: Literal["evidence_export"] = "evidence_export"
    receipt: ExportReceipt


class ResourceUsagePayload(StrictSchema):
    kind: Literal["resource_usage"] = "resource_usage"
    usage: ResourceUsage


class TeardownPayload(StrictSchema):
    kind: Literal["teardown"] = "teardown"
    resource_kind: str = Field(max_length=100, description="sandbox | model-host")
    resource_id: str = Field(max_length=200)
    released: bool
    detail: str = Field(default="", max_length=1000)


class PolicyViolationPayload(StrictSchema):
    kind: Literal["policy_violation"] = "policy_violation"
    code: ErrorCode
    detail: str = Field(max_length=2000)


class LogPayload(StrictSchema):
    kind: Literal["log"] = "log"
    text: str = Field(
        max_length=4000,
        description="Sanitized, user-safe line. Never raw target output and never "
        "anything carrying a credential.",
    )


class TriageStubPayload(StrictSchema):
    """`TRIAGE` has no `JobKind` (architecture spec §2.5) — a deliberate "hollow
    stage" whose three required events (`STAGE_STARTED`, `LOG`, `STAGE_COMPLETED`)
    carry no additional structured data, only the tag identifying which stub emitted
    them (`orchestrator.queue._emit_triage_stub_events`, which has emitted exactly
    `{"kind": "triage_stub"}` since `5105212`, months before this variant existed).

    D-116: this tag was missing from the union entirely, so every real mission —
    `TRIAGE` is mandatory in the workflow — produced an event the discriminated union
    rejected with `union_tag_invalid`. That crashed both `GET .../events` (SSE) and
    `GET .../events/replay` the moment they reached it. Added as a real, correctly
    typed variant rather than a permissive catch-all, so a *genuinely* new/unknown
    `kind` added later still fails loudly here instead of silently passing through.
    """

    kind: Literal["triage_stub"] = "triage_stub"


EventPayload = Annotated[
    Union[
        StateChangedPayload,
        StageProgressPayload,
        SnapshotPayload,
        BaselinePayload,
        FindingPayload,
        ReproducerPayload,
        FuzzingPayload,
        PatchCandidatePayload,
        VerificationPayload,
        MissionVerdictPayload,
        EvidenceExportPayload,
        ResourceUsagePayload,
        TeardownPayload,
        PolicyViolationPayload,
        LogPayload,
        TriageStubPayload,
    ],
    Field(discriminator="kind"),
]


class MissionEvent(StrictSchema):
    """One immutable mission event. Append-only; never edited after emission."""

    id: UUID = Field(description="Globally unique event id.")
    mission_id: UUID
    sequence: int = Field(
        ge=1,
        description="Gap-free per-mission ordinal. Also the SSE `id:` field, so a "
        "reconnecting client can detect and replay a gap.",
    )
    timestamp: datetime = Field(description="UTC, emitted by the orchestrator.")
    type: EventType
    stage: MissionStage | None = Field(
        default=None, description="Workflow stage in progress, when one applies."
    )
    state: MissionState = Field(description="Mission state at emission time.")
    status: EventStatus = EventStatus.RUNNING
    severity: Severity = Severity.INFO
    message: str = Field(
        max_length=1000,
        description="User-safe line for the event rail. Sanitized at the source.",
    )
    payload: EventPayload = Field(
        description="Typed, discriminated on `kind`. Everything the UI renders comes "
        "from here."
    )
    evidence_refs: list[str] = Field(
        default_factory=list,
        description="Opaque artifact pointers; resolved through the evidence "
        "endpoints, never linked directly.",
    )
    metrics: dict[str, float] = Field(
        default_factory=dict,
        description="Real measured telemetry only. No decorative values — a metric "
        "the pipeline cannot measure is absent, not zero.",
    )
    trace_id: str = Field(
        max_length=64,
        description="Correlates this event with the request and the server logs.",
    )
