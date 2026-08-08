"""D-047 — `paused_from`, persisted, and both directions of the skip it closes.

BUG-005 as QA reproduced it was the forward skip: `BASELINE → PAUSED → EXPORTING →
VERIFIED`, a terminal verdict on a mission that never entered `PATCH` or `VERIFY`. The
backward one is the half nobody had named — resuming into `BASELINE` from a pause taken
in `VERIFY` re-runs the baseline and writes a **second** `BaselineReport` for the same
snapshot. That report is the denominator for "regression preserved" (P0-5), so two of
them make the central verification claim ambiguous to anyone auditing the bundle.
"""

from __future__ import annotations

import pytest

from contracts.enums import MissionState
from contracts.errors import InvalidStateTransitionError
from missions.models import BaselineReport
from orchestrator import transitions
from orchestrator.tests.conftest import NOW, TRACE, walk_to

pytestmark = pytest.mark.django_db(transaction=True)


def test_pausing_records_where_the_mission_paused_from(mission):
    walk_to(mission, MissionState.BASELINE)
    transitions.transition(mission.id, MissionState.PAUSED, trace_id=TRACE, now=NOW)

    mission.refresh_from_db()
    assert mission.state_enum is MissionState.PAUSED
    assert mission.paused_from_enum is MissionState.BASELINE


def test_the_seven_step_walk_to_a_verdict_is_closed(mission):
    """QA's case F, step for step.

    `BASELINE -> PAUSED` legal, `PAUSED -> EXPORTING` refused. Before D-047 both were
    allowed and the mission reached `VERIFIED` having done none of the work.
    """
    walk_to(mission, MissionState.BASELINE)
    transitions.transition(mission.id, MissionState.PAUSED, trace_id=TRACE, now=NOW)

    with pytest.raises(InvalidStateTransitionError) as excinfo:
        transitions.transition(
            mission.id, MissionState.EXPORTING, trace_id=TRACE, now=NOW
        )
    assert "resumes only into the state it paused from" in str(excinfo.value)

    mission.refresh_from_db()
    assert mission.state_enum is MissionState.PAUSED


def test_a_pause_in_verify_cannot_resume_into_baseline(mission):
    """The backward half, and the second `BaselineReport` it would have produced."""
    walk_to(mission, MissionState.VERIFY)
    transitions.transition(mission.id, MissionState.PAUSED, trace_id=TRACE, now=NOW)

    with pytest.raises(InvalidStateTransitionError):
        transitions.transition(
            mission.id, MissionState.BASELINE, trace_id=TRACE, now=NOW
        )

    mission.refresh_from_db()
    assert mission.paused_from_enum is MissionState.VERIFY


def test_only_one_baseline_report_can_exist_for_a_mission(mission):
    """Belt and braces on the same property, at the storage layer.

    Even if a resume bug got past `assert_resume`, the database refuses the second
    baseline — so an evidence bundle cannot carry two denominators for one snapshot.
    """
    from django.db import IntegrityError

    BaselineReport.objects.create(
        mission=mission,
        configure_ok=True,
        build_ok=True,
        tests_total=14,
        tests_passed=14,
        tests_failed=0,
        duration_seconds=3.2,
        adapter="C_CMAKE_CTEST",
        recorded_at=NOW,
    )
    with pytest.raises(IntegrityError):
        BaselineReport.objects.create(
            mission=mission,
            configure_ok=True,
            build_ok=True,
            tests_total=14,
            tests_passed=14,
            tests_failed=0,
            duration_seconds=3.4,
            adapter="C_CMAKE_CTEST",
            recorded_at=NOW,
        )


def test_resuming_into_the_recorded_origin_works_and_clears_the_marker(mission):
    walk_to(mission, MissionState.CORRELATE)
    transitions.transition(mission.id, MissionState.PAUSED, trace_id=TRACE, now=NOW)
    transitions.transition(mission.id, MissionState.CORRELATE, trace_id=TRACE, now=NOW)

    mission.refresh_from_db()
    assert mission.state_enum is MissionState.CORRELATE
    assert mission.paused_from is None


def test_a_paused_mission_can_always_get_out(mission):
    """Getting out safely never depends on the bookkeeping that made it necessary."""
    walk_to(mission, MissionState.STRESS_TEST)
    transitions.transition(mission.id, MissionState.PAUSED, trace_id=TRACE, now=NOW)
    transitions.transition(mission.id, MissionState.CANCELLING, trace_id=TRACE, now=NOW)

    mission.refresh_from_db()
    assert mission.state_enum is MissionState.CANCELLING
