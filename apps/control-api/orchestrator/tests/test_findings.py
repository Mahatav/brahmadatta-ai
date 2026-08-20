"""`orchestrator.findings.record_finding` (#168, T2).

D-061 §5's gap: "No `Finding`-recording function exists anywhere." This is the
first real caller-facing test of the function that closes it, mirroring
`test_candidate_freeze.py`'s own shape for `record_patch_candidate`/
`record_verification` — the pattern this module was told to follow.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from contracts.enums import (
    AnalyzerTool,
    DiscoveryMethod,
    EventType,
    FindingCategory,
    LanguageAdapter,
    MissionState,
    Severity,
)
from missions.models import Authorization, Finding, Mission, MissionEvent, Reproducer, Snapshot
from orchestrator import findings
from orchestrator.tests.conftest import NOW, SNAPSHOT_SHA, TRACE, walk_to

pytestmark = pytest.mark.django_db(transaction=True)


def _second_mission() -> Mission:
    """An ordinary second mission — mirrors
    `test_cross_mission_evidence.py`'s own helper of the same shape."""
    other = Mission.objects.create(
        name="a different mission",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    Authorization.objects.create(
        mission=other,
        statement="I am authorized to test this repository on behalf of the owner.",
        granted_by="Mahatav Arora",
        granted_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(hours=8),
        repository_ref="file:///demo/repositories/pktcfg",
    )
    Snapshot.objects.create(
        mission=other, archive_sha256=SNAPSHOT_SHA, file_count=31, bytes_total=120_000
    )
    return other


def _record(mission, **overrides):
    kwargs = {
        "category": FindingCategory.HEAP_BUFFER_OVERFLOW,
        "severity": Severity.HIGH,
        "tool": AnalyzerTool.ADDRESS_SANITIZER,
        "discovery_method": DiscoveryMethod.FUZZING_CAMPAIGN,
        "file_path": "src/decode.c",
        "line": 43,
        "function": "emit_tab",
        "fingerprint": "fuzz:ADDRESS_SANITIZER:heap-buffer-overflow:emit_tab:deadbeef",
        "title": "heap-buffer-overflow in emit_tab (decode.c:43)",
        "detected_at": NOW,
        "trace_id": TRACE,
        "now": NOW,
    }
    kwargs.update(overrides)
    return findings.record_finding(mission.id, **kwargs)


def test_record_finding_persists_a_real_row(mission):
    walk_to(mission, MissionState.STRESS_TEST)

    row = _record(mission)

    assert isinstance(row, Finding)
    assert row.mission_id == mission.id
    assert row.category == FindingCategory.HEAP_BUFFER_OVERFLOW.value
    assert row.tool == AnalyzerTool.ADDRESS_SANITIZER.value
    assert row.discovery_method == DiscoveryMethod.FUZZING_CAMPAIGN.value
    assert row.fingerprint.startswith("fuzz:")
    assert row.reproducible is False
    assert Finding.objects.filter(mission=mission).count() == 1


def test_record_finding_emits_finding_recorded_inside_the_mission_lock(mission):
    walk_to(mission, MissionState.STRESS_TEST)

    row = _record(mission)

    event = MissionEvent.objects.get(mission=mission, type=str(EventType.FINDING_RECORDED))
    assert event.payload["finding"]["id"] == str(row.id)
    assert event.trace_id == TRACE


def test_record_finding_dedupes_by_mission_and_fingerprint(mission):
    """The FUZZ-shaped idempotency check (D-061 §3 rule 2): a retried campaign that
    rediscovers the same crash must not produce a second `Finding` row."""
    walk_to(mission, MissionState.STRESS_TEST)

    first = _record(mission)
    second = _record(mission)

    assert first.id == second.id
    assert Finding.objects.filter(mission=mission).count() == 1
    # Only one FINDING_RECORDED event, not two — the second call is a pure read.
    assert (
        MissionEvent.objects.filter(
            mission=mission, type=str(EventType.FINDING_RECORDED)
        ).count()
        == 1
    )


def test_record_finding_does_not_dedupe_across_missions(mission):
    other = _second_mission()
    walk_to(mission, MissionState.STRESS_TEST)
    walk_to(other, MissionState.STRESS_TEST)

    first = _record(mission)
    second = _record(other)

    assert first.id != second.id
    assert Finding.objects.filter(fingerprint=first.fingerprint).count() == 2


def test_record_finding_truncates_oversized_report_text(mission):
    walk_to(mission, MissionState.STRESS_TEST)

    row = _record(mission, sanitizer_report="x" * 25000, code_slice="y" * 25000)

    assert len(row.sanitizer_report) == 20000
    assert len(row.code_slice) == 20000


def test_a_replayed_reproducer_finding_requires_its_replay_source(mission):
    """`FindingSummary`'s own validator, exercised through the write path: a
    `REPLAYED_REPRODUCER` finding with no `replay_source` is refused before
    anything is written — same discipline `record_patch_candidate`/
    `record_verification` get from validating against a frozen schema first."""
    walk_to(mission, MissionState.STRESS_TEST)

    with pytest.raises(ValueError):
        _record(
            mission,
            discovery_method=DiscoveryMethod.REPLAYED_REPRODUCER,
            replay_source=None,
            fingerprint="fuzz:replayed:no-source",
        )

    assert Finding.objects.filter(mission=mission).count() == 0


# ---------------------------------------------------------------------------------
# D-106: `record_reproducer` — the write side of the reproducer-persistence gap
# D-098/D-105 both hit live: `VERIFY`'s `REPRODUCER_ELIMINATED` gate always came back
# `NOT_RUN` because nothing ever wrote a `Reproducer` row for a `FUZZ`-discovered
# `Finding`.
# ---------------------------------------------------------------------------------

_SHA_A = "a" * 64
_SHA_B = "b" * 64


def _record_reproducer(finding, **overrides):
    kwargs = {
        "sha256": _SHA_A,
        "size_bytes": 21,
        "uri": f"artifact://{finding.mission_id}/reproducer/{_SHA_A}",
        "test_command": "./pktcfg_replay crash-abc123 x1",
        "trace_id": TRACE,
        "now": NOW,
    }
    kwargs.update(overrides)
    return findings.record_reproducer(finding.id, **kwargs)


def test_record_reproducer_persists_a_real_row(mission):
    walk_to(mission, MissionState.STRESS_TEST)
    finding = _record(mission)

    row = _record_reproducer(finding)

    assert isinstance(row, Reproducer)
    assert row.finding_id == finding.id
    assert row.minimized is False
    assert row.replay_attempts == 0
    assert row.replay_successes == 0
    assert row.test_command == "./pktcfg_replay crash-abc123 x1"
    assert row.artifact["sha256"] == _SHA_A
    assert row.artifact["kind"] == "reproducer_input"
    assert row.artifact["size_bytes"] == 21
    assert Reproducer.objects.filter(finding=finding).count() == 1


def test_record_reproducer_emits_reproducer_recorded_inside_the_mission_lock(mission):
    walk_to(mission, MissionState.STRESS_TEST)
    finding = _record(mission)

    row = _record_reproducer(finding)

    event = MissionEvent.objects.get(mission=mission, type=str(EventType.REPRODUCER_RECORDED))
    assert event.payload["reproducer"]["id"] == str(row.id)
    assert event.trace_id == TRACE


def test_record_reproducer_dedupes_by_finding_and_sha256(mission):
    """The FUZZ-shaped idempotency check (D-061 §3 rule 2, applied to D-106's own
    write path): a retried campaign that re-ingests the same crash bytes must not
    produce a second `Reproducer` row."""
    walk_to(mission, MissionState.STRESS_TEST)
    finding = _record(mission)

    first = _record_reproducer(finding)
    second = _record_reproducer(finding)

    assert first.id == second.id
    assert Reproducer.objects.filter(finding=finding).count() == 1
    assert (
        MissionEvent.objects.filter(
            mission=mission, type=str(EventType.REPRODUCER_RECORDED)
        ).count()
        == 1
    )


def test_record_reproducer_allows_a_second_distinct_artifact_for_the_same_finding(mission):
    walk_to(mission, MissionState.STRESS_TEST)
    finding = _record(mission)

    first = _record_reproducer(finding, sha256=_SHA_A)
    second = _record_reproducer(finding, sha256=_SHA_B)

    assert first.id != second.id
    assert Reproducer.objects.filter(finding=finding).count() == 2


def test_record_reproducer_is_readable_through_verify_dispatchs_own_resolver(mission, settings, tmp_path):
    """The actual acceptance criterion: not just that a row exists, but that
    `orchestrator.verify_dispatch._resolve_reproducer_path` — the function `VERIFY`'s
    `REPRODUCER_ELIMINATED` gate actually calls — resolves it to a real, readable
    file. Ingests through the same `authorization.store.ingest_from_path` primitive
    `workers.fuzzing.dispatch` uses in production, rather than hand-writing the
    `artifact` JSON, so this proves the two ends of D-106's fix actually agree on the
    content-addressed layout."""
    from django.test import override_settings

    from authorization.store import ingest_from_path
    from orchestrator.verify_dispatch import _resolve_reproducer_path

    walk_to(mission, MissionState.STRESS_TEST)
    finding = _record(mission)

    artifact_root = tmp_path / "artifacts"
    source = tmp_path / "crash-abc123"
    source.write_bytes(b"a real crashing input")

    with override_settings(ARTIFACT_ROOT=artifact_root):
        ingest = ingest_from_path(artifact_root, source, max_bytes=10_000_000)
        _record_reproducer(
            finding,
            sha256=ingest.sha256,
            size_bytes=ingest.bytes_written,
            uri=f"artifact://{mission.id}/reproducer/{ingest.sha256}",
        )

        class _FakePatch:
            def __init__(self, finding):
                self.finding = finding

        class _FakeCtx:
            workspace_root = tmp_path / "workspace"

        resolved = _resolve_reproducer_path(_FakeCtx(), _FakePatch(finding))

        assert resolved.is_file()
        assert resolved.read_bytes() == b"a real crashing input"
