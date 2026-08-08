"""The "no code path" half of issue #82's honesty criterion.

`test_provenance_labelling.py` asserts that each renderer behaves. That is necessary and it
is not sufficient: it says nothing about a renderer somebody adds next week. This module
covers the gap by asserting a structural property instead of a behavioural one — **all
provenance wording in this package lives in `gateway/provenance.py`** — so a second place
that describes a response in words fails the build rather than shipping.

## What this can and cannot claim

It is a claim about `services/model-gateway/`. It is **not** a claim about the whole
product. The Command Center (`apps/command-center/`) and the evidence builder are other
seats' code and this test cannot see them; the gateway's contribution is to hand them a
label they should print verbatim, and `render_for_ui()['label']` is that string. Whether
they print it is theirs to test, and it is named as an open question in the handoff rather
than assumed here.

Scanning source text is a blunt instrument and it is the right one here. The alternative —
a registry renderers opt into — is bypassed by not opting in, which is exactly the failure
mode being defended against.
"""

from __future__ import annotations

import ast
from datetime import UTC
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
CHOKEPOINT = PACKAGE / "provenance.py"

#: Phrases that only read as a claim about where a response came from. A module other than
#: `provenance.py` containing one of these is, by construction, a second place that can
#: describe a response — which is the thing being prevented.
#:
#: Bare "recorded" and bare "operator-supplied" are deliberately **not** here. Both occur
#: legitimately in error and log messages ("no recorded transcript for this request",
#: "cannot read the operator-supplied candidate at ..."), which are diagnostics, not labels.
#: Including them would make the test noisy, and a noisy test gets an exemption added to it,
#: which is how this kind of guard dies. The exact finished labels are checked separately by
#: `test_no_module_reproduces_a_finished_provenance_label`.
CLAIM_PHRASES = (
    "model-generated",
    "model generated",
    "live inference",
    "model output recorded",
    ", replayed",
)


def _modules() -> list[Path]:
    return sorted(
        path
        for path in PACKAGE.rglob("*.py")
        if path != CHOKEPOINT and "tests" not in path.parts and path.name != "__init__.py"
    )


def _string_literals(path: Path) -> list[str]:
    """Every string literal in a module, excluding docstrings and comments.

    Prose is allowed to discuss provenance — these modules are heavily commented and that
    is deliberate. What is not allowed is a *runtime* string that could reach a screen.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                docstrings.add(doc)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value not in docstrings
    ]


@pytest.mark.parametrize("module", _modules(), ids=lambda p: p.name)
def test_only_provenance_py_puts_a_provenance_claim_into_a_runtime_string(
    module: Path,
) -> None:
    offenders = [
        (phrase, literal)
        for literal in _string_literals(module)
        for phrase in CLAIM_PHRASES
        if phrase in literal.lower()
    ]
    assert not offenders, (
        f"{module.relative_to(PACKAGE.parent)} contains provenance wording in a runtime "
        "string:\n"
        + "\n".join(f"  {phrase!r} in {literal!r}" for phrase, literal in offenders)
        + "\n\nEvery sentence describing where a response came from is produced by "
        "gateway.provenance.describe(). A second one is a second thing to keep in sync, "
        "and the one that drifts is the one on screen."
    )


def test_no_module_reproduces_a_finished_provenance_label() -> None:
    """The exact strings `describe()` returns appear in exactly one file.

    Complements the phrase scan above, which is deliberately narrow. This one is exact and
    total: a copy-pasted label anywhere else in the package fails here.
    """
    from datetime import datetime

    from gateway.provenance import ResponseProvenance, ResponseSource, describe

    labels = {
        describe(
            ResponseProvenance(
                source=ResponseSource.RECORDED_TRANSCRIPT,
                model_name="m",
                served_from="h",
                generated_at=datetime(2026, 8, 13, tzinfo=UTC),
                replayed_from_transcript="x.json",
                captured_at=datetime(2026, 8, 6, tzinfo=UTC),
                transcript_sha256="d" * 64,
            )
        ),
        describe(ResponseProvenance(source=ResponseSource.OPERATOR_SUPPLIED)),
        describe(ResponseProvenance(source=ResponseSource.LIVE_INFERENCE)),
    }
    # The date-bearing labels are checked by their fixed prefix and suffix; the rest exactly.
    needles = {label.replace("2026-08-06", "").replace("2026-08-13", "") for label in labels}

    for module in _modules():
        literals = _string_literals(module)
        for needle in needles:
            fragment = needle.strip().strip("()")
            offenders = [text for text in literals if fragment in text]
            assert not offenders, (
                f"{module.relative_to(PACKAGE.parent)} contains the finished label "
                f"{fragment!r} in a runtime string: {offenders!r}. Labels come from "
                "gateway.provenance.describe() and from nowhere else."
            )


def test_the_chokepoint_is_where_the_wording_actually_is() -> None:
    """Guards the guard: if the strings moved, the scan above became vacuous."""
    text = CHOKEPOINT.read_text(encoding="utf-8")
    for phrase in ("model output recorded ", "operator-supplied candidate", "live inference"):
        assert phrase in text, (
            f"{phrase!r} is no longer in provenance.py. Either the wording changed — in "
            "which case the fallback ladder and issue #82 need updating too — or the "
            "renderers moved and this test is now checking nothing."
        )


def test_the_renderer_list_in_the_labelling_tests_is_exhaustive() -> None:
    """The two honesty tests only cover the package together if this holds.

    `test_provenance_labelling.RENDERERS` is checked against everything public in
    `provenance.py` that returns something renderable, so adding a fourth renderer without
    adding it to that list fails here rather than going untested.
    """
    import gateway.provenance as provenance_module
    from gateway.tests.test_provenance_labelling import RENDERERS

    public_renderers = {
        name for name in provenance_module.__all__ if name.startswith(("render_", "describe"))
    }
    assert public_renderers == {f.__name__ for f in RENDERERS}, (
        "provenance.py exports a renderer that test_provenance_labelling.py does not "
        "exercise. Every function that turns provenance into words has to be in that "
        "parametrisation, or 'no code path presents a replayed response as live' is only "
        "true of the paths somebody remembered."
    )
