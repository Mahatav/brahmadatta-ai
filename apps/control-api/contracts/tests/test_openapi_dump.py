"""The committed OpenAPI dump must match what the code generates.

This is what makes the freeze enforceable. If someone changes a schema and does not
re-run `tools/export_openapi.py`, this fails — before the Astro client is typed
against a document that no longer describes the server.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.api import api
from tools.export_openapi import OUTPUT_PATH, _stringify_keys, render

#: P0 surface. Cut endpoints are asserted absent further down, so nobody quietly
#: re-adds a CUT feature through the API layer.
EXPECTED_PATHS = {
    "/api/v1/missions",
    "/api/v1/missions/{mission_id}",
    "/api/v1/missions/{mission_id}/authorize",
    "/api/v1/missions/{mission_id}/snapshot",
    "/api/v1/missions/{mission_id}/preflight",
    "/api/v1/missions/{mission_id}/start",
    "/api/v1/missions/{mission_id}/pause",
    "/api/v1/missions/{mission_id}/cancel",
    "/api/v1/missions/{mission_id}/events",
    "/api/v1/missions/{mission_id}/events/replay",
    "/api/v1/missions/{mission_id}/findings",
    "/api/v1/missions/{mission_id}/findings/{finding_id}",
    "/api/v1/missions/{mission_id}/baseline",
    "/api/v1/missions/{mission_id}/fuzzing",
    "/api/v1/missions/{mission_id}/patches",
    "/api/v1/missions/{mission_id}/patches/{patch_id}/verification",
    "/api/v1/missions/{mission_id}/evidence",
    "/api/v1/missions/{mission_id}/export",
    "/api/v1/system/health",
    "/api/v1/system/workers",
    "/api/v1/system/sandboxes",
    "/api/v1/system/sandboxes/{sandbox_id}/teardown",
}

CUT_PATHS = {
    "/api/v1/missions/{mission_id}/git-bisect",
    "/api/v1/system/gpu-leases",
    "/api/v1/system/gpu-leases/{id}/teardown",
}


@pytest.fixture(scope="module")
def schema() -> dict:
    """The published document, with status keys normalized exactly as the dump does."""
    return _stringify_keys(api.get_openapi_schema())


def test_committed_dump_is_current(schema: dict):
    assert OUTPUT_PATH.exists(), (
        f"{OUTPUT_PATH} is missing. Run tools/export_openapi.py."
    )
    committed = Path(OUTPUT_PATH).read_text(encoding="utf-8")
    assert committed == render(schema), (
        "packages/schemas/openapi.json is stale. Re-run "
        "`.venv/bin/python tools/export_openapi.py` and commit the result."
    )


def test_every_p0_endpoint_is_present(schema: dict):
    assert set(schema["paths"]) == EXPECTED_PATHS


def test_cut_endpoints_are_absent(schema: dict):
    assert not (set(schema["paths"]) & CUT_PATHS)


def test_health_is_the_only_unauthenticated_operation(schema: dict):
    unauthenticated = []
    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            security = operation.get("security")
            if not security:
                unauthenticated.append(f"{method.upper()} {path}")
    assert unauthenticated == ["GET /api/v1/system/health"]


def test_every_operation_documents_the_error_envelope(schema: dict):
    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            responses = operation["responses"]
            for status in ("401", "403", "422"):
                assert status in responses, f"{method.upper()} {path} lacks {status}"
                content = responses[status]["content"]["application/json"]
                assert content["schema"]["$ref"].endswith("/ErrorEnvelope")


def test_sse_endpoint_declares_an_event_stream(schema: dict):
    operation = schema["paths"]["/api/v1/missions/{mission_id}/events"]["get"]
    content = operation["responses"]["200"]["content"]
    assert "text/event-stream" in content
    assert content["text/event-stream"]["schema"]["$ref"].endswith("/MissionEvent")


def test_operation_ids_are_stable_and_unique(schema: dict):
    ids = [
        operation["operationId"]
        for operations in schema["paths"].values()
        for operation in operations.values()
    ]
    assert len(ids) == len(set(ids))
    # The TypeScript client names its functions from these; renaming one is a
    # breaking change to the frontend.
    assert "getSystemHealth" in ids
    assert "authorizeMission" in ids


def test_the_dump_is_valid_json_and_pins_the_version(schema: dict):
    parsed = json.loads(Path(OUTPUT_PATH).read_text(encoding="utf-8"))
    assert parsed["openapi"].startswith("3.")
    assert parsed["info"]["version"] == "0.1.0"


def test_the_event_envelope_reaches_the_generated_client(schema: dict):
    """django-ninja only emits schemas reachable from a route, and OpenAPI cannot
    describe SSE frames. Without the replay endpoint returning `Page[MissionEvent]`,
    the widest and most drift-prone part of the contract would be absent from the
    generated TypeScript entirely — and "a contract change breaks the frontend build"
    would be false. This asserts the reachability, not merely the endpoint.
    """
    components = schema["components"]["schemas"]
    assert "MissionEvent" in components
    assert "Page_MissionEvent_" in components

    replay = schema["paths"]["/api/v1/missions/{mission_id}/events/replay"]["get"]
    ref = replay["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert ref.endswith("/Page_MissionEvent_")

    # Every payload variant has to be emitted too, or the discriminated union the
    # frontend switches on is incomplete.
    from contracts.schemas.envelope import EventPayload

    variants = [
        variant.__name__
        for variant in EventPayload.__origin__.__args__  # type: ignore[attr-defined]
    ]
    missing = [name for name in variants if name not in components]
    assert not missing, f"payload variants missing from the document: {missing}"


def test_replay_provenance_is_expressible_in_the_published_contract(schema: dict):
    provenance = schema["components"]["schemas"]["ModelProvenance"]["properties"]
    for field in ("replayed_from_transcript", "captured_at", "transcript_sha256"):
        assert field in provenance


def test_cancelled_has_its_own_posture_in_the_published_contract(schema: dict):
    assert "CANCELLED" in schema["components"]["schemas"]["MissionPosture"]["enum"]


def test_confidence_appears_only_on_model_provenance(schema: dict):
    """A structural read of the published contract, not of our source."""
    offenders = {
        name: sorted(component.get("properties", {}))
        for name, component in schema["components"]["schemas"].items()
        if any(
            "confidence" in prop.lower()
            for prop in component.get("properties", {})
        )
        and name != "ModelProvenance"
    }
    assert not offenders, f"confidence leaked into: {offenders}"
