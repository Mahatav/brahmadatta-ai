"""Prerequisite fix for #154: transition() must translate Mission.DoesNotExist."""
from __future__ import annotations

import uuid

import pytest

from authorization.errors import MissionNotFoundError
from contracts.enums import MissionState
from orchestrator import transitions
from orchestrator.tests.conftest import NOW, TRACE

pytestmark = pytest.mark.django_db(transaction=True)


def test_transition_against_a_missing_mission_is_a_clean_404_not_a_500():
    """preflight/start/pause/cancel are the first callers to hit `transition()`
    directly with a possibly-invalid mission_id (every existing caller pre-locks
    through its own guard first). Before the fix, `Mission.DoesNotExist` propagated
    unhandled out of `select_for_update().get(...)`."""
    missing_id = uuid.uuid4()
    with pytest.raises(MissionNotFoundError):
        transitions.transition(
            missing_id, MissionState.AUTHORIZED, trace_id=TRACE, now=NOW
        )
