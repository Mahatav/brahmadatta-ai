"""The enums have to be exhaustive, and the tables over them have to stay exhaustive.

These are the tests that fail when someone adds a mission state and forgets the Core
would then render an unlabelled ring.
"""

from __future__ import annotations

import pytest

from contracts.enums import (
    POSTURE_BY_STATE,
    TERMINAL_STATES,
    MissionPosture,
    MissionStage,
    MissionState,
    posture_for,
)
from contracts.state_machine import STAGE_FOR_STATE, TRANSITIONS


def test_every_state_has_a_posture():
    missing = set(MissionState) - set(POSTURE_BY_STATE)
    assert not missing, f"states with no displayed posture: {sorted(missing)}"


def test_every_state_maps_to_a_stage_slot():
    missing = set(MissionState) - set(STAGE_FOR_STATE)
    assert not missing, f"states missing from STAGE_FOR_STATE: {sorted(missing)}"


def test_every_state_has_a_transition_row():
    missing = set(MissionState) - set(TRANSITIONS)
    assert not missing, f"states with no transition row: {sorted(missing)}"


def test_transition_targets_are_real_states():
    for source, targets in TRANSITIONS.items():
        for target in targets:
            assert isinstance(target, MissionState), (source, target)


def test_terminal_states_are_dead_ends():
    for state in TERMINAL_STATES:
        assert TRANSITIONS[state] == frozenset(), f"{state} is not terminal"


def test_only_terminal_states_are_dead_ends():
    for state, targets in TRANSITIONS.items():
        if not targets:
            assert state in TERMINAL_STATES, f"{state} is a dead end but not terminal"


def test_the_nine_workflow_stages_are_present():
    """authorize -> ingest -> baseline -> analyze -> stress-test -> correlate ->
    patch -> verify -> export evidence."""
    assert [stage.value for stage in MissionStage] == [
        "AUTHORIZE",
        "INGEST",
        "BASELINE",
        "ANALYZE",
        "STRESS_TEST",
        "CORRELATE",
        "PATCH",
        "VERIFY",
        "EXPORT_EVIDENCE",
    ]


def test_architecture_document_states_all_exist():
    """Every state named in docs/03-technical/16-system-architecture-document.md."""
    documented = [
        "CREATED",
        "VALIDATING",
        "SNAPSHOTTED",
        "BASELINE",
        "TRIAGE",
        "STRESS_TEST",
        "CORRELATE",
        "PATCH",
        "VERIFY",
        "VERIFIED",
        "REJECTED",
        "HUMAN_REVIEW",
        "FAILED",
        "CANCELLED",
    ]
    for name in documented:
        assert name in MissionState.__members__, f"{name} dropped from the contract"


@pytest.mark.parametrize(
    ("state", "posture"),
    [
        (MissionState.CREATED, MissionPosture.PROTECTED),
        (MissionState.TRIAGE, MissionPosture.INVESTIGATING),
        (MissionState.CORRELATE, MissionPosture.VULNERABILITY_CONFIRMED),
        (MissionState.PATCH, MissionPosture.PATCHING),
        (MissionState.VERIFIED, MissionPosture.VERIFIED),
        (MissionState.REJECTED, MissionPosture.REJECTED),
        (MissionState.HUMAN_REVIEW, MissionPosture.HUMAN_REVIEW),
        (MissionState.FAILED, MissionPosture.FAILED),
    ],
)
def test_posture_derivation(state, posture):
    assert posture_for(state) is posture
