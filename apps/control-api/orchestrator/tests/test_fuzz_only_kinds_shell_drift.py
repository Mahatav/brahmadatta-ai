"""#203 (QA-01, found in PR #197's review) — `infrastructure/scripts/run-fuzz-worker.sh`
used to hardcode `--kinds FUZZ,MINIMIZE` as a bash string literal, independent of
`orchestrator.queue.FUZZ_ONLY_KINDS`. `DEFAULT_WORKER_KINDS` (`frozenset(JobKind) -
FUZZ_ONLY_KINDS`) recomputes itself automatically whenever `JobKind` grows — proven by
`orchestrator/tests/test_queue_kind_filter.py`'s own
`test_default_worker_kinds_is_every_other_kind_with_nothing_forgotten` — but the shell
script's old literal did not, and nothing in the suite checked the two stayed in
agreement.

**The real fix (landed together with #199 in the same change).** The script no longer
hardcodes `--kinds` at all: it calls `manage.py print_fuzz_kinds`
(`missions/management/commands/print_fuzz_kinds.py`), which prints `orchestrator.
queue.FUZZ_ONLY_KINDS` back out fresh on every invocation, and passes that value
straight through to `manage.py run_worker --kinds`. See `missions/tests/
test_print_fuzz_kinds_command.py` for the test proving that command is a live
derivation, not a second hardcoded copy (including an adversarial monkeypatch of
`FUZZ_ONLY_KINDS` that a bare literal could never track).

This file's job is different and still worth keeping as its own regression test: prove
the *shell script itself* actually wires that command's output into `run_worker
--kinds`, rather than reintroducing a literal next to it (or forgetting to use it) the
next time someone edits the script by hand. It does this two ways:

1. **Static** — the script's `exec ... --kinds ...` line does not contain a bare,
   parseable list of `JobKind` names (which would mean a literal crept back in), and
   the script does invoke `manage.py print_fuzz_kinds` somewhere before that line.
2. **Runtime** — actually spawn `manage.py print_fuzz_kinds` the same way the script
   does (same interpreter, same settings module) and check its output agrees with
   `orchestrator.queue.FUZZ_ONLY_KINDS` right now, and that the two worker fleets
   (fuzz-worker's derived kinds, the containerized worker's `DEFAULT_WORKER_KINDS`)
   jointly cover every `JobKind` with no gap and no overlap.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from missions.models import JobKind
from orchestrator import queue

REPO_ROOT = Path(__file__).resolve().parents[4]
CONTROL_API = REPO_ROOT / "apps" / "control-api"
SCRIPT_PATH = REPO_ROOT / "infrastructure" / "scripts" / "run-fuzz-worker.sh"

_EXEC_KINDS_RE = re.compile(r"^\s*exec\b.*--kinds\s+(\S+)", re.MULTILINE)


def _script_text() -> str:
    if not SCRIPT_PATH.is_file():
        pytest.fail(f"{SCRIPT_PATH.relative_to(REPO_ROOT)} does not exist.")
    return SCRIPT_PATH.read_text(encoding="utf-8")


def _run_print_fuzz_kinds() -> frozenset[JobKind]:
    """Spawns `manage.py print_fuzz_kinds` for real -- the same command `run-fuzz-
    worker.sh` execs -- rather than importing `queue.FUZZ_ONLY_KINDS` a second time in
    this test process, so this genuinely proves what a fresh process invocation
    prints, not just what the constant equals in the already-imported test process."""
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings.test"),
        "DJANGO_SECRET_KEY": os.environ.get(
            "DJANGO_SECRET_KEY", "fuzz-worker-shell-drift-test-not-a-real-secret-01"
        ),
        "DATABASE_URL": os.environ.get("DATABASE_URL", "sqlite://:memory:"),
    }
    result = subprocess.run(
        [sys.executable, "manage.py", "print_fuzz_kinds"],
        cwd=CONTROL_API,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"'manage.py print_fuzz_kinds' failed (exit {result.returncode}):\n"
        f"{result.stderr.strip()[-1000:]}"
    )
    raw = result.stdout.strip()
    assert raw, "'manage.py print_fuzz_kinds' printed nothing"
    valid = {member.value: member for member in JobKind}
    names = [chunk.strip() for chunk in raw.split(",") if chunk.strip()]
    unknown = [name for name in names if name.upper() not in valid]
    assert not unknown, f"unrecognized JobKind value(s) in print_fuzz_kinds output: {unknown!r}"
    return frozenset(valid[name.upper()] for name in names)


# --------------------------------------------------------------------------------------
# Static — the script wires the derived command in, not a hardcoded literal
# --------------------------------------------------------------------------------------


def test_run_fuzz_worker_sh_does_not_hardcode_a_kinds_literal() -> None:
    text = _script_text()
    matches = _EXEC_KINDS_RE.findall(text)
    assert len(matches) == 1, (
        f"expected exactly one `exec ... --kinds <value>` line in "
        f"{SCRIPT_PATH.relative_to(REPO_ROOT)}, found {len(matches)}: {matches!r}."
    )

    raw_value = matches[0]
    valid = {member.value for member in JobKind}
    # A regression back to a hardcoded literal looks like `--kinds FUZZ,MINIMIZE` --
    # every comma-separated chunk resolves to a real JobKind name. The derived form
    # (`--kinds "${FUZZ_KINDS}"`) does not, because it is a shell variable reference,
    # not kind names.
    chunks = {chunk.strip().strip('"').strip("'") for chunk in raw_value.split(",")}
    assert not chunks <= valid, (
        f"{SCRIPT_PATH.relative_to(REPO_ROOT)}'s `exec ... --kinds {raw_value}` looks "
        "like a hardcoded literal JobKind list, not a derived shell variable (#203) -- "
        "the whole point of this fix is that --kinds must be computed from "
        "orchestrator.queue.FUZZ_ONLY_KINDS at invocation time (e.g. via `manage.py "
        "print_fuzz_kinds`), never restated by hand here."
    )


def test_run_fuzz_worker_sh_calls_print_fuzz_kinds_before_its_exec_line() -> None:
    text = _script_text()
    assert "print_fuzz_kinds" in text, (
        f"{SCRIPT_PATH.relative_to(REPO_ROOT)} must derive its --kinds value by "
        "calling `manage.py print_fuzz_kinds` (#203) -- no reference to that command "
        "found in the script."
    )
    derive_pos = text.index("print_fuzz_kinds")
    exec_match = _EXEC_KINDS_RE.search(text)
    assert exec_match is not None
    assert derive_pos < exec_match.start(), (
        "print_fuzz_kinds must be called *before* the exec line that consumes its "
        "output."
    )


# --------------------------------------------------------------------------------------
# Runtime — the actually-derived value agrees with FUZZ_ONLY_KINDS, and the two worker
# fleets jointly cover every JobKind, with no gap and no overlap
# --------------------------------------------------------------------------------------


def test_run_fuzz_worker_sh_derived_kinds_matches_fuzz_only_kinds() -> None:
    derived_kinds = _run_print_fuzz_kinds()

    assert derived_kinds == queue.FUZZ_ONLY_KINDS, (
        f"'manage.py print_fuzz_kinds' (what infrastructure/scripts/run-fuzz-worker.sh "
        f"execs `--kinds` from) printed "
        f"{{{', '.join(sorted(k.value for k in derived_kinds))}}}, but "
        f"orchestrator.queue.FUZZ_ONLY_KINDS is "
        f"{{{', '.join(sorted(k.value for k in queue.FUZZ_ONLY_KINDS))}}}. These two "
        "must name exactly the same JobKinds (#203)."
    )


def test_the_two_worker_fleets_jointly_cover_every_jobkind_with_no_gap_or_overlap() -> None:
    derived_kinds = _run_print_fuzz_kinds()
    all_kinds = frozenset(JobKind)

    union = derived_kinds | queue.DEFAULT_WORKER_KINDS
    missing = all_kinds - union
    assert not missing, (
        "No worker fleet claims: "
        f"{sorted(k.value for k in missing)}. Every JobKind must be claimable by "
        "either fuzz-worker's derived --kinds or the containerized worker's "
        "DEFAULT_WORKER_KINDS -- a JobKind claimed by neither sits QUEUED forever "
        "with no error (#203's exact failure mode)."
    )

    overlap = derived_kinds & queue.DEFAULT_WORKER_KINDS
    assert not overlap, (
        f"Both fleets would claim: {sorted(k.value for k in overlap)}. fuzz-worker's "
        "--kinds and the containerized worker's DEFAULT_WORKER_KINDS must be "
        "disjoint (D-073's fleet split is by JobKind, not by transport, and depends "
        "on that partition being exact)."
    )

    assert union == all_kinds  # restated as an equality for a single clear diagnostic
