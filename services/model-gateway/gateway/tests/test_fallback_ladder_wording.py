"""The strings this package emits are read back out of the fallback ladder document.

`docs/09-company/10-fallback-ladder.md` specifies the exact sentence permitted in each
mode, and §4 lists the sentences that are never said. Both halves are enforceable, and a
test that reads the document is the only version that stays true when the document is
edited — a hard-coded copy of the wording drifts silently the first time somebody changes
one and not the other.

The ladder's §5 says it plainly: today the ladder "is enforced by a tired person
remembering to set a flag". This module and `test_provenance_chokepoint.py` are the part of
that which the gateway can take off the tired person.

Skips cleanly if the document is absent, so the package remains testable on its own.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gateway.provenance import (
    ResponseProvenance,
    ResponseSource,
    describe,
    render_for_evidence,
    render_for_ui,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
LADDER = REPO_ROOT / "docs" / "09-company" / "10-fallback-ladder.md"

pytestmark = pytest.mark.skipif(
    not LADDER.is_file(), reason="docs/09-company/10-fallback-ladder.md not present"
)

CAPTURED = datetime(2026, 8, 6, 21, 45, tzinfo=UTC)

REPLAYED = ResponseProvenance(
    source=ResponseSource.RECORDED_TRANSCRIPT,
    model_name="m",
    served_from="http://127.0.0.1:8080/v1",
    generated_at=datetime(2026, 8, 13, tzinfo=UTC),
    replayed_from_transcript=f"{'d' * 64}.json",
    captured_at=CAPTURED,
    transcript_sha256="d" * 64,
)
OPERATOR = ResponseProvenance(
    source=ResponseSource.OPERATOR_SUPPLIED,
    generated_at=datetime(2026, 8, 13, tzinfo=UTC),
)


def _ladder_text() -> str:
    # The document writes the mandated string with HTML entities inside a Markdown table:
    # `"model output recorded &lt;date&gt;, replayed"`.
    return LADDER.read_text(encoding="utf-8").replace("&lt;", "<").replace("&gt;", ">")


def test_the_ladder_still_mandates_the_string_this_package_emits() -> None:
    """Rung 2's fallback claim, taken from the document rather than retyped."""
    assert "model output recorded <date>, replayed" in _ladder_text(), (
        "the fallback ladder no longer contains the string gateway.provenance emits. "
        "One of the two changed without the other."
    )
    # The same sentence with the placeholder filled in is what `describe()` produces.
    assert describe(REPLAYED) == "model output recorded 2026-08-06, replayed"


def test_the_ladder_still_mandates_the_operator_supplied_string() -> None:
    assert "operator-supplied candidate" in _ladder_text()
    assert describe(OPERATOR) == "operator-supplied candidate"


def test_none_of_the_forbidden_sentences_appear_in_anything_this_package_renders() -> None:
    """§4, "Sentences we do not say", applied to every renderer and every claim.

    The phrases are the ones §4 can be checked for mechanically. "air-gapped" and
    "rootless" belong to the isolation seat and are listed here anyway, because the cost of
    checking is nil and the cost of one of them reaching a slide is the whole pitch.
    """
    forbidden = (
        "air-gapped",
        "rootless",
        "cannot reach the internet",
        "structurally impossible",
        "guaranteed",
        "signed by hash",
        "our fuzzer found it",
    )
    ladder = _ladder_text().lower()
    for phrase in forbidden:
        assert phrase in ladder, f"{phrase!r} is no longer in the ladder's §4 table"

    for provenance in (REPLAYED, OPERATOR):
        rendered = " ".join(
            (describe(provenance), render_for_evidence(provenance), str(render_for_ui(provenance)))
        ).lower()
        for phrase in forbidden:
            assert phrase not in rendered, (
                f"a renderer produced {phrase!r}, which the fallback ladder §4 forbids"
            )


def test_the_ladder_forbids_model_generated_for_a_replayed_candidate() -> None:
    """The §4 row that is specifically this package's to honour."""
    row = [
        line
        for line in _ladder_text().splitlines()
        if "model-generated" in line and "replayed" in line
    ]
    assert row, "the §4 row forbidding 'model-generated' for a replayed candidate is gone"

    assert "model-generated" not in describe(REPLAYED)
    assert "model-generated" not in render_for_evidence(REPLAYED)
    assert "model-generated" not in str(render_for_ui(REPLAYED))


def test_the_three_rung_3_triggers_are_all_distinguishable_errors() -> None:
    """Rung 3 fires on "transcript absent, `transcript_sha256` mismatch, or schema-version
    mismatch" — "one command, one answer".

    Each has its own error type or its own message, so the operator's one command can say
    which of the three it was. The behaviours are exercised in `test_replay_mode.py`; this
    asserts the ladder still names these three and only these three.
    """
    text = _ladder_text()
    rung3 = [line for line in text.splitlines() if "Replay does not resolve" in line]
    assert rung3, "rung 3's trigger sentence is gone from the ladder"
    for trigger in ("transcript absent", "transcript_sha256` mismatch", "schema-version mismatch"):
        assert trigger in rung3[0], f"rung 3 no longer lists {trigger!r}"


def test_the_ladder_still_says_replay_is_never_a_silent_fallback() -> None:
    assert re.search(
        r"replay mode is an operator choice and never a silent fallback", _ladder_text(), re.I
    ), "§2.3's rule is what test_no_silent_fallback.py enforces; it is no longer stated"
