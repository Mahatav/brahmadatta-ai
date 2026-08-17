"""Assembling the frozen `EvidenceBundle` schema from what earlier stages already
persisted (#168, T6).

**Nothing here recomputes a fact another stage already recorded.** Every field is read
off `BaselineReport`/`Finding`/`Reproducer`/`FuzzingReport`/`PatchCandidate`/
`VerificationRecord`/`Authorization`/`Snapshot`/`ResourceSample` rows (or, for the
findings/patches/verification family, `orchestrator.evidence_repository`'s own readers,
so a shape fix there is not duplicated here) and reassembled into the one schema the
judge is handed. This module is a read, never a write — `orchestrator.evidence_export`
is the module that turns the result into durable bytes and DB rows.

## Honest partial data (`CLAUDE.md`'s "no decorative fake metrics" rule, applied here)

A mission can legitimately reach `EXPORTING` — or be exported mid-pipeline on the
failure path, architecture spec §6.2, "the bundle is still exported" — with whole
sections of evidence never produced: `CORRELATE` found nothing to bind, so there is no
`Finding`; no finding, so no `PatchCandidate`; no candidate, so no
`VerificationRecord`. Every one of those is represented as it actually is:

* `baseline` / `fuzzing` — `None` when no report row exists (the schema already makes
  both `Optional`), never a zeroed-out placeholder that reads as "ran and found
  nothing."
* `findings` / `reproducers` / `patches` / `verifications` — empty lists, which is what
  "queried and there is nothing" already means in this schema; no sentinel needed.
* `verdict_summary` — built only when at least one `VerificationRecord` exists.
  Constructing one over zero verifications would produce a technically-valid
  `HUMAN_REVIEW_REQUIRED` summary (`derive_mission_verdict([])` already returns that)
  that reads as "we looked and a human is needed," when the truer statement is "nothing
  ran that could produce a verdict yet." `None` here is `assemble_evidence_bundle`
  choosing not to make a claim the data does not support; the empty `verifications` list
  still carries the same information for anything that wants to derive its own summary.
* `recommended_patch_id` — set only when exactly one candidate verified, mirroring the
  schema's own validator (`EvidenceBundle._recommended_patch_is_derived_from_the_evidence`);
  never hand-picked.

`orchestrator.evidence_export.render_markdown` is what turns an absent section into a
sentence a reader sees ("No patch candidates: CORRELATE produced no finding to patch"),
not this module — this module's job stops at producing a schema instance that does not
lie, in either direction.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from django.utils import timezone

from authorization.errors import MissionNotFoundError
from contracts.enums import ErrorCode, InferenceMode, SubstitutionKind
from contracts.errors import ContractError
from contracts.schemas.common import ResourceUsage
from contracts.schemas.evidence import (
    CandidateVerdict,
    EvidenceBundle,
    MissionVerdictSummary,
    Substitution,
)
from contracts.verdict import GateStatus, derive_mission_verdict
from missions.models import Mission
from orchestrator import evidence_repository, repository

#: `packages.sandbox.ISOLATION_MODE` is a deployment-level constant (which backend is
#: actually wired in, not a per-run measurement — see this module's own note below on
#: why nothing persists a per-stage isolation record today). Imported lazily inside the
#: function that needs it rather than at module import time, mirroring
#: `workers.baseline.dispatch`'s own import of the same package, so a control-api
#: process that never runs a stage does not pay for the import at startup either.


class EvidenceUnavailableError(ContractError):
    """There is not enough recorded for this mission to assemble an honest bundle.

    Distinct from `MissionNotFoundError` (no such mission at all): this is a real
    mission with no snapshot or no authorization on file yet — reachable only if
    export is attempted before `SNAPSHOTTED`/`AUTHORIZED`, which no real pipeline path
    does (every job-backed state sits downstream of both), but the HTTP `POST
    /export`/`GET /evidence` endpoints accept a mission id from any state per
    architecture spec §5.3 ("exportable from any state"), so a caller can reach this
    directly. Refuses rather than fabricating a `snapshot_sha256`/`authorization_
    statement` the schema requires but the mission never recorded.
    """

    code = ErrorCode.CONFLICT
    http_status = 409
    default_message = (
        "This mission has no recorded snapshot and/or authorization yet; there is "
        "not enough evidence to assemble a bundle."
    )


#: Human-readable reason attached to the always-on `SUBPROCESS_JAIL_ISOLATION`
#: substitution below. Stated once here rather than inline so
#: `test_evidence_bundle.py` can assert against the same string this module renders.
_SUBPROCESS_JAIL_REASON = (
    "The rootless-container sandbox backend (#15) is not built in this checkout; "
    "stages ran inside packages.sandbox's subprocess jail (#81) instead — a weaker "
    "isolation posture than a container, reported as what it is (D-049)."
)


def assemble_evidence_bundle(mission_id: UUID, *, now: datetime | None = None) -> EvidenceBundle:
    """Read every table T6's earlier stages already wrote and reassemble the frozen
    `EvidenceBundle` schema. Raises `MissionNotFoundError` / `EvidenceUnavailableError`
    rather than fabricating a field the schema requires but nothing recorded.
    """
    now = now or timezone.now()
    try:
        mission = Mission.objects.get(pk=mission_id)
    except Mission.DoesNotExist as exc:
        raise MissionNotFoundError(
            "No mission with that id.", details={"mission_id": str(mission_id)}
        ) from exc

    snapshot_sha256 = repository.latest_snapshot_sha256(mission)
    if not snapshot_sha256:
        raise EvidenceUnavailableError(
            "This mission has no recorded snapshot; nothing has been ingested to "
            "generate evidence about.",
            details={"mission_id": str(mission_id)},
        )

    authorization_row = mission.authorizations.order_by("-granted_at").first()
    if authorization_row is None:
        raise EvidenceUnavailableError(
            "This mission has no authorization record on file.",
            details={"mission_id": str(mission_id)},
        )

    baseline = _optional(evidence_repository.get_baseline_report, mission_id)
    fuzzing = _optional(evidence_repository.get_fuzzing_report, mission_id)
    findings, _ = evidence_repository.list_findings(mission_id, limit=10_000, offset=0)
    reproducers = _all_reproducers(mission_id, findings)
    patches, _ = evidence_repository.list_patch_candidates(mission_id, limit=10_000, offset=0)
    verifications = repository.load_verifications(mission_id)

    verdict_summary = _verdict_summary(patches, verifications)
    recommended_patch_id = _recommended_patch_id(verifications)

    resource_usage = _resource_usage(mission)
    gates_not_run = _gates_not_run(verifications)
    substitutions = _substitutions(now, findings, fuzzing, patches)
    tool_versions = _tool_versions(mission, baseline, fuzzing, verifications, patches)

    from packages.sandbox import ISOLATION_MODE  # local import, see module docstring

    return EvidenceBundle(
        mission_id=mission.id,
        generated_at=now,
        snapshot_sha256=snapshot_sha256,
        authorization_statement=authorization_row.statement,
        baseline=baseline,
        findings=findings,
        reproducers=reproducers,
        fuzzing=fuzzing,
        patches=patches,
        verifications=verifications,
        verdict_summary=verdict_summary,
        recommended_patch_id=recommended_patch_id,
        resource_usage=resource_usage,
        gates_not_run=gates_not_run,
        substitutions=substitutions,
        isolation_mode=ISOLATION_MODE,
        tool_versions=tool_versions,
    )


def _optional(reader, mission_id: UUID):
    """`evidence_repository`'s per-table readers raise `Http404` on "no row"; the
    bundle represents that as `None`, per this module's own "honest partial data"
    section, rather than letting the 404 propagate out of an assembly function that
    is allowed to be missing whole sections."""
    from django.http import Http404

    try:
        return reader(mission_id)
    except Http404:
        return None


def _all_reproducers(mission_id: UUID, findings) -> list:
    """`EvidenceBundle.reproducers` is a flat, mission-wide list; `evidence_repository`
    only exposes reproducers nested under one finding's detail. One extra read per
    finding is the honest cost of not inventing a bulk reader that does not exist yet;
    the number of findings a seven-day demo mission produces is small."""
    reproducers = []
    for summary in findings:
        detail = evidence_repository.get_finding_detail(mission_id, summary.id)
        if detail.reproducer is not None:
            reproducers.append(detail.reproducer)
    return reproducers


def _verdict_summary(patches, verifications) -> MissionVerdictSummary | None:
    if not verifications:
        return None
    provenance_by_patch = {patch.id: patch.provenance for patch in patches}
    candidates = [
        CandidateVerdict(
            patch_id=record.patch_id,
            verification_id=record.id,
            verdict=record.verdict,
            provenance=provenance_by_patch.get(record.patch_id),
            summary=_verification_summary(record),
        )
        for record in verifications
    ]
    mission_verdict = derive_mission_verdict([c.verdict for c in candidates])
    verified = sum(1 for c in candidates if c.verdict == "VERIFIED")
    rejected = sum(1 for c in candidates if c.verdict == "REJECTED")
    human_review = sum(1 for c in candidates if c.verdict == "HUMAN_REVIEW_REQUIRED")
    return MissionVerdictSummary(
        mission_verdict=mission_verdict,
        candidates=candidates,
        verified_count=verified,
        rejected_count=rejected,
        human_review_count=human_review,
    )


def _verification_summary(record) -> str:
    failing = [
        result.name
        for result in record.gates.results()
        if result.status in (GateStatus.FAIL, GateStatus.NOT_RUN, GateStatus.ERROR)
    ]
    if not failing:
        return "All gates passed."
    return f"Did not clear: {', '.join(str(name) for name in failing)}."


def _recommended_patch_id(verifications):
    verified_ids = {record.patch_id for record in verifications if record.verdict == "VERIFIED"}
    if len(verified_ids) == 1:
        return next(iter(verified_ids))
    return None


def _resource_usage(mission: Mission) -> ResourceUsage:
    """Summed/maxed across every `ResourceSample` this mission recorded. Zeroed
    fields when no samples exist at all are the schema's only vocabulary for "not
    measured yet" — `render_markdown` (`orchestrator.evidence_export`) states that
    distinction in prose; this function cannot, since `ResourceUsage` has no
    "recorded" flag (a gap in the frozen schema, not something to invent a workaround
    for here)."""
    samples = list(mission.resource_samples.all())
    if not samples:
        return ResourceUsage(
            cpu_seconds=0.0, peak_memory_mb=0.0, wall_seconds=0.0, sandbox_count=0, gpu_seconds=0.0
        )
    return ResourceUsage(
        cpu_seconds=sum(s.cpu_seconds for s in samples),
        peak_memory_mb=max(s.peak_memory_mb for s in samples),
        wall_seconds=sum(s.wall_seconds for s in samples),
        sandbox_count=sum(s.sandbox_count for s in samples),
        gpu_seconds=sum(s.gpu_seconds for s in samples),
    )


def _gates_not_run(verifications) -> list[str]:
    """Derived from the verification records just read, never hand-set — the shape
    architecture spec §5.4 point 4 (Δ #51) asks for, applied at the point of assembly
    rather than in a schema validator (that fix is `contracts/`'s to make; out of this
    task's scope, and flagged in the handoff)."""
    entries: list[str] = []
    for record in verifications:
        short_patch = str(record.patch_id)[:8]
        for result in record.gates.results():
            if result.status in (GateStatus.NOT_RUN, GateStatus.ERROR):
                entries.append(
                    f"patch {short_patch}: {result.name} {result.status} — {result.detail or 'no reason recorded'}"
                )
    return entries


def _substitutions(now, findings, fuzzing, patches) -> list[Substitution]:
    """Every fallback path this module can actually detect from recorded data, per
    `SubstitutionKind`'s own members. `SUBPROCESS_JAIL_ISOLATION` is unconditional —
    see `_SUBPROCESS_JAIL_REASON` — because it is a fact about how this deployment is
    wired, true for every mission until #15 lands, not a per-run measurement."""
    substitutions = [
        Substitution(
            kind=SubstitutionKind.SUBPROCESS_JAIL_ISOLATION,
            reason=_SUBPROCESS_JAIL_REASON,
            recorded_at=now,
        )
    ]

    if fuzzing is not None and fuzzing.replay_source:
        substitutions.append(
            Substitution(
                kind=SubstitutionKind.REPRODUCER_REPLAY,
                reason=(
                    f"Fuzzing mode {fuzzing.mode} replayed a recorded corpus instead of "
                    f"running a live campaign."
                ),
                artifact_ref=fuzzing.replay_source,
                recorded_at=now,
            )
        )

    for summary in findings:
        if summary.replay_source:
            substitutions.append(
                Substitution(
                    kind=SubstitutionKind.REPRODUCER_REPLAY,
                    reason=(
                        f"Finding {summary.id} was discovered via a replayed "
                        f"reproducer, not a live campaign."
                    ),
                    artifact_ref=summary.replay_source,
                    recorded_at=now,
                )
            )

    for patch in patches:
        if patch.provenance == "OPERATOR_SUPPLIED":
            substitutions.append(
                Substitution(
                    kind=SubstitutionKind.OPERATOR_SUPPLIED_PATCH,
                    reason=(
                        f"Patch candidate {patch.id} was supplied by an operator, not "
                        f"generated by the model."
                    ),
                    recorded_at=now,
                )
            )
        elif (
            patch.model is not None
            and patch.model.inference_mode == InferenceMode.REPLAYED_TRANSCRIPT
        ):
            substitutions.append(
                Substitution(
                    kind=SubstitutionKind.MODEL_REPLAY,
                    reason=(
                        f"Patch candidate {patch.id} was replayed from a captured "
                        f"model transcript rather than generated live."
                    ),
                    artifact_ref=patch.model.replayed_from_transcript,
                    recorded_at=now,
                )
            )

    return substitutions


def _tool_versions(mission, baseline, fuzzing, verifications, patches) -> dict[str, str]:
    """Every real tool/version this module can read off already-recorded rows.
    Nothing here is guessed: a value is only present if some stage already recorded
    it. `StageToolRun` (architecture spec §5.1) is the intended primary source but is
    not yet populated by any stage as of T1/T5 — checked directly, zero rows in any
    fixture or migration data — so this mostly draws from `GateResult.tool` and the
    baseline/fuzzing rows today. An empty dict is the honest answer when none of these
    have anything recorded, not a fabricated placeholder."""
    versions: dict[str, str] = {}

    for run in mission.stage_tool_runs.all():
        if run.tool_name:
            versions[run.tool_name] = run.tool_version

    if baseline is not None and baseline.adapter:
        versions.setdefault("adapter", baseline.adapter)

    if fuzzing is not None and fuzzing.engine:
        versions.setdefault("fuzzer", fuzzing.engine)

    for record in verifications:
        for result in record.gates.results():
            if result.tool:
                versions.setdefault(str(result.name).lower(), result.tool)

    for patch in patches:
        if patch.model is not None:
            label = patch.model.model_name
            if patch.model.model_revision:
                label = f"{label}@{patch.model.model_revision}"
            versions.setdefault("model", label)

    return versions
