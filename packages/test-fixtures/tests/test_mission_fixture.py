"""The committed mission fixture conforms to the frozen contract.

This is the "fails loudly" half of #71. `packages/schemas/openapi.json` is the frozen
dump, and it is also what `apps/command-center/src/lib/api/schema.d.ts` is generated
from — so a fixture that validates here is a fixture the Command Center's TypeScript
types accept, and a contract change that breaks one breaks the other in the same run.

Validation is against the JSON Schema in the dump rather than against the pydantic
models on purpose. The dump is the artifact the frontend consumes; checking the models
would check something the frontend never sees. The models still get exercised — the
generator in `tools/build_mission_fixture.py` constructs every event through them, so
the cross-field validators JSON Schema cannot express (verdict derivation, provenance
pairing, count consistency) run at build time.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

jsonschema = pytest.importorskip(
    "jsonschema",
    reason="jsonschema is in requirements-dev.txt; install it to run the contract check",
)

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "packages" / "test-fixtures" / "missions" / "mission-pktcfg-001.events.jsonl"
OPENAPI = REPO_ROOT / "packages" / "schemas" / "openapi.json"

#: D-038. `STRESS_TEST` precedes `CORRELATE`, because correlation binds the crash the
#: stress test produced. Every panel built against this fixture inherits the ordering,
#: so it is asserted here rather than left to the generator alone.
RULED_STAGE_ORDER = [
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


@pytest.fixture(scope="module")
def events() -> list[dict[str, Any]]:
    assert FIXTURE.is_file(), f"fixture missing: {FIXTURE}"
    return [
        json.loads(line)
        for line in FIXTURE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.fixture(scope="module")
def validator() -> Any:
    assert OPENAPI.is_file(), f"frozen contract missing: {OPENAPI}"
    document = json.loads(OPENAPI.read_text(encoding="utf-8"))
    assert "MissionEvent" in document["components"]["schemas"], (
        "the frozen dump has no MissionEvent schema — the contract moved out from under "
        "this fixture"
    )
    # `$ref` alongside the document body: the ref resolves against the root, which is the
    # whole OpenAPI document, so every nested component ref resolves too.
    schema = {**document, "$ref": "#/components/schemas/MissionEvent"}
    return jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER
    )


# --- the contract gate ----------------------------------------------------------


def test_every_event_validates_against_the_frozen_envelope(
    events: list[dict[str, Any]], validator: Any
) -> None:
    failures: list[str] = []
    for event in events:
        errors = sorted(validator.iter_errors(event), key=lambda e: list(e.absolute_path))
        for error in errors:
            path = "/".join(str(part) for part in error.absolute_path) or "<root>"
            failures.append(f"  seq {event.get('sequence')} at {path}: {error.message}")

    assert not failures, (
        "The committed fixture no longer matches packages/schemas/openapi.json.\n\n"
        + "\n".join(failures[:40])
        + "\n\nEither the contract changed and the fixture must be regenerated "
        "(packages/test-fixtures/tools/build_mission_fixture.py), or the change to the "
        "contract was not intended."
    )


def test_fixture_is_not_empty(events: list[dict[str, Any]]) -> None:
    assert len(events) >= 40, (
        f"a full mission is more than {len(events)} events; something truncated the fixture"
    )


# --- invariants every panel will assume -----------------------------------------


def test_sequence_is_gap_free(events: list[dict[str, Any]]) -> None:
    """`sequence` is documented as a gap-free per-mission counter.

    The gap #71 asks for belongs in the *stream*, not in the stored log — a client
    detects a gap because the transport lost frames, never because the server skipped a
    number. `sse_replay.py --drop` injects it at stream time.
    """
    sequences = [event["sequence"] for event in events]
    assert sequences == list(range(1, len(events) + 1))


def test_one_mission_one_trace(events: list[dict[str, Any]]) -> None:
    assert len({event["mission_id"] for event in events}) == 1
    assert len({event["trace_id"] for event in events}) == 1


def test_timestamps_do_not_go_backwards(events: list[dict[str, Any]]) -> None:
    stamps = [_parse(event["timestamp"]) for event in events]
    assert stamps == sorted(stamps)


def test_timestamps_must_not_be_compared_as_strings(events: list[dict[str, Any]]) -> None:
    """A trap worth failing on deliberately rather than discovering in a panel.

    RFC 3339 omits the fractional part when it is zero, so the stream contains both
    `13:00:00Z` and `13:00:00.400000Z`. Lexicographically `.` sorts before `Z`, so a
    naive string sort puts the later event first. `sequence` is the ordering key — it is
    a gap-free integer and it is what the SSE `id:` field carries. Sort by that.
    """
    raw = [event["timestamp"] for event in events]
    parsed = [_parse(value) for value in raw]
    assert parsed == sorted(parsed), "the fixture itself must be chronological"
    assert raw != sorted(raw), (
        "This fixture no longer demonstrates the string-sort trap. That is fine, but a "
        "panel must still order by `sequence`, never by the timestamp string."
    )


def test_stage_order_follows_the_d038_ruling(events: list[dict[str, Any]]) -> None:
    seen: list[str] = []
    for event in events:
        stage = event.get("stage")
        if stage and stage not in seen:
            seen.append(stage)
    assert seen == RULED_STAGE_ORDER, (
        f"D-038 rules the phase order {RULED_STAGE_ORDER}; the fixture walks {seen}. "
        f"Every panel built against this fixture inherits the ordering."
    )


# --- the full mission the issue asks for ----------------------------------------


def test_mission_walks_authorize_to_verified(events: list[dict[str, Any]]) -> None:
    states = [event["state"] for event in events]
    assert states[0] == "CREATED"
    assert states[-1] == "VERIFIED"
    for expected in ("AUTHORIZED", "SNAPSHOTTED", "BASELINE", "TRIAGE", "STRESS_TEST",
                     "CORRELATE", "PATCH", "VERIFY", "EXPORTING"):
        assert expected in states, f"mission never passed through {expected}"


def test_baseline_reports_real_counts(events: list[dict[str, Any]]) -> None:
    baseline = _one_payload(events, "baseline")["report"]
    assert baseline["configure_ok"] is True
    assert baseline["build_ok"] is True
    assert baseline["tests_total"] == 8, "pktcfg has 8 ctest cases"
    assert baseline["tests_failed"] == 0
    assert baseline["passed"] is True, "the derived D3 gate signal must agree with the counts"
    assert any(event["type"] == "BASELINE_PASSED" for event in events), (
        "the D3 kill criterion is the literal string BASELINE_PASSED"
    )


def test_crash_is_found_minimized_and_reproducible(events: list[dict[str, Any]]) -> None:
    finding = _one_payload(events, "finding")["finding"]
    assert finding["category"] == "HEAP_BUFFER_OVERFLOW"
    assert finding["reproducible"] is True

    reproducer = _one_payload(events, "reproducer")["reproducer"]
    assert reproducer["minimized"] is True
    assert reproducer["replay_successes"] == reproducer["replay_attempts"] > 0
    assert reproducer["finding_id"] == finding["id"]


def test_one_candidate_verified_and_one_rejected(events: list[dict[str, Any]]) -> None:
    verdicts = [
        payload["verification"] for payload in _payloads(events, "verification")
    ]
    assert {record["verdict"] for record in verdicts} == {"VERIFIED", "REJECTED"}, (
        "the demo's differentiator is a Verified beside a Rejected"
    )

    summary = _one_payload(events, "mission_verdict")["summary"]
    assert summary["mission_verdict"] == "VERIFIED"
    assert summary["verified_count"] == 1
    assert summary["rejected_count"] == 1
    assert {c["verdict"] for c in summary["candidates"]} == {"VERIFIED", "REJECTED"}


def test_the_rejected_candidate_fails_on_a_gate_not_on_confidence(
    events: list[dict[str, Any]],
) -> None:
    """The whole point of the demo: the tempting patch has the *highest* model
    confidence in the mission and is rejected anyway, by a deterministic gate."""
    records = {
        payload["verification"]["verdict"]: payload["verification"]
        for payload in _payloads(events, "verification")
    }
    rejected = records["REJECTED"]
    assert rejected["gates"]["regression_preserved"]["status"] == "FAIL"
    assert rejected["gates"]["reproducer_eliminated"]["status"] == "PASS", (
        "the rejected candidate must genuinely eliminate the crash — that is what makes "
        "it tempting"
    )

    confidences = [
        payload["patch"]["model"]["confidence"]
        for payload in _payloads(events, "patch_candidate")
        if payload["patch"].get("model")
    ]
    rejected_patch = next(
        payload["patch"]
        for payload in _payloads(events, "patch_candidate")
        if payload["patch"]["id"] == rejected["patch_id"]
    )
    assert rejected_patch["model"]["confidence"] == max(confidences), (
        "the rejected candidate should carry the highest confidence in the mission; "
        "otherwise the fixture does not demonstrate that confidence is not evidence"
    )


# --- the ugly cases the issue asks for ------------------------------------------


def test_fixture_includes_a_failed_stage(events: list[dict[str, Any]]) -> None:
    failed = [event for event in events if event["status"] == "FAILED"]
    assert failed, "a fixture with no failed stage teaches panels only the happy path"
    stage_failures = [event for event in failed if event["type"] == "STAGE_COMPLETED"]
    assert stage_failures, "at least one stage must complete with status FAILED"


def test_fixture_includes_a_degraded_state(events: list[dict[str, Any]]) -> None:
    degraded = [
        event
        for event in events
        if event["status"] != "FAILED" and event["severity"] in {"MEDIUM", "HIGH"}
    ]
    assert degraded, "no degraded-but-continuing events"

    indeterminate = [
        event
        for event in events
        if event["payload"]["kind"] == "stage_progress"
        and event["payload"]["percent_complete"] is None
    ]
    assert indeterminate, (
        "a degraded stage reports percent_complete: null so the panel shows an "
        "indeterminate indicator instead of inventing a number"
    )

    replayed = [
        payload["patch"]
        for payload in _payloads(events, "patch_candidate")
        if (payload["patch"].get("model") or {}).get("replayed_from_transcript")
    ]
    assert replayed, (
        "the degraded model host must be visible in typed data, not only in a log line"
    )


def test_fixture_includes_a_policy_violation(events: list[dict[str, Any]]) -> None:
    violations = _payloads(events, "policy_violation")
    assert violations, "no POLICY_VIOLATION event; that payload variant is never exercised"


def test_fixture_exercises_every_payload_variant(
    events: list[dict[str, Any]], validator: Any
) -> None:
    """A panel switches exhaustively over `payload.kind`. A variant the fixture never
    emits is a branch nobody can develop against."""
    document = json.loads(OPENAPI.read_text(encoding="utf-8"))
    declared = {
        name.replace("Payload", "")
        for name in document["components"]["schemas"]
        if name.endswith("Payload")
    }
    present = {event["payload"]["kind"] for event in events}
    # `kind` is snake_case; the schema names are PascalCase. Compare on count and on the
    # variants the envelope union actually declares.
    union = document["components"]["schemas"]["MissionEvent"]["properties"]["payload"]
    variants = union.get("oneOf") or union.get("anyOf") or []
    expected = set()
    for variant in variants:
        ref = variant.get("$ref", "")
        name = ref.rsplit("/", 1)[-1]
        if name:
            expected.add(name)
    assert declared  # the dump really does declare payload schemas

    missing_count = len(expected) - len(present)
    assert missing_count <= 0, (
        f"the envelope declares {len(expected)} payload variants; the fixture emits "
        f"{len(present)} ({sorted(present)}). Panels cannot be built against a variant "
        f"the fixture never produces."
    )


# --- helpers ---------------------------------------------------------------------


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _payloads(events: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [event["payload"] for event in events if event["payload"]["kind"] == kind]


def _one_payload(events: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    found = _payloads(events, kind)
    assert found, f"fixture emits no {kind} payload"
    return found[0]
