"""Rule 2 for this seat: confidence is displayed, never trusted.

`CLAUDE.md`: *"A patch is never accepted on model confidence alone... Any code path that
lets confidence substitute for verification is a bug."* The control API enforces its half
structurally — `ModelProvenance.confidence` is not reachable from `GateMatrix`, so
`derive_verdict` cannot see it. This is the gateway's half: the value travels, and nothing
here reads it.

Behavioural tests catch a threshold somebody writes today. The static scan catches the one
somebody writes next month, which is the one that matters, because by then nobody is
reviewing this file.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from gateway.schemas import GenerationRequest
from gateway.service import build_gateway
from gateway.settings import GatewaySettings
from gateway.tests.conftest import FakeLiveBackend

PACKAGE = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("confidence", [None, 0.0, 0.01, 0.5, 1.0])
def test_every_confidence_produces_the_same_behaviour(
    live_settings: GatewaySettings,
    request_: GenerationRequest,
    confidence: float | None,
) -> None:
    backend = FakeLiveBackend()
    backend.candidate = backend.candidate.model_copy(update={"confidence": confidence})

    response = build_gateway(live_settings, live_backend=backend).generate(request_)

    assert backend.calls == 1, "no retry, no second attempt, at any score"
    assert response.candidate.confidence == confidence, "recorded exactly as given"
    assert response.provenance.confidence == confidence, "and carried into provenance"


def test_a_zero_confidence_candidate_is_still_returned(
    live_settings: GatewaySettings, request_: GenerationRequest
) -> None:
    """Suppressing a low score would be the gateway making a verdict-shaped decision."""
    backend = FakeLiveBackend()
    backend.candidate = backend.candidate.model_copy(update={"confidence": 0.0})
    response = build_gateway(live_settings, live_backend=backend).generate(request_)
    assert response.candidate.diff


def _modules() -> list[Path]:
    return sorted(p for p in PACKAGE.rglob("*.py") if "tests" not in p.parts)


@pytest.mark.parametrize("module", _modules(), ids=lambda p: p.name)
def test_no_module_branches_on_confidence(module: Path) -> None:
    """Static: `confidence` is never a condition, a comparison, or a sort key.

    Assignment, attribute access and keyword passing are fine — that is the value
    travelling. What is not fine is it appearing inside an `if`, a `while`, a comparison, a
    boolean operation, or a `key=`, because each of those is the value influencing what the
    system does.
    """
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    offenders: list[str] = []

    def mentions_confidence(node: ast.AST) -> bool:
        return any(
            (isinstance(child, ast.Name) and child.id == "confidence")
            or (isinstance(child, ast.Attribute) and child.attr == "confidence")
            for child in ast.walk(node)
        )

    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.While, ast.IfExp)) and mentions_confidence(node.test):
            offenders.append(f"line {node.lineno}: branch on confidence")
        elif isinstance(node, (ast.Compare, ast.BoolOp)) and mentions_confidence(node):
            offenders.append(f"line {node.lineno}: comparison involving confidence")

    assert not offenders, (
        f"{module.relative_to(PACKAGE.parent)} reads confidence as a decision:\n"
        + "\n".join(f"  - {line}" for line in offenders)
        + "\n\nConfidence is displayed beside its source and is an input to nothing. A "
        "gateway that branches on it is the first half of a verdict that a model decided."
    )
