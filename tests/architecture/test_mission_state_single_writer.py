"""SEC-16, the review-time half: one writer of mission state, one caller of the guard.

The runtime guard in `missions/lifecycle.py` stops the write. This stops the *pattern* —
and the threat actor here is not an attacker, it is a future developer with a plausible
reason, so review time is the right layer. This is the same structural-read technique as
`orchestrator/tests/test_verdict_completeness.py::test_the_records_are_loaded_by_mission_with_no_filter`,
applied one level up.

Runs at the repository root with no Django import, so it works in the `pytest tests/`
CI step that has no `DJANGO_SETTINGS_MODULE`.
"""

from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_API = REPO_ROOT / "apps" / "control-api"

#: The one module allowed to move a mission through its lifecycle.
SANCTIONED_TRANSITION_MODULE = "orchestrator/transitions.py"

#: `verification_started_at` is the D-046 freeze, and the sanctioned writer of that one
#: column is the verification recorder — it sets the freeze under the same lock that
#: writes the record. It is listed explicitly rather than folded in, so that adding a
#: third writer is a visible edit to this list.
SANCTIONED_FREEZE_MODULE = "orchestrator/candidates.py"


def _production_sources() -> list[Path]:
    """Every non-test Python file under the control API."""
    if not CONTROL_API.is_dir():  # pragma: no cover - the app always exists
        pytest.skip("apps/control-api does not exist yet")
    return [
        path
        for path in sorted(CONTROL_API.rglob("*.py"))
        if "/tests/" not in path.as_posix()
        and not path.name.startswith("test_")
        and "/migrations/" not in path.as_posix()
    ]


def _relative(path: Path) -> str:
    return path.relative_to(CONTROL_API).as_posix()


def _code_only(path: Path) -> str:
    """The file with comments and string literals removed.

    Necessary, and it makes the check stronger rather than weaker. Several of the
    modules under test *quote the exploit* in their docstrings — explaining why the
    guard exists is the whole reason those docstrings are worth reading — and a naive
    grep flags the explanation as the violation. Tokenizing means these tests read what
    the interpreter runs, not what the file says about itself.
    """
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except tokenize.TokenError:  # pragma: no cover - a syntax error fails elsewhere
        return source

    # Blank out comments and string literals in place, so line numbers, indentation and
    # intra-line spacing all survive and the regexes below can be written the way the
    # code actually reads.
    blanked = [list(line) for line in lines]
    for token in tokens:
        if token.type not in (tokenize.COMMENT, tokenize.STRING):
            continue
        (start_row, start_col), (end_row, end_col) = token.start, token.end
        for row in range(start_row, end_row + 1):
            if row - 1 >= len(blanked):  # pragma: no cover - defensive
                continue
            line = blanked[row - 1]
            first = start_col if row == start_row else 0
            last = end_col if row == end_row else len(line)
            for col in range(first, min(last, len(line))):
                line[col] = " "
    return "\n".join("".join(line) for line in blanked)


def test_only_the_orchestrator_assigns_mission_state():
    """`mission.state = ...` appears in exactly one production file."""
    pattern = re.compile(r"^\s*\w*mission\w*\.state\s*=(?!=)", re.MULTILINE)
    offenders = {
        _relative(path)
        for path in _production_sources()
        if pattern.search(_code_only(path))
    }
    assert offenders == {SANCTIONED_TRANSITION_MODULE}, (
        f"Mission.state is assigned in {sorted(offenders)}. Only "
        f"{SANCTIONED_TRANSITION_MODULE} may move a mission's state: it is the only "
        f"place that holds the row lock and has loaded the mission's COMPLETE "
        f"verification set. A second writer reaches a terminal verdict past guards "
        f"that were never run (SEC-16)."
    )


def test_only_the_orchestrator_bulk_updates_a_lifecycle_field():
    """`.update(state=...)` never calls `save()`, so the model guard cannot see it."""
    pattern = re.compile(
        r"\.update\([^)]*\b(state|paused_from|verdict|verification_started_at)\s*=",
        re.DOTALL,
    )
    offenders = {
        _relative(path)
        for path in _production_sources()
        if pattern.search(_code_only(path))
    }
    assert not offenders, (
        f"a mission lifecycle field is bulk-updated in {sorted(offenders)}. Use "
        f"orchestrator.transitions.transition, which takes the row lock first."
    )


def test_assert_transition_has_exactly_one_production_caller():
    """The guard is only meaningful when it is on the single path to the write.

    A second caller is not automatically wrong — but it is always a decision, and this
    test makes it one someone has to take deliberately rather than by autocomplete.
    """
    pattern = re.compile(r"^(?!def |\s*def ).*\bassert_transition\(", re.MULTILINE)
    callers = {
        _relative(path)
        for path in _production_sources()
        if _relative(path) != "contracts/state_machine.py"
        and pattern.search(_code_only(path))
    }
    assert callers == {SANCTIONED_TRANSITION_MODULE}, (
        f"assert_transition is called from {sorted(callers)}. It is a guard on the "
        f"transaction-scoped write path; called from anywhere else it validates a "
        f"decision nobody is about to persist under the lock (SEC-16)."
    )


def test_only_the_verification_recorder_writes_the_freeze_column():
    """D-046's column has one writer, and it is the one that writes the record."""
    pattern = re.compile(r"\.verification_started_at\s*=(?!=)")
    offenders = {
        _relative(path)
        for path in _production_sources()
        if pattern.search(_code_only(path))
    }
    assert offenders <= {SANCTIONED_FREEZE_MODULE, SANCTIONED_TRANSITION_MODULE}, (
        f"the D-046 freeze column is written in {sorted(offenders)}. Adding a writer "
        f"means adding it to this list, which is the point."
    )


def test_the_lifecycle_permission_is_claimed_in_exactly_two_places():
    """`lifecycle_write()` is the capability that makes a mission write legal.

    If it spreads, the guard becomes decorative. Two call sites today: the transition
    path, and the freeze write inside the verification recorder.
    """
    pattern = re.compile(r"^\s*(?:with .*)?\blifecycle_write\(\)", re.MULTILINE)
    claimants = {
        _relative(path)
        for path in _production_sources()
        if _relative(path) != "missions/lifecycle.py"
        and pattern.search(_code_only(path))
    }
    assert claimants == {SANCTIONED_TRANSITION_MODULE, SANCTIONED_FREEZE_MODULE}, (
        f"lifecycle_write() is entered in {sorted(claimants)}. Every additional "
        f"claimant is another place a mission can be moved without the row lock and "
        f"the complete evidence set."
    )
