"""`POST /missions/{id}/patches` — the operator-supplied-candidate entry point into
`PATCH`/`VERIFY` (T-3, D-008).

## What this closes

Three live rehearsals of the #50 D7 gate (D-084, D-085) confirmed there was no
HTTP-reachable path for an operator to supply a patch candidate — `orchestrator.
patch_generate_executor` only ever calls the live self-hosted model
(`MODEL_GATEWAY_MODE=live`), and the gate's own acceptance criteria need **both** a
`Verified` and a `Rejected` verdict produced in one run, which is a poor fit for a
live, non-deterministic model when the project's own kill criterion is about
reproducibility. D-008 already permits an operator-supplied candidate, explicitly
labelled as such; this module is the first HTTP surface that reaches it.

## What this module deliberately does NOT do

It does not re-implement candidate recording, policy evaluation, state transition,
job enqueueing or verification. Every one of those is an existing, already-reviewed
function called here in the order the rest of the pipeline already calls them:

* `orchestrator.candidates.record_patch_candidate` — the same D-046 freeze
  (`Mission.verification_started_at`) and the same real, deterministic
  `orchestrator.patch_policy.evaluate_patch_policy` gate a model-generated candidate
  goes through. `provenance` is hardcoded to `PatchProvenance.OPERATOR_SUPPLIED`
  here — an HTTP caller has no way to claim `MODEL_GENERATED` for a diff it typed
  itself (`PatchCandidate`'s own validator forbids `ModelProvenance` on an
  `OPERATOR_SUPPLIED` row too, so this is enforced twice).
* `orchestrator.transitions.transition` — the *only* writer of `Mission.state`
  (SEC-16). This module never assigns `mission.state` directly.
* `orchestrator.queue.enqueue_job` — the same `Job` table `run_worker`'s claim loop
  and `run_orchestrator`'s `dispatch_terminal_jobs` already drive. The `VERIFY` job
  this enqueues is claimed, executed (`orchestrator.verify_dispatch._verify_executor`,
  real `git apply`/`cmake`/`ctest` inside a `packages.sandbox.Jail`, SEC-47) and
  routed onward (`orchestrator.verify_dispatch._verify_transition_policy`) by the
  exact same, unmodified worker/orchestrator processes a model-generated candidate's
  `VERIFY` job would be. There is no parallel verification path, no shortcut around
  any gate, and no branch anywhere in this module on the diff's provenance once it is
  past `record_patch_candidate`.

## Why the transition into VERIFY happens here rather than through a terminal job

`PATCH_GENERATE`'s own transition policy (`orchestrator.patch_generate_executor.
_patch_generate_transition_policy`) fires off a *terminal `PATCH_GENERATE` Job* —
there is no such job when the candidate came from an operator instead of the model,
so nothing would ever drive `PATCH -> VERIFY` for it otherwise. This module makes
that one call directly, under the same mission-row lock the rest of this flow runs
under, using the same `orchestrator.transitions.transition` every other caller in
this codebase uses. It is the one piece of orchestration logic this module owns; the
rest is composition.

## Multiple operator candidates against the same mission

D-046's freeze is keyed on `Mission.verification_started_at`, set by
`orchestrator.candidates.record_verification` on the *first* `VerificationRecord` a
mission writes — not on `Mission.state == VERIFY`. A mission already in `VERIFY`
(this module's own first call put it there) can still accept a second
operator-supplied candidate as long as no verification has run yet, exactly the
"PATCH produces N candidates, VERIFY produces N jobs" fan-out architecture spec §2.3
describes for the model-generated case. This is what lets a single mission carry the
D6/D7 gate's own `candidate-a` (intended `Verified`) and `candidate-b` (intended
`Rejected`) pair through this identical endpoint, one call each.
"""

from __future__ import annotations

from uuid import UUID

from django.db import transaction
from django.http import Http404
from django.utils import timezone

from authorization.errors import MissionNotFoundError
from contracts.enums import MissionState, PatchPolicyStatus, PatchProvenance
from contracts.errors import InvalidStateTransitionError
from missions.models import Finding, JobKind, Mission, PatchCandidate
from orchestrator import candidates as candidate_writes
from orchestrator import queue, transitions

#: States a mission must be in to accept an operator-supplied candidate: `PATCH` (the
#: point `PATCH_GENERATE` would normally run, per this endpoint's own brief) or
#: `VERIFY` (a second-or-later candidate submitted to a mission this same endpoint
#: already advanced — see the module docstring's "Multiple operator candidates"
#: section). Anything else is not a state a candidate diff is meaningful in: earlier
#: than `PATCH`, there may be no `Finding` yet to patch; later than `VERIFY`, the
#: candidate set has either frozen or the mission has already left the pipeline.
_ACCEPTING_STATES: frozenset[MissionState] = frozenset(
    {MissionState.PATCH, MissionState.VERIFY}
)


def submit_operator_candidate(
    mission_id: UUID,
    *,
    finding_id: UUID,
    diff: str,
    rationale: str,
    trace_id: str,
    now=None,
) -> PatchCandidate:
    """Record an operator-supplied candidate and dispatch it into `VERIFY`.

    Raises `MissionNotFoundError` (404), `Http404` (404, unknown/foreign finding —
    mirrors `orchestrator.evidence_repository`'s own convention for this exact case),
    `InvalidStateTransitionError` (409, mission not in `PATCH`/`VERIFY`) or
    `CandidateSetFrozenError` (409, verification already started — raised by
    `record_patch_candidate` itself). Every one is a `ContractError` (or `Http404`,
    which `api.errors` already maps to the same envelope shape), so the router needs
    no translation of its own.

    The mission row is locked for the whole call — record, transition, enqueue —
    rather than released between steps. `record_patch_candidate` and `transition`
    each take their own `select_for_update` too; on the same connection and the same
    already-open transaction that is a re-entrant lock on a row this call already
    holds, not a second lock, so nesting them here is safe and is what lets two
    operator submissions against the same mission never interleave (D-046's freeze
    check and the `PATCH -> VERIFY` transition both need to see a consistent state).
    """
    now = now or timezone.now()

    with transaction.atomic():
        try:
            mission = Mission.objects.select_for_update().get(pk=mission_id)
        except Mission.DoesNotExist as exc:
            raise MissionNotFoundError(
                "No mission with that id.", details={"mission_id": str(mission_id)}
            ) from exc

        current_state = mission.state_enum
        if current_state not in _ACCEPTING_STATES:
            raise InvalidStateTransitionError(
                f"An operator-supplied candidate cannot be submitted while the "
                f"mission is in {current_state}. It may be submitted once the "
                f"mission reaches PATCH (where PATCH_GENERATE would normally run), "
                f"and until VERIFY starts producing verification records.",
                details={
                    "mission_id": str(mission.id),
                    "current_state": str(current_state),
                    "accepted_states": sorted(str(s) for s in _ACCEPTING_STATES),
                },
            )

        if not Finding.objects.filter(mission_id=mission.id, id=finding_id).exists():
            raise Http404("finding not found")

        candidate = candidate_writes.record_patch_candidate(
            mission.id,
            finding_id=finding_id,
            provenance=PatchProvenance.OPERATOR_SUPPLIED,
            diff=diff,
            trace_id=trace_id,
            rationale=rationale,
            now=now,
        )

        # Advance PATCH -> VERIFY only for a candidate the real policy gate actually
        # accepted. A policy-rejected submission is recorded in full (visible on
        # `GET .../patches`, with its own `PATCH_POLICY_EVALUATED` event already
        # emitted by `record_patch_candidate`) but leaves the mission exactly where
        # it was — in PATCH, still able to accept another submission — rather than
        # advancing it into a VERIFY stage with nothing to verify and no job that
        # will ever move it onward. Mirrors the shape (not the exact target) of
        # `orchestrator.patch_generate_executor._patch_generate_transition_policy`,
        # which also only advances past PATCH once `accepted_count > 0`; this module
        # does not reuse its `HUMAN_REVIEW` fallback, since `TRANSITIONS[HUMAN_REVIEW]`
        # is a dead end (`frozenset()`) that would permanently block a legitimate
        # follow-up submission an operator makes after a rejected first attempt.
        if candidate.policy_status == PatchPolicyStatus.ACCEPTED.value:
            if current_state is MissionState.PATCH:
                transitions.transition(
                    mission.id,
                    MissionState.VERIFY,
                    trace_id=trace_id,
                    reason="operator-supplied candidate submitted",
                    now=now,
                )

            # Real dispatch, not a synchronous verification: this enqueues the exact
            # `Job` row `run_worker`'s claim loop and `run_orchestrator`'s
            # `dispatch_terminal_jobs` already drive for every other kind.
            queue.enqueue_job(
                mission.id,
                JobKind.VERIFY,
                payload={"patch_id": str(candidate.id)},
                now=now,
            )

    return candidate
