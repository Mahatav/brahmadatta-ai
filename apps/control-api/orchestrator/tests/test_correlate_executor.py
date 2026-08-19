"""`JobKind.CORRELATE` executor (#168, T3) — the two signals it reads, and the
priority between them. See `orchestrator/correlate_executor.py`'s own module
docstring for the full reasoning; this file proves it.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from django.db import IntegrityError

from contracts.enums import FindingCategory
from missions.models import Finding, Job, JobKind, JobState, Mission
from orchestrator.executors import ExecutorContext, JobOutcome, executor_for
from orchestrator.tests.conftest import NOW, TRACE

pytestmark = pytest.mark.django_db(transaction=True)


def _ctx(mission: Mission) -> ExecutorContext:
    return ExecutorContext(
        job=Job(mission=mission, kind=JobKind.CORRELATE, state=JobState.RUNNING),
        mission=mission,
        source_dir=Path("."),
        workspace_root=Path("."),
        trace_id=TRACE,
        cancel_requested=lambda: False,
    )


def _terminal_fuzz_job(
    mission: Mission, *, crashes_found: object, state=JobState.SUCCEEDED
) -> Job:
    """`crashes_found` is typed `object`, not `int`: several tests below deliberately
    write a malformed value here (a string, `None`, a list, a dict) to exercise
    `_correlate_executor`'s `int()`-cast error handling (SEC-44) -- `Job.result` is a
    JSON field with no schema of its own to stop that at write time, which is exactly
    the untrusted-shape scenario these tests exist to cover."""
    return Job.objects.create(
        mission=mission,
        kind=JobKind.FUZZ,
        state=state,
        result={"crashes_found": crashes_found},
        run_after=NOW,
        deadline_at=NOW + timedelta(hours=1),
        finished_at=NOW,
    )


def test_reports_nothing_to_correlate_when_no_finding_and_no_fuzz_job(mission):
    """The common no-signal case: nothing recorded, and no FUZZ job to fall back to
    (e.g. a mission driven straight into CORRELATE by a test's own `walk_to`)."""
    result = executor_for(JobKind.CORRELATE)(_ctx(mission))
    assert result.outcome is JobOutcome.SUCCEEDED
    assert result.result["correlated"] is False
    assert result.result["source"] == "no_signal"
    assert result.result["finding_count"] == 0


def test_reports_nothing_to_correlate_when_fuzz_job_reports_zero_crashes(mission):
    _terminal_fuzz_job(mission, crashes_found=0)
    result = executor_for(JobKind.CORRELATE)(_ctx(mission))
    assert result.outcome is JobOutcome.SUCCEEDED
    assert result.result["correlated"] is False
    assert result.result["source"] == "no_signal"
    assert result.result["crashes_found"] == 0


def test_falls_back_to_raw_fuzz_crashes_found_when_no_finding_rows_exist(mission):
    """T2 has not landed `record_finding` yet — see this module's docstring. The
    fallback signal is the same `crashes_found` key `_fuzz_transition_policy` already
    treats as the provisional FUZZ/CORRELATE contract."""
    _terminal_fuzz_job(mission, crashes_found=3)
    result = executor_for(JobKind.CORRELATE)(_ctx(mission))
    assert result.outcome is JobOutcome.SUCCEEDED
    assert result.result["correlated"] is True
    assert result.result["source"] == "fuzz_result_crashes_found"
    assert result.result["crashes_found"] == 3
    assert result.result["finding_ids"] == []


def test_uses_finding_rows_when_present(mission, finding: Finding):
    result = executor_for(JobKind.CORRELATE)(_ctx(mission))
    assert result.outcome is JobOutcome.SUCCEEDED
    assert result.result["correlated"] is True
    assert result.result["source"] == "finding_rows"
    assert result.result["finding_count"] == 1
    assert result.result["finding_ids"] == [str(finding.id)]


def test_finding_rows_take_priority_over_a_conflicting_raw_crash_count(mission, finding: Finding):
    """A `Finding` row is the authoritative signal (it's what `PATCH_GENERATE` actually
    needs a `finding_id` for) — present even alongside a zero-crash FUZZ result, it
    still wins."""
    _terminal_fuzz_job(mission, crashes_found=0)
    result = executor_for(JobKind.CORRELATE)(_ctx(mission))
    assert result.result["correlated"] is True
    assert result.result["source"] == "finding_rows"


def test_finding_rows_win_even_when_fuzz_job_also_reports_a_positive_crash_count(
    mission, finding: Finding
):
    """The scenario `test_finding_rows_take_priority_over_a_conflicting_raw_crash_count`
    does not actually cover: that test's fallback signal is `crashes_found=0`, which
    would independently produce `correlated: False` even without a `Finding` present,
    so it never proves priority against a *conflicting affirmative* signal. Here both
    signals independently say "something to bind" -- `Finding` must still be the one
    that wins, and the `Finding`-branch result must not leak/merge in the FUZZ job's
    own `crashes_found` count (that key belongs only to the `fuzz_result_crashes_found`
    branch, per `_correlate_executor`'s two disjoint result shapes)."""
    _terminal_fuzz_job(mission, crashes_found=9)
    result = executor_for(JobKind.CORRELATE)(_ctx(mission))
    assert result.result["correlated"] is True
    assert result.result["source"] == "finding_rows"
    assert result.result["finding_count"] == 1
    assert result.result["finding_ids"] == [str(finding.id)]
    assert "crashes_found" not in result.result


def test_a_second_terminal_fuzz_job_for_the_same_mission_is_now_database_impossible(mission):
    """SEC-42 (#176) / D-086: this is the reworked version of what used to be
    `test_only_the_latest_terminal_fuzz_job_by_finished_at_is_used` -- before
    `job_mission_kind_unique` existed, a mission really could accumulate more than
    one terminal `FUZZ` job for the reason SEC-42's own review demonstrated live (two
    racing `ensure_jobs_enqueued()` calls), and `_latest_terminal_fuzz_job`
    (`orchestrator/correlate_executor.py`) picking the row with the latest
    `finished_at` -- not insertion order -- was a real, exercised code path, not
    speculative defense.

    That row-level scenario is now refused by the database itself: a second `Job`
    row for `(mission, FUZZ)` cannot be created at all once the first exists, so this
    test instead proves *that*, directly, rather than continuing to construct a
    now-illegal fixture. `_latest_terminal_fuzz_job`'s own `.order_by("-finished_at")`
    is left exactly as backend-developer wrote it -- this task's own scope is the
    schema, not `correlate_executor.py` -- but it is worth backend-developer's own
    note that this ordering is now unreachable defense-in-depth for `FUZZ`
    specifically, not a live path, the moment this constraint lands.
    """
    _terminal_fuzz_job(mission, crashes_found=0)

    with pytest.raises(IntegrityError):
        _terminal_fuzz_job(mission, crashes_found=7)

    assert Job.objects.filter(mission=mission, kind=JobKind.FUZZ).count() == 1


@pytest.mark.parametrize(
    "malformed_value",
    ["not-a-number", "3.7", [1, 2, 3], {"nested": "dict"}],
)
def test_a_malformed_crashes_found_degrades_to_no_signal_instead_of_raising(
    mission, malformed_value
):
    """SEC-44 (cybersecurity review of PR #186): a non-integer `crashes_found` used to
    raise `ValueError`/`TypeError` uncaught inside the executor, which `run_worker`'s
    outer handler then reported as a `FAILED` job -- routing the whole mission to
    `Mission.FAILED` instead of the graceful `HUMAN_REVIEW` outcome every other
    malformed-input case already produces. The fix (`correlate_executor.py`'s
    `try/except (TypeError, ValueError)` around the `int()` cast) shipped with no
    regression test of its own; this closes that gap. `"3.7"` (a string, not a float)
    is included because `int("3.7")` raises `ValueError` even though `int(3.7)` (an
    actual float) would truncate cleanly to `3` with no exception at all -- the exact
    kind of "looks numeric, isn't `int()`-castable *as a string*" value a campaign-
    output JSON parser could plausibly emit for a field it expected to be an int.
    """
    _terminal_fuzz_job(mission, crashes_found=malformed_value)
    result = executor_for(JobKind.CORRELATE)(_ctx(mission))
    assert result.outcome is JobOutcome.SUCCEEDED
    assert result.result["correlated"] is False
    assert result.result["source"] == "no_signal"
    assert result.result["crashes_found"] == 0


def test_a_none_crashes_found_degrades_to_no_signal(mission):
    """`None` never reaches the `int()` cast at all -- `raw_crashes_found or 0`
    short-circuits first, the same `or 0` guard that already handles a missing key.
    Named as its own case because it is a real, plausible value for a campaign-output
    parser to emit (an explicit JSON `null`), not just a missing key."""
    _terminal_fuzz_job(mission, crashes_found=None)
    result = executor_for(JobKind.CORRELATE)(_ctx(mission))
    assert result.result["correlated"] is False
    assert result.result["source"] == "no_signal"
    assert result.result["crashes_found"] == 0


def test_a_negative_crashes_found_degrades_to_no_signal(mission):
    """Claimed handled in cybersecurity's PR #186 review ("negative int -> int(-5)
    succeeds, -5 > 0 is False -> correlated: False") but never captured as a named,
    persistent regression test -- only as a one-off manual repro in the review
    comment. Closing that gap here. `result["crashes_found"]` echoes the actual
    computed (negative) count rather than clamping it -- the same "report what was
    computed" behavior the zero-crash case already exercises -- so the mission-routing
    assertion is on `correlated`/`source`, the two keys the transition policy actually
    reads (`_correlate_transition_policy` only ever checks `result["correlated"]`)."""
    _terminal_fuzz_job(mission, crashes_found=-5)
    result = executor_for(JobKind.CORRELATE)(_ctx(mission))
    assert result.result["correlated"] is False
    assert result.result["source"] == "no_signal"
    assert result.result["crashes_found"] == -5


def test_does_not_leak_another_missions_finding_rows(mission):
    """SEC-15's own discipline, applied here: a `Finding` belonging to a different
    mission must never make this mission's CORRELATE decision for it."""
    other = Mission.objects.create(
        name="another mission",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter="C_CMAKE_CTEST",
        policy={},
    )
    Finding.objects.create(
        mission=other,
        category=FindingCategory.HEAP_BUFFER_OVERFLOW.value,
        severity="HIGH",
        tool="ADDRESS_SANITIZER",
        discovery_method="FUZZING_CAMPAIGN",
        file_path="src/decode.c",
        line=74,
        fingerprint="other-missions-finding",
        reproducible=True,
        title="a different mission's finding entirely",
        detected_at=NOW,
    )

    result = executor_for(JobKind.CORRELATE)(_ctx(mission))

    assert result.result["correlated"] is False
    assert result.result["source"] == "no_signal"
    assert result.result["finding_count"] == 0
