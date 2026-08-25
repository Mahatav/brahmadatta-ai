"""SEC-42 (#176) / D-083 §4 / D-086: `Finding(mission, fingerprint)` no longer relies
on `orchestrator.findings.record_finding`'s own mission-lock discipline alone.

`record_finding` already makes a duplicate unreachable *through that function alone*
(D-083 §4: the existence check runs inside the same `select_for_update()` mission
lock as the `create()` call, so two calls that both go through `record_finding`
serialize and the second one's existence check sees the first one's committed row
before ever attempting a write — proved sequentially, not concurrently, by
`test_findings.py::test_record_finding_dedupes_by_mission_and_fingerprint`). That is
a property of *this one call path's* discipline, not of the schema — anything that
writes a `Finding` row without going through `record_finding` (a bug in a future
caller, direct model usage, an admin action, a management command) gets no
protection from it at all. This module proves the schema itself, independent of any
caller's discipline, is what actually stops the duplicate — the same "declared in
Meta is not the same as verified" standard #176 raised for `Job`.

Mirrors `test_queue_enqueue_race.py`'s pattern: real threads, real Postgres
connections, a `threading.Barrier` forcing two writers to fire at the same instant,
`_requires_real_row_locking` because SQLite does not support genuine concurrent
writers the same way (single-writer, `IntegrityError`-shaped `OperationalError`s
rather than blocking).
"""

from __future__ import annotations

import threading
from unittest import mock

import pytest
from django.db import IntegrityError, connection, connections

from contracts.enums import (
    AnalyzerTool,
    DiscoveryMethod,
    FindingCategory,
    MissionState,
    Severity,
)
from missions.models import Finding
from orchestrator.tests.conftest import NOW, walk_to

pytestmark = pytest.mark.django_db(transaction=True)

_requires_real_row_locking = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Real concurrent writer connections are required to prove this race; "
    "SQLite does not support genuine concurrent writers the same way. Run with "
    "DATABASE_URL pointed at Postgres, as CI does.",
)


def _finding_kwargs(mission, fingerprint: str) -> dict:
    return {
        "mission": mission,
        "category": FindingCategory.HEAP_BUFFER_OVERFLOW.value,
        "severity": Severity.HIGH.value,
        "tool": AnalyzerTool.ADDRESS_SANITIZER.value,
        "discovery_method": DiscoveryMethod.FUZZING_CAMPAIGN.value,
        "file_path": "src/decode.c",
        "fingerprint": fingerprint,
        "title": "race",
        "detected_at": NOW,
    }


@_requires_real_row_locking
def test_finding_mission_fingerprint_unique_constraint_rejects_a_concurrent_duplicate_write(
    mission,
):
    """Direct proof `finding_mission_fingerprint_unique` — not `record_finding`'s own
    mission-lock discipline — is what refuses a second `(mission, fingerprint)` row.
    Bypasses `record_finding` entirely and writes `Finding.objects.create()` directly
    from two real threads forced to overlap with a `threading.Barrier`."""
    walk_to(mission, MissionState.STRESS_TEST)
    fingerprint = "race-fingerprint"
    assert not Finding.objects.filter(mission=mission, fingerprint=fingerprint).exists()

    n = 2
    barrier = threading.Barrier(n)
    created: list[Finding | None] = [None, None]
    errors: list[Exception | None] = [None, None]

    def _create(i: int) -> None:
        try:
            barrier.wait(timeout=5)
            created[i] = Finding.objects.create(**_finding_kwargs(mission, fingerprint))
        except Exception as exc:  # noqa: BLE001 - captured for assertion, not hidden
            errors[i] = exc
        finally:
            connections.close_all()

    threads = [threading.Thread(target=_create, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
        assert not t.is_alive()

    successes = [c for c in created if c is not None]
    failures = [e for e in errors if e is not None]
    assert len(successes) == 1, f"expected exactly one writer to win the race, got {len(successes)}"
    assert len(failures) == 1, f"expected exactly one writer to be refused, got {len(failures)}"
    assert isinstance(failures[0], IntegrityError), failures[0]

    assert Finding.objects.filter(mission=mission, fingerprint=fingerprint).count() == 1


def test_record_finding_survives_a_genuine_create_race(mission):
    """`orchestrator.findings.record_finding`'s own `IntegrityError` fallback,
    exercised for real — not merely declared. Mirrors
    `test_baseline_executor.py::test_persist_report_survives_a_genuine_race`'s shape
    exactly (sequential calls standing in for two workers that both got past a
    pre-flight check that is not supposed to let that happen): the module's own
    existence check is patched out for one call so it reaches `Finding.objects.
    create` a second time for the same `(mission, fingerprint)` pair, same as two
    real concurrent callers would if some future caller ever bypassed the mission
    lock `record_finding` itself relies on. The database constraint added by D-086 is
    what turns that into a caught, handled `IntegrityError` instead of a second row.
    """
    from orchestrator import findings

    walk_to(mission, MissionState.STRESS_TEST)
    kwargs = dict(
        category=FindingCategory.HEAP_BUFFER_OVERFLOW,
        severity=Severity.HIGH,
        tool=AnalyzerTool.ADDRESS_SANITIZER,
        discovery_method=DiscoveryMethod.FUZZING_CAMPAIGN,
        file_path="src/decode.c",
        fingerprint="race-fingerprint-sequential",
        title="race",
        detected_at=NOW,
        trace_id="test-trace-0000000000000000",
        now=NOW,
    )

    first = findings.record_finding(mission.id, **kwargs)

    # Force the second call past its own dedupe check, standing in for a second
    # caller that raced the first one and, like the first, found nothing yet. Scoped
    # to this one call only — `record_finding`'s own IntegrityError-fallback query
    # (`Finding.objects.get`, a different Manager method) is untouched, and the
    # patch is reverted before this test's own final assertions run.
    original_filter = Finding.objects.filter

    def _blind_filter(*args, **filter_kwargs):
        if filter_kwargs.get("fingerprint") == "race-fingerprint-sequential":
            return Finding.objects.none()
        return original_filter(*args, **filter_kwargs)

    with mock.patch.object(Finding.objects, "filter", side_effect=_blind_filter):
        second = findings.record_finding(mission.id, **kwargs)

    assert first.id == second.id
    assert (
        Finding.objects.filter(mission=mission, fingerprint="race-fingerprint-sequential").count()
        == 1
    )
    # #30: the losing writer still counts as a real rediscovery of the same crash --
    # the IntegrityError fallback bumps `crash_count` on the winner's row rather than
    # silently dropping the fact that a second caller found it too.
    second.refresh_from_db()
    assert second.crash_count == 2
