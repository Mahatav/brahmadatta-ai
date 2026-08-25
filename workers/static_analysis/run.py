"""Mission-facing wrapper for the Semgrep scan (#22, D-144).

Mirrors `workers/fuzzing/run.py::run_fuzzing_stage`'s own shape and error-handling
boundary: a caller-configuration problem (`adapters.semgrep.errors.
SemgrepAdapterError`, `ValueError` — unpinned image, missing source/ruleset
directory) becomes a `NOT_RUN` outcome here; `packages.sandbox.errors.JailError`
(the sandbox itself could not start) is deliberately NOT caught here — see
`adapters/semgrep/run_semgrep.py`'s own docstring — and is `workers.static_analysis.
dispatch`'s executor's job to turn into an `infra_failure` result, exactly like
`workers/fuzzing/dispatch.py`'s `_fuzz_executor` does for `JailError` around
`run_fuzzing_stage`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from adapters.semgrep.errors import SemgrepAdapterError
from adapters.semgrep.parser import SemgrepMatch
from adapters.semgrep.run_semgrep import run_semgrep_scan
from packages.sandbox.container import ContainerJailPolicy

__all__ = ["AnalyzeOutcome", "run_analyze_stage"]


@dataclass(frozen=True, slots=True)
class AnalyzeOutcome:
    """Field names deliberately mirror `workers.fuzzing.run.FuzzingOutcome`'s shape
    (`mode`, `recorded_at`, `failure`) so a reader already familiar with that stage
    recognises this one."""

    mission_id: str
    mode: str  # "LIVE_SCAN" | "NOT_RUN"
    tool: str = "semgrep"
    tool_version: str = "unknown"
    ruleset_version: str = "unknown"
    image_digest: str | None = None
    runtime_seconds: float = 0.0
    files_scanned: int = 0
    matches: tuple[SemgrepMatch, ...] = field(default_factory=tuple)
    tool_errors: tuple[str, ...] = field(default_factory=tuple)
    stdout_truncated: bool = False
    failure_reason: str | None = None
    recorded_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def ran(self) -> bool:
        return self.mode == "LIVE_SCAN"

    def as_dict(self) -> dict[str, object]:
        """JSON-serializable summary — never includes a match's raw `code_snippet`
        (unredacted repository content); `workers.static_analysis.dispatch` is the
        boundary that redacts and persists per-match detail into `Finding` rows.
        """
        return {
            "mission_id": self.mission_id,
            "mode": self.mode,
            "tool": self.tool,
            "tool_version": self.tool_version,
            "ruleset_version": self.ruleset_version,
            "image_digest": self.image_digest,
            "runtime_seconds": self.runtime_seconds,
            "files_scanned": self.files_scanned,
            "matches_found": len(self.matches),
            "tool_errors": list(self.tool_errors),
            "stdout_truncated": self.stdout_truncated,
            "failure_reason": self.failure_reason,
            "recorded_at": self.recorded_at.isoformat(),
        }


def _not_run(mission_id: str, recorded_at: datetime, reason: str) -> AnalyzeOutcome:
    return AnalyzeOutcome(
        mission_id=mission_id,
        mode="NOT_RUN",
        recorded_at=recorded_at,
        failure_reason=reason,
    )


def run_analyze_stage(
    mission_id: str | uuid.UUID,
    source_dir: Path | str,
    *,
    policy: ContainerJailPolicy,
    rules_dir: Path | str,
) -> AnalyzeOutcome:
    """Run the real, live Semgrep scan and return a mission-shaped outcome.

    Never raises on a caller-configuration fault (mirrors `run_fuzzing_stage`'s own
    contract) — only a genuine sandbox/infrastructure fault
    (`packages.sandbox.errors.JailError`) propagates past this function.
    """
    mission_id_str = str(mission_id)
    recorded_at = datetime.now(UTC)

    try:
        result = run_semgrep_scan(source_dir, policy, rules_dir=rules_dir, mission_ref=mission_id_str)
    except (SemgrepAdapterError, ValueError) as exc:
        return _not_run(mission_id_str, recorded_at, str(exc) or exc.__class__.__name__)

    if not result.report.ok:
        return AnalyzeOutcome(
            mission_id=mission_id_str,
            mode="NOT_RUN",
            tool_version=result.report.tool_version,
            ruleset_version=result.ruleset_version,
            image_digest=result.image_digest,
            runtime_seconds=result.runtime_seconds,
            tool_errors=result.report.tool_errors,
            recorded_at=recorded_at,
            failure_reason="semgrep reported a scan-level error; see tool_errors",
        )

    return AnalyzeOutcome(
        mission_id=mission_id_str,
        mode="LIVE_SCAN",
        tool_version=result.report.tool_version,
        ruleset_version=result.ruleset_version,
        image_digest=result.image_digest,
        runtime_seconds=result.runtime_seconds,
        files_scanned=len(result.report.scanned_files),
        matches=result.report.matches,
        tool_errors=result.report.tool_errors,
        stdout_truncated=result.stdout_truncated,
        recorded_at=recorded_at,
    )
