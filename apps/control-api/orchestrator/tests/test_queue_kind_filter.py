"""D-073 — `orchestrator.queue.claim_job`'s `kinds` filter, and the two properties the
worker-fleet split depends on:

1. **Kind-scoping is real.** A worker claiming `{FUZZ}` never receives a `BASELINE`
   job, and a worker claiming `{BASELINE}` never receives a `FUZZ` job — proven
   through the real `claim_job`/`Job` machinery, not asserted about the query in the
   abstract.
2. **The fail-closed default.** `DEFAULT_WORKER_KINDS` (what `manage.py run_worker`
   resolves `--kinds` to when the flag is omitted) never contains `FUZZ` or
   `MINIMIZE`, so the containerized `worker` service — which has no docker CLI and is
   never given one, per D-036 — can never win a job it has no way to run.

No real Postgres row-locking is exercised here (that is `test_queue_claim_locking.py`'s
job, and is orthogonal to this file: the `kind__in` clause is a plain filter, not a
locking primitive, and behaves identically on SQLite and Postgres). This file runs on
the default in-memory SQLite test database.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from contracts.enums import MissionState
from missions.models import Job, JobKind, JobState
from orchestrator import queue
from orchestrator.tests.conftest import NOW, walk_to

pytestmark = pytest.mark.django_db


def _enqueue(mission, kind: JobKind, *, created_at_offset=timedelta(0)) -> Job:
    job = Job.objects.create(
        mission=mission,
        kind=kind,
        state=JobState.QUEUED,
        run_after=NOW,
        deadline_at=NOW + timedelta(hours=1),
    )
    Job.objects.filter(pk=job.pk).update(created_at=NOW + created_at_offset)
    job.refresh_from_db()
    return job


# --------------------------------------------------------------------------------------
# Property 1 — kind-scoping is real, through the real claim_job
# --------------------------------------------------------------------------------------


def test_a_fuzz_only_claimer_never_claims_a_baseline_job(mission):
    walk_to(mission, MissionState.BASELINE)
    baseline_job = _enqueue(mission, JobKind.BASELINE)

    claimed = queue.claim_job("fuzz-worker-1", kinds={JobKind.FUZZ, JobKind.MINIMIZE}, now=NOW)

    assert claimed is None
    baseline_job.refresh_from_db()
    assert baseline_job.state == JobState.QUEUED, "BASELINE job must be untouched"


def test_a_general_worker_using_the_default_kinds_never_claims_a_fuzz_job(mission):
    """The other half of the same property, phrased the way D-073 states it: a worker
    that only ever passes `DEFAULT_WORKER_KINDS` (what `run_worker` resolves an
    omitted `--kinds` to) must never win a `FUZZ` job."""
    walk_to(mission, MissionState.STRESS_TEST)
    fuzz_job = _enqueue(mission, JobKind.FUZZ)

    claimed = queue.claim_job("worker-1", kinds=queue.DEFAULT_WORKER_KINDS, now=NOW)

    assert claimed is None
    fuzz_job.refresh_from_db()
    assert fuzz_job.state == JobState.QUEUED, "FUZZ job must be untouched"


def test_a_general_worker_using_the_default_kinds_never_claims_a_minimize_job(mission):
    walk_to(mission, MissionState.STRESS_TEST)
    minimize_job = _enqueue(mission, JobKind.MINIMIZE)

    claimed = queue.claim_job("worker-1", kinds=queue.DEFAULT_WORKER_KINDS, now=NOW)

    assert claimed is None
    minimize_job.refresh_from_db()
    assert minimize_job.state == JobState.QUEUED


def test_a_fuzz_only_claimer_does_claim_a_queued_fuzz_job(mission):
    walk_to(mission, MissionState.STRESS_TEST)
    fuzz_job = _enqueue(mission, JobKind.FUZZ)

    claimed = queue.claim_job("fuzz-worker-1", kinds={JobKind.FUZZ, JobKind.MINIMIZE}, now=NOW)

    assert claimed is not None and claimed.id == fuzz_job.id
    fuzz_job.refresh_from_db()
    assert fuzz_job.state == JobState.LEASED
    assert fuzz_job.lease_owner == "fuzz-worker-1"


def test_a_general_worker_using_the_default_kinds_still_claims_a_baseline_job(mission):
    """The exclusion is scoped to FUZZ/MINIMIZE only — everything else keeps working
    exactly as before this change, with no compose or CLI change required."""
    walk_to(mission, MissionState.BASELINE)
    baseline_job = _enqueue(mission, JobKind.BASELINE)

    claimed = queue.claim_job("worker-1", kinds=queue.DEFAULT_WORKER_KINDS, now=NOW)

    assert claimed is not None and claimed.id == baseline_job.id


def test_two_disjoint_kind_sets_each_claim_only_their_own_job_from_a_mixed_queue(mission):
    """Both fleets, one table, one tick's worth of queued work: the general worker and
    fuzz-worker each walk away with exactly the job that belongs to them, and neither
    sees the other's."""
    walk_to(mission, MissionState.BASELINE)
    baseline_job = _enqueue(mission, JobKind.BASELINE, created_at_offset=timedelta(seconds=0))

    fuzz_job = Job.objects.create(
        mission=mission,
        kind=JobKind.FUZZ,
        state=JobState.QUEUED,
        run_after=NOW,
        deadline_at=NOW + timedelta(hours=1),
    )
    Job.objects.filter(pk=fuzz_job.pk).update(created_at=NOW + timedelta(seconds=1))
    fuzz_job.refresh_from_db()

    general_claim = queue.claim_job("worker-1", kinds=queue.DEFAULT_WORKER_KINDS, now=NOW)
    fuzz_claim = queue.claim_job(
        "fuzz-worker-1", kinds={JobKind.FUZZ, JobKind.MINIMIZE}, now=NOW
    )

    assert general_claim is not None and general_claim.id == baseline_job.id
    assert fuzz_claim is not None and fuzz_claim.id == fuzz_job.id


def test_kinds_none_preserves_the_pre_d073_behavior_of_claiming_across_every_kind(mission):
    """Backward compatibility for any other caller of `claim_job` that does not pass
    `kinds` at all (the parameter's own default) — this is deliberately still
    permissive; the fail-closed guarantee lives at the `run_worker` call site, which
    always resolves and passes a concrete set. See that command's module docstring."""
    walk_to(mission, MissionState.STRESS_TEST)
    fuzz_job = _enqueue(mission, JobKind.FUZZ)

    claimed = queue.claim_job("worker-1", now=NOW)

    assert claimed is not None and claimed.id == fuzz_job.id


# --------------------------------------------------------------------------------------
# Property 2 — the fail-closed default itself, as a fact about the constant
# --------------------------------------------------------------------------------------


def test_default_worker_kinds_excludes_fuzz_and_minimize():
    assert JobKind.FUZZ not in queue.DEFAULT_WORKER_KINDS
    assert JobKind.MINIMIZE not in queue.DEFAULT_WORKER_KINDS
    # #22, D-144: ANALYZE opens a ContainerJail too (Semgrep) — same D-036 reasoning.
    assert JobKind.ANALYZE not in queue.DEFAULT_WORKER_KINDS


def test_default_worker_kinds_is_every_other_kind_with_nothing_forgotten():
    """Guards the guard: `DEFAULT_WORKER_KINDS` must not silently shrink below "every
    kind except the two fuzz-only ones" — that would strand a legitimate JobKind's
    jobs on no worker at all, with no error, per this constant's own docstring."""
    assert queue.DEFAULT_WORKER_KINDS == frozenset(JobKind) - queue.FUZZ_ONLY_KINDS
    assert queue.DEFAULT_WORKER_KINDS | queue.FUZZ_ONLY_KINDS == frozenset(JobKind)
    assert queue.DEFAULT_WORKER_KINDS & queue.FUZZ_ONLY_KINDS == frozenset()


def test_fuzz_only_kinds_is_exactly_fuzz_minimize_and_analyze():
    """#22, D-144: `JobKind.ANALYZE` opens a `ContainerJail` exactly like `FUZZ`/
    `MINIMIZE` do (`workers.static_analysis.dispatch`, Semgrep in `--network none`) —
    added to the container-runtime-only set. See `orchestrator/queue.py`'s own
    docstring on `FUZZ_ONLY_KINDS` for why the name is kept despite now being
    imprecise."""
    assert queue.FUZZ_ONLY_KINDS == frozenset({JobKind.FUZZ, JobKind.MINIMIZE, JobKind.ANALYZE})
