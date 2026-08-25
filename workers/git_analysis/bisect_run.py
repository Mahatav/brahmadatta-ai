"""End-to-end `git bisect` driver (#24): `start` -> `bad` -> `good` -> `run
bisect_step.py` -> read the answer -> `reset`, wrapped around a real repository.

This is the pure, callable half of what a future orchestrator `ANALYZE`/`TRIAGE`
executor would dispatch -- the same shape `workers/baseline/run.py`'s
`run_baseline_stage`/`emit_baseline_events` pair already established for a stage with
no orchestrator wiring yet: a plain function that does the real work and returns a
frozen outcome, plus a second function that turns that outcome into mission-event
envelopes the orchestrator can send once something exists to send them to.

**This module does not wire bisect into `apps/control-api/orchestrator/queue.py`'s
`advance_through_triage` stub.** That stub currently auto-completes `TRIAGE` with a
"no analyzers configured" placeholder because nothing real ran there yet (see its own
docstring and `docs/09-company/06-architecture-spec.md` line ~304). Turning bisect into
a real, dispatched `TRIAGE` analyzer means deciding, at the architecture level, when a
mission has a good/bad commit range to bisect at all (a live mission's "good" baseline
commit is not automatically known the way #5's fixture's is), how it composes with
`#22` (Semgrep) and `#23` (compiler warnings) landing in the same stage, and whether
it is automatic or operator-triggered -- real design questions for
`software-architect`/`engineering-manager`, not a call this module makes unilaterally.
See the PR description and handoff for the open question this leaves.

Events emitted here use `EventType.STAGE_STARTED` / `STAGE_PROGRESS` /
`STAGE_COMPLETED` -- vocabulary `apps/control-api/contracts/enums.py` already defines
and `advance_through_triage`'s own stub already uses for the same stage -- rather than
inventing bisect-specific event-type strings. No enum file is touched by this change.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from adapters.cpp.variants import MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS

__all__ = [
    "BisectOutcome",
    "BisectStepLogEntry",
    "GitCommandError",
    "emit_bisect_events",
    "run_git_bisect",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
BISECT_STEP_SCRIPT = Path(__file__).resolve().parent / "bisect_step.py"

_EVENT_STAGE_STARTED = "STAGE_STARTED"
_EVENT_STAGE_PROGRESS = "STAGE_PROGRESS"
_EVENT_STAGE_COMPLETED = "STAGE_COMPLETED"
_MISSION_STAGE_ANALYZE = "ANALYZE"
_MISSION_STATE_TRIAGE = "TRIAGE"

#: `git bisect log` step lines look like `git bisect good <sha>` / `git bisect bad
#: <sha>` / `git bisect skip <sha>`, one per commit actually tested, in the order they
#: were tested. Deliberately does NOT try to also capture a trailing "# <subject>" on
#: the same regex: git's own log format puts that comment on the line *before* each
#: command (`# good: [<sha>] <subject>`, above `git bisect good <sha>`), not after it
#: -- an earlier version of this regex used `\s*#\s*(?P<subject>.*)` here, and because
#: `\s` matches a newline, it silently walked past the end of the command line and
#: attached the *next* line's unrelated comment as if it were this step's subject.
#: Subjects are resolved separately, correctly, via `git log` in `run_git_bisect`.
_STEP_LINE_RE = re.compile(
    r"^git bisect (?P<verdict>good|bad|skip) (?P<sha>[0-9a-f]{7,40})$",
    re.MULTILINE,
)
#: The line `git bisect run` (or a manual `git bisect good/bad` sequence that converges)
#: appends once bisection is complete: `# first bad commit: [<sha>] <subject>`.
_CULPRIT_LINE_RE = re.compile(r"^# first bad commit: \[(?P<sha>[0-9a-f]{7,40})\] (?P<subject>.*)$", re.MULTILINE)


class GitCommandError(RuntimeError):
    """A `git` invocation this driver depends on (not a bisect *step* -- those go
    through `bisect_step.py` and never raise) failed outright."""

    def __init__(self, argv: list[str], returncode: int, stderr: str) -> None:
        self.argv = argv
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"{' '.join(argv)} exited {returncode}: {stderr.strip()[:500]}")


@dataclass(frozen=True, slots=True)
class BisectStepLogEntry:
    """One line of `git bisect log` -- one commit `git bisect run` actually tested."""

    sha: str
    verdict: str
    subject: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"sha": self.sha, "verdict": self.verdict, "subject": self.subject}


@dataclass(frozen=True, slots=True)
class BisectOutcome:
    """Everything a caller needs out of one full bisect run."""

    mission_id: str
    repo_path: str
    good_commit: str
    bad_commit: str
    culprit_commit: str | None
    culprit_subject: str
    steps: tuple[BisectStepLogEntry, ...]
    duration_seconds: float
    recorded_at: datetime
    succeeded: bool
    raw_log: str
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "repo_path": self.repo_path,
            "good_commit": self.good_commit,
            "bad_commit": self.bad_commit,
            "culprit_commit": self.culprit_commit,
            "culprit_subject": self.culprit_subject,
            "steps": [s.as_dict() for s in self.steps],
            "steps_tested": len(self.steps),
            "duration_seconds": self.duration_seconds,
            "recorded_at": self.recorded_at.isoformat(),
            "succeeded": self.succeeded,
            "error": self.error,
        }


def _run_git(argv: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(  # noqa: S603 - argv is always a literal list built by this module, shell is never used
        argv, cwd=str(cwd), capture_output=True, text=True, timeout=60
    )
    if check and result.returncode != 0:
        raise GitCommandError(argv, result.returncode, result.stderr)
    return result


def _parse_bisect_log(raw_log: str) -> tuple[tuple[tuple[str, str], ...], str | None, str]:
    """Every `git bisect <verdict> <sha>` line in `git bisect log`'s output, in order,
    as `(sha, VERDICT)` pairs -- callers still need to drop the first two (the caller's
    own initial `bad`/`good` endpoint assertions, not a step `git bisect run` tested;
    see `run_git_bisect`, which is the only caller and always issues exactly those two
    commands, in that fixed order, before `git bisect run` ever starts searching)."""
    matches = tuple(
        (m.group("sha"), m.group("verdict").upper()) for m in _STEP_LINE_RE.finditer(raw_log)
    )
    culprit_match = _CULPRIT_LINE_RE.search(raw_log)
    culprit_sha = culprit_match.group("sha") if culprit_match else None
    culprit_subject = culprit_match.group("subject").strip() if culprit_match else ""
    return matches, culprit_sha, culprit_subject


def _resolve_subjects(repo: Path, shas: Sequence[str]) -> dict[str, str]:
    """One-shot commit-subject lookup for a batch of shas, via `git log --no-walk`
    rather than one `git show`/`git log` call per commit -- steps parsed out of a
    single `git bisect log` are usually a handful, but there is no reason to pay for
    N processes when one does the same job. Falls back to an empty subject per sha
    (never raises) if `git log` itself cannot resolve one of them for any reason --
    a missing subject is a cosmetic gap in an event message, not a correctness
    failure this driver should abort a whole bisection outcome over.
    """
    if not shas:
        return {}
    result = _run_git(
        ["git", "log", "--no-walk", "--format=%H%x01%s", *shas], cwd=repo, check=False
    )
    subjects: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "\x01" not in line:
            continue
        sha, _, subject = line.partition("\x01")
        subjects[sha] = subject
    return subjects


def run_git_bisect(
    mission_id: str | uuid.UUID,
    repo_path: Path | str,
    good_commit: str,
    bad_commit: str,
    check_argv: list[str],
    *,
    timeout_seconds: float = 120.0,
    memory_bytes: int = MIN_JAIL_MEMORY_BYTES_FOR_SANITIZERS,
    python_executable: str | None = None,
) -> BisectOutcome:
    """Run a complete `git bisect` session against an already-cloned repository.

    `repo_path` must already be a real git repository containing both `good_commit`
    and `bad_commit` in its history (for #5's fixture: run
    `demo/repositories/restore-pktcfg-history.sh` first). `check_argv` is the check
    command `bisect_step.py` runs at every step -- it receives `repo_path` appended as
    its final argument, the same convention `pktcfg-bisect-check.sh` already documents.

    Leaves `repo_path` back on whatever `HEAD` `git bisect start` found it on
    (`git bisect reset`'s own behaviour) even when bisection fails partway through --
    the `finally` block runs `git bisect reset` unconditionally so a failed or
    interrupted call never leaves the repository checked out mid-bisect for whatever
    caller (or concurrent test) looks at it next.

    Never raises for an ordinary bisection failure (`git bisect run` itself reporting
    a nonzero status, or no culprit found) -- that comes back as
    `BisectOutcome(succeeded=False, error=...)`, the same "a red result is a valid,
    complete result" rule `workers/baseline/run.py` already follows. Only a `git`
    invocation this driver depends on failing outright (`start`/`bad`/`good` rejecting
    the given commits, `git` itself missing) raises `GitCommandError` -- that is a
    caller-supplied-bad-input problem, not a bisection outcome.
    """
    started = time.monotonic()
    recorded_at = datetime.now(UTC)
    repo = Path(repo_path).resolve()
    python_exe = python_executable or sys.executable

    _run_git(["git", "bisect", "start"], cwd=repo)
    try:
        _run_git(["git", "bisect", "bad", bad_commit], cwd=repo)
        _run_git(["git", "bisect", "good", good_commit], cwd=repo)

        wrapper_argv = [
            python_exe,
            str(BISECT_STEP_SCRIPT),
            "--timeout-seconds",
            str(timeout_seconds),
            "--memory-bytes",
            str(memory_bytes),
            "--",
            *check_argv,
        ]
        run_result = _run_git(["git", "bisect", "run", *wrapper_argv], cwd=repo, check=False)

        log_result = _run_git(["git", "bisect", "log"], cwd=repo)
        raw_matches, culprit_sha, culprit_subject = _parse_bisect_log(log_result.stdout)
        # The first two `git bisect <verdict> <sha>` lines are always this function's
        # own initial `bisect bad <bad_commit>` / `bisect good <good_commit>` calls
        # above, in that fixed order -- not commits `git bisect run`'s search actually
        # tested. See `_parse_bisect_log`'s docstring.
        tested_matches = raw_matches[2:]
        subjects = _resolve_subjects(repo, [sha for sha, _ in tested_matches])
        steps = tuple(
            BisectStepLogEntry(sha=sha, verdict=verdict, subject=subjects.get(sha, ""))
            for sha, verdict in tested_matches
        )

        succeeded = run_result.returncode == 0 and culprit_sha is not None
        error = None
        if not succeeded:
            error = (
                f"git bisect run exited {run_result.returncode}; "
                f"culprit_found={culprit_sha is not None}. "
                f"stderr tail: {run_result.stderr.strip()[-500:]}"
            )

        return BisectOutcome(
            mission_id=str(mission_id),
            repo_path=str(repo),
            good_commit=good_commit,
            bad_commit=bad_commit,
            culprit_commit=culprit_sha,
            culprit_subject=culprit_subject,
            steps=steps,
            duration_seconds=time.monotonic() - started,
            recorded_at=recorded_at,
            succeeded=succeeded,
            raw_log=log_result.stdout,
            error=error,
        )
    finally:
        # Best-effort: a repository already back at its original HEAD (nothing to
        # reset) makes `git bisect reset` a harmless no-op; a repository this driver
        # never got as far as `bisect start`-ing successfully never reaches this
        # `finally` at all, since the un-try-wrapped `bisect start` call above would
        # already have raised before entering it.
        _run_git(["git", "bisect", "reset"], cwd=repo, check=False)


def emit_bisect_events(outcome: BisectOutcome, *, sequence_start: int = 1) -> list[dict[str, Any]]:
    """`STAGE_STARTED` + one `STAGE_PROGRESS` per tested commit + `STAGE_COMPLETED`,
    shaped like `contracts.schemas.envelope.MissionEvent` -- same envelope shape and
    the same "returned, not sent, because there is nothing to send to yet" rule
    `workers/baseline/run.py`'s `emit_baseline_events` already documents.
    """
    envelope_common = {
        "mission_id": outcome.mission_id,
        "stage": _MISSION_STAGE_ANALYZE,
        "state": _MISSION_STATE_TRIAGE,
    }
    base_time = outcome.recorded_at
    events: list[dict[str, Any]] = []
    seq = sequence_start

    events.append(
        {
            "id": str(uuid.uuid4()),
            "sequence": seq,
            "timestamp": base_time.isoformat(),
            "type": _EVENT_STAGE_STARTED,
            "status": "RUNNING",
            "severity": "INFO",
            "message": f"git bisect started: good={outcome.good_commit[:12]} bad={outcome.bad_commit[:12]}",
            "payload": {
                "kind": "bisect",
                "good_commit": outcome.good_commit,
                "bad_commit": outcome.bad_commit,
            },
            "evidence_refs": [],
            "metrics": {},
            **envelope_common,
        }
    )
    seq += 1

    for step in outcome.steps:
        events.append(
            {
                "id": str(uuid.uuid4()),
                "sequence": seq,
                "timestamp": base_time.isoformat(),
                "type": _EVENT_STAGE_PROGRESS,
                "status": "RUNNING",
                "severity": "INFO",
                "message": f"bisect {step.verdict.lower()} {step.sha[:12]}"
                + (f" -- {step.subject}" if step.subject else ""),
                "payload": {"kind": "bisect_step", **step.as_dict()},
                "evidence_refs": [],
                "metrics": {},
                **envelope_common,
            }
        )
        seq += 1

    completed_message = (
        f"git bisect found the first bad commit: {outcome.culprit_commit[:12]} "
        f"{outcome.culprit_subject}"
        if outcome.succeeded and outcome.culprit_commit
        else f"git bisect did not converge: {outcome.error}"
    )
    events.append(
        {
            "id": str(uuid.uuid4()),
            "sequence": seq,
            "timestamp": base_time.isoformat(),
            "type": _EVENT_STAGE_COMPLETED,
            "status": "COMPLETED" if outcome.succeeded else "FAILED",
            "severity": "INFO" if outcome.succeeded else "ERROR",
            "message": completed_message,
            "payload": {"kind": "bisect", "report": outcome.as_dict()},
            "evidence_refs": [],
            "metrics": {
                "steps_tested": float(len(outcome.steps)),
                "duration_seconds": outcome.duration_seconds,
            },
            **envelope_common,
        }
    )

    return events
