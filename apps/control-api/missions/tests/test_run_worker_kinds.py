"""D-073 — `manage.py run_worker --kinds`.

Two things get tested against the real command, not against a private helper in
isolation:

1. `--kinds` parses (case-insensitively, comma-separated) into a concrete
   `frozenset[JobKind]`, and rejects garbage loudly (`CommandError`) rather than
   falling back to "claim everything".
2. **The fail-closed property, end to end.** A `run_worker --once` invocation with no
   `--kinds` flag at all — exactly the compose default for the containerized `worker`
   service — never claims a queued `FUZZ` job, proven by actually running the command
   against a real queued `Job` row and checking it is untouched afterward. The same
   invocation with `--kinds FUZZ,MINIMIZE` does claim it.
"""

from __future__ import annotations

import io
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from contracts.enums import MissionState
from missions.management.commands.run_worker import parse_kinds
from missions.models import Job, JobKind, JobState
from orchestrator import queue
from orchestrator.tests.conftest import NOW, walk_to

# `mission` fixture is discovered via missions/tests/conftest.py, which re-exports it
# from orchestrator/tests/conftest.py — imported directly here (rather than that) it
# reads to a static analyzer as this file's test-function parameters shadowing an
# unused import (ruff F811), even though pytest resolves it correctly either way.

pytestmark = pytest.mark.django_db


# --------------------------------------------------------------------------------------
# parse_kinds
# --------------------------------------------------------------------------------------


def test_parse_kinds_none_resolves_to_default_worker_kinds():
    assert parse_kinds(None) == queue.DEFAULT_WORKER_KINDS


def test_parse_kinds_none_never_includes_fuzz_or_minimize():
    resolved = parse_kinds(None)
    assert JobKind.FUZZ not in resolved
    assert JobKind.MINIMIZE not in resolved


def test_parse_kinds_parses_a_comma_separated_list():
    assert parse_kinds("FUZZ,MINIMIZE") == {JobKind.FUZZ, JobKind.MINIMIZE}


def test_parse_kinds_is_case_insensitive_and_trims_whitespace():
    assert parse_kinds(" fuzz , Minimize ") == {JobKind.FUZZ, JobKind.MINIMIZE}


def test_parse_kinds_single_value():
    assert parse_kinds("BASELINE") == {JobKind.BASELINE}


def test_parse_kinds_rejects_an_unknown_kind():
    with pytest.raises(CommandError, match="unrecognized JobKind"):
        parse_kinds("FUZZ,NOT_A_REAL_KIND")


def test_parse_kinds_rejects_an_empty_string_rather_than_claiming_everything():
    """Passing `--kinds` with nothing after it is operator error, not `None` — it
    must not silently resolve to 'no filter'."""
    with pytest.raises(CommandError, match="named no kinds"):
        parse_kinds("")


def test_parse_kinds_rejects_a_string_of_only_commas():
    with pytest.raises(CommandError, match="named no kinds"):
        parse_kinds(",,,")


# --------------------------------------------------------------------------------------
# The fail-closed property, through the real `run_worker` command and the real queue
# --------------------------------------------------------------------------------------


def _enqueue_fuzz_job(mission) -> Job:
    walk_to(mission, MissionState.STRESS_TEST)
    return Job.objects.create(
        mission=mission,
        kind=JobKind.FUZZ,
        state=JobState.QUEUED,
        run_after=NOW,
        deadline_at=NOW + timedelta(hours=1),
    )


def test_run_worker_with_no_kinds_flag_never_claims_a_queued_fuzz_job(mission, settings):
    """The exact compose default for the containerized `worker` service: no `--kinds`
    flag anywhere in its command line. Must never win a `FUZZ` job it has no docker
    CLI to run."""
    fuzz_job = _enqueue_fuzz_job(mission)

    out = io.StringIO()
    call_command("run_worker", once=True, stdout=out)

    fuzz_job.refresh_from_db()
    assert fuzz_job.state == JobState.QUEUED, (
        "a worker started with no --kinds flag claimed a FUZZ job it cannot run"
    )
    assert "nothing queued" in out.getvalue()


def test_run_worker_with_kinds_fuzz_does_claim_a_queued_fuzz_job(mission):
    """The other half: the bare-metal fuzz-worker invocation
    (`--kinds FUZZ,MINIMIZE`) does claim the same job the default excludes."""
    fuzz_job = _enqueue_fuzz_job(mission)

    out = io.StringIO()
    call_command("run_worker", once=True, kinds="FUZZ,MINIMIZE", stdout=out)

    fuzz_job.refresh_from_db()
    assert fuzz_job.state != JobState.QUEUED, (
        "a worker started with --kinds FUZZ,MINIMIZE failed to claim a queued FUZZ job"
    )
    assert "ran one job" in out.getvalue()


def test_run_worker_with_no_kinds_flag_still_claims_a_baseline_job(mission):
    """Confirms the exclusion is scoped to FUZZ/MINIMIZE only, through the real
    command — the general worker's day-to-day behavior is unchanged."""
    walk_to(mission, MissionState.BASELINE)
    baseline_job = Job.objects.create(
        mission=mission,
        kind=JobKind.BASELINE,
        state=JobState.QUEUED,
        run_after=NOW,
        deadline_at=NOW + timedelta(hours=1),
    )

    out = io.StringIO()
    call_command("run_worker", once=True, stdout=out)

    baseline_job.refresh_from_db()
    assert baseline_job.state != JobState.QUEUED
    assert "ran one job" in out.getvalue()


def test_run_worker_prints_the_resolved_kind_set_at_startup(mission):
    """Operator-visible confirmation of which kinds this process will claim — the
    thing D-073 §5 item 4 asks a cybersecurity reviewer to be able to check without
    reading source: start it and read the first line."""
    out = io.StringIO()
    call_command("run_worker", once=True, stdout=out)
    printed = out.getvalue()
    assert "claiming kinds" in printed
    assert "FUZZ" not in printed.split("claiming kinds", 1)[1].split("\n", 1)[0]


def test_run_worker_with_an_unrecognized_kind_refuses_to_start(mission):
    with pytest.raises(CommandError):
        call_command("run_worker", once=True, kinds="NOT_A_REAL_KIND")
