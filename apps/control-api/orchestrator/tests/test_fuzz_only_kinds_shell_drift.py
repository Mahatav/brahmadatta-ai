"""#203 (QA-01, found in PR #197's review) — `infrastructure/scripts/run-fuzz-worker.sh`
hardcodes `--kinds FUZZ,MINIMIZE` as a bash string literal, independent of
`orchestrator.queue.FUZZ_ONLY_KINDS`. `DEFAULT_WORKER_KINDS` (`frozenset(JobKind) -
FUZZ_ONLY_KINDS`) recomputes itself automatically whenever `JobKind` grows — proven by
`orchestrator/tests/test_queue_kind_filter.py`'s own
`test_default_worker_kinds_is_every_other_kind_with_nothing_forgotten` — but the shell
script's literal does not, and nothing in the suite checked the two stayed in
agreement.

**Concrete failure mode.** `FUZZ_ONLY_KINDS` gains a third member (a new `JobKind` that
also needs `ContainerJail`) and the developer updates `queue.py` but forgets the shell
script (nothing forces both edits together). `DEFAULT_WORKER_KINDS` correctly excludes
the new kind, so the general `worker` correctly never claims it — but `fuzz-worker`
still only ever claims `{FUZZ, MINIMIZE}` (the stale literal). The new kind's jobs are
claimed by **neither** fleet: no error, no `FAILED` job, no log line — they sit
`QUEUED` forever.

This file parses the shell script's *actual* `--kinds` argument (never hardcoding the
expected value itself — that would just be restating the same fact a second time, the
exact failure mode this test exists to prevent) and asserts it against the real Python
constant it must stay in sync with.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from missions.models import JobKind
from orchestrator import queue

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO_ROOT / "infrastructure" / "scripts" / "run-fuzz-worker.sh"

# The line that actually governs runtime behavior is the `exec` line — the `echo`
# just above it in the script is operator-facing logging and is not what this test
# holds to account (a driftied echo would be a cosmetic bug, not a silent-stall one).
_EXEC_KINDS_RE = re.compile(r"^\s*exec\b.*--kinds\s+(\S+)", re.MULTILINE)


def _parse_shell_fuzz_kinds() -> frozenset[JobKind]:
    """The shell script's real, current `--kinds` value, turned into a
    `frozenset[JobKind]` the same way `missions.management.commands.run_worker.
    parse_kinds` would. Fails loudly (not silently skips) if the script's shape has
    changed enough that this regex no longer finds exactly one `exec ... --kinds ...`
    line — that is itself a signal this test needs a human look, not a green
    checkmark for a property it can no longer actually verify.
    """
    if not SCRIPT_PATH.is_file():
        pytest.fail(f"{SCRIPT_PATH.relative_to(REPO_ROOT)} does not exist.")

    text = SCRIPT_PATH.read_text(encoding="utf-8")
    matches = _EXEC_KINDS_RE.findall(text)
    assert len(matches) == 1, (
        f"expected exactly one `exec ... --kinds <value>` line in "
        f"{SCRIPT_PATH.relative_to(REPO_ROOT)}, found {len(matches)}: {matches!r}. "
        "This test's regex assumes the script execs `manage.py run_worker --kinds "
        "<value>` exactly once — if the script's shape changed, update this parser, "
        "don't just widen the assertion."
    )

    raw_value = matches[0]
    names = [chunk.strip() for chunk in raw_value.split(",") if chunk.strip()]
    assert names, (
        f"{SCRIPT_PATH.relative_to(REPO_ROOT)}'s --kinds value parsed to no names at "
        f"all (raw: {raw_value!r})."
    )

    valid = {member.value: member for member in JobKind}
    unknown = [name for name in names if name.upper() not in valid]
    assert not unknown, (
        f"{SCRIPT_PATH.relative_to(REPO_ROOT)}'s --kinds names unrecognized JobKind "
        f"value(s) {unknown!r} (raw: {raw_value!r}). Valid values: "
        f"{sorted(valid)}."
    )
    return frozenset(valid[name.upper()] for name in names)


# --------------------------------------------------------------------------------------
# Property 1 — the shell script's --kinds and orchestrator.queue.FUZZ_ONLY_KINDS agree
# --------------------------------------------------------------------------------------


def test_run_fuzz_worker_sh_kinds_matches_fuzz_only_kinds() -> None:
    shell_kinds = _parse_shell_fuzz_kinds()

    assert shell_kinds == queue.FUZZ_ONLY_KINDS, (
        f"infrastructure/scripts/run-fuzz-worker.sh execs `--kinds "
        f"{','.join(sorted(k.value for k in shell_kinds))}`, but "
        f"orchestrator.queue.FUZZ_ONLY_KINDS is "
        f"{{{', '.join(sorted(k.value for k in queue.FUZZ_ONLY_KINDS))}}}. These two "
        "must name exactly the same JobKinds (#203) — a drift here means a JobKind "
        "requiring ContainerJail is claimed by neither worker fleet (silently stuck "
        "QUEUED forever) or fuzz-worker claims a kind it has no business running."
    )


# --------------------------------------------------------------------------------------
# Property 2 — the two fleets (fuzz-worker's shell kinds, and the containerized
# worker's DEFAULT_WORKER_KINDS) jointly cover every JobKind, with no gap and no
# overlap
# --------------------------------------------------------------------------------------


def test_the_two_worker_fleets_jointly_cover_every_jobkind_with_no_gap_or_overlap() -> None:
    shell_kinds = _parse_shell_fuzz_kinds()
    all_kinds = frozenset(JobKind)

    union = shell_kinds | queue.DEFAULT_WORKER_KINDS
    missing = all_kinds - union
    assert not missing, (
        "No worker fleet claims: "
        f"{sorted(k.value for k in missing)}. Every JobKind must be claimable by "
        "either fuzz-worker's --kinds or the containerized worker's "
        "DEFAULT_WORKER_KINDS — a JobKind claimed by neither sits QUEUED forever "
        "with no error (#203's exact failure mode)."
    )

    overlap = shell_kinds & queue.DEFAULT_WORKER_KINDS
    assert not overlap, (
        f"Both fleets would claim: {sorted(k.value for k in overlap)}. fuzz-worker's "
        "--kinds and the containerized worker's DEFAULT_WORKER_KINDS must be "
        "disjoint (D-073's fleet split is by JobKind, not by transport, and depends "
        "on that partition being exact)."
    )

    assert union == all_kinds  # restated as an equality for a single clear diagnostic
