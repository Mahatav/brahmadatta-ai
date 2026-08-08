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
from tools.export_openapi import (
    CANONICAL_REASON_PHRASES,
    OUTPUT_PATH,
    _STDLIB_REASON_PHRASES,
    _stringify_keys,
    render,
)

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


def test_substitution_provenance_is_published_and_required(schema: dict):
    """The approved fallbacks (#81, #82, #83) must be expressible — and the primary
    path must not be claimable by a substituted one — in the document the frontend and
    the evidence report are generated from."""
    components = schema["components"]["schemas"]

    for name in ("DiscoveryMethod", "FuzzingMode", "IsolationMode", "EvidenceSource",
                 "SubstitutionKind", "Substitution"):
        assert name in components, f"{name} missing from the published contract"

    # Required, not optional: a discovery method cannot simply be left out.
    assert "discovery_method" in components["FindingSummary"]["required"]
    assert "mode" in components["FuzzingReport"]["required"]
    assert "isolation_mode" in components["SandboxStatus"]["required"]

    # The bundle discloses substitutions rather than leaving them to be inferred.
    assert "substitutions" in components["EvidenceBundle"]["properties"]


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


# --- #103: the dump must not depend on which interpreter rendered it --------------


def test_no_response_description_is_an_interpreter_supplied_reason_phrase(schema: dict):
    """The regression test for #103.

    django-ninja labels responses from `http.client.responses`, which is the standard
    library's `HTTPStatus` table — and that table changes between Python releases (3.13
    renamed four phrases, one of which appears 23 times here). A dump carrying a phrase
    straight from the running interpreter is not deterministic, and a drift check that
    fires on non-drift is one people learn to mute.

    Read from the *rendered* document rather than from the raw schema, because
    rendering is where the pinning happens.
    """
    rendered = json.loads(render(schema))
    offenders = []
    for path, operations in rendered["paths"].items():
        for method, operation in operations.items():
            for status, response in operation["responses"].items():
                description = response.get("description")
                stdlib = _STDLIB_REASON_PHRASES.get(int(status))
                pinned = CANONICAL_REASON_PHRASES.get(int(status))
                if description == stdlib and description != pinned:
                    offenders.append(f"{method.upper()} {path} -> {status}")
    assert not offenders, (
        f"these responses carry this interpreter's reason phrase rather than the "
        f"pinned one: {offenders}"
    )


def test_every_status_in_the_document_has_a_pinned_reason_phrase(schema: dict):
    """A new endpoint with an unpinned status must fail the export, not silently
    reopen #103 on whichever interpreter runs next."""
    rendered = json.loads(render(schema))
    statuses = {
        int(status)
        for operations in rendered["paths"].values()
        for operation in operations.values()
        for status in operation["responses"]
    }
    unpinned = {
        status
        for status in statuses
        if status in _STDLIB_REASON_PHRASES
        and status not in CANONICAL_REASON_PHRASES
    }
    assert not unpinned, f"add to CANONICAL_REASON_PHRASES: {sorted(unpinned)}"


def test_the_pinned_phrases_survive_a_renamed_stdlib_phrase(schema: dict, monkeypatch):
    """Simulate the 3.13 rename directly: change the interpreter's table under the
    exporter and assert the rendered document does not move.

    This is the property a version pin in `requirements.txt` would not have — a pin
    holds only until someone runs the exporter on a newer interpreter, which is exactly
    how #103 was found.
    """
    before = render(schema)

    # `_STDLIB_REASON_PHRASES` *is* `http.client.responses` — the same dict object
    # django-ninja reads when it labels a response. Mutating it is therefore a faithful
    # stand-in for running on an interpreter that renamed the phrase, rather than a
    # stand-in for our own lookup only.
    monkeypatch.setitem(_STDLIB_REASON_PHRASES, 422, "Some Future Name For 422")
    monkeypatch.setitem(_STDLIB_REASON_PHRASES, 409, "Some Future Name For 409")

    regenerated = _stringify_keys(api.get_openapi_schema())
    assert (
        regenerated["paths"]["/api/v1/system/health"]["get"]["responses"]["422"][
            "description"
        ]
        == "Some Future Name For 422"
    ), "the simulation did not take: ninja is not reading the patched table"

    assert render(regenerated) == before


def test_an_unpinned_status_raises_rather_than_drifting():
    from tools.export_openapi import UnpinnedReasonPhrase, _normalize_reason_phrases

    document = {
        "paths": {
            "/api/v1/whatever": {
                "get": {"responses": {"418": {"description": "I'm a Teapot"}}}
            }
        }
    }
    with pytest.raises(UnpinnedReasonPhrase):
        _normalize_reason_phrases(document)


def test_a_hand_written_description_is_left_alone(schema: dict):
    """Only phrases the interpreter supplied are replaced; the SSE stream's own
    description is prose we wrote and must survive untouched."""
    rendered = json.loads(render(schema))
    sse = rendered["paths"]["/api/v1/missions/{mission_id}/events"]["get"]
    assert sse["responses"]["200"]["description"].startswith("Ordered mission event")
