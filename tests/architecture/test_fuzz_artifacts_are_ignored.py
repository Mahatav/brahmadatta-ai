"""Nothing a fuzz campaign produces may be committable — and the authored demo fixtures
must stay committable.

Both halves matter, and a `.gitignore` change is exactly the kind of edit that gets one
half right and silently breaks the other.

Why the first half. Crash inputs, corpus entries and coverage profiles produced by a
campaign are *derived from the target repository's content*. This repository is private
today and the CEO can open it at any time (D-001). The day that happens, a stray
`crash-8f3a...` committed three weeks earlier is target content published without anyone
deciding to. The previous rules were anchored to the repository root, so a run inside
`demo/repositories/<target>/` wrote files git would happily have staged.

Why the second half. `demo/repositories/pktcfg/corpus/seed-*.bin` and
`demo/repositories/pktcfg/crash/crash-literal-tab.bin` are authored fixtures — the demo
target owner wrote them, they are reviewed, and the D5 gate depends on them being present
in a clean clone. `crash-*` as a broad ignore pattern eats the crash fixture, so the
negations are load-bearing rather than decorative.

Uses `git check-ignore`, so it tests git's actual behaviour rather than re-implementing
gitignore matching, which is not a thing anyone should do twice.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Paths a campaign produces. None of these files exists; check-ignore does not need them to.
MUST_BE_IGNORED = [
    "fuzz-out/crash-8f3a1c",
    "demo/repositories/pktcfg/fuzz-out/crash-8f3a1c",
    "demo/repositories/pktcfg/build/crashes/crash-8f3a1c",
    "workers/fuzzing/crash-deadbeef",
    "workers/fuzzing/leak-deadbeef",
    "workers/fuzzing/timeout-deadbeef",
    "workers/fuzzing/oom-deadbeef",
    "workers/fuzzing/slow-unit-deadbeef",
    "artifacts/run.profraw",
    "apps/control-api/coverage.profdata",
    "reports/semgrep.sarif",
]

# Authored fixtures. These must stay committable.
MUST_NOT_BE_IGNORED = [
    "demo/repositories/pktcfg/corpus/seed-simple.bin",
    "demo/repositories/pktcfg/corpus/seed-bad-magic.bin",
    "demo/repositories/pktcfg/crash/crash-literal-tab.bin",
    "demo/repositories/pktcfg/fuzz/pktcfg_fuzz.c",
    "demo/repositories/pktcfg/src/parser.c",
]


def _is_ignored(rel: str) -> bool:
    # Fixed argv, no shell; `rel` is a literal from the tables above.
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", "--", rel],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    if result.returncode not in (0, 1):
        pytest.fail(f"git check-ignore failed for {rel}: {result.stderr.decode()[:300]}")
    return result.returncode == 0


@pytest.mark.parametrize("rel", MUST_BE_IGNORED)
def test_generated_fuzz_output_is_ignored(rel: str) -> None:
    assert _is_ignored(rel), (
        f"'{rel}' is NOT gitignored. Anything a fuzz campaign produces is derived from a "
        "target repository's content and must not be committable — see the Fuzzing block "
        "in .gitignore."
    )


@pytest.mark.parametrize("rel", MUST_NOT_BE_IGNORED)
def test_authored_demo_fixtures_stay_committable(rel: str) -> None:
    assert not _is_ignored(rel), (
        f"'{rel}' IS gitignored, and must not be. It is an authored, reviewed demo fixture "
        "that a clean clone needs. The broad crash-*/corpus rules in .gitignore need a "
        "matching negation — check the '!demo/repositories/*/...' lines."
    )
