"""Replay a stored reproducer as a first-class mission path.

#83's promise is deliberately narrower than fuzzing: a mission can start from an
already-stored crash input, build a sanitized target, replay that input through the
direct harness, and record a sanitizer-confirmed finding without starting a fuzz
campaign at all. This module owns that path.

The output mirrors the evidence/event shape used elsewhere in the backend, but stays
as plain dictionaries for now like `workers.baseline.run`: no Django app, event bus, or
evidence persistence is imported from this worker.

## Redacting `ReplayFinding.sanitizer_report` (#246, following #191/D-125)

`_finding_from_sanitizer` builds `sanitizer_report` from `run_replay_stage`'s own
`stderr` — the raw, joined `captured_stderr` of every replay attempt, verbatim output
of the sandboxed process — the exact same "raw captured tool output" class `workers/
fuzzing/dispatch.py` already redacts via `orchestrator.redaction.redact_sanitizer_report`
before it reaches `Finding.sanitizer_report` (#191, SEC-50, D-125). This module cannot
call that function directly, for a real structural reason rather than convenience:

`orchestrator` lives at `apps/control-api/orchestrator/`, and `apps/control-api` only
lands on `sys.path` as a side effect of Django settings loading — `config/settings/
base.py` does the `sys.path.insert(0, str(BASE_DIR))` itself, and that module is only
ever imported via `manage.py`, `wsgi`/`asgi`, or pytest-django's `DJANGO_SETTINGS_MODULE`
machinery. This module's own docstring above commits to importing no Django app, and
`workers/replay/cli.py` runs as `python -m workers.replay` with only the repo root on
`sys.path` — confirmed directly: `import orchestrator.redaction` from a bare
interpreter at the repo root raises `ModuleNotFoundError`, exactly the failure `workers/
fuzzing/dispatch.py` never hits because it only ever runs inside the Django process
that already did that `sys.path` insertion. Making this worker depend on Django having
initialized first — just to reach one redaction function — would be a much larger,
undocumented coupling than the leak-prevention it buys.

`_redact_sanitizer_report` below is therefore a duplicate of `orchestrator.redaction.
redact_sanitizer_report`'s two regexes and behaviour (absolute-path and environment/
secret-assignment-line stripping, substituting in place rather than discarding the
whole report), not a new detector — the same "mirror the shape, do not import across
the boundary" choice `services/model-gateway/gateway/validation_errors.py` already made
for its own cross-package boundary (that module's own docstring explains its case: a
deliberately separate dependency closure rather than a sys.path accident, but the same
resolution). If the two drift apart, that is a real signal — a reviewer touching either
should check the other.
"""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from adapters.cpp.pipeline import ReproducerResult, run_reproducer, run_variant
from adapters.cpp.sanitizer import SanitizerFinding
from adapters.cpp.variants import Variant, spec_for
from packages.sandbox import Jail, JailPolicy

__all__ = [
    "ReplayFinding",
    "ReplayOutcome",
    "ReplayReproducerRecord",
    "emit_replay_events",
    "run_replay_stage",
]

_EVENT_FINDING_RECORDED = "FINDING_RECORDED"
_EVENT_REPRODUCER_RECORDED = "REPRODUCER_RECORDED"
_EVENT_STAGE_COMPLETED = "STAGE_COMPLETED"
_MISSION_STATE_STRESS_TEST = "STRESS_TEST"
_MISSION_STAGE_STRESS_TEST = "STRESS_TEST"
_DEFAULT_REPRODUCER = Path("crash") / "crash-literal-tab.bin"

# --------------------------------------------------------------------------------------
# Duplicated from `apps/control-api/orchestrator/redaction.py::redact_sanitizer_report`
# (#191/D-125) — see this module's docstring, "Redacting ReplayFinding.sanitizer_report",
# for why this cannot be a direct import instead.
# --------------------------------------------------------------------------------------

#: Same leak class as `orchestrator.redaction.sanitize_detail`'s `=`-ban (`DATABASE_URL=
#: postgresql://...`-shaped content), but redacting only the offending line rather than
#: the whole report — an `ALLCAPS_NAME=value` assignment, optionally `export`-prefixed,
#: is not a shape a genuine ASan/UBSan grammar line (header, stack frame, or `SUMMARY:`)
#: ever produces.
_ENV_ASSIGNMENT_LINE_RE = re.compile(r"(?im)^.*\b(?:export\s+)?[A-Z_][A-Z0-9_]{2,}\s*=\s*\S.*$")

#: The secret-keyword vocabulary itself, mirroring `orchestrator.redaction.
#: _SECRET_KEYWORD_RE` / `gateway/context.py::_SECRET_LINE`.
_SECRET_KEYWORD_RE = re.compile(r"api[_-]?key|token|secret|password", re.IGNORECASE)

#: Mirrors `orchestrator.redaction._SECRET_LINE_RE`: a named-secret assignment
#: (`api_key=...`, `token: ...`) regardless of casing, which `_ENV_ASSIGNMENT_LINE_RE`
#: alone would miss for a lowercase key.
_SECRET_LINE_RE = re.compile(rf"(?im)^.*\b(?:{_SECRET_KEYWORD_RE.pattern})\s*[:=].*$")

#: Mirrors `orchestrator.redaction._ABSOLUTE_PATH_RE`: a Unix absolute path or a Windows
#: drive path, substituted in place so a stack frame keeps its frame index, address, and
#: function name and loses only the path span.
_ABSOLUTE_PATH_RE = re.compile(r"(?<![\w./-])(?:/[A-Za-z0-9._@%+=:,~ -]+)+|[A-Za-z]:\\[^\s:]+")

_REDACTED_LINE = "[redacted: line removed - looked like a secret or environment assignment]"
_REDACTED_PATH = "[redacted absolute path]"


def _redact_sanitizer_report(report: str) -> str:
    """Strip absolute paths and environment/secret-shaped lines from a raw ASan/UBSan
    report, keeping everything else — crash type, stack frames, offsets.

    Byte-for-byte the same behaviour as `orchestrator.redaction.redact_sanitizer_report`
    (see this module's docstring for why that function is duplicated here rather than
    imported). Idempotent for the same reason: neither regex matches its own placeholder
    text.
    """
    if not report:
        return report
    redacted = _SECRET_LINE_RE.sub(_REDACTED_LINE, report)
    redacted = _ENV_ASSIGNMENT_LINE_RE.sub(_REDACTED_LINE, redacted)
    redacted = _ABSOLUTE_PATH_RE.sub(_REDACTED_PATH, redacted)
    return redacted


@dataclass(frozen=True, slots=True)
class ReplayFinding:
    id: str
    mission_id: str
    category: str
    severity: str
    tool: str
    discovery_method: str
    replay_source: str
    file_path: str
    line: int | None
    function: str | None
    fingerprint: str
    reproducible: bool
    detected_at: datetime
    title: str
    sanitizer_report: str

    def as_summary_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "mission_id": self.mission_id,
            "category": self.category,
            "severity": self.severity,
            "tool": self.tool,
            "discovery_method": self.discovery_method,
            "replay_source": self.replay_source,
            "location": {
                "file_path": self.file_path,
                "line": self.line,
                "function": self.function,
            },
            "fingerprint": self.fingerprint,
            "reproducible": self.reproducible,
            "detected_at": self.detected_at.isoformat(),
            "title": self.title,
        }


@dataclass(frozen=True, slots=True)
class ReplayReproducerRecord:
    id: str
    finding_id: str
    minimized: bool
    replay_attempts: int
    replay_successes: int
    test_command: str
    artifact: dict[str, Any]
    created_at: datetime

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "finding_id": self.finding_id,
            "minimized": self.minimized,
            "replay_attempts": self.replay_attempts,
            "replay_successes": self.replay_successes,
            "test_command": self.test_command,
            "artifact": self.artifact,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class ReplayOutcome:
    mission_id: str
    source_dir: str
    replay_source: str
    replay_attempts: int
    replay_successes: int
    duration_seconds: float
    build_variant: str
    fuzzing_report: dict[str, Any]
    finding: ReplayFinding | None
    reproducer: ReplayReproducerRecord | None
    captured_stdout: str
    captured_stderr: str
    recorded_at: datetime

    @property
    def confirmed(self) -> bool:
        return self.finding is not None and self.replay_successes == self.replay_attempts

    def as_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "source_dir": self.source_dir,
            "replay_source": self.replay_source,
            "replay_attempts": self.replay_attempts,
            "replay_successes": self.replay_successes,
            "duration_seconds": self.duration_seconds,
            "build_variant": self.build_variant,
            "confirmed": self.confirmed,
            "fuzzing_report": self.fuzzing_report,
            "finding": self.finding.as_summary_dict() if self.finding else None,
            "reproducer": self.reproducer.as_dict() if self.reproducer else None,
            "recorded_at": self.recorded_at.isoformat(),
        }


def run_replay_stage(
    mission_id: str | uuid.UUID,
    source_dir: Path | str,
    workspace_root: Path | str,
    *,
    reproducer_path: Path | str | None = None,
    replay_attempts: int = 5,
    jail_policy: JailPolicy | None = None,
) -> ReplayOutcome:
    """Run the stored-reproducer path without starting a fuzz campaign.

    The reproducer is executed in separate processes. A sanitizer abort stops one
    process at the first fault, so five independent invocations are the observable
    claim "5/5 replayed" actually needs.
    """
    if replay_attempts < 1:
        raise ValueError("replay_attempts must be >= 1")

    started = time.monotonic()
    mission_id_str = str(mission_id)
    recorded_at = datetime.now(UTC)
    source = Path(source_dir).resolve()
    reproducer = (
        Path(reproducer_path).resolve()
        if reproducer_path is not None
        else (source / _DEFAULT_REPRODUCER).resolve()
    )
    if not reproducer.is_file():
        raise FileNotFoundError(f"stored reproducer not found: {reproducer}")

    workspace = Path(workspace_root).resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    spec = spec_for(Variant.ASAN_UBSAN)
    policy = jail_policy or JailPolicy(memory_bytes=spec.min_jail_memory_bytes)
    results: list[ReproducerResult] = []

    with Jail.create(policy, parent=workspace) as jail:
        build = run_variant(source, jail, Variant.ASAN_UBSAN)
        binary = build.build_dir / "pktcfg_replay"
        for _ in range(replay_attempts):
            results.append(run_reproducer(jail, binary, (str(reproducer), "1"), spec=spec))

    first_finding = _first_finding(results)
    replay_successes = sum(1 for result in results if result.findings)
    stdout = "\n".join(result.captured_stdout for result in results if result.captured_stdout)
    stderr = "\n".join(result.captured_stderr for result in results if result.captured_stderr)
    replay_ref = _artifact_uri("reproducer", reproducer.name)
    finding = (
        _finding_from_sanitizer(first_finding, mission_id_str, replay_ref, recorded_at, stderr)
        if first_finding is not None
        else None
    )
    reproducer_record = (
        _reproducer_record(
            finding.id,
            reproducer,
            replay_attempts,
            replay_successes,
            recorded_at,
        )
        if finding is not None
        else None
    )

    return ReplayOutcome(
        mission_id=mission_id_str,
        source_dir=str(source),
        replay_source=replay_ref,
        replay_attempts=replay_attempts,
        replay_successes=replay_successes,
        duration_seconds=time.monotonic() - started,
        build_variant=Variant.ASAN_UBSAN.value,
        fuzzing_report=_not_run_fuzzing_report(mission_id_str, recorded_at),
        finding=finding,
        reproducer=reproducer_record,
        captured_stdout=stdout,
        captured_stderr=stderr,
        recorded_at=recorded_at,
    )


def emit_replay_events(outcome: ReplayOutcome, *, sequence_start: int = 1) -> list[dict[str, Any]]:
    """Return mission events for the replay path.

    The stress-test/fuzzing stage is emitted as skipped with a `NOT_RUN` fuzzing report,
    then the replay-confirmed finding and reproducer are recorded separately. This is
    intentionally not a fuzz pass.
    """
    events: list[dict[str, Any]] = [
        {
            "id": str(uuid.uuid4()),
            "sequence": sequence_start,
            "timestamp": outcome.recorded_at.isoformat(),
            "type": _EVENT_STAGE_COMPLETED,
            "status": "SUCCEEDED",
            "severity": "INFO",
            "message": (
                "STRESS_TEST_SKIPPED: fuzzing did not run; stored reproducer replay "
                f"confirmed {outcome.replay_successes}/{outcome.replay_attempts}."
            ),
            "payload": {"kind": "fuzzing", "report": outcome.fuzzing_report},
            "evidence_refs": [outcome.replay_source],
            "metrics": {
                "fuzz_executions": 0.0,
                "replay_attempts": float(outcome.replay_attempts),
                "replay_successes": float(outcome.replay_successes),
            },
            "mission_id": outcome.mission_id,
            "stage": _MISSION_STAGE_STRESS_TEST,
            "state": _MISSION_STATE_STRESS_TEST,
        }
    ]

    if outcome.finding is not None:
        events.append(
            {
                "id": str(uuid.uuid4()),
                "sequence": sequence_start + len(events),
                "timestamp": outcome.finding.detected_at.isoformat(),
                "type": _EVENT_FINDING_RECORDED,
                "status": "SUCCEEDED",
                "severity": outcome.finding.severity,
                "message": outcome.finding.title,
                "payload": {"kind": "finding", "finding": outcome.finding.as_summary_dict()},
                "evidence_refs": [outcome.replay_source],
                "metrics": {"replay_successes": float(outcome.replay_successes)},
                "mission_id": outcome.mission_id,
                "stage": _MISSION_STAGE_STRESS_TEST,
                "state": _MISSION_STATE_STRESS_TEST,
            }
        )

    if outcome.reproducer is not None:
        events.append(
            {
                "id": str(uuid.uuid4()),
                "sequence": sequence_start + len(events),
                "timestamp": outcome.reproducer.created_at.isoformat(),
                "type": _EVENT_REPRODUCER_RECORDED,
                "status": "SUCCEEDED",
                "severity": "CRITICAL" if outcome.confirmed else "ERROR",
                "message": (
                    f"Stored reproducer replayed {outcome.replay_successes}/"
                    f"{outcome.replay_attempts} with sanitizer confirmation."
                ),
                "payload": {"kind": "reproducer", "reproducer": outcome.reproducer.as_dict()},
                "evidence_refs": [outcome.replay_source],
                "metrics": {
                    "replay_attempts": float(outcome.replay_attempts),
                    "replay_successes": float(outcome.replay_successes),
                },
                "mission_id": outcome.mission_id,
                "stage": _MISSION_STAGE_STRESS_TEST,
                "state": _MISSION_STATE_STRESS_TEST,
            }
        )

    return events


def _first_finding(results: list[ReproducerResult]) -> SanitizerFinding | None:
    for result in results:
        if result.findings:
            return result.findings[0]
    return None


def _finding_from_sanitizer(
    finding: SanitizerFinding,
    mission_id: str,
    replay_source: str,
    detected_at: datetime,
    sanitizer_report: str,
) -> ReplayFinding:
    category = _category_for(finding)
    function = None if finding.function == "<unknown>" else finding.function
    file_path = finding.file or "<unknown>"
    title = _title_for(category, function, file_path, finding.line)
    return ReplayFinding(
        id=str(uuid.uuid4()),
        mission_id=mission_id,
        category=category,
        severity="CRITICAL" if category.endswith("BUFFER_OVERFLOW") else "HIGH",
        tool=finding.tool,
        discovery_method="REPLAYED_REPRODUCER",
        replay_source=replay_source,
        file_path=file_path,
        line=finding.line,
        function=function,
        fingerprint=_fingerprint(finding),
        reproducible=True,
        detected_at=detected_at,
        title=title,
        # #246 (following #191/D-125): redact before storing in the dataclass, not just
        # before display — `sanitizer_report` is raw captured stderr up to this point,
        # and `_redact_sanitizer_report` (this module's duplicate of `orchestrator.
        # redaction.redact_sanitizer_report`) is the same redaction pass `workers/
        # fuzzing/dispatch.py` applies at its own capture point.
        sanitizer_report=_redact_sanitizer_report(sanitizer_report[-20000:]),
    )


def _reproducer_record(
    finding_id: str,
    reproducer: Path,
    attempts: int,
    successes: int,
    created_at: datetime,
) -> ReplayReproducerRecord:
    return ReplayReproducerRecord(
        id=str(uuid.uuid4()),
        finding_id=finding_id,
        minimized=True,
        replay_attempts=attempts,
        replay_successes=successes,
        test_command=f"./pktcfg_replay {reproducer.name} x{attempts}",
        artifact={
            "uri": _artifact_uri("reproducer", reproducer.name),
            "kind": "crash-input",
            "sha256": _sha256(reproducer),
            "size_bytes": reproducer.stat().st_size,
        },
        created_at=created_at,
    )


def _not_run_fuzzing_report(mission_id: str, recorded_at: datetime) -> dict[str, Any]:
    return {
        "mission_id": mission_id,
        "mode": "NOT_RUN",
        "harness": "pktcfg_fuzz_one_input",
        "engine": "libFuzzer",
        "runtime_seconds": 0.0,
        "executions": 0,
        "crashes_found": 0,
        "unique_crashes": 0,
        "corpus_size": 0,
        "sanitizers": ["address", "undefined"],
        "finding_ids": [],
        "replay_source": None,
        "recorded_at": recorded_at.isoformat(),
    }


def _category_for(finding: SanitizerFinding) -> str:
    kind = finding.kind.lower()
    if "heap-buffer-overflow" in kind:
        return "HEAP_BUFFER_OVERFLOW"
    if "stack-buffer-overflow" in kind:
        return "STACK_BUFFER_OVERFLOW"
    if "global-buffer-overflow" in kind:
        return "GLOBAL_BUFFER_OVERFLOW"
    if "use-after-free" in kind:
        return "USE_AFTER_FREE"
    if "double-free" in kind:
        return "DOUBLE_FREE"
    if "leak" in kind:
        return "MEMORY_LEAK"
    if finding.tool == "UNDEFINED_BEHAVIOUR_SANITIZER":
        return "UNDEFINED_BEHAVIOUR"
    return "OTHER"


def _fingerprint(finding: SanitizerFinding) -> str:
    material = ":".join(
        [
            "replayed",
            finding.tool,
            finding.kind,
            finding.function,
            finding.file or "",
            str(finding.line or ""),
        ]
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"replayed:{finding.tool}:{finding.kind}:{finding.function}:{digest}"[:128]


def _title_for(category: str, function: str | None, file_path: str, line: int | None) -> str:
    location = f"{Path(file_path).name}:{line}" if line is not None else Path(file_path).name
    bug = category.replace("_", " ").lower()
    if function:
        return f"{bug} in {function} ({location})"
    return f"{bug} at {location}"


def _artifact_uri(kind: str, name: str) -> str:
    return f"artifact://{kind}/{name}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

