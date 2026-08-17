"""Rendering the assembled `EvidenceBundle` to durable bytes, and recording the
`Export` row that points at them (#168, T6).

`orchestrator.evidence_bundle.assemble_evidence_bundle` is a pure read; everything
that actually writes something lives here: `report.md`/`report.json`/
`manifest.json`/`gate-matrix.json`/`tool-versions.json` (architecture spec §5.3's
directory layout), a deterministic `.tar.gz` of that directory, and — mirroring
`authorization.store`'s content-addressed pattern T0b already established for
snapshot bytes — ingestion of that tarball into `ARTIFACT_ROOT`, indexed by an
`Artifact` row and pointed at by one `Export` row per successful call.

## Idempotency (D-061 §3 rule 2, this stage's version of it)

`Export` has no per-mission uniqueness constraint (`missions/models.py` — a mission
may legitimately be exported more than once, e.g. the operator re-requests a
different `formats` subset). What D-061 §3 actually asks for is narrower: **a worker
that crashed after writing a bundle but before its `JobKind.EXPORT` job reached
`SUCCEEDED` must not redo the work on restart.** `export_mission`'s `reuse_existing`
flag is that check — `True` for the pipeline-driven executor path (`export_
executor.py`), which always wants the mission's existing bundle if one is already on
record; `False` for the operator-facing `POST /export` endpoint, where a fresh
request is a fresh, deliberate action (mirroring `POST` semantics generally — this
project's own convention, `missions.service.create_mission`, uses `Mission.
idempotency_key` for a comparable "retry-safe" behaviour on that endpoint, but
`ExportRequest.idempotency_key` has no backing column on `Export` today, a real,
disclosed gap — see the module docstring's "Known gaps" section below).

Beyond that flag: `store.ingest_from_path` is itself idempotent by content address
(`authorization/store.py` — a destination that already exists is left alone rather
than rewritten), so even a `reuse_existing=False` call that happens to produce
byte-identical bundle content never corrupts or duplicates the artifact bytes on
disk — only a new `Export` row (a new `export_id`, new `generated_at`) is added,
which is the correct behaviour for a new export *request*.

## Known gaps, disclosed rather than silently absorbed

* `ExportRequest.include_artifacts=True` does not yet copy raw stage artifacts
  (build logs, crash inputs, patch diffs as separate files) into the bundle's
  `artifacts/` directory — there is no existing function anywhere in this codebase
  that resolves an `ArtifactRef.uri` back to bytes under `ARTIFACT_ROOT` (checked
  directly; `authorization.store.path_for` needs a sha256, and no `ArtifactRef` in
  this contract carries one for every kind yet). The flag is honoured as far as
  writing an empty `artifacts/` directory with a `NOTE.txt` stating this plainly,
  rather than silently ignoring the flag or fabricating file contents.
* `ExportRequest.idempotency_key` is accepted by the schema and validated, but is
  not persisted anywhere (`Export` has no such column) — a second `POST /export`
  with the same key currently produces a second `Export` row rather than replaying
  the first response. Flagged in this task's handoff for database-engineer/CTO
  sign-off on whether it is worth a migration; not fixed unilaterally here (schema
  changes are not this task's call, per this repo's role boundaries).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from authorization import archive, store
from authorization.errors import MissionNotFoundError
from contracts.schemas.common import ArtifactRef
from contracts.schemas.evidence import EvidenceBundle, ExportReceipt
from contracts.verdict import GateStatus
from missions.models import Artifact, Export, Mission, PatchCandidate
from orchestrator.evidence_bundle import assemble_evidence_bundle

#: `Artifact.kind` for the one durable object this module writes. A single value
#: because the tarball is the artifact of record — its contents already carry
#: report.md/report.json/manifest.json/gate-matrix.json/tool-versions.json; there is
#: no separate content-addressed row per component file (see module docstring).
BUNDLE_ARTIFACT_KIND = "evidence_bundle"

DEFAULT_FORMATS: tuple[str, ...] = ("markdown", "json")


def default_export_workspace_root() -> Path:
    """`EXPORT_WORKSPACE_ROOT`, read at call time so `override_settings` in tests is
    honoured — same reasoning as `orchestrator.snapshot.default_workspace_root`."""
    configured = getattr(settings, "EXPORT_WORKSPACE_ROOT", None)
    if configured:
        return Path(configured)
    return Path(settings.ARTIFACT_ROOT).parent / "exports"


@dataclass(frozen=True)
class ExportOutcome:
    receipt: ExportReceipt
    reused_existing: bool


def export_mission(
    mission_id,
    *,
    formats: list[str] | None = None,
    include_artifacts: bool = False,
    reuse_existing: bool = True,
    workspace_root: Path | None = None,
    now: datetime | None = None,
) -> ExportOutcome:
    """Assemble (or reuse) this mission's evidence bundle and return an `ExportOutcome`.

    `reuse_existing=True` is the D-061 §3 idempotency check: if this mission already
    has an `Export` row, return it verbatim rather than re-rendering and re-tarring —
    the pipeline-driven `JobKind.EXPORT` executor always calls it this way. The
    HTTP-facing `POST /export` endpoint calls it with `reuse_existing=False`, since
    each request is a deliberate, distinct export action (see module docstring).
    """
    now = now or timezone.now()
    try:
        mission = Mission.objects.get(pk=mission_id)
    except Mission.DoesNotExist as exc:
        raise MissionNotFoundError(
            "No mission with that id.", details={"mission_id": str(mission_id)}
        ) from exc

    if reuse_existing:
        existing = Export.objects.filter(mission=mission).order_by("-generated_at").first()
        if existing is not None:
            return ExportOutcome(receipt=_receipt_from_export(existing), reused_existing=True)

    formats = list(formats) if formats else list(DEFAULT_FORMATS)
    root = workspace_root if workspace_root is not None else default_export_workspace_root()

    bundle = assemble_evidence_bundle(mission.id, now=now)

    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    bundle_name = f"brahmadatta-evidence-{mission.id}-{stamp}"
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    bundle_dir = root / f"{bundle_name}-{uuid.uuid4().hex}"
    bundle_dir.mkdir(parents=True, mode=0o700, exist_ok=False)

    try:
        manifest_entries = _write_bundle_files(bundle_dir, bundle, formats, include_artifacts)
        (bundle_dir / "manifest.json").write_text(
            json.dumps(
                {"generated_at": bundle.generated_at.isoformat(), "files": manifest_entries},
                indent=2,
            )
        )

        tar_path = bundle_dir.parent / f"{bundle_name}.tar"
        tar_gz_path = bundle_dir.parent / f"{bundle_name}.tar.gz"
        archive.build_tar_from_directory(bundle_dir, tar_path)
        _gzip_deterministic(tar_path, tar_gz_path)
        tar_path.unlink(missing_ok=True)

        ingest = store.ingest_from_path(
            Path(settings.ARTIFACT_ROOT),
            tar_gz_path,
            max_bytes=settings.EVIDENCE_BUNDLE_MAX_BYTES,
        )
        tar_gz_path.unlink(missing_ok=True)
    finally:
        shutil.rmtree(bundle_dir, ignore_errors=True)

    artifact, _ = Artifact.objects.get_or_create(
        sha256=ingest.sha256,
        defaults={
            "kind": BUNDLE_ARTIFACT_KIND,
            "size_bytes": ingest.bytes_written,
            "mission": mission,
        },
    )

    recommended_patch = None
    if bundle.recommended_patch_id is not None:
        recommended_patch = PatchCandidate.objects.filter(pk=bundle.recommended_patch_id).first()

    artifact_ref = ArtifactRef(
        uri=f"artifact://{mission.id}/{BUNDLE_ARTIFACT_KIND}/{artifact.sha256}",
        kind=BUNDLE_ARTIFACT_KIND,
        sha256=artifact.sha256,
        size_bytes=artifact.size_bytes,
    )

    export_row = Export.objects.create(
        mission=mission,
        formats=formats,
        artifact_refs=[artifact_ref.model_dump(mode="json")],
        isolation_mode=str(bundle.isolation_mode),
        recommended_patch=recommended_patch,
        generated_at=now,
    )

    return ExportOutcome(receipt=_receipt_from_export(export_row), reused_existing=False)


def _receipt_from_export(export_row: Export) -> ExportReceipt:
    return ExportReceipt(
        mission_id=export_row.mission_id,
        export_id=export_row.id,
        formats=list(export_row.formats),
        artifacts=[ArtifactRef(**ref) for ref in export_row.artifact_refs],
        generated_at=export_row.generated_at,
    )


# ------------------------------------------------------------------------------------
# File rendering
# ------------------------------------------------------------------------------------


def _write_bundle_files(
    bundle_dir: Path, bundle: EvidenceBundle, formats: list[str], include_artifacts: bool
) -> list[dict]:
    """Write every component file architecture spec §5.3 names, and return the
    `manifest.json` entries describing what was written (sha256 computed from the
    bytes actually on disk, never assumed)."""
    entries: list[dict] = []

    if "markdown" in formats:
        entries.append(
            _write_file(
                bundle_dir, bundle_dir, "report.md", render_markdown(bundle).encode(), "report"
            )
        )
    if "json" in formats:
        entries.append(
            _write_file(
                bundle_dir,
                bundle_dir,
                "report.json",
                bundle.model_dump_json(indent=2).encode(),
                "report",
            )
        )

    entries.append(
        _write_file(
            bundle_dir,
            bundle_dir,
            "gate-matrix.json",
            json.dumps(render_gate_matrix(bundle), indent=2).encode(),
            "gate_matrix",
        )
    )
    entries.append(
        _write_file(
            bundle_dir,
            bundle_dir,
            "tool-versions.json",
            json.dumps(bundle.tool_versions, indent=2, sort_keys=True).encode(),
            "tool_versions",
        )
    )

    if include_artifacts:
        artifacts_dir = bundle_dir / "artifacts"
        artifacts_dir.mkdir(mode=0o700)
        note = (
            "Raw stage artifacts (build logs, crash inputs, patch diffs as separate "
            "files) are not copied into this directory in this build — no function "
            "in this codebase yet resolves an ArtifactRef back to its stored bytes "
            "generically. The diffs and sanitized text this bundle can vouch for are "
            "already inline in report.json/report.md. Disclosed here rather than "
            "silently ignoring `include_artifacts=true`."
        )
        entries.append(_write_file(bundle_dir, artifacts_dir, "NOTE.txt", note.encode(), "note"))

    return entries


def _write_file(bundle_dir: Path, directory: Path, name: str, data: bytes, kind: str) -> dict:
    """Write `data` under `directory` (which is `bundle_dir` itself, or a
    subdirectory of it) and describe it relative to `bundle_dir` — the path
    `manifest.json` and the eventual tarball both use."""
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    path = directory / name
    path.write_bytes(data)
    return {
        "path": path.relative_to(bundle_dir).as_posix(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "kind": kind,
    }


def render_gate_matrix(bundle: EvidenceBundle) -> list[dict]:
    """Every `VerificationRecord`'s matrix, flattened for skimming — architecture spec
    §5.3's `gate-matrix.json`."""
    flattened = []
    for record in bundle.verifications:
        flattened.append(
            {
                "patch_id": str(record.patch_id),
                "verification_id": str(record.id),
                "verdict": str(record.verdict),
                "gates": {
                    str(result.name): {
                        "status": str(result.status),
                        "tool": result.tool,
                        "detail": result.detail,
                    }
                    for result in record.gates.results()
                },
            }
        )
    return flattened


def render_markdown(bundle: EvidenceBundle) -> str:
    """`report.md` — what the judge is handed. Every section that has no data states
    so explicitly (this module's own "honest partial data" obligation); nothing is
    silently omitted or padded with a placeholder."""
    lines: list[str] = []
    lines.append(f"# Brahmadatta evidence bundle — mission {bundle.mission_id}")
    lines.append("")
    lines.append(f"Generated: {bundle.generated_at.isoformat()}")
    lines.append(f"Snapshot sha256: `{bundle.snapshot_sha256}`")
    lines.append(f"Isolation mode: {bundle.isolation_mode}")
    lines.append("")
    lines.append("## Authorization")
    lines.append("")
    lines.append(bundle.authorization_statement)
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    if bundle.verdict_summary is not None:
        summary = bundle.verdict_summary
        lines.append(
            f"**MISSION VERDICT: {summary.mission_verdict}** — "
            f"{summary.verified_count} verified / {summary.rejected_count} rejected / "
            f"{summary.human_review_count} human review, of {len(summary.candidates)} "
            f"candidate(s)."
        )
        if bundle.recommended_patch_id is not None:
            lines.append(f"Recommended patch: `{bundle.recommended_patch_id}`")
    else:
        lines.append(
            "**No verdict yet.** No verification record exists for this mission "
            "— either verification has not run, or (see Findings/Patches below) "
            "there was never a candidate to verify."
        )
    lines.append("")

    lines.append("## Baseline")
    lines.append("")
    if bundle.baseline is not None:
        b = bundle.baseline
        lines.append(
            f"configure_ok={b.configure_ok} build_ok={b.build_ok} "
            f"tests={b.tests_passed}/{b.tests_total} passed "
            f"({b.tests_failed} failed) — {b.duration_seconds:.1f}s, adapter {b.adapter}"
        )
        lines.append(f"Passed (D3 gate denominator): **{b.passed}**")
    else:
        lines.append("No baseline recorded for this mission.")
    lines.append("")

    lines.append("## Fuzzing")
    lines.append("")
    if bundle.fuzzing is not None:
        f = bundle.fuzzing
        lines.append(
            f"mode={f.mode} harness={f.harness} engine={f.engine} "
            f"runtime={f.runtime_seconds:.1f}s executions={f.executions} "
            f"crashes_found={f.crashes_found} unique_crashes={f.unique_crashes} "
            f"corpus_size={f.corpus_size} sanitizers={', '.join(f.sanitizers) or 'none'}"
        )
    else:
        lines.append("No fuzzing report recorded for this mission.")
    lines.append("")

    lines.append(f"## Findings ({len(bundle.findings)})")
    lines.append("")
    if bundle.findings:
        for finding in bundle.findings:
            lines.append(
                f"- `{finding.id}` {finding.severity} {finding.category} — "
                f"{finding.title} ({finding.location.file_path}:{finding.location.line}), "
                f"reproducible={finding.reproducible}, via {finding.discovery_method}"
            )
    else:
        lines.append(
            "No findings recorded. Either the stress-test/analysis stages have not "
            "run, or they ran and found nothing to bind — not the same as a clean "
            "target, and not claimed as one."
        )
    lines.append("")

    lines.append(f"## Patch candidates ({len(bundle.patches)})")
    lines.append("")
    if bundle.patches:
        verifications_by_patch = {v.patch_id: v for v in bundle.verifications}
        for patch in bundle.patches:
            lines.append(
                f"### `{patch.id}` ({patch.provenance}, {patch.policy_status}, "
                f"{patch.files_changed} file(s), {patch.lines_changed} line(s))"
            )
            lines.append("")
            verification = verifications_by_patch.get(patch.id)
            if verification is not None:
                lines.append(
                    f"Verdict: **{verification.verdict}** — {_gate_denominator(verification)}"
                )
                lines.append("")
                lines.append(_render_gate_table(verification))
            else:
                lines.append(
                    "Not verified: this candidate has no `VerificationRecord` "
                    "(policy rejection, or verification has not run yet)."
                )
            lines.append("")
    else:
        lines.append(
            "No patch candidates. CORRELATE produced no finding to patch, or PATCH has not run yet."
        )
    lines.append("")

    lines.append("## Substitutions (fallback paths used)")
    lines.append("")
    for substitution in bundle.substitutions:
        lines.append(f"- **{substitution.kind}**: {substitution.reason}")
    if not bundle.substitutions:
        lines.append("None — every primary path ran throughout.")
    lines.append("")

    lines.append("## Gates that did not run")
    lines.append("")
    if bundle.gates_not_run:
        for entry in bundle.gates_not_run:
            lines.append(f"- {entry}")
    else:
        lines.append("None recorded (either every gate ran, or no verification has run yet).")
    lines.append("")

    lines.append("## Resource usage")
    lines.append("")
    r = bundle.resource_usage
    lines.append(
        f"cpu_seconds={r.cpu_seconds:.1f} peak_memory_mb={r.peak_memory_mb:.1f} "
        f"wall_seconds={r.wall_seconds:.1f} sandbox_count={r.sandbox_count} "
        f"gpu_seconds={r.gpu_seconds:.1f}"
    )
    if r.cpu_seconds == 0 and r.wall_seconds == 0 and r.sandbox_count == 0:
        lines.append(
            "_Note: no `ResourceSample` rows exist for this mission — this reads as "
            "zero because nothing has been measured yet, not because zero resources "
            "were used._"
        )
    lines.append("")

    lines.append("## Tool versions")
    lines.append("")
    if bundle.tool_versions:
        for name, version in sorted(bundle.tool_versions.items()):
            lines.append(f"- {name}: {version}")
    else:
        lines.append("None recorded.")
    lines.append("")

    return "\n".join(lines)


def _gate_denominator(verification) -> str:
    ran = sum(
        1
        for result in verification.gates.results()
        if result.status is GateStatus.PASS or result.status is GateStatus.FAIL
    )
    total = sum(1 for _ in verification.gates.results())
    return f"{ran} of {total} gates ran"


def _render_gate_table(verification) -> str:
    rows = ["| Gate | Status | Tool | Detail |", "|---|---|---|---|"]
    for result in verification.gates.results():
        rows.append(
            f"| {result.name} | {result.status} | {result.tool or '—'} | {result.detail or '—'} |"
        )
    return "\n".join(rows)


def _gzip_deterministic(source: Path, dest: Path) -> None:
    """Gzip `source` to `dest` with a fixed mtime, so the same tar bytes always
    produce the same gzip bytes — mirroring `authorization.archive.
    build_tar_from_directory`'s own determinism for the tar layer beneath this."""
    with source.open("rb") as raw:
        data = raw.read()
    with open(dest, "wb") as out:
        with gzip.GzipFile(filename="", mode="wb", fileobj=out, mtime=0) as gz:
            gz.write(data)
