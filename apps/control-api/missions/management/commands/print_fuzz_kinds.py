"""`manage.py print_fuzz_kinds` — the single source of truth
`infrastructure/scripts/run-fuzz-worker.sh` reads to build its `--kinds` argument,
instead of restating `orchestrator.queue.FUZZ_ONLY_KINDS` as a second, hand-synced
bash string literal (#203, QA-01, found in PR #197's review).

Prints exactly one line: `orchestrator.queue.FUZZ_ONLY_KINDS`'s current members, as a
comma-joined, sorted list of `JobKind` values (e.g. `FUZZ,MINIMIZE`) — nothing else,
so a caller can capture stdout directly (`$(python manage.py print_fuzz_kinds)`) with
no parsing beyond a split on `,`. Any other output on stdout (a progress message, a
deprecation warning) would corrupt that capture, so this command does nothing but
write the one line.

Deliberately reads `queue.FUZZ_ONLY_KINDS` through the module (`from orchestrator
import queue`, then `queue.FUZZ_ONLY_KINDS` inside `handle()`) rather than
`from orchestrator.queue import FUZZ_ONLY_KINDS` at import time — the latter would
bind a local alias once at import and no longer be a live read of the module
attribute, which is exactly the "second copy of the same fact" shape #203 exists to
eliminate. See `orchestrator/tests/test_fuzz_only_kinds_shell_drift.py` (this
command's output vs. `run-fuzz-worker.sh`'s actual `--kinds` argument) and
`missions/tests/test_print_fuzz_kinds_command.py` (the adversarial test proving this
command is a live derivation, not a coincidentally-matching hardcoded value).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from orchestrator import queue


class Command(BaseCommand):
    help = (
        "Print orchestrator.queue.FUZZ_ONLY_KINDS as a comma-joined, sorted list of "
        "JobKind values (e.g. FUZZ,MINIMIZE) -- the single source of truth "
        "infrastructure/scripts/run-fuzz-worker.sh derives its --kinds argument from "
        "(#203). Emits nothing but that one line."
    )

    def handle(self, *args, **options) -> None:
        self.stdout.write(",".join(sorted(kind.value for kind in queue.FUZZ_ONLY_KINDS)))
