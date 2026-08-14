"""Context assembly for model patch requests.

D5's gateway rule is stricter than "validate the endpoint": the model may only see a
bounded, redacted finding package. The caller never hands this module a repository root,
a file handle, or an arbitrary prompt string. It hands over a structured finding and a
policy, and this module produces the one `ContextPackage` that can be converted into a
`GenerationRequest`.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from gateway.schemas import GatewayResponse, GenerationRequest
from gateway.service import ModelGateway

__all__ = [
    "ContextFinding",
    "ContextPackage",
    "ContextPolicy",
    "PatchPolicyContext",
    "build_context",
    "request_patch",
]

PROMPT_VERSION = "patch-prompt/4"
MAX_CONTEXT_CHARS = 12_000
_SECRET_LINE = re.compile(r"(?im)^.*(?:api[_-]?key|token|secret|password)\s*[:=].*$")
_ABSOLUTE_PATH = re.compile(
    r"(?<![\w./-])(?:/[A-Za-z0-9._@%+=:,~ -]+)+|[A-Za-z]:\\[^\s:]+"
)


class PatchPolicyContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed_paths: tuple[str, ...] = ()
    max_files_changed: int = Field(default=1, ge=1, le=10)
    max_lines_changed: int = Field(default=40, ge=1, le=500)


class ContextPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    patch: PatchPolicyContext = Field(default_factory=PatchPolicyContext)
    reproducer_replay_attempts: int = Field(default=5, ge=1, le=100)


class ContextFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mission_id: str = Field(min_length=1, max_length=100)
    finding_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    category: str = Field(min_length=1, max_length=120)
    severity: str = Field(min_length=1, max_length=80)
    file_path: str = Field(min_length=1, max_length=1000)
    function: str | None = Field(default=None, max_length=300)
    sanitizer_report: str = Field(default="", max_length=20_000)
    code_slice: str = Field(default="", max_length=20_000)
    reproducer_uri: str | None = Field(default=None, max_length=500)
    reproducer_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class ContextPackage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mission_id: str = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=1, max_length=MAX_CONTEXT_CHARS)
    prompt_version: str = Field(default=PROMPT_VERSION, max_length=100)
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    context_bytes: int = Field(ge=1)
    redactions_applied: tuple[str, ...] = ()


def build_context(finding: ContextFinding, policy: ContextPolicy) -> ContextPackage:
    """Build the only model-visible context package."""
    raw = _prompt_sections(finding, policy)
    sanitized, redactions = _redact(raw)
    prompt = sanitized[:MAX_CONTEXT_CHARS].rstrip()
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return ContextPackage(
        mission_id=finding.mission_id,
        prompt=prompt,
        prompt_sha256=digest,
        context_bytes=len(prompt.encode("utf-8")),
        redactions_applied=tuple(redactions),
    )


def request_patch(
    context: ContextPackage,
    policy: ContextPolicy,
    gateway: ModelGateway,
) -> GatewayResponse:
    """Ask the configured local gateway for a schema-valid patch candidate."""
    request = GenerationRequest(
        mission_id=context.mission_id,
        prompt=context.prompt,
        prompt_version=context.prompt_version,
        temperature=0.0,
        max_output_tokens=_max_output_tokens(policy),
    )
    return gateway.generate(request)


def _prompt_sections(finding: ContextFinding, policy: ContextPolicy) -> str:
    location = f"{finding.file_path}"
    if finding.function:
        location += f"::{finding.function}"
    allowed_paths = ", ".join(policy.patch.allowed_paths) or "<none>"
    return "\n\n".join(
        [
            "You are repairing a C/C++ security defect. Return JSON only: "
            "diff, rationale, touched_files, confidence.",
            f"Mission: {finding.mission_id}",
            f"Finding: {finding.finding_id} | {finding.category} | {finding.severity}",
            f"Title: {finding.title}",
            f"Location: {location}",
            "Patch policy: "
            f"allowed_paths={allowed_paths}; "
            f"max_files_changed={policy.patch.max_files_changed}; "
            f"max_lines_changed={policy.patch.max_lines_changed}; "
            f"replay_attempts={policy.reproducer_replay_attempts}",
            f"Reproducer: {_artifact_line(finding)}",
            f"Sanitizer excerpt:\n{finding.sanitizer_report}",
            f"Relevant code slice:\n{finding.code_slice}",
        ]
    )


def _artifact_line(finding: ContextFinding) -> str:
    if not finding.reproducer_uri:
        return "not recorded"
    if not finding.reproducer_sha256:
        return finding.reproducer_uri
    return f"{finding.reproducer_uri} sha256:{finding.reproducer_sha256}"


def _redact(text: str) -> tuple[str, Sequence[str]]:
    redactions: list[str] = []
    if _SECRET_LINE.search(text):
        text = _SECRET_LINE.sub("[REDACTED SECRET LINE]", text)
        redactions.append("secret-line")
    if _ABSOLUTE_PATH.search(text):
        text = _ABSOLUTE_PATH.sub("[REDACTED ABSOLUTE PATH]", text)
        redactions.append("absolute-path")
    return text, redactions


def _max_output_tokens(policy: ContextPolicy) -> int:
    return min(4096, max(1024, policy.patch.max_lines_changed * 80))
