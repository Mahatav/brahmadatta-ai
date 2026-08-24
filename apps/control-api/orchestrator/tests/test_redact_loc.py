"""`orchestrator.redaction.looks_secret_shaped`/`redact_loc` — #258.

Unit-level coverage for the helper `api/sse.py::safe_to_schema` now calls; the
end-to-end regression against a real `MissionEvent` row lives in
`api/tests/test_event_stream.py::
test_safe_to_schema_redacts_a_secret_shaped_forbidden_field_key_from_loc`.
"""

from __future__ import annotations

from orchestrator.redaction import REDACTED_LOC_SEGMENT, looks_secret_shaped, redact_loc


def test_looks_secret_shaped_matches_the_same_vocabulary_as_secret_line_detection():
    assert looks_secret_shaped("sk-live-SOME-SECRET-999")
    assert looks_secret_shaped("api_key")
    assert looks_secret_shaped("API-KEY")
    assert looks_secret_shaped("auth_token")
    assert looks_secret_shaped("user_password")


def test_looks_secret_shaped_is_false_for_ordinary_field_names():
    assert not looks_secret_shaped("payload")
    assert not looks_secret_shaped("log")
    assert not looks_secret_shaped("leaked_repo_field")
    assert not looks_secret_shaped("extra_forbidden")


def test_looks_secret_shaped_is_false_for_non_string_segments():
    """A `loc` segment can be an int (a list index) — never secret-shaped by
    construction, and must not raise on a non-string input."""
    assert not looks_secret_shaped(0)
    assert not looks_secret_shaped(None)


def test_redact_loc_replaces_only_the_secret_shaped_segment():
    loc = ("payload", "log", "sk-live-SOME-SECRET-999")
    redacted = redact_loc(loc)
    assert redacted == ("payload", "log", REDACTED_LOC_SEGMENT)


def test_redact_loc_leaves_a_fully_ordinary_loc_untouched():
    loc = ("payload", "log", "leaked_repo_field")
    assert redact_loc(loc) == loc


def test_redact_loc_preserves_int_list_indices():
    loc = ("evidence_refs", 2, "sk-live-SOME-SECRET-999")
    assert redact_loc(loc) == ("evidence_refs", 2, REDACTED_LOC_SEGMENT)
