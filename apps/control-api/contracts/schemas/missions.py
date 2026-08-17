"""Mission lifecycle schemas.

Two safety properties are expressed in the types rather than in validation code:

* `SandboxPolicy.network` is `Literal["deny"]`. The API has no vocabulary for a
  sandbox with egress. An operator cannot request one, the UI cannot offer one, and
  a future caller cannot enable one without changing this file and the frozen
  OpenAPI dump alongside it.
* `MissionDetail.authorization` is the record itself, not a boolean. The Command
  Center displays who authorized the run and until when, because "authorized: true"
  is exactly the kind of claim that survives a bug.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from contracts.authorization import AuthorizationRecord
from contracts.enums import (
    LanguageAdapter,
    MissionPosture,
    MissionStage,
    MissionState,
    Verdict,
)
from contracts.schemas.common import ResourceUsage, StrictSchema
from contracts.schemas.envelope import MissionEvent
from contracts.schemas.evidence import MissionVerdictSummary


class SandboxPolicy(StrictSchema):
    """Resource ceilings and the isolation posture for the target sandbox (P0-2)."""

    network: Literal["deny"] = Field(
        default="deny",
        description="Egress is denied. There is no other permitted value — the type "
        "is the enforcement.",
    )
    cpu_limit: int = Field(default=4, ge=1, le=64)
    memory_mb: int = Field(default=8192, ge=512, le=131072)
    max_seconds: int = Field(default=5400, ge=60, le=43200)
    runtime: Literal["podman", "docker", "subprocess-jail"] = Field(
        default="docker",
        description="Container runtime, or the subprocess-jail fallback (#81). "
        "`docker` is D-024's accepted substitute for rootless Podman — a standard "
        "rootful-daemon container with `--network none`, never reported as "
        "`podman`'s stronger isolation claim. The subprocess-jail fallback is "
        "weaker isolation still and is reported as such everywhere it is used — "
        "it is not a silent substitution.",
    )


class PatchPolicy(StrictSchema):
    """The limits that make a rejection demonstrable as well as safe (P0-9)."""

    allowed_paths: list[str] = Field(
        default_factory=list,
        description="Glob allowlist. A candidate touching anything else is rejected "
        "before it is ever built.",
    )
    max_files_changed: int = Field(default=1, ge=1, le=10)
    max_lines_changed: int = Field(default=40, ge=1, le=500)


class MissionPolicy(StrictSchema):
    sandbox: SandboxPolicy = Field(default_factory=SandboxPolicy)
    patch: PatchPolicy = Field(default_factory=PatchPolicy)
    fuzz_seconds: int = Field(default=1800, ge=0, le=43200)
    reproducer_replay_attempts: int = Field(
        default=5,
        ge=1,
        le=100,
        description="How many times a minimized input must replay from a clean "
        "build before `reproducible` is set.",
    )
    patch_generation_attempts: int = Field(
        default=10,
        ge=1,
        le=20,
        description="Fan-out width for JobKind.PATCH_GENERATE (D-027, architecture "
        "spec §3.4: '1 job, N attempts internally'). Each attempt that produces a "
        "parseable candidate is persisted as its own PatchCandidate row the moment "
        "it is produced, whether policy-accepted or not. Default 10 matches the D6 "
        "kill criterion's supporting threshold ('at least 3 of 10 attempts', "
        "docs/09-company/01-vision-and-p0-cut.md). Added by #168 T4 — not present "
        "in the original architecture spec's MissionPolicy listing, so documented "
        "here as the addition it is (backend-developer's minor-contract-detail "
        "authority per its own role brief).",
    )


class MissionCreateRequest(StrictSchema):
    name: str = Field(min_length=1, max_length=200)
    repository_ref: str = Field(
        min_length=1,
        max_length=500,
        description="Authorized repository URL or the name of an uploaded archive. "
        "Never a public target chosen at scan time.",
    )
    adapter: LanguageAdapter
    policy: MissionPolicy = Field(default_factory=MissionPolicy)
    idempotency_key: str | None = Field(
        default=None,
        max_length=200,
        description="Replaying a create with the same key returns the same mission "
        "rather than creating a second one.",
    )


class SnapshotRequest(StrictSchema):
    """Ingest an immutable snapshot of the authorized repository (P0-1).

    The digest is supplied by the caller and re-computed server-side; a mismatch is
    a hard failure, so a swapped archive cannot inherit an existing authorization.
    """

    source: Literal["upload", "git"] = "git"
    commit_sha: str | None = Field(default=None, max_length=64)
    archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    archive_ref: str | None = Field(
        default=None,
        max_length=500,
        description="Pointer to the uploaded archive when source='upload'.",
    )
    idempotency_key: str | None = Field(default=None, max_length=200)


class SnapshotRecord(StrictSchema):
    id: UUID
    mission_id: UUID
    commit_sha: str | None = None
    archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    file_count: int = Field(ge=0)
    bytes_total: int = Field(ge=0)
    created_at: datetime
    immutable: Literal[True] = Field(
        default=True,
        description="Snapshots are write-once. The field exists so the evidence "
        "bundle states the property rather than implying it.",
    )


class PreflightCheck(StrictSchema):
    name: str = Field(max_length=120)
    passed: bool
    detail: str = Field(default="", max_length=1000)


class PreflightReport(StrictSchema):
    """Validates authorization, commands, adapter and limits before anything runs."""

    mission_id: UUID
    passed: bool
    checks: list[PreflightCheck]
    checked_at: datetime
    blocking_codes: list[str] = Field(
        default_factory=list,
        description="Error codes that must clear before the mission may start.",
    )


class StartRequest(StrictSchema):
    confirm_authorized: Literal[True] = Field(
        description="Explicit operator confirmation. Typed as a literal so an "
        "accidental `false` is a validation error rather than a silent no-op."
    )
    idempotency_key: str | None = Field(default=None, max_length=200)


class PauseRequest(StrictSchema):
    reason: str = Field(default="", max_length=500)


class CancelRequest(StrictSchema):
    reason: str = Field(default="", max_length=500)
    confirm: Literal[True] = Field(
        description="Cancellation tears down sandboxes and stops the run; it is "
        "always confirmed explicitly."
    )


class MissionProgress(StrictSchema):
    """What the Core renders. Derived server-side so two clients never disagree."""

    stage: MissionStage | None = None
    stages_completed: list[MissionStage] = Field(default_factory=list)
    percent_complete: float | None = Field(default=None, ge=0, le=100)
    last_event_sequence: int = Field(default=0, ge=0)


class MissionCounts(StrictSchema):
    """Summary counters. Every one is a real count from the evidence database."""

    findings: int = Field(default=0, ge=0)
    reproducible_findings: int = Field(default=0, ge=0)
    patch_candidates: int = Field(default=0, ge=0)
    verifications: int = Field(default=0, ge=0)
    tests_passed: int = Field(default=0, ge=0)
    tests_failed: int = Field(default=0, ge=0)


class MissionSummary(StrictSchema):
    id: UUID
    name: str = Field(max_length=200)
    state: MissionState
    posture: MissionPosture
    adapter: LanguageAdapter
    repository_ref: str = Field(max_length=500)
    authorized: bool = Field(
        description="True only when an unrevoked, unexpired authorization record "
        "exists. Derived from the record, never set directly."
    )
    verdict: Verdict | None = None
    created_at: datetime
    updated_at: datetime


class MissionDetail(StrictSchema):
    id: UUID
    name: str = Field(max_length=200)
    state: MissionState
    posture: MissionPosture
    adapter: LanguageAdapter
    repository_ref: str = Field(max_length=500)
    policy: MissionPolicy
    authorization: AuthorizationRecord | None = Field(
        default=None,
        description="The record itself. Absent means nothing may run.",
    )
    snapshot: SnapshotRecord | None = None
    progress: MissionProgress
    counts: MissionCounts
    resource_usage: ResourceUsage
    verdict: Verdict | None = Field(
        default=None,
        description="The mission verdict, derived from the set of per-candidate "
        "verdicts. Never displayed without `verdict_summary` beside it.",
    )
    verdict_summary: MissionVerdictSummary | None = Field(
        default=None,
        description="Per-candidate breakdown. A mission runs N candidates through the "
        "identical pipeline — the demo runs two, one Verified and one Rejected — and "
        "the rejection is the differentiator, so it travels with the mission verdict "
        "rather than being reduced away.",
    )
    allowed_transitions: list[MissionState] = Field(
        default_factory=list,
        description="What the operator controls may legally do next. The UI disables "
        "its buttons from this rather than duplicating the state machine.",
    )
    last_event: MissionEvent | None = None
    created_at: datetime
    updated_at: datetime
