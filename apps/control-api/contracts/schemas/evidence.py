"""Evidence schemas: findings, reproducers, patches, verification, bundles.

The confidence rule lives here in its enforced form. `ModelProvenance.confidence` is
the *only* place a model score appears in the whole contract. It sits beside the
patch candidate, is rendered in the patch panel, and is written into the evidence
bundle — and it is not reachable from `GateMatrix`, so `derive_verdict` cannot see
it. `VerificationRecord` then re-derives the verdict from the gates and refuses to
exist if the stored verdict disagrees.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field, computed_field, model_validator

from contracts.enums import (
    AnalyzerTool,
    DiscoveryMethod,
    FindingCategory,
    FuzzingMode,
    InferenceMode,
    IsolationMode,
    PatchPolicyStatus,
    PatchProvenance,
    Severity,
    SubstitutionKind,
    Verdict,
)
from contracts.schemas.common import ArtifactRef, ResourceUsage, StrictSchema
from contracts.verdict import GateMatrix, derive_mission_verdict, derive_verdict


class ModelProvenance(StrictSchema):
    """Where a model-generated candidate came from, and how sure the model claimed
    to be.

    `confidence` is recordable and displayable. It is not an input to any gate, any
    verdict, or any routing decision — see the module docstring of
    `contracts.verdict`. If you find yourself wanting to branch on it, that is the
    bug the rule exists to prevent.
    """

    model_name: str = Field(max_length=200)
    model_revision: str = Field(default="", max_length=200)
    served_from: str = Field(
        max_length=200,
        description="Host serving the model. Always local or private — validated at "
        "startup by contracts.checks.check_model_endpoints.",
    )
    prompt_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    context_bytes: int = Field(default=0, ge=0)
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="DISPLAY ONLY. The model's self-reported confidence. Cannot "
        "influence a verdict, a gate, or an escalation; recorded so the evidence "
        "bundle shows what the model claimed alongside what the tools proved.",
    )
    # --- replay provenance ------------------------------------------------------
    # D-015 cut the rented GPU, so the D5 gate rests on a quantized CPU-served model
    # on day five of seven. A replay-mode gateway — serving a previously captured
    # response instead of generating one live — is the fallback, and it is only
    # honest if the schema can say so. Same rule as D-008: a replayed response is
    # legitimate; claiming it was generated live is not.
    #
    # D-049: the replay triple alone was not enough, because *silence* read as live
    # inference — QA reproduced exactly that (BUG-007 case D1). A replay-mode gateway
    # that forgot three fields produced a record indistinguishable from a live
    # generation. `inference_mode` is required and has no default, so the claim has to
    # be stated either way.
    inference_mode: InferenceMode = Field(
        description="LIVE_INFERENCE or REPLAYED_TRANSCRIPT. Required, no default: a "
        "default here would be the system making a provenance claim on the caller's "
        "behalf when they said nothing, and every such default should point at the "
        "weaker claim or not exist. Whatever renders provenance reads this."
    )
    replayed_from_transcript: str | None = Field(
        default=None,
        max_length=500,
        description="Set when this response was replayed from a captured transcript "
        "rather than generated live. Whatever renders provenance must say 'replayed'.",
    )
    captured_at: datetime | None = Field(
        default=None,
        description="When the replayed transcript was originally generated.",
    )
    transcript_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
        description="Digest of the replayed transcript, so the claim is checkable.",
    )

    @model_validator(mode="after")
    def _replay_fields_are_all_or_nothing(self) -> "ModelProvenance":
        replay = (
            self.replayed_from_transcript,
            self.captured_at,
            self.transcript_sha256,
        )
        if any(value is not None for value in replay) and not all(
            value is not None for value in replay
        ):
            raise ValueError(
                "replayed_from_transcript, captured_at and transcript_sha256 are set "
                "together or not at all — a partially-declared replay cannot be "
                "distinguished from a live generation."
            )
        return self

    @model_validator(mode="after")
    def _inference_mode_matches_the_replay_fields(self) -> "ModelProvenance":
        declared_replay = self.inference_mode is InferenceMode.REPLAYED_TRANSCRIPT
        has_replay = self.replayed_from_transcript is not None
        if declared_replay and not has_replay:
            raise ValueError(
                "REPLAYED_TRANSCRIPT must name the transcript it was replayed from, "
                "when it was captured, and its digest — otherwise the claim is not "
                "checkable by anyone outside the team."
            )
        if not declared_replay and has_replay:
            raise ValueError(
                "a response carrying replay provenance cannot declare itself "
                "LIVE_INFERENCE."
            )
        return self

    @property
    def is_replayed(self) -> bool:
        return self.inference_mode is InferenceMode.REPLAYED_TRANSCRIPT


class SourceLocation(StrictSchema):
    file_path: str = Field(max_length=1000)
    line: int | None = Field(default=None, ge=1)
    function: str | None = Field(default=None, max_length=300)


class FindingSummary(StrictSchema):
    id: UUID
    mission_id: UUID
    category: FindingCategory
    severity: Severity
    tool: AnalyzerTool
    discovery_method: DiscoveryMethod = Field(
        description="How this finding came to exist. Required, with no default: only "
        "FUZZING_CAMPAIGN supports the claim 'our fuzzer discovered it'. A replayed "
        "reproducer (#83) is honest and weaker, and has to say so."
    )
    replay_source: str | None = Field(
        default=None,
        max_length=500,
        description="Artifact pointer to the recorded reproducer. Required when "
        "discovery_method is REPLAYED_REPRODUCER, and forbidden otherwise.",
    )
    location: SourceLocation
    fingerprint: str = Field(
        max_length=128, description="Stable deduplication key across runs."
    )
    crash_count: int = Field(
        default=1,
        ge=1,
        description="How many raw crash occurrences share this fingerprint, "
        "including the one that created this finding (#30). A rediscovery of the "
        "same root cause increments this rather than creating a second finding.",
    )
    reproducible: bool = Field(
        description="True only when a minimized input replayed the failure from a "
        "clean build. Not a guess."
    )
    detected_at: datetime
    title: str = Field(max_length=300)

    @model_validator(mode="after")
    def _replay_source_matches_discovery_method(self) -> "FindingSummary":
        replayed = self.discovery_method is DiscoveryMethod.REPLAYED_REPRODUCER
        if replayed and not self.replay_source:
            raise ValueError(
                "REPLAYED_REPRODUCER findings must name the recorded reproducer they "
                "were replayed from."
            )
        if not replayed and self.replay_source:
            raise ValueError(
                "replay_source is only meaningful for REPLAYED_REPRODUCER findings; a "
                "live discovery must not carry one."
            )
        return self


class ReproducerRecord(StrictSchema):
    id: UUID
    finding_id: UUID
    minimized: bool
    replay_attempts: int = Field(ge=0)
    replay_successes: int = Field(ge=0)
    test_command: str = Field(max_length=1000)
    artifact: ArtifactRef
    created_at: datetime

    @model_validator(mode="after")
    def _successes_within_attempts(self) -> "ReproducerRecord":
        if self.replay_successes > self.replay_attempts:
            raise ValueError("replay_successes cannot exceed replay_attempts")
        return self


class FindingDetail(StrictSchema):
    summary: FindingSummary
    sanitizer_report: str = Field(
        default="",
        max_length=20000,
        description="Sanitized sanitizer output: stack frames and the failure kind. "
        "Absolute paths and environment values are stripped before it reaches here.",
    )
    code_slice: str = Field(
        default="",
        max_length=20000,
        description="The relevant source region only. Never the whole repository.",
    )
    reproducer: ReproducerRecord | None = None
    related_finding_ids: list[UUID] = Field(default_factory=list)
    artifacts: list[ArtifactRef] = Field(default_factory=list)


class BaselineReport(StrictSchema):
    """The denominator for 'regression preserved' (P0-5). Real counts or nothing."""

    mission_id: UUID
    configure_ok: bool
    build_ok: bool
    tests_total: int = Field(ge=0)
    tests_passed: int = Field(ge=0)
    tests_failed: int = Field(ge=0)
    duration_seconds: float = Field(ge=0)
    adapter: str = Field(max_length=100)
    recorded_at: datetime
    log_ref: ArtifactRef | None = None

    @model_validator(mode="after")
    def _counts_add_up(self) -> "BaselineReport":
        if self.tests_passed + self.tests_failed > self.tests_total:
            raise ValueError("tests_passed + tests_failed cannot exceed tests_total")
        return self

    @computed_field(  # type: ignore[prop-decorator]
        description="The D3 gate signal, derived from the recorded counts: configure "
        "and build succeeded, at least one test ran, and none failed. Emitted "
        "alongside the BASELINE_PASSED / BASELINE_FAILED event types. It is an "
        "outcome, not a mission state."
    )
    @property
    def passed(self) -> bool:
        return (
            self.configure_ok
            and self.build_ok
            and self.tests_total > 0
            and self.tests_failed == 0
        )


class FuzzingReport(StrictSchema):
    mission_id: UUID
    mode: FuzzingMode = Field(
        description="Whether a campaign actually ran. Required, no default — a "
        "replayed corpus (#83) cannot be reported as a live campaign."
    )
    harness: str = Field(max_length=200)
    engine: str = Field(default="libFuzzer", max_length=100)
    runtime_seconds: float = Field(ge=0)
    executions: int = Field(ge=0)
    crashes_found: int = Field(ge=0)
    unique_crashes: int = Field(ge=0)
    corpus_size: int = Field(ge=0)
    sanitizers: list[str] = Field(default_factory=list)
    finding_ids: list[UUID] = Field(default_factory=list)
    replay_source: str | None = Field(
        default=None,
        max_length=500,
        description="Artifact pointer to the recorded corpus. Required when mode is "
        "REPLAYED_CORPUS, forbidden otherwise.",
    )
    recorded_at: datetime

    @model_validator(mode="after")
    def _mode_matches_the_numbers(self) -> "FuzzingReport":
        if self.mode is FuzzingMode.REPLAYED_CORPUS and not self.replay_source:
            raise ValueError(
                "REPLAYED_CORPUS must name the recorded corpus it was replayed from."
            )
        if self.mode is not FuzzingMode.REPLAYED_CORPUS and self.replay_source:
            raise ValueError("replay_source is only meaningful for REPLAYED_CORPUS.")
        if self.mode is FuzzingMode.NOT_RUN and (
            self.executions or self.runtime_seconds or self.crashes_found
        ):
            raise ValueError(
                "a campaign reported as NOT_RUN cannot also report executions, "
                "runtime, or crashes."
            )
        return self


class PatchCandidate(StrictSchema):
    id: UUID
    mission_id: UUID
    finding_id: UUID
    provenance: PatchProvenance = Field(
        description="MODEL_GENERATED or OPERATOR_SUPPLIED. Never inflated: an "
        "operator-written candidate is labelled as one in the UI and the report."
    )
    model: ModelProvenance | None = Field(
        default=None,
        description="Present only when provenance is MODEL_GENERATED.",
    )
    diff: str = Field(
        max_length=200000, description="Unified diff, sanitized, rendered in the UI."
    )
    files_changed: int = Field(ge=0)
    lines_changed: int = Field(ge=0)
    policy_status: PatchPolicyStatus
    policy_detail: str = Field(default="", max_length=2000)
    rationale: str = Field(
        default="",
        max_length=5000,
        description="The model's stated reasoning. Displayed separately from "
        "evidence and never treated as evidence.",
    )
    created_at: datetime

    @model_validator(mode="after")
    def _provenance_matches_model(self) -> "PatchCandidate":
        if self.provenance is PatchProvenance.MODEL_GENERATED and self.model is None:
            raise ValueError(
                "MODEL_GENERATED candidates must carry ModelProvenance; an unattributed "
                "candidate cannot be claimed as model-generated."
            )
        if self.provenance is PatchProvenance.OPERATOR_SUPPLIED and self.model is not None:
            raise ValueError(
                "OPERATOR_SUPPLIED candidates must not carry ModelProvenance."
            )
        return self


class VerificationRecord(StrictSchema):
    """A verdict and the deterministic gates that produced it.

    The validator re-runs `derive_verdict` over the gates and rejects any record
    whose verdict does not follow from them. This is the structural form of "a patch
    is never accepted on model confidence alone": there is no way to construct,
    persist, or serialize a `VERIFIED` record over a failing regression gate.
    """

    id: UUID
    mission_id: UUID
    patch_id: UUID
    gates: GateMatrix
    verdict: Verdict
    started_at: datetime
    finished_at: datetime
    worktree_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
        description="Digest of the clean worktree the verification ran in.",
    )
    resource_usage: ResourceUsage | None = None

    @model_validator(mode="after")
    def _verdict_follows_from_gates(self) -> "VerificationRecord":
        derived = derive_verdict(self.gates)
        if self.verdict != derived:
            raise ValueError(
                f"verdict {self.verdict} does not follow from the gate matrix "
                f"(deterministic derivation gives {derived}). A verdict may only be "
                f"derived from gate results."
            )
        return self


class CandidateVerdict(StrictSchema):
    """One candidate's outcome, for the side-by-side view."""

    patch_id: UUID
    verification_id: UUID
    verdict: Verdict
    provenance: PatchProvenance
    summary: str = Field(
        default="",
        max_length=500,
        description="One-line reason, e.g. 'regression suite: 2 of 14 failed'.",
    )


class MissionVerdictSummary(StrictSchema):
    """The mission verdict, and every candidate verdict it was derived from.

    The demo's whole point is showing a `Verified` beside a `Rejected`. A single
    mission-level verdict that hid the rejection would remove the differentiator, so
    the breakdown travels with the verdict everywhere it is displayed.
    """

    mission_verdict: Verdict
    candidates: list[CandidateVerdict] = Field(default_factory=list)
    verified_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    human_review_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _summary_is_consistent_and_derived(self) -> "MissionVerdictSummary":
        verdicts = [candidate.verdict for candidate in self.candidates]
        counts = {
            Verdict.VERIFIED: self.verified_count,
            Verdict.REJECTED: self.rejected_count,
            Verdict.HUMAN_REVIEW_REQUIRED: self.human_review_count,
        }
        for verdict, count in counts.items():
            actual = sum(1 for item in verdicts if item is verdict)
            if actual != count:
                raise ValueError(
                    f"{verdict} count is {count} but {actual} candidates carry it; "
                    f"a mission verdict may not misreport its own basis."
                )
        derived = derive_mission_verdict(verdicts)
        if self.mission_verdict != derived:
            raise ValueError(
                f"mission_verdict {self.mission_verdict} does not follow from the "
                f"candidate verdicts (derivation gives {derived})."
            )
        return self


class Substitution(StrictSchema):
    """One fallback path that was used instead of the primary one.

    The CEO approved fallbacks for D1–D7 (#81, #82, #83). Using one is legitimate;
    letting a reader infer it from a missing section is not. Every substitution is
    declared here, printed in the report, and shown in the UI.
    """

    kind: SubstitutionKind
    reason: str = Field(
        min_length=1,
        max_length=1000,
        description="Why the primary path was not used. Stated plainly.",
    )
    artifact_ref: str | None = Field(
        default=None,
        max_length=500,
        description="The recorded artifact the substitution drew on, where one exists.",
    )
    recorded_at: datetime


class EvidenceBundle(StrictSchema):
    """What the judge is handed (P0-12)."""

    mission_id: UUID
    generated_at: datetime
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorization_statement: str = Field(max_length=4000)
    baseline: BaselineReport | None = None
    findings: list[FindingSummary] = Field(default_factory=list)
    reproducers: list[ReproducerRecord] = Field(default_factory=list)
    fuzzing: FuzzingReport | None = None
    patches: list[PatchCandidate] = Field(
        default_factory=list,
        description="Every candidate the mission produced, accepted and rejected "
        "alike. The rejected one is the differentiator, not an embarrassment.",
    )
    verifications: list[VerificationRecord] = Field(
        default_factory=list,
        description="One record per candidate, each with its own gate matrix.",
    )
    verdict_summary: MissionVerdictSummary | None = Field(
        default=None,
        description="The mission verdict and the per-candidate breakdown it was "
        "derived from.",
    )
    recommended_patch_id: UUID | None = Field(
        default=None,
        description="The one diff we stand behind. Derived and validated, not "
        "free-form: it must name a patch in `patches` whose verification verdict is "
        "VERIFIED, and when exactly one candidate verified it must be that one. A "
        "bundle showing two verified patches without naming one invites a judge to "
        "pick the wrong one and ask why we shipped it.",
    )
    resource_usage: ResourceUsage
    gates_not_run: list[str] = Field(
        default_factory=list,
        description="Gates that did not run, disclosed rather than omitted.",
    )
    substitutions: list[Substitution] = Field(
        default_factory=list,
        description="Every fallback path used in this run. Empty means the primary "
        "path ran throughout — a claim the pipeline has to earn, not assume.",
    )
    isolation_mode: IsolationMode = Field(
        description="How the target was contained. Required, with no default (D-049): "
        "the previous default claimed ROOTLESS_CONTAINER, which is the stronger of the "
        "two, so a bundle assembled by code that forgot the field overclaimed the "
        "isolation posture. A subprocess jail (#81) is weaker and is reported as what "
        "it is.",
    )
    tool_versions: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _recommended_patch_is_derived_from_the_evidence(self) -> "EvidenceBundle":
        """A hand-set field sitting next to the data that already contains the truth
        is a field that can lie, and it is exactly the kind that gets filled in at 2am
        on D7. Same reasoning the architecture spec applied to `gates_not_run`.
        """
        verified_patch_ids = [
            record.patch_id
            for record in self.verifications
            if record.verdict is Verdict.VERIFIED
        ]
        known_patch_ids = {patch.id for patch in self.patches}

        if self.recommended_patch_id is None:
            if len(set(verified_patch_ids)) == 1:
                raise ValueError(
                    "exactly one candidate verified, so recommended_patch_id must name "
                    "it; leaving it unset defers the choice to whoever renders the "
                    "report."
                )
            return self

        if self.recommended_patch_id not in known_patch_ids:
            raise ValueError(
                f"recommended_patch_id {self.recommended_patch_id} does not name a "
                f"candidate in this bundle's `patches`."
            )
        if self.recommended_patch_id not in verified_patch_ids:
            raise ValueError(
                f"recommended_patch_id {self.recommended_patch_id} names a candidate "
                f"with no VERIFIED verification record. A recommendation is a claim "
                f"about what the gates proved, not a preference."
            )
        return self


class OperatorPatchCandidateRequest(StrictSchema):
    """`POST /missions/{id}/patches` (T-3, D-008). An operator-authored unified diff,
    submitted for the same finding `PATCH_GENERATE` would otherwise have targeted.

    Deliberately carries no `provenance`, `policy_status` or `model` field — the
    server sets `provenance=OPERATOR_SUPPLIED` unconditionally (an HTTP caller cannot
    claim `MODEL_GENERATED` for a diff it typed itself) and the real policy gate
    (`orchestrator.patch_policy.evaluate_patch_policy`) computes `policy_status` from
    the diff and the mission's own policy, exactly as it does for a model-generated
    candidate. See `orchestrator.operator_candidates.submit_operator_candidate`.
    """

    finding_id: UUID = Field(
        description="Which finding this diff addresses. Must belong to this mission."
    )
    diff: str = Field(
        min_length=1,
        max_length=200000,
        description="Unified diff (`git diff` / `diff -u` format). Verified through "
        "the same deterministic gate matrix a model-generated candidate goes "
        "through — never accepted on say-so.",
    )
    rationale: str = Field(
        default="",
        max_length=5000,
        description="Optional operator note on why this diff is believed to fix the "
        "finding. Displayed separately from evidence, never treated as evidence.",
    )


class ExportRequest(StrictSchema):
    formats: list[str] = Field(
        default_factory=lambda: ["markdown", "json"],
        description="Subset of ['markdown', 'json'].",
    )
    include_artifacts: bool = Field(
        default=False,
        description="Bundle raw artifacts alongside the report. Never includes the "
        "target's source archive.",
    )
    idempotency_key: str | None = Field(default=None, max_length=200)


class ExportReceipt(StrictSchema):
    mission_id: UUID
    export_id: UUID
    formats: list[str]
    artifacts: list[ArtifactRef]
    generated_at: datetime
