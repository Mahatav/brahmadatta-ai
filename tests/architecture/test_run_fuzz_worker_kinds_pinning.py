"""#199 (SEC-55, found during PR #197's cybersecurity review) — `infrastructure/
scripts/run-fuzz-worker.sh` hardcoded `--kinds FUZZ,MINIMIZE`, but a caller-supplied
`--kinds` passed through `"$@"` silently overrode it (`manage.py run_worker`'s
argparse is last-flag-wins) -- someone invoking this script with an extra flag could
accidentally start fuzz-worker claiming a different kind set than D-073 intends,
defeating the whole point of this dedicated, isolation-critical entrypoint (it is the
ONLY process anywhere in this system given real Docker access).

The fix: the script rejects a caller-supplied `--kinds` outright, before any other
preflight step runs (docker reachability, Postgres connectivity, etc.) -- so this
behavior does not depend on those being available on the machine running the test.

This is a real subprocess test against the actual script (matching this repository's
convention for exercising a shell entrypoint from Python -- see `tests/architecture/
test_fuzz_worker_isolation.py`'s runtime half), not a static read of its source: the
property under test is "the process actually refuses to start", which only a real
invocation proves.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "infrastructure" / "scripts" / "run-fuzz-worker.sh"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT_PATH), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_script_exists_and_is_the_expected_entrypoint() -> None:
    assert SCRIPT_PATH.is_file(), f"{SCRIPT_PATH} is missing"


def test_caller_supplied_kinds_space_form_is_rejected() -> None:
    result = _run("--kinds", "FUZZ")
    assert result.returncode != 0, (
        "run-fuzz-worker.sh must refuse to start when the caller passes --kinds "
        f"(#199); it exited 0 instead. stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "--kinds" in result.stderr
    assert "#199" in result.stderr


def test_caller_supplied_kinds_equals_form_is_rejected() -> None:
    result = _run("--kinds=BASELINE")
    assert result.returncode != 0, (
        "run-fuzz-worker.sh must refuse --kinds=<value> too, not just the "
        f"space-separated form (#199). stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "--kinds" in result.stderr


def test_caller_supplied_kinds_attempting_to_widen_scope_is_also_rejected() -> None:
    """The exact D-073 nightmare scenario the finding describes: an operator (or a
    copy-pasted command) tries to hand fuzz-worker a kind set beyond FUZZ/MINIMIZE.
    Must be refused exactly like any other --kinds, not specially allowed or denied
    based on its value -- the script does not try to be clever about which values are
    'safe'; it rejects the flag itself."""
    result = _run("--kinds", "BASELINE,CORRELATE,PATCH_GENERATE")
    assert result.returncode != 0
    assert "--kinds" in result.stderr


def test_the_rejection_happens_before_any_other_preflight_check() -> None:
    """The failure must be about --kinds specifically, not a side effect of some
    other preflight step (docker, Postgres, etc.) failing first -- otherwise this
    behavior would only be provable on a machine with those available, which the
    isolation-critical property (#199) should not depend on."""
    result = _run("--kinds", "FUZZ", "--once")
    assert "docker" not in result.stderr.lower()
    assert "database_url" not in result.stderr.lower()
    assert result.stdout == "", (
        "no preflight banner ('== fuzz-worker preflight ...') should have printed "
        f"before the --kinds rejection fired; got stdout={result.stdout!r}"
    )


def test_kinds_free_invocation_is_not_rejected_by_the_kinds_guard() -> None:
    """The negative control: an invocation with no --kinds anywhere in its arguments
    must not trip the guard added for #199. It may still fail later (no docker/DB in
    this test environment is not guaranteed), but not because of --kinds."""
    result = _run("--once")
    assert "does not accept a caller-supplied --kinds" not in result.stderr


def test_an_unrelated_flag_containing_the_substring_kinds_is_not_mistaken_for_it() -> None:
    """Guards the guard's own precision: a flag that merely contains 'kinds' as a
    substring (not exactly `--kinds` or `--kinds=...`) must not be treated as the
    caller trying to override the pinned kind set."""
    result = _run("--totally-unrelated-kinds-of-thing", "value")
    assert "does not accept a caller-supplied --kinds" not in result.stderr
