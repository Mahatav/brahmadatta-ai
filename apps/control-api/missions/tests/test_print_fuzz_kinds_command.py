"""`manage.py print_fuzz_kinds` (#203, QA-01) — the command `infrastructure/scripts/
run-fuzz-worker.sh` calls to build its `--kinds` argument, instead of restating
`orchestrator.queue.FUZZ_ONLY_KINDS` as a second, hand-synced bash literal.

Two properties:

1. Its output, parsed back into `JobKind`s, equals `orchestrator.queue.
   FUZZ_ONLY_KINDS` right now.
2. **It is a live derivation, not a coincidentally-matching hardcoded copy.** This is
   the property #203 actually cares about — today's values agreeing is necessary but
   not sufficient; a second hardcoded `"FUZZ,MINIMIZE"` inside the command itself would
   pass property 1 and still drift the moment `FUZZ_ONLY_KINDS` changes. Proven by
   monkeypatching `orchestrator.queue.FUZZ_ONLY_KINDS` to include a real `JobKind` that
   is *not* in it today (`SANITIZER_BUILD`) and confirming the command's output moves
   with it. If this command instead held its own literal, this test would fail.
"""

from __future__ import annotations

import io

import pytest
from django.core.management import call_command

from missions.models import JobKind
from orchestrator import queue


def _run() -> frozenset[JobKind]:
    out = io.StringIO()
    call_command("print_fuzz_kinds", stdout=out)
    printed = out.getvalue().strip()
    assert printed, "print_fuzz_kinds must print exactly one non-empty line"
    return frozenset(JobKind(name) for name in printed.split(","))


def test_print_fuzz_kinds_matches_fuzz_only_kinds_today() -> None:
    assert _run() == queue.FUZZ_ONLY_KINDS


def test_print_fuzz_kinds_prints_nothing_but_the_one_line() -> None:
    out = io.StringIO()
    call_command("print_fuzz_kinds", stdout=out)
    # Exactly one line, no trailing blank lines, no progress/log chatter -- a caller
    # capturing this with `$(...)` must get exactly the comma-joined kind list back.
    assert out.getvalue().rstrip("\n").count("\n") == 0


def test_print_fuzz_kinds_is_a_live_derivation_not_a_second_hardcoded_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extra = JobKind.SANITIZER_BUILD
    assert extra not in queue.FUZZ_ONLY_KINDS, (
        "this test needs a real JobKind that is genuinely outside FUZZ_ONLY_KINDS "
        "today to prove anything -- if SANITIZER_BUILD ever moves into "
        "FUZZ_ONLY_KINDS, swap this constant for a different currently-excluded kind"
    )
    patched = queue.FUZZ_ONLY_KINDS | {extra}
    monkeypatch.setattr(queue, "FUZZ_ONLY_KINDS", patched)

    assert _run() == patched, (
        "print_fuzz_kinds did not track a monkeypatched orchestrator.queue."
        "FUZZ_ONLY_KINDS -- it must read the module attribute live at call time "
        "(`queue.FUZZ_ONLY_KINDS` inside handle()), not bind a local alias at import "
        "time or hold its own separately-hardcoded value (#203's exact failure mode, "
        "one level removed)."
    )
