"""The event envelope: required fields, discrimination, and strictness."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from contracts.enums import EventType, MissionPosture, MissionStage, MissionState
from contracts.schemas.envelope import (
    EventPayload,
    LogPayload,
    MissionEvent,
    StateChangedPayload,
)

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)


def event(**overrides) -> MissionEvent:
    data = {
        "id": uuid4(),
        "mission_id": uuid4(),
        "sequence": 1,
        "timestamp": NOW,
        "type": EventType.STATE_CHANGED,
        "state": MissionState.BASELINE,
        "stage": MissionStage.BASELINE,
        "message": "Baseline build started",
        "payload": StateChangedPayload(
            to_state=MissionState.BASELINE, posture=MissionPosture.INVESTIGATING
        ),
        "trace_id": "0123456789abcdef",
    }
    data.update(overrides)
    return MissionEvent(**data)


def test_the_envelope_carries_the_six_required_fields():
    """id, mission id, timestamp, type, payload, trace id — issue #6."""
    for name in ("id", "mission_id", "timestamp", "type", "payload", "trace_id"):
        assert name in MissionEvent.model_fields
        assert MissionEvent.model_fields[name].is_required()


def test_a_valid_event_round_trips_through_json():
    original = event()
    restored = MissionEvent.model_validate_json(original.model_dump_json())
    assert restored == original


def test_payload_is_discriminated_on_kind():
    parsed = event(
        type=EventType.LOG, payload={"kind": "log", "text": "configure completed"}
    )
    assert isinstance(parsed.payload, LogPayload)


def test_an_unknown_payload_kind_is_rejected():
    with pytest.raises(ValidationError):
        event(payload={"kind": "vibes", "text": "trust me"})


def test_unknown_top_level_fields_are_rejected():
    with pytest.raises(ValidationError):
        event(confidence=0.99)


def test_sequence_starts_at_one():
    with pytest.raises(ValidationError):
        event(sequence=0)


def test_every_payload_variant_declares_a_unique_kind():
    variants = EventPayload.__origin__.__args__  # type: ignore[attr-defined]
    kinds = [
        variant.model_fields["kind"].default for variant in variants
    ]
    assert len(kinds) == len(set(kinds)), f"duplicate payload kinds: {kinds}"
    assert all(isinstance(kind, str) and kind for kind in kinds)


def test_the_d3_gate_signal_is_an_unambiguous_literal():
    """The D3 kill criterion is written as the literal string `BASELINE_PASSED`.

    It is an outcome, not a mission state — the mission is in `BASELINE` while the
    stage runs. The observable signal is the event type plus the derived `passed`
    field on the report, so a gate check on 2026-08-09 has an exact string to look for.
    """
    from uuid import uuid4

    from contracts.schemas.evidence import BaselineReport

    assert "BASELINE_PASSED" in EventType.__members__
    assert "BASELINE_FAILED" in EventType.__members__
    assert "BASELINE_PASSED" not in MissionState.__members__

    green = BaselineReport(
        mission_id=uuid4(),
        configure_ok=True,
        build_ok=True,
        tests_total=14,
        tests_passed=14,
        tests_failed=0,
        duration_seconds=31.4,
        adapter="C_CMAKE_CTEST",
        recorded_at=NOW,
    )
    assert green.passed is True
    assert "passed" in green.model_dump()

    red = green.model_copy(update={"tests_failed": 2, "tests_passed": 12})
    assert red.passed is False

    unbuilt = green.model_copy(update={"build_ok": False})
    assert unbuilt.passed is False


def test_metrics_are_numeric_only():
    """No decorative strings in the telemetry map."""
    with pytest.raises(ValidationError):
        event(metrics={"coverage_percent": "78.6%"})
    assert event(metrics={"coverage_percent": 78.6}).metrics["coverage_percent"] == 78.6
