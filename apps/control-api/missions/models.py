"""Persistent mission state (#14).

One row per fact, per architecture spec §5.1. Four rules from that section are
implemented here rather than left to the caller:

* **`gates` is `jsonb`, not five foreign-key rows.** `GateMatrix` is the frozen
  contract; a relational copy of it is a second source of truth that will drift. It is
  validated against that schema on write instead — `VerificationRecord.clean()`, called
  from `save()`. Test: `missions/tests/test_models.py::test_a_malformed_gate_matrix_is_refused_on_write`.
* **`MissionEvent.sequence` is gap-free per mission.** Allocation lives in
  `orchestrator.events`, inside the transaction that holds `SELECT … FOR UPDATE` on the
  mission row. Not a database sequence (those gap on rollback) and not `max()+1` without
  the lock. `unique_together(mission, sequence)` catches the mistake if anyone tries.
* **`Authorization` and `Snapshot` are append-only.** Enforced by a `save()` override
  that refuses an update to an existing row. The evidence bundle has to show that
  authority existed at the moment each stage ran, and an edited record cannot show that.
* **Indexes that matter and no more**: `(mission, sequence)` on events,
  `(state, run_after)` and `(lease_expires_at)` on jobs, `sha256` unique on artifacts.

## Two columns that carry rulings

`Mission.paused_from` (D-047) and `Mission.verification_started_at` (D-046). Neither is
bookkeeping. See their field comments, and the guards in `orchestrator/`.

## What is stored as JSON, and why that is not laziness

`policy`, `gates`, `model_provenance`, `resource_usage` and `payload` are all frozen
pydantic schemas already. Storing them as JSON and validating against the schema keeps
exactly one definition of each shape.

**Which of them are validated on write, precisely** — because an earlier version of this
docstring claimed all of them and implemented none, which a security review caught and
which is the standing rule's exact subject:

| Column | On write | On read |
|---|---|---|
| `VerificationRecord.gates` + `verdict` | ✅ `clean()`, from `save()` | ✅ `repository.load_verifications` re-derives |
| `PatchCandidate.model_provenance` | ✅ `clean()`, from `save()` | via the schema when loaded |
| `Mission.policy`, `MissionEvent.payload`, `Job.payload/result` | ❌ not validated | — |

The two that are validated are the two on the evidence→verdict path. The others are
descriptive and a malformed one cannot produce a false verdict; they are listed as
unvalidated rather than quietly implied to be safe.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models

from contracts.errors import MissionStateWriteError
from contracts.enums import (
    AnalyzerTool,
    DiscoveryMethod,
    EventStatus,
    EventType,
    FindingCategory,
    FuzzingMode,
    IsolationMode,
    LanguageAdapter,
    MissionStage,
    MissionState,
    PatchPolicyStatus,
    PatchProvenance,
    Severity,
    Verdict,
)
from missions.lifecycle import LIFECYCLE_FIELDS, lifecycle_write_permitted


def _choices(enum_cls: type) -> list[tuple[str, str]]:
    """Django choices from a `StrEnum`, so the DB constraint and the contract agree."""
    return [(member.value, member.value) for member in enum_cls]


#: Longest member of any enum stored as a char column, with room to spare. A single
#: constant so a new member never silently truncates.
ENUM_MAX_LENGTH = 64


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AppendOnlyModel(models.Model):
    """A row that may be created and never updated.

    `Authorization` and `Snapshot` are the audit trail the evidence bundle reproduces
    verbatim. Revocation is a *new field on write*, not an edit — which is why
    `Authorization.revoked_at` is set through `objects.filter(...).update(...)` in the
    one place that revokes, and not through `save()`.
    """

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self._state.adding is False:
            raise ValidationError(
                f"{type(self).__name__} is append-only; this row already exists and "
                f"cannot be edited. Write a new row, or use an explicit queryset "
                f"update for the one field the contract allows to change."
            )
        super().save(*args, **kwargs)


class MissionQuerySet(models.QuerySet):
    """Refuses a bulk update of a lifecycle field (SEC-16).

    `Mission.objects.filter(...).update(state=...)` never calls `save()`, so the model
    guard below does not see it. A reviewer walked `CREATED → VERIFIED` that way in one
    statement. Both doors have to be shut or neither is.
    """

    def update(self, **kwargs: Any) -> int:
        touched = LIFECYCLE_FIELDS & set(kwargs)
        if touched and not lifecycle_write_permitted():
            raise MissionStateWriteError(
                f"Bulk update of mission lifecycle field(s) {sorted(touched)} outside "
                f"orchestrator.transitions.transition.",
                details={"fields": sorted(touched)},
            )
        return super().update(**kwargs)


class Mission(TimestampedModel):
    """The mission row.

    `orchestrator.transitions.transition` is the **only** sanctioned writer of `state`,
    `paused_from` and `verdict`, and `orchestrator.candidates.record_verification` is
    the only sanctioned writer of `verification_started_at`. That is enforced here
    rather than asserted: see `missions/lifecycle.py` for why the convention alone was
    not enough, and `tests/architecture/test_mission_state_single_writer.py` for the
    review-time half of the same guarantee.
    """

    objects = MissionQuerySet.as_manager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    repository_ref = models.CharField(max_length=500)
    adapter = models.CharField(
        max_length=ENUM_MAX_LENGTH, choices=_choices(LanguageAdapter)
    )
    policy = models.JSONField(
        default=dict, help_text="MissionPolicy, serialized from the frozen schema."
    )

    state = models.CharField(
        max_length=ENUM_MAX_LENGTH,
        choices=_choices(MissionState),
        default=MissionState.CREATED.value,
    )

    # D-047. The state a paused mission may resume into, and the only one. Without it
    # `PAUSED → *` is a forward skip *and* a backward one: a mission paused in VERIFY
    # could resume into BASELINE, re-run the baseline and write a second BaselineReport
    # for the same snapshot — and BaselineReport is the denominator for "regression
    # preserved" (P0-5), so two of them make the central verification claim ambiguous.
    paused_from = models.CharField(
        max_length=ENUM_MAX_LENGTH,
        choices=_choices(MissionState),
        null=True,
        blank=True,
        help_text="Set when the mission pauses, cleared when it resumes. NULL on a "
        "mission that is not paused; a PAUSED mission with NULL here can only abort.",
    )

    # D-046. The freeze. Set when the first VerificationRecord is written, and the
    # candidate-insert path refuses once it is set. This is the *enforcement* — "has
    # verification started" is state, and state lives in the store. The contract-level
    # statement is `contracts.state_machine.assert_candidate_set_open`.
    verification_started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When VERIFY first produced a record. Once set, the candidate set "
        "is closed: adding a candidate afterwards is generate-until-pass.",
    )

    verdict = models.CharField(
        max_length=ENUM_MAX_LENGTH,
        choices=_choices(Verdict),
        null=True,
        blank=True,
        help_text="Derived from the whole candidate set, never from the last run.",
    )

    class Meta:
        db_table = "mission"
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return f"{self.name} ({self.state})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Refuse a lifecycle write from outside the orchestrator (SEC-16).

        A new mission is exempt: creating one in `CREATED` writes `state` by definition,
        and `CREATED` is not a state any guard would have prevented. Everything after
        that goes through `transition`.

        `update_fields` is honoured when given, so a save that does not name a lifecycle
        field is not refused for merely having those attributes loaded on the instance.
        Without `update_fields`, Django writes every column, so the write is treated as
        touching them.
        """
        if not self._state.adding and not lifecycle_write_permitted():
            update_fields = kwargs.get("update_fields")
            touched = (
                LIFECYCLE_FIELDS & set(update_fields)
                if update_fields is not None
                else LIFECYCLE_FIELDS
            )
            if touched:
                raise MissionStateWriteError(
                    f"Write to mission lifecycle field(s) {sorted(touched)} outside "
                    f"orchestrator.transitions.transition. If this is an ordinary data "
                    f"edit, pass update_fields naming only the columns it touches.",
                    details={"mission_id": str(self.pk), "fields": sorted(touched)},
                )
        super().save(*args, **kwargs)

    @property
    def state_enum(self) -> MissionState:
        return MissionState(self.state)

    @property
    def paused_from_enum(self) -> MissionState | None:
        return MissionState(self.paused_from) if self.paused_from else None


class Authorization(AppendOnlyModel):
    """P0-1. Until this exists and is active, no stage may run."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mission = models.ForeignKey(
        Mission, on_delete=models.CASCADE, related_name="authorizations"
    )
    statement = models.TextField(max_length=4000)
    granted_by = models.CharField(max_length=200)
    granted_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    repository_ref = models.CharField(max_length=500)
    snapshot_sha256 = models.CharField(max_length=64, null=True, blank=True)
    evidence_ref = models.CharField(max_length=500, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "authorization"
        ordering = ["-granted_at"]


class Snapshot(AppendOnlyModel):
    """Immutable repository snapshot. The digest is recomputed server-side."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mission = models.ForeignKey(
        Mission, on_delete=models.CASCADE, related_name="snapshots"
    )
    commit_sha = models.CharField(max_length=64, null=True, blank=True)
    archive_sha256 = models.CharField(max_length=64)
    file_count = models.PositiveIntegerField(default=0)
    bytes_total = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "snapshot"
        ordering = ["-created_at"]


class MissionEvent(models.Model):
    """Append-only, gap-free per mission. The SSE stream and the replay endpoint both
    read this table and nothing else."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mission = models.ForeignKey(
        Mission, on_delete=models.CASCADE, related_name="events"
    )
    sequence = models.PositiveIntegerField(
        help_text="Gap-free per-mission ordinal, allocated under the mission row lock."
    )
    timestamp = models.DateTimeField()
    type = models.CharField(max_length=ENUM_MAX_LENGTH, choices=_choices(EventType))
    stage = models.CharField(
        max_length=ENUM_MAX_LENGTH,
        choices=_choices(MissionStage),
        null=True,
        blank=True,
    )
    state = models.CharField(max_length=ENUM_MAX_LENGTH, choices=_choices(MissionState))
    status = models.CharField(
        max_length=ENUM_MAX_LENGTH,
        choices=_choices(EventStatus),
        default=EventStatus.RUNNING.value,
    )
    severity = models.CharField(
        max_length=ENUM_MAX_LENGTH,
        choices=_choices(Severity),
        default=Severity.INFO.value,
    )
    message = models.CharField(max_length=1000)
    payload = models.JSONField(default=dict)
    evidence_refs = models.JSONField(default=list)
    metrics = models.JSONField(default=dict)
    trace_id = models.CharField(max_length=64)

    class Meta:
        db_table = "mission_event"
        ordering = ["mission_id", "sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["mission", "sequence"], name="mission_event_sequence_unique"
            ),
        ]
        indexes = [
            models.Index(fields=["mission", "sequence"], name="event_mission_seq_idx"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self._state.adding is False:
            raise ValidationError(
                "MissionEvent is append-only; an emitted event is never edited."
            )
        super().save(*args, **kwargs)


class JobKind(models.TextChoices):
    """Architecture spec §3.1. The list is `Fixed` there; extending it is a
    backend-developer call, narrowing it is not."""

    BASELINE = "BASELINE"
    SANITIZER_BUILD = "SANITIZER_BUILD"
    FUZZ = "FUZZ"
    MINIMIZE = "MINIMIZE"
    CORRELATE = "CORRELATE"
    PATCH_GENERATE = "PATCH_GENERATE"
    VERIFY = "VERIFY"
    EXPORT = "EXPORT"
    TEARDOWN = "TEARDOWN"


class JobState(models.TextChoices):
    QUEUED = "QUEUED"
    LEASED = "LEASED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


#: Per-kind attempt ceilings, architecture spec §3.4. VERIFY is 1 and is not a knob:
#: retrying a verification is how a flaky pass becomes a verdict.
MAX_ATTEMPTS_BY_KIND: dict[str, int] = {
    JobKind.BASELINE: 1,
    JobKind.SANITIZER_BUILD: 1,
    JobKind.FUZZ: 2,
    JobKind.MINIMIZE: 1,
    JobKind.CORRELATE: 1,
    JobKind.PATCH_GENERATE: 1,
    JobKind.VERIFY: 1,
    JobKind.EXPORT: 3,
    JobKind.TEARDOWN: 3,
}


class Job(models.Model):
    """The queue. One table, no broker — `SKIP LOCKED` is why there is no Redis.

    `deadline_at` is not nullable. A job with no deadline is the one that is still
    running at 03:00 with nobody watching, which is the failure the overnight contract
    (§3.3) exists to prevent.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mission = models.ForeignKey(Mission, on_delete=models.CASCADE, related_name="jobs")
    kind = models.CharField(max_length=ENUM_MAX_LENGTH, choices=JobKind.choices)
    state = models.CharField(
        max_length=ENUM_MAX_LENGTH,
        choices=JobState.choices,
        default=JobState.QUEUED,
    )
    payload = models.JSONField(
        default=dict, help_text="Inputs. Never a secret, never a raw archive."
    )
    result = models.JSONField(
        default=dict,
        help_text="Summary the orchestrator reads to pick the next transition.",
    )
    attempt = models.PositiveSmallIntegerField(default=1)
    max_attempts = models.PositiveSmallIntegerField(default=1)
    run_after = models.DateTimeField()
    deadline_at = models.DateTimeField(
        help_text="Mandatory at enqueue, set from MissionPolicy. Hitting it is a "
        "result (TIMED_OUT), not a failure."
    )
    lease_owner = models.CharField(max_length=200, default="", blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    cancel_requested = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "job"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["state", "run_after"], name="job_claim_idx"),
            models.Index(fields=["lease_expires_at"], name="job_lease_idx"),
        ]


class BaselineReport(models.Model):
    """The denominator for 'regression preserved' (P0-5). Real counts or nothing.

    One per mission, enforced by the unique constraint below rather than by
    convention. That constraint is the second half of D-047: even if a resume bug got
    past `assert_resume`, the database refuses the second baseline for the mission, so
    an evidence bundle cannot carry two of them for one snapshot.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mission = models.OneToOneField(
        Mission, on_delete=models.CASCADE, related_name="baseline"
    )
    configure_ok = models.BooleanField()
    build_ok = models.BooleanField()
    tests_total = models.PositiveIntegerField(default=0)
    tests_passed = models.PositiveIntegerField(default=0)
    tests_failed = models.PositiveIntegerField(default=0)
    duration_seconds = models.FloatField(default=0.0)
    adapter = models.CharField(max_length=100)
    recorded_at = models.DateTimeField()
    log_ref = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "baseline_report"


class Finding(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mission = models.ForeignKey(
        Mission, on_delete=models.CASCADE, related_name="findings"
    )
    category = models.CharField(
        max_length=ENUM_MAX_LENGTH, choices=_choices(FindingCategory)
    )
    severity = models.CharField(max_length=ENUM_MAX_LENGTH, choices=_choices(Severity))
    tool = models.CharField(max_length=ENUM_MAX_LENGTH, choices=_choices(AnalyzerTool))
    discovery_method = models.CharField(
        max_length=ENUM_MAX_LENGTH,
        choices=_choices(DiscoveryMethod),
        help_text="No default: only FUZZING_CAMPAIGN supports 'our fuzzer found it'.",
    )
    replay_source = models.CharField(max_length=500, null=True, blank=True)
    file_path = models.CharField(max_length=1000)
    line = models.PositiveIntegerField(null=True, blank=True)
    function = models.CharField(max_length=300, null=True, blank=True)
    fingerprint = models.CharField(max_length=128)
    reproducible = models.BooleanField(
        default=False,
        help_text="True only when a minimized input replayed from a clean build.",
    )
    title = models.CharField(max_length=300)
    sanitizer_report = models.TextField(max_length=20000, default="", blank=True)
    code_slice = models.TextField(max_length=20000, default="", blank=True)
    detected_at = models.DateTimeField()

    class Meta:
        db_table = "finding"
        ordering = ["detected_at"]
        indexes = [
            models.Index(fields=["mission", "fingerprint"], name="finding_fp_idx"),
        ]


class Reproducer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    finding = models.ForeignKey(
        Finding, on_delete=models.CASCADE, related_name="reproducers"
    )
    minimized = models.BooleanField(default=False)
    replay_attempts = models.PositiveIntegerField(default=0)
    replay_successes = models.PositiveIntegerField(default=0)
    test_command = models.CharField(max_length=1000)
    artifact = models.JSONField(default=dict)
    created_at = models.DateTimeField()

    class Meta:
        db_table = "reproducer"


class FuzzingReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mission = models.ForeignKey(
        Mission, on_delete=models.CASCADE, related_name="fuzzing_reports"
    )
    mode = models.CharField(
        max_length=ENUM_MAX_LENGTH,
        choices=_choices(FuzzingMode),
        help_text="No default: a replayed corpus cannot be reported as a live run.",
    )
    harness = models.CharField(max_length=200)
    engine = models.CharField(max_length=100, default="libFuzzer")
    runtime_seconds = models.FloatField(default=0.0)
    executions = models.BigIntegerField(default=0)
    crashes_found = models.PositiveIntegerField(default=0)
    unique_crashes = models.PositiveIntegerField(default=0)
    corpus_size = models.PositiveIntegerField(default=0)
    sanitizers = models.JSONField(default=list)
    replay_source = models.CharField(max_length=500, null=True, blank=True)
    recorded_at = models.DateTimeField()

    class Meta:
        db_table = "fuzzing_report"


class PatchCandidate(models.Model):
    """One candidate diff. `PATCH` produces N of these; `VERIFY` produces one
    `VerificationRecord` per policy-passing one (#80).

    Inserting one is *not* a plain `save()`. Go through
    `orchestrator.candidates.record_patch_candidate`, which takes the mission row lock
    and refuses once `Mission.verification_started_at` is set (D-046).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mission = models.ForeignKey(
        Mission, on_delete=models.CASCADE, related_name="patch_candidates"
    )
    finding = models.ForeignKey(
        Finding, on_delete=models.CASCADE, related_name="patch_candidates"
    )
    provenance = models.CharField(
        max_length=ENUM_MAX_LENGTH,
        choices=_choices(PatchProvenance),
        help_text="Never inflated: an operator-written candidate is labelled as one.",
    )
    model_provenance = models.JSONField(
        null=True,
        blank=True,
        help_text="ModelProvenance. Present only when provenance is MODEL_GENERATED.",
    )
    diff = models.TextField(max_length=200000)
    files_changed = models.PositiveIntegerField(default=0)
    lines_changed = models.PositiveIntegerField(default=0)
    policy_status = models.CharField(
        max_length=ENUM_MAX_LENGTH, choices=_choices(PatchPolicyStatus)
    )
    policy_detail = models.CharField(max_length=2000, default="", blank=True)
    rationale = models.TextField(max_length=5000, default="", blank=True)
    created_at = models.DateTimeField()

    class Meta:
        db_table = "patch_candidate"
        ordering = ["created_at"]

    def clean(self) -> None:
        """Validate the candidate against the frozen schema, and honour the freeze.

        Two properties, both of which used to live only in
        `orchestrator.candidates.record_patch_candidate`:

        * **The D-046 freeze (SEC-17).** This class's own docstring said "inserting one
          is not a plain `save()`" — which is a comment, not a mechanism, and
          `PatchCandidate.objects.create()` on a frozen mission was reachable. The three
          other models in this file that need a write rule enforce it in `save()`; this
          one now does too.
        * **Provenance (D-008).** `MODEL_GENERATED` must carry `ModelProvenance` and
          `OPERATOR_SUPPLIED` must not. The schema already refuses both; running it here
          means the ORM cannot write what the contract would reject.
        """
        from contracts.schemas.evidence import PatchCandidate as PatchCandidateSchema

        if self._state.adding:
            frozen_at = (
                Mission.objects.filter(pk=self.mission_id)
                .values_list("verification_started_at", flat=True)
                .first()
            )
            if frozen_at is not None:
                raise ValidationError(
                    f"Mission {self.mission_id} froze its candidate set at "
                    f"{frozen_at.isoformat()}; a candidate added now could only be an "
                    f"attempt to generate until something passes (D-046)."
                )

        try:
            PatchCandidateSchema(
                id=self.id,
                mission_id=self.mission_id,
                finding_id=self.finding_id,
                provenance=self.provenance,
                model=self.model_provenance,
                diff=self.diff,
                files_changed=self.files_changed,
                lines_changed=self.lines_changed,
                policy_status=self.policy_status,
                policy_detail=self.policy_detail,
                rationale=self.rationale,
                created_at=self.created_at,
            )
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError(
                f"PatchCandidate does not satisfy the frozen contract: {exc}"
            ) from exc

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.clean()
        super().save(*args, **kwargs)


class VerificationRecord(models.Model):
    """A verdict and the deterministic gates that produced it.

    `gates` is the serialized `GateMatrix`; `verdict` is re-derived from it by the
    pydantic schema on the way in and on the way out. There is no writer path that can
    store a `VERIFIED` verdict over a failing regression gate.

    At most one per candidate — `unique` on `patch`. Re-verifying a candidate until it
    passes is the same failure D-046 closes at the other end, and the constraint makes
    it a database error rather than a review question.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mission = models.ForeignKey(
        Mission, on_delete=models.CASCADE, related_name="verifications"
    )
    patch = models.OneToOneField(
        PatchCandidate, on_delete=models.CASCADE, related_name="verification"
    )
    gates = models.JSONField(help_text="GateMatrix, serialized from the frozen schema.")
    verdict = models.CharField(max_length=ENUM_MAX_LENGTH, choices=_choices(Verdict))
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField()
    worktree_sha256 = models.CharField(max_length=64, null=True, blank=True)
    resource_usage = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "verification_record"
        ordering = ["started_at"]
        indexes = [
            models.Index(fields=["mission", "verdict"], name="verification_verdict_idx"),
        ]

    def clean(self) -> None:
        """Validate `gates` and `verdict` against the frozen schema (SEC-20).

        `repository.load_verifications` already re-derives the verdict on read, so a row
        that disagrees with itself cannot be *used*. That was not enough: a malformed
        blob written directly then made every transition raise on load — including
        `→ CANCELLING` and `→ FAILED`, which exist precisely so that getting out safely
        is never blocked by the bookkeeping. One bad row wedged the mission.

        Refusing on write is the first half. `orchestrator.transitions.transition`
        tolerating an unreadable set on the abort paths is the second.
        """
        from contracts.schemas.evidence import VerificationRecord as VerificationSchema

        try:
            VerificationSchema(
                id=self.id,
                mission_id=self.mission_id,
                patch_id=self.patch_id,
                gates=self.gates,
                verdict=self.verdict,
                started_at=self.started_at,
                finished_at=self.finished_at,
                worktree_sha256=self.worktree_sha256,
                resource_usage=self.resource_usage,
            )
        except Exception as exc:
            raise ValidationError(
                f"VerificationRecord does not satisfy the frozen contract: {exc}"
            ) from exc

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.clean()
        super().save(*args, **kwargs)


class ResourceSample(models.Model):
    """Measured, never estimated. `gpu_seconds` is 0.0 for this build (D-015)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mission = models.ForeignKey(
        Mission, on_delete=models.CASCADE, related_name="resource_samples"
    )
    cpu_seconds = models.FloatField(default=0.0)
    peak_memory_mb = models.FloatField(default=0.0)
    wall_seconds = models.FloatField(default=0.0)
    sandbox_count = models.PositiveIntegerField(default=0)
    gpu_seconds = models.FloatField(default=0.0)
    sampled_at = models.DateTimeField()

    class Meta:
        db_table = "resource_sample"
        ordering = ["sampled_at"]


class Artifact(models.Model):
    """The index over the content-addressed store (spec §5.2).

    `sha256` is the primary key, which is the whole point: the same bytes written twice
    are one row, and the manifest *is* the integrity proof rather than a claim beside it.
    """

    sha256 = models.CharField(max_length=64, primary_key=True)
    kind = models.CharField(max_length=64)
    size_bytes = models.BigIntegerField(default=0)
    mission = models.ForeignKey(
        Mission, on_delete=models.CASCADE, related_name="artifacts"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "artifact"
        ordering = ["created_at"]


class Export(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mission = models.ForeignKey(
        Mission, on_delete=models.CASCADE, related_name="exports"
    )
    formats = models.JSONField(default=list)
    artifact_refs = models.JSONField(default=list)
    isolation_mode = models.CharField(
        max_length=ENUM_MAX_LENGTH,
        choices=_choices(IsolationMode),
        help_text="How the target was contained. No default (D-049): the stronger "
        "claim must never be made by omission.",
    )
    recommended_patch = models.ForeignKey(
        PatchCandidate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recommended_by_exports",
        help_text="The one diff we stand behind. Validated against the verification "
        "records by EvidenceBundle before the bundle is written.",
    )
    generated_at = models.DateTimeField()

    class Meta:
        db_table = "export"
        ordering = ["-generated_at"]
