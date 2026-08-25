"""Enumerations. Exhaustive by construction — nothing in the API accepts a free
string where one of these applies.

`MissionState` is the machine state, owned by the orchestrator.
`MissionPosture` is what the Brahmadatta Core displays, derived from the state; the
UI never invents its own mapping (`docs/02-design/00-ui-design-direction.md` line 57).
"""

from __future__ import annotations

from enum import StrEnum


class MissionState(StrEnum):
    """Persistent mission state machine.

    Extends the sequence in `docs/03-technical/16-system-architecture-document.md`
    §"Mission state machine" with the states the nine-step demo needs and the
    document only implies:

    * `AUTHORIZED` — the authorization record exists and is active. Nothing may run
      before this state; see `contracts.state_machine`.
    * `EXPORTING`  — evidence bundle being written. The mission is not `VERIFIED`
      until the evidence exists (P0-12).
    * `PAUSED` / `CANCELLING` — operator controls in the API specification that the
      document's state list omitted.
    """

    CREATED = "CREATED"
    AUTHORIZED = "AUTHORIZED"
    SNAPSHOTTED = "SNAPSHOTTED"
    VALIDATING = "VALIDATING"
    BASELINE = "BASELINE"
    TRIAGE = "TRIAGE"
    STRESS_TEST = "STRESS_TEST"
    CORRELATE = "CORRELATE"
    PATCH = "PATCH"
    VERIFY = "VERIFY"
    EXPORTING = "EXPORTING"
    PAUSED = "PAUSED"
    CANCELLING = "CANCELLING"
    # Terminal
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_STATES: frozenset[MissionState] = frozenset(
    {
        MissionState.VERIFIED,
        MissionState.REJECTED,
        MissionState.HUMAN_REVIEW,
        MissionState.FAILED,
        MissionState.CANCELLED,
    }
)


class MissionPosture(StrEnum):
    """What the Core displays. Derived from `MissionState`, never set directly.

    `CANCELLED` extends the list in `docs/02-design/00-ui-design-direction.md`, which
    names eight postures and has no home for a deliberately-cancelled mission. Folding
    it into `FAILED` would show a red alert ring on the most visible element in the
    product for an operator action that worked exactly as intended.
    """

    PROTECTED = "PROTECTED"
    INVESTIGATING = "INVESTIGATING"
    VULNERABILITY_CONFIRMED = "VULNERABILITY_CONFIRMED"
    PATCHING = "PATCHING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class MissionStage(StrEnum):
    """The nine workflow steps: authorize → ingest → baseline → analyze →
    stress-test → correlate → patch → verify → export evidence.

    Note the ordering of `ANALYZE`/`STRESS_TEST`/`CORRELATE`. The workflow sentence
    repeated across the pack reads "analyze → correlate → stress-test"; the
    architecture document's state machine reads `TRIAGE → STRESS_TEST → CORRELATE`.
    The state machine ordering is used, because correlation joins static and dynamic
    evidence and therefore cannot precede the dynamic run that produces it.
    """

    AUTHORIZE = "AUTHORIZE"
    INGEST = "INGEST"
    BASELINE = "BASELINE"
    ANALYZE = "ANALYZE"
    STRESS_TEST = "STRESS_TEST"
    CORRELATE = "CORRELATE"
    PATCH = "PATCH"
    VERIFY = "VERIFY"
    EXPORT_EVIDENCE = "EXPORT_EVIDENCE"


class EventType(StrEnum):
    """Every event the UI can receive. Adding a member is a contract change."""

    MISSION_CREATED = "MISSION_CREATED"
    MISSION_AUTHORIZED = "MISSION_AUTHORIZED"
    SNAPSHOT_RECORDED = "SNAPSHOT_RECORDED"
    PREFLIGHT_COMPLETED = "PREFLIGHT_COMPLETED"
    STATE_CHANGED = "STATE_CHANGED"
    STAGE_STARTED = "STAGE_STARTED"
    STAGE_PROGRESS = "STAGE_PROGRESS"
    STAGE_COMPLETED = "STAGE_COMPLETED"
    BASELINE_RECORDED = "BASELINE_RECORDED"
    #: The D3 kill criterion is written as the literal string `BASELINE_PASSED`
    #: (docs/09-company/01-vision-and-p0-cut.md §4). It is an *outcome*, not a mission
    #: state — the mission state is `BASELINE` while the stage runs, then `TRIAGE`.
    #: These two event types are the unambiguous observable signal, so a gate check on
    #: 2026-08-09 has an exact string to look for and cannot fail on a misreading.
    BASELINE_PASSED = "BASELINE_PASSED"
    BASELINE_FAILED = "BASELINE_FAILED"
    FINDING_RECORDED = "FINDING_RECORDED"
    REPRODUCER_RECORDED = "REPRODUCER_RECORDED"
    PATCH_CANDIDATE_RECORDED = "PATCH_CANDIDATE_RECORDED"
    PATCH_POLICY_EVALUATED = "PATCH_POLICY_EVALUATED"
    VERIFICATION_RECORDED = "VERIFICATION_RECORDED"
    #: One per mission, carrying every candidate verdict — see MissionVerdictPayload.
    MISSION_VERDICT_RECORDED = "MISSION_VERDICT_RECORDED"
    EVIDENCE_EXPORTED = "EVIDENCE_EXPORTED"
    RESOURCE_USAGE_SAMPLED = "RESOURCE_USAGE_SAMPLED"
    TEARDOWN_CONFIRMED = "TEARDOWN_CONFIRMED"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    MISSION_PAUSED = "MISSION_PAUSED"
    MISSION_RESUMED = "MISSION_RESUMED"
    MISSION_CANCELLED = "MISSION_CANCELLED"
    MISSION_FAILED = "MISSION_FAILED"
    LOG = "LOG"


class EventStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class Severity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Verdict(StrEnum):
    """The only three outcomes a verification run can produce (P0-11)."""

    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


class GateStatus(StrEnum):
    """Outcome of one deterministic gate. There is no `LIKELY` and no score."""

    PASS = "PASS"
    FAIL = "FAIL"
    NOT_RUN = "NOT_RUN"
    ERROR = "ERROR"


class GateName(StrEnum):
    COMPILE = "COMPILE"
    REPRODUCER_ELIMINATED = "REPRODUCER_ELIMINATED"
    REGRESSION_PRESERVED = "REGRESSION_PRESERVED"
    STATIC_DELTA = "STATIC_DELTA"
    RENEWED_FUZZING = "RENEWED_FUZZING"


class PatchProvenance(StrEnum):
    """Where a candidate came from. Never inflated: an operator-authored candidate
    is labelled as one in the UI and in the evidence bundle (P0 cut §3, D-008).
    """

    MODEL_GENERATED = "MODEL_GENERATED"
    OPERATOR_SUPPLIED = "OPERATOR_SUPPLIED"


class PatchPolicyStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED_PATH_NOT_ALLOWED = "REJECTED_PATH_NOT_ALLOWED"
    REJECTED_TOO_MANY_FILES = "REJECTED_TOO_MANY_FILES"
    REJECTED_TOO_MANY_LINES = "REJECTED_TOO_MANY_LINES"
    REJECTED_MALFORMED_DIFF = "REJECTED_MALFORMED_DIFF"


class FindingCategory(StrEnum):
    HEAP_BUFFER_OVERFLOW = "HEAP_BUFFER_OVERFLOW"
    STACK_BUFFER_OVERFLOW = "STACK_BUFFER_OVERFLOW"
    GLOBAL_BUFFER_OVERFLOW = "GLOBAL_BUFFER_OVERFLOW"
    USE_AFTER_FREE = "USE_AFTER_FREE"
    DOUBLE_FREE = "DOUBLE_FREE"
    MEMORY_LEAK = "MEMORY_LEAK"
    UNDEFINED_BEHAVIOUR = "UNDEFINED_BEHAVIOUR"
    INTEGER_OVERFLOW = "INTEGER_OVERFLOW"
    NULL_DEREFERENCE = "NULL_DEREFERENCE"
    ASSERTION_FAILURE = "ASSERTION_FAILURE"
    TIMEOUT = "TIMEOUT"
    OTHER = "OTHER"


class AnalyzerTool(StrEnum):
    """Tools that may produce a finding. Semgrep is CUT for the seven-day build
    (P1-2) and is absent deliberately — adding it back is a scope decision.
    """

    COMPILER_DIAGNOSTIC = "COMPILER_DIAGNOSTIC"
    ADDRESS_SANITIZER = "ADDRESS_SANITIZER"
    UNDEFINED_BEHAVIOUR_SANITIZER = "UNDEFINED_BEHAVIOUR_SANITIZER"
    LIBFUZZER = "LIBFUZZER"
    CTEST = "CTEST"


class LanguageAdapter(StrEnum):
    C_CMAKE_CTEST = "C_CMAKE_CTEST"
    C_MAKE_CTEST = "C_MAKE_CTEST"


# --- substitution provenance ---------------------------------------------------
#
# The CEO approved fallbacks for D1–D7 (issues #81, #82, #83). A fallback is
# legitimate; presenting one as the primary path is not. These enums exist so a
# substituted path is *inexpressible* as the primary one — same rule as D-008 on
# operator-supplied patches. Each is a required field somewhere, so "we'll remember to
# set the flag" is not a thing that can be forgotten at 2am on the day.


class DiscoveryMethod(StrEnum):
    """How a finding came to exist. Required on every finding; no default.

    `FUZZING_CAMPAIGN` is the strongest claim and the only one that supports "our
    fuzzer discovered it". The other two are honest and weaker: the seven-day plan
    already names direct harnessing as the *starting* position rather than the
    fallback, and #83 adds reproducer replay under that.

    `STATIC_ANALYSIS` (#23, D-144) is a fourth, independent claim: a finding surfaced
    by reading source text (or, for #23 specifically, a compiler's own diagnostic
    output from a real build) with no execution and no crash involved — never
    conflated with `FUZZING_CAMPAIGN`, which specifically claims a dynamic run found
    it. Named and valued identically to what #22 (Semgrep integration, CUT-milestone,
    also authorized by D-144) independently adds for the same reason, on its own
    not-yet-merged branch as of this writing — see `workers/baseline/dispatch.py`'s
    module docstring for the coordination note on that overlap. If #22 lands first,
    this becomes a trivial duplicate-member merge conflict to resolve by keeping one
    copy; the string value either author picked is identical, so no downstream data is
    at risk either way.
    """

    FUZZING_CAMPAIGN = "FUZZING_CAMPAIGN"
    DIRECT_HARNESS = "DIRECT_HARNESS"
    REPLAYED_REPRODUCER = "REPLAYED_REPRODUCER"
    STATIC_ANALYSIS = "STATIC_ANALYSIS"


class EvidenceSource(StrEnum):
    """Whether a gate result came from running a tool or from a stored artifact.

    A gate may only PASS on `TOOL_EXECUTION`. A replayed artifact can be recorded and
    displayed; it cannot pass a gate.
    """

    TOOL_EXECUTION = "TOOL_EXECUTION"
    REPLAYED_ARTIFACT = "REPLAYED_ARTIFACT"


class InferenceMode(StrEnum):
    """Whether a model response was generated live or replayed from a transcript.

    Required on every `ModelProvenance`; no default, by the same reasoning as
    `DiscoveryMethod` and `FuzzingMode` (D-049). D-015 cut the rented GPU, so the D5
    gate rests on a quantized CPU-served model and a replay-mode gateway is the
    approved fallback. Serving a captured response is legitimate; letting silence
    claim it was generated live is not.
    """

    LIVE_INFERENCE = "LIVE_INFERENCE"
    REPLAYED_TRANSCRIPT = "REPLAYED_TRANSCRIPT"


class FuzzingMode(StrEnum):
    """Whether a fuzzing campaign actually ran (#83)."""

    LIVE_CAMPAIGN = "LIVE_CAMPAIGN"
    REPLAYED_CORPUS = "REPLAYED_CORPUS"
    NOT_RUN = "NOT_RUN"


class IsolationMode(StrEnum):
    """How the target was contained (#81, #15).

    `SUBPROCESS_JAIL` is materially weaker than either container mode and it is an
    acceptable D3 fallback; it must never be reported as a container path.

    `CONTAINER_NO_NETWORK` [Δ #15] is D-024's accepted substitute for rootless
    isolation: a standard (rootful-daemon) container with `--network none`, a fixed
    non-root uid, every capability dropped, `no-new-privileges`, and a read-only root
    filesystem — every property in `docs/09-company/08-security-review.md` §6.2
    *except* the user-namespace remapping true rootless would add. D-024 condition 8
    is binding: a run in this mode is never reported as `ROOTLESS_CONTAINER`, because
    that would claim the one property (`--network none` aside) it does not deliver —
    protection against a container-runtime escape reaching host root.

    `ROOTLESS_CONTAINER` is kept for a genuine rootless Podman/Docker run, should one
    ever land; nothing in this codebase produces it today.
    """

    ROOTLESS_CONTAINER = "ROOTLESS_CONTAINER"
    CONTAINER_NO_NETWORK = "CONTAINER_NO_NETWORK"
    SUBPROCESS_JAIL = "SUBPROCESS_JAIL"


class SubstitutionKind(StrEnum):
    """The fallback paths that exist. Any that was used is disclosed in the evidence
    bundle rather than inferred by a reader from a missing section."""

    MODEL_REPLAY = "MODEL_REPLAY"
    REPRODUCER_REPLAY = "REPRODUCER_REPLAY"
    SUBPROCESS_JAIL_ISOLATION = "SUBPROCESS_JAIL_ISOLATION"
    OPERATOR_SUPPLIED_PATCH = "OPERATOR_SUPPLIED_PATCH"


class Role(StrEnum):
    """Roles from `docs/03-technical/22-authentication-and-authorization-plan.md`."""

    OPERATOR = "operator"
    REVIEWER = "reviewer"
    ADMINISTRATOR = "administrator"


class ErrorCode(StrEnum):
    """The error vocabulary from `docs/03-technical/21-api-specification.md`, plus
    the transport-level codes the API cannot avoid emitting.

    `GPU_LIMIT_EXCEEDED` is retained even though rented GPU is CUT (D-015): the local
    model host is leased and torn down the same way, and dropping the code would make
    the evidence bundles of a future run unreadable by an older client.
    """

    INVALID_AUTHORIZATION = "INVALID_AUTHORIZATION"
    UNSUPPORTED_REPOSITORY = "UNSUPPORTED_REPOSITORY"
    PREFLIGHT_FAILED = "PREFLIGHT_FAILED"
    BASELINE_BUILD_FAILED = "BASELINE_BUILD_FAILED"
    BASELINE_FLAKY = "BASELINE_FLAKY"
    SANDBOX_POLICY_VIOLATION = "SANDBOX_POLICY_VIOLATION"
    #: Added at D1 from the architecture spec §6.1 / §6.3 (PR #79).
    SANDBOX_UNAVAILABLE = "SANDBOX_UNAVAILABLE"
    JOB_TIMED_OUT = "JOB_TIMED_OUT"
    NO_REPRODUCIBLE_FINDING = "NO_REPRODUCIBLE_FINDING"
    PATCH_POLICY_REJECTED = "PATCH_POLICY_REJECTED"
    MODEL_CAPACITY_UNAVAILABLE = "MODEL_CAPACITY_UNAVAILABLE"
    GPU_LIMIT_EXCEEDED = "GPU_LIMIT_EXCEEDED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    #: Added at D1. A mission tried to enter a verdict state without a verification
    #: record to justify it. Distinct from VERIFICATION_FAILED, which means the gates
    #: ran and said no.
    VERIFICATION_REQUIRED = "VERIFICATION_REQUIRED"
    SAFE_CANCELLATION_IN_PROGRESS = "SAFE_CANCELLATION_IN_PROGRESS"
    # Transport / request-level
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
    CONFLICT = "CONFLICT"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


#: Machine state → what the Core displays. Exhaustive: every `MissionState` maps.
POSTURE_BY_STATE: dict[MissionState, MissionPosture] = {
    MissionState.CREATED: MissionPosture.PROTECTED,
    MissionState.AUTHORIZED: MissionPosture.PROTECTED,
    MissionState.SNAPSHOTTED: MissionPosture.PROTECTED,
    MissionState.VALIDATING: MissionPosture.INVESTIGATING,
    MissionState.BASELINE: MissionPosture.INVESTIGATING,
    MissionState.TRIAGE: MissionPosture.INVESTIGATING,
    MissionState.STRESS_TEST: MissionPosture.INVESTIGATING,
    MissionState.CORRELATE: MissionPosture.VULNERABILITY_CONFIRMED,
    MissionState.PATCH: MissionPosture.PATCHING,
    MissionState.VERIFY: MissionPosture.PATCHING,
    MissionState.EXPORTING: MissionPosture.PATCHING,
    MissionState.PAUSED: MissionPosture.HUMAN_REVIEW,
    MissionState.CANCELLING: MissionPosture.CANCELLED,
    MissionState.VERIFIED: MissionPosture.VERIFIED,
    MissionState.REJECTED: MissionPosture.REJECTED,
    MissionState.HUMAN_REVIEW: MissionPosture.HUMAN_REVIEW,
    MissionState.FAILED: MissionPosture.FAILED,
    MissionState.CANCELLED: MissionPosture.CANCELLED,
}


def posture_for(state: MissionState) -> MissionPosture:
    """Derive the displayed posture. Raises on an unmapped state so a new state can
    never reach the UI as an unlabelled Core."""
    try:
        return POSTURE_BY_STATE[MissionState(state)]
    except KeyError as exc:  # pragma: no cover - guarded by test_enums
        raise KeyError(f"No posture mapped for mission state {state!r}") from exc
