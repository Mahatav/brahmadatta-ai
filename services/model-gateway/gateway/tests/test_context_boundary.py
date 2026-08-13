from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path
from typing import get_type_hints

import pytest

from gateway.context import (
    ContextFinding,
    ContextPackage,
    ContextPolicy,
    PatchPolicyContext,
    build_context,
    request_patch,
)
from gateway.service import build_gateway
from gateway.settings import GatewayMode, GatewaySettings
from gateway.tests.conftest import FakeLiveBackend

PACKAGE = Path(__file__).resolve().parents[1]
CONTEXT_MODULE = PACKAGE / "context.py"


def _finding() -> ContextFinding:
    return ContextFinding(
        mission_id="m-0001",
        finding_id="f-0001",
        title="heap buffer overflow in pkt_decode_into",
        category="HEAP_BUFFER_OVERFLOW",
        severity="CRITICAL",
        file_path="src/decode.c",
        function="pkt_decode_into",
        sanitizer_report=(
            "ASan at /Users/manu/private/repo/src/decode.c:128\n"
            "API_TOKEN=sk-demo-should-not-leave\n"
            "WRITE of size 1"
        ),
        code_slice="PASSWORD=hunter2\nbuf[i] = value;",
        reproducer_uri="artifact://reproducer/crash.bin",
        reproducer_sha256="a" * 64,
    )


def test_build_context_redacts_paths_and_secret_lines_before_prompt_hash() -> None:
    context = build_context(
        _finding(),
        ContextPolicy(
            patch=PatchPolicyContext(
                allowed_paths=("src/decode.c",),
                max_files_changed=1,
                max_lines_changed=40,
            )
        ),
    )

    assert isinstance(context, ContextPackage)
    assert "sk-demo" not in context.prompt
    assert "hunter2" not in context.prompt
    assert "/Users/manu" not in context.prompt
    assert "[REDACTED SECRET LINE]" in context.prompt
    assert "[REDACTED ABSOLUTE PATH]" in context.prompt
    assert set(context.redactions_applied) == {"secret-line", "absolute-path"}
    assert re.fullmatch(r"[0-9a-f]{64}", context.prompt_sha256)


def test_request_patch_is_the_gateway_consumer_of_context(
    live_settings: GatewaySettings,
) -> None:
    gateway = build_gateway(live_settings, live_backend=FakeLiveBackend())
    context = build_context(_finding(), ContextPolicy())

    response = request_patch(context, ContextPolicy(), gateway)

    assert response.candidate.diff.startswith("--- a/")
    assert response.provenance.prompt_sha256 == context.prompt_sha256
    assert response.provenance.context_bytes == context.context_bytes


def test_context_boundary_signatures_do_not_accept_repo_roots_or_free_prompt_strings() -> None:
    build_signature = inspect.signature(build_context)
    request_signature = inspect.signature(request_patch)
    build_hints = get_type_hints(build_context)
    request_hints = get_type_hints(request_patch)

    assert list(build_signature.parameters) == ["finding", "policy"]
    assert list(request_signature.parameters) == ["context", "policy", "gateway"]
    assert build_hints["finding"] is ContextFinding
    assert build_hints["policy"] is ContextPolicy
    assert request_hints["context"] is ContextPackage
    assert request_hints["policy"] is ContextPolicy


def test_context_package_is_only_constructed_by_build_context() -> None:
    offenders: list[str] = []
    for path in PACKAGE.rglob("*.py"):
        if path == CONTEXT_MODULE or "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _name(node.func) == "ContextPackage":
                offenders.append(f"{path.relative_to(PACKAGE.parent)}:{node.lineno}")

    assert offenders == []


@pytest.mark.parametrize("module", sorted(PACKAGE.rglob("*.py")), ids=lambda p: p.name)
def test_gateway_public_functions_do_not_accept_repository_roots(module: Path) -> None:
    if "tests" in module.parts:
        return
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    offenders: list[str] = []
    banned_fragments = ("repo_root", "repository_root", "worktree", "source_root")

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
            name = arg.arg.lower()
            if any(fragment in name for fragment in banned_fragments):
                offenders.append(f"{node.name}({arg.arg}) at line {node.lineno}")

    assert offenders == []


def test_context_request_never_silently_switches_to_replay(tmp_path: Path) -> None:
    settings = GatewaySettings(
        mode=GatewayMode.LIVE,
        endpoint="http://127.0.0.1:8080/v1",
        transcript_root=tmp_path,
        resolve_endpoint=False,
    ).validate()
    context = build_context(_finding(), ContextPolicy())

    with pytest.raises(Exception, match="nothing was attempted"):
        request_patch(context, ContextPolicy(), build_gateway(settings))


def _name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""
