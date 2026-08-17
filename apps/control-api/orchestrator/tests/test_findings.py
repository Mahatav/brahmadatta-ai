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
from missions.models import Authorization, Finding, Mission, MissionEvent, Snapshot
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
