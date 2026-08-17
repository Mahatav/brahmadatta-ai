"""`orchestrator.evidence_export` — SEC-48 / SEC-49 (`.project/decisions.md` D-071b).

Two shapes of adversarial test, mirroring the cybersecurity reviewer's own approach
on PR #187 rather than inventing a different one:

1. **SEC-48.** Poison a `GateResult.detail` with content shaped like the concrete leak
   this review reproduced (a fabricated `DATABASE_URL=postgresql://...` line spliced
   into captured subprocess-shaped text, and a bare `KEY=value` secret line on an
   `ERROR` gate that only `_gates_not_run` ever renders), carry it through a real
   `record_verification` -> `export_mission` round-trip, extract the *actual* tarball
   this produces under `ARTIFACT_ROOT`, and assert none of `report.md`, `report.json`,
   or `gate-matrix.json` contain it. Also asserts the sanitizer is not
   over-redacting: a benign, already-safe `detail` (including `contracts/verdict.py`'s
   own `_CUT_REASON`, present on every `GateMatrix` by default) survives untouched.
2. **SEC-49.** Force `EVIDENCE_BUNDLE_MAX_BYTES` far below any real bundle's size,
   confirm `export_mission` fails with `UnreadableArchiveError`, and confirm no
   `.tar`/`.tar.gz` is left behind anywhere under the workspace root afterward.
"""

from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

from authorization.errors import UnreadableArchiveError
from contracts.enums import (
    EvidenceSource,
    GateName,
    GateStatus,
    MissionState,
    PatchPolicyStatus,
    PatchProvenance,
)
from contracts.verdict import GateMatrix, GateResult
from missions.models import Artifact
from orchestrator import candidates, transitions
from orchestrator.evidence_export import export_mission
from orchestrator.redaction import sanitize_detail
from orchestrator.tests.conftest import CANDIDATE_A, NOW, TRACE, gate_matrix, walk_to

pytestmark = pytest.mark.django_db(transaction=True)

#: Shaped exactly like the leak this review reproduced: a captured `cmake configure`
#: failure whose stdout happened to include an inherited `DATABASE_URL` (the concrete
#: SEC-44 exfiltration channel this same review chain named) spliced straight into
#: `detail`, the way a pre-SEC-45 `_summarize` used to build it.
_POISONED_CONNECTION_STRING_DETAIL = (
    "cmake configure: -- Configuring done\n"
    "-- DATABASE_URL=postgresql://brahmadatta:s3cr3t-pw@10.0.0.5:5432/prod\n"
    "CMake Error: could not find CMAKE_C_COMPILER exit=1"
)

#: A bare `KEY=value` secret with no scheme separator and no newline — the shape
#: `_gates_not_run` (`orchestrator/evidence_bundle.py`) is the only exported path for,
#: since it only ever fires on `NOT_RUN`/`ERROR` gates.
_POISONED_ENV_LINE_DETAIL = "REDIS_URL=redis://:hunter2@cache.internal:6379/0"

#: A secret that carries no scheme separator at all, to prove the `KEY=value` check
#: (not just the `://` check) is doing real work on its own.
_POISONED_BARE_ASSIGNMENT_DETAIL = "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI-K7MDENG-bPxRfiCYEXAMPLEKEY"


def _mission_with_poisoned_verification(mission, finding):
    """Drive a mission to `EXPORTING` with one candidate whose verification carries
    poisoned `detail` values on three different gates: a `FAIL` (`compile`, read by
    `render_gate_matrix`/`_render_gate_table`/`model_dump_json()`), and two
    `NOT_RUN`/`ERROR` gates (read only by `evidence_bundle._gates_not_run`)."""
    walk_to(mission, MissionState.PATCH)
    candidate = candidates.record_patch_candidate(
        mission.id,
        finding_id=finding.id,
        provenance=PatchProvenance.OPERATOR_SUPPLIED,
        diff=CANDIDATE_A.read_text(),
        files_changed=1,
        lines_changed=7,
        policy_status=PatchPolicyStatus.ACCEPTED,
        trace_id=TRACE,
        now=NOW,
    )
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)

    poisoned_matrix = GateMatrix(
        compile=GateResult(
            name=GateName.COMPILE,
            status=GateStatus.FAIL,
            evidence_source=EvidenceSource.TOOL_EXECUTION,
            tool="cmake",
            detail=_POISONED_CONNECTION_STRING_DETAIL,
        ),
        reproducer_eliminated=GateResult.not_run(
            GateName.REPRODUCER_ELIMINATED,
            "Not run: configure failed before a replay binary existed.",
        ),
        regression_preserved=GateResult(
            name=GateName.REGRESSION_PRESERVED,
            status=GateStatus.ERROR,
            evidence_source=EvidenceSource.TOOL_EXECUTION,
            tool="ctest",
            detail=_POISONED_ENV_LINE_DETAIL,
        ),
    )
    candidates.record_verification(
        mission.id,
        patch_id=candidate.id,
        gates=poisoned_matrix,
        started_at=NOW,
        finished_at=NOW,
        trace_id=TRACE,
        now=NOW,
    )
    transitions.transition(mission.id, MissionState.EXPORTING, trace_id=TRACE, now=NOW)
    mission.refresh_from_db()
    return candidate


def _extract_bundle_files(artifact: Artifact, artifact_root: Path) -> dict[str, str]:
    stored_path = artifact_root / artifact.sha256[:2] / artifact.sha256
    assert stored_path.is_file(), "the exported tarball must actually be on disk"
    contents: dict[str, str] = {}
    with tarfile.open(stored_path, "r:gz") as tar:
        for member in tar.getmembers():
            if member.isfile() and member.name.split("/")[-1] in (
                "report.md",
                "report.json",
                "gate-matrix.json",
            ):
                extracted = tar.extractfile(member)
                assert extracted is not None
                contents[member.name.split("/")[-1]] = extracted.read().decode()
    assert set(contents) == {"report.md", "report.json", "gate-matrix.json"}
    return contents


# ---------------------------------------------------------------------------------
# 1. SEC-48 — the poisoned `detail` never reaches an exported file
# ---------------------------------------------------------------------------------


def test_poisoned_connection_string_detail_never_reaches_the_exported_bundle(
    mission, finding, tmp_path, settings
):
    settings.ARTIFACT_ROOT = tmp_path / "artifacts"
    settings.EXPORT_WORKSPACE_ROOT = tmp_path / "exports"

    _mission_with_poisoned_verification(mission, finding)

    outcome = export_mission(mission.id, reuse_existing=False, now=NOW)
    artifact = Artifact.objects.get(mission=mission, kind="evidence_bundle")
    files = _extract_bundle_files(artifact, settings.ARTIFACT_ROOT)

    secret_shaped_fragments = [
        "DATABASE_URL",
        "postgresql://",
        "s3cr3t-pw",
        "10.0.0.5",
        "REDIS_URL",
        "redis://",
        "hunter2",
        "cache.internal",
        "CMake Error",  # raw tool-output fragment; not part of any sanctioned summary
    ]
    for filename, content in files.items():
        for fragment in secret_shaped_fragments:
            assert fragment not in content, (
                f"{filename} leaked a secret-shaped fragment ({fragment!r}) from a "
                f"poisoned GateResult.detail — SEC-48 regression"
            )
        # The redaction placeholder itself must appear in place of the poisoned
        # values, not a silent drop of the whole record.
        assert "[redacted at export boundary" in content

    assert outcome.reused_existing is False


def test_bare_assignment_secret_with_no_scheme_is_also_redacted(
    mission, finding, tmp_path, settings
):
    """The `KEY=value` check must not depend on a `://` scheme separator being
    present — a bare secret assignment with no scheme is exactly as dangerous."""
    settings.ARTIFACT_ROOT = tmp_path / "artifacts"
    settings.EXPORT_WORKSPACE_ROOT = tmp_path / "exports"

    walk_to(mission, MissionState.PATCH)
    candidate = candidates.record_patch_candidate(
        mission.id,
        finding_id=finding.id,
        provenance=PatchProvenance.OPERATOR_SUPPLIED,
        diff=CANDIDATE_A.read_text(),
        files_changed=1,
        lines_changed=7,
        policy_status=PatchPolicyStatus.ACCEPTED,
        trace_id=TRACE,
        now=NOW,
    )
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)
    matrix = GateMatrix(
        compile=GateResult(
            name=GateName.COMPILE,
            status=GateStatus.FAIL,
            evidence_source=EvidenceSource.TOOL_EXECUTION,
            tool="cmake",
            detail=_POISONED_BARE_ASSIGNMENT_DETAIL,
        ),
        reproducer_eliminated=GateResult.not_run(
            GateName.REPRODUCER_ELIMINATED, "Not run: configure failed."
        ),
        regression_preserved=GateResult.not_run(
            GateName.REGRESSION_PRESERVED, "Not run: configure failed."
        ),
    )
    candidates.record_verification(
        mission.id,
        patch_id=candidate.id,
        gates=matrix,
        started_at=NOW,
        finished_at=NOW,
        trace_id=TRACE,
        now=NOW,
    )
    transitions.transition(mission.id, MissionState.EXPORTING, trace_id=TRACE, now=NOW)

    export_mission(mission.id, reuse_existing=False, now=NOW)
    artifact = Artifact.objects.get(mission=mission, kind="evidence_bundle")
    files = _extract_bundle_files(artifact, settings.ARTIFACT_ROOT)

    for filename, content in files.items():
        assert "AWS_SECRET_ACCESS_KEY" not in content, filename
        assert "wJalrXUtnFEMI" not in content, filename


def test_sanitizer_does_not_over_redact_benign_detail(mission, finding, tmp_path, settings):
    """A real, honest gate outcome — including `contracts/verdict.py`'s own
    `_CUT_REASON`, present on every `GateMatrix` by default — must survive the export
    boundary unchanged. A redaction pass that nukes everything is not a fix."""
    settings.ARTIFACT_ROOT = tmp_path / "artifacts"
    settings.EXPORT_WORKSPACE_ROOT = tmp_path / "exports"

    walk_to(mission, MissionState.PATCH)
    candidate = candidates.record_patch_candidate(
        mission.id,
        finding_id=finding.id,
        provenance=PatchProvenance.OPERATOR_SUPPLIED,
        diff=CANDIDATE_A.read_text(),
        files_changed=1,
        lines_changed=7,
        policy_status=PatchPolicyStatus.ACCEPTED,
        trace_id=TRACE,
        now=NOW,
    )
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)
    candidates.record_verification(
        mission.id,
        patch_id=candidate.id,
        gates=gate_matrix(),  # all PASS, benign tool/detail — the conftest default
        started_at=NOW,
        finished_at=NOW,
        trace_id=TRACE,
        now=NOW,
    )
    transitions.transition(mission.id, MissionState.EXPORTING, trace_id=TRACE, now=NOW)

    export_mission(mission.id, reuse_existing=False, now=NOW)
    artifact = Artifact.objects.get(mission=mission, kind="evidence_bundle")
    files = _extract_bundle_files(artifact, settings.ARTIFACT_ROOT)

    for filename, content in files.items():
        assert "[redacted at export boundary" not in content, (
            f"{filename} redacted a benign, safe-shaped detail — false positive"
        )
        # `static_delta`/`renewed_fuzzing` default to NOT_RUN with this exact reason
        # on every GateMatrix; it must not be mistaken for something unsafe.
        assert "Not run: cut from the seven-day build" in content


# ---------------------------------------------------------------------------------
# 2. `orchestrator.redaction.sanitize_detail` — unit-level, direct
# ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "detail",
    [
        _POISONED_CONNECTION_STRING_DETAIL,
        _POISONED_ENV_LINE_DETAIL,
        _POISONED_BARE_ASSIGNMENT_DETAIL,
        "line one\nline two\nline three",  # multi-line raw output, no other marker
        "-----BEGIN PRIVATE KEY-----\nMIIC...",
        "x" * 400,  # exceeds the safe-length ceiling
        "detail with a shell metachar: $(whoami)",
    ],
)
def test_sanitize_detail_redacts_every_poisoned_shape(detail):
    assert sanitize_detail(detail) != detail


@pytest.mark.parametrize(
    "detail",
    [
        "",
        "cmake: exit=0",
        "ctest: Regression suite passed: 12 tests ran exit=0",
        "Not run: cut from the seven-day build (see docs/09-company/03-seven-day-plan.md).",
        "Crash reproducer replay completed without a sanitizer fault.",
    ],
)
def test_sanitize_detail_passes_every_benign_shape_through_unchanged(detail):
    assert sanitize_detail(detail) == detail


# ---------------------------------------------------------------------------------
# 3. SEC-49 — the cap is enforced before ingest, and the failure path cleans up
# ---------------------------------------------------------------------------------


def _verified_mission_ready_to_export(mission, finding):
    walk_to(mission, MissionState.PATCH)
    candidate = candidates.record_patch_candidate(
        mission.id,
        finding_id=finding.id,
        provenance=PatchProvenance.OPERATOR_SUPPLIED,
        diff=CANDIDATE_A.read_text(),
        files_changed=1,
        lines_changed=7,
        policy_status=PatchPolicyStatus.ACCEPTED,
        trace_id=TRACE,
        now=NOW,
    )
    transitions.transition(mission.id, MissionState.VERIFY, trace_id=TRACE, now=NOW)
    candidates.record_verification(
        mission.id,
        patch_id=candidate.id,
        gates=gate_matrix(),
        started_at=NOW,
        finished_at=NOW,
        trace_id=TRACE,
        now=NOW,
    )
    transitions.transition(mission.id, MissionState.EXPORTING, trace_id=TRACE, now=NOW)


def test_oversized_bundle_fails_cleanly_and_leaves_no_orphaned_tarball(
    mission, finding, tmp_path, settings
):
    settings.ARTIFACT_ROOT = tmp_path / "artifacts"
    export_root = tmp_path / "exports"
    settings.EXPORT_WORKSPACE_ROOT = export_root
    settings.EVIDENCE_BUNDLE_MAX_BYTES = 10  # far below any real bundle's size

    _verified_mission_ready_to_export(mission, finding)

    with pytest.raises(UnreadableArchiveError):
        export_mission(mission.id, reuse_existing=False, now=NOW)

    # Nothing durable was recorded for the failed attempt.
    assert Artifact.objects.filter(mission=mission, kind="evidence_bundle").count() == 0

    # No tarball (or its pre-gzip .tar sibling), and no leftover bundle_dir, anywhere
    # under the workspace root — the exact orphan SEC-49 named.
    if export_root.exists():
        leftover = [p for p in export_root.rglob("*") if p.is_file()]
        assert leftover == [], f"orphaned file(s) left in EXPORT_WORKSPACE_ROOT: {leftover}"
        leftover_dirs = [p for p in export_root.rglob("*") if p.is_dir()]
        assert leftover_dirs == [], (
            f"orphaned bundle_dir(s) left in EXPORT_WORKSPACE_ROOT: {leftover_dirs}"
        )


def test_retrying_after_an_oversized_export_does_not_accumulate_orphans(
    mission, finding, tmp_path, settings
):
    """The exact scenario the reviewer named: 'any OPERATOR_ROLES caller retrying
    POST /export against an oversized mission accumulates full-size orphaned
    tarballs indefinitely'. Three retries must leave the same clean state as one."""
    settings.ARTIFACT_ROOT = tmp_path / "artifacts"
    export_root = tmp_path / "exports"
    settings.EXPORT_WORKSPACE_ROOT = export_root
    settings.EVIDENCE_BUNDLE_MAX_BYTES = 10

    _verified_mission_ready_to_export(mission, finding)

    for _ in range(3):
        with pytest.raises(UnreadableArchiveError):
            export_mission(mission.id, reuse_existing=False, now=NOW)

    if export_root.exists():
        leftover = [p for p in export_root.rglob("*")]
        assert leftover == [], f"orphaned entries accumulated after retries: {leftover}"
