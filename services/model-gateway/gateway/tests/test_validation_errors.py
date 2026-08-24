"""`gateway.validation_errors` — #258.

Unit-level coverage for the helper `gateway/ollama.py` and `gateway/transcripts.py`
now share; the end-to-end regressions against real call sites live in
`test_ollama_backend.py` and `test_replay_mode.py`/`test_transcripts_cli.py`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, ValidationError

from gateway.validation_errors import (
    REDACTED_LOC_SEGMENT,
    looks_secret_shaped,
    safe_validation_error_shape,
)


def test_looks_secret_shaped_matches_the_same_vocabulary_as_context_py():
    assert looks_secret_shaped("sk-live-SOME-SECRET-999")
    assert looks_secret_shaped("api_key")
    assert looks_secret_shaped("API-KEY")
    assert looks_secret_shaped("auth_token")
    assert looks_secret_shaped("user_password")


def test_looks_secret_shaped_is_false_for_ordinary_field_names():
    assert not looks_secret_shaped("response")
    assert not looks_secret_shaped("confidence")
    assert not looks_secret_shaped(0)
    assert not looks_secret_shaped(None)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confidence: float


def test_safe_validation_error_shape_strips_input_and_redacts_a_secret_shaped_key():
    secret_value = "sk-live-SUPER-SECRET-value"
    secret_key = "sk-live-SOME-SECRET-999"

    try:
        _Strict.model_validate({"confidence": secret_value, secret_key: "y"})
    except ValidationError as exc:
        shape = safe_validation_error_shape(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected a ValidationError")

    shape_text = repr(shape)
    assert secret_value not in shape_text
    assert secret_key not in shape_text
    assert "input" not in shape_text
    assert any(e["loc"] == ("confidence",) for e in shape)
    assert any(REDACTED_LOC_SEGMENT in e["loc"] for e in shape)
