"""End-to-end `git bisect` against real fixtures (#24's own verification requirement):
the real #5 seeded history for the "finds the known first-bad-commit" acceptance
criterion, plus a small synthetic repo for the timeout path so that assertion does not
depend on the real toolchain being slow enough to observe -- it is asserted directly.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from workers.git_analysis.bisect_run import emit_bisect_events, run_git_bisect
from workers.git_analysis.tests.conftest import KNOWN_BAD_COMMIT, KNOWN_GOOD_COMMIT

REPO_ROOT = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.slow

PKTCFG_BISECT_CHECK = REPO_ROOT / "demo" / "repositories" / "pktcfg-bisect-check.sh"


def test_git_bisect_finds_the_known_seeded_defect_commit(pktcfg_repo: Path) -> None:
    """The issue's own verification requirement: run the real fixture's git bisect,
    through this wrapper (not the throwaway oracle script alone), and land on exactly
    114383dd517e49e1285b53608184cb744adb2aaa -- #5/D-146's documented answer key."""
    outcome = run_git_bisect(
        mission_id="test-mission-24",
        repo_path=pktcfg_repo,
        good_commit=KNOWN_GOOD_COMMIT,
        bad_commit=KNOWN_BAD_COMMIT,  # HEAD == the known-bad commit in this fixture
        check_argv=["bash", str(PKTCFG_BISECT_CHECK)],
        timeout_seconds=60,
    )

    assert outcome.succeeded, outcome.error
    assert outcome.culprit_commit == KNOWN_BAD_COMMIT
    assert "literal tab" in outcome.culprit_subject
    # A meaningful bisection actually ran a binary search, not a degenerate one-step
    # answer -- #5's history has 14 commits between the two endpoints tested.
    assert len(outcome.steps) >= 2
    assert all(step.verdict in ("GOOD", "BAD", "SKIP") for step in outcome.steps)

    # The repo is left clean, not mid-bisect, once this driver returns.
    status = subprocess.run(
        ["git", "status", "--porcelain=v1"], cwd=pktcfg_repo, capture_output=True, text=True, check=True
    )
    assert status.stdout.strip() == ""
    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=pktcfg_repo, capture_output=True, text=True, check=True
    )
    assert branch.stdout.strip() == "main"


def test_emit_bisect_events_shapes_a_full_timeline(pktcfg_repo: Path) -> None:
    outcome = run_git_bisect(
        mission_id="test-mission-24",
        repo_path=pktcfg_repo,
        good_commit=KNOWN_GOOD_COMMIT,
        bad_commit=KNOWN_BAD_COMMIT,
        check_argv=["bash", str(PKTCFG_BISECT_CHECK)],
        timeout_seconds=60,
    )
    events = emit_bisect_events(outcome)

    assert events[0]["type"] == "STAGE_STARTED"
    assert events[-1]["type"] == "STAGE_COMPLETED"
    assert events[-1]["status"] == "COMPLETED"
    assert KNOWN_BAD_COMMIT[:12] in events[-1]["message"]
    progress_events = [e for e in events if e["type"] == "STAGE_PROGRESS"]
    assert len(progress_events) == len(outcome.steps)
    for e in events:
        assert e["stage"] == "ANALYZE"
        assert e["state"] == "TRIAGE"
        assert e["mission_id"] == "test-mission-24"
    # sequence numbers are contiguous and start where asked
    sequences = [e["sequence"] for e in events]
    assert sequences == list(range(1, len(events) + 1))


def test_run_git_bisect_rejects_a_bad_commit_reference(pktcfg_repo: Path) -> None:
    from workers.git_analysis.bisect_run import GitCommandError

    with pytest.raises(GitCommandError):
        run_git_bisect(
            mission_id="test-mission-24",
            repo_path=pktcfg_repo,
            good_commit="0000000000000000000000000000000000000000",
            bad_commit=KNOWN_BAD_COMMIT,
            check_argv=["bash", str(PKTCFG_BISECT_CHECK)],
            timeout_seconds=10,
        )
    # Even a rejected bad ref does not leave the repo mid-bisect.
    status = subprocess.run(
        ["git", "status", "--porcelain=v1"], cwd=pktcfg_repo, capture_output=True, text=True, check=True
    )
    assert status.stdout.strip() == ""


@pytest.fixture
def hanging_repo(tmp_path: Path) -> tuple[Path, list[str]]:
    """A tiny, throwaway three-commit linear history -- independent of the pktcfg
    toolchain -- used only to prove the *driver's* end-to-end timeout behaviour: a
    check command that hangs at every commit must still let `run_git_bisect` converge
    (on "no good commit found", since every step is a skip) in bounded time, not hang
    the whole session the way a bare `git bisect run` with no per-step timeout would.
    """
    repo = tmp_path / "hang-repo"
    repo.mkdir()

    def run(*args: str) -> None:
        subprocess.run(args, cwd=repo, check=True, capture_output=True, text=True)

    run("git", "init", "-q", "-b", "main")
    run("git", "config", "user.email", "test@example.com")
    run("git", "config", "user.name", "Test")
    shas = []
    for i in range(3):
        (repo / "file.txt").write_text(f"revision {i}\n")
        run("git", "add", "file.txt")
        run("git", "commit", "-q", "-m", f"revision {i}")
        shas.append(subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip())
    return repo, shas


def test_run_git_bisect_a_hung_check_at_every_commit_does_not_hang_the_session(
    hanging_repo: tuple[Path, list[str]],
) -> None:
    import time

    repo, shas = hanging_repo
    good, bad = shas[0], shas[-1]
    hang_check = [sys.executable, "-c", "import time; time.sleep(120)"]

    started = time.monotonic()
    outcome = run_git_bisect(
        mission_id="test-mission-24-timeout",
        repo_path=repo,
        good_commit=good,
        bad_commit=bad,
        check_argv=hang_check,
        timeout_seconds=1.0,
    )
    elapsed = time.monotonic() - started

    # Bounded by the per-step timeout times the (tiny) number of steps, nowhere near
    # the 120s each individual check would otherwise sleep for.
    assert elapsed < 30.0, f"bisect session took {elapsed:.1f}s against 1s/step budgets -- a hang was not bounded"
    # Every step was untestable, so git bisect run itself cannot converge on an
    # answer -- that is the correct, honest outcome for an always-hanging check, not a
    # fabricated good/bad verdict.
    assert not outcome.succeeded
    assert outcome.culprit_commit is None
    assert outcome.steps, "expected at least one step to have been attempted and logged as a skip"
    assert all(step.verdict == "SKIP" for step in outcome.steps)
