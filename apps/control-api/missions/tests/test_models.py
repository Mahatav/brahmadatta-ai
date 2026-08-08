"""#14 — the persistence rules the architecture spec §5.1 hands the schema.

Each of these is a property the spec states in prose. A property is described as
enforced only when a named test demonstrates it, so each one gets a test here rather
than a sentence in a docstring.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from contracts.enums import EventType, LanguageAdapter, MissionState, Severity
from missions.models import (
    Authorization,
    Job,
    JobKind,
    Mission,
    MissionEvent,
    Snapshot,
)

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)


@pytest.fixture
def mission() -> Mission:
    return Mission.objects.create(
        name="pktcfg",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )


def test_a_new_mission_starts_in_created_with_nothing_claimed(mission: Mission):
    assert mission.state_enum is MissionState.CREATED
    assert mission.paused_from is None
    assert mission.verification_started_at is None
    assert mission.verdict is None


def test_an_authorization_cannot_be_edited_after_it_is_written(mission: Mission):
    """The evidence bundle reproduces this record verbatim to show authority existed at
    the moment each stage ran. An edited record cannot show that."""
    record = Authorization.objects.create(
        mission=mission,
        statement="I am authorized to test this repository on behalf of the owner.",
        granted_by="Mahatav Arora",
        granted_at=NOW,
        expires_at=NOW + timedelta(hours=4),
        repository_ref="file:///demo/repositories/pktcfg",
    )

    record.statement = "Something more convenient."
    with pytest.raises(ValidationError) as excinfo:
        record.save()
    assert "append-only" in str(excinfo.value)

    record.refresh_from_db()
    assert record.statement.startswith("I am authorized")


def test_a_snapshot_cannot_be_edited_after_it_is_written(mission: Mission):
    """Swapping the archive after authorization must not be expressible as an edit."""
    snapshot = Snapshot.objects.create(
        mission=mission, archive_sha256="a" * 64, file_count=1, bytes_total=1
    )
    snapshot.archive_sha256 = "b" * 64
    with pytest.raises(ValidationError):
        snapshot.save()


def test_an_emitted_event_cannot_be_edited(mission: Mission):
    event = _event(mission, 1)
    event.message = "different"
    with pytest.raises(ValidationError):
        event.save()


def test_the_event_sequence_is_unique_per_mission(mission: Mission):
    """The backstop under `orchestrator.events.next_sequence`. If allocation ever
    escapes the mission row lock, this turns a silently reused ordinal — which would
    make the SSE gap detector lie — into an IntegrityError."""
    _event(mission, 1)
    with pytest.raises(IntegrityError):
        _event(mission, 1)


def test_two_missions_have_independent_sequences(mission: Mission):
    other = Mission.objects.create(
        name="other",
        repository_ref="file:///demo/repositories/other",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    _event(mission, 1)
    _event(other, 1)
    assert MissionEvent.objects.count() == 2


def test_a_job_cannot_be_enqueued_without_a_deadline(mission: Mission):
    """§3.3 property 3. A job with no deadline is the one still running at 03:00 with
    nobody watching."""
    with pytest.raises(IntegrityError):
        Job.objects.create(
            mission=mission,
            kind=JobKind.FUZZ,
            run_after=NOW,
            deadline_at=None,
        )


def test_verify_jobs_are_not_retryable():
    """§3.4. Retrying a verification is how a flaky pass becomes a verdict."""
    from missions.models import MAX_ATTEMPTS_BY_KIND

    assert MAX_ATTEMPTS_BY_KIND[JobKind.VERIFY] == 1
    assert MAX_ATTEMPTS_BY_KIND[JobKind.BASELINE] == 1
    assert MAX_ATTEMPTS_BY_KIND[JobKind.EXPORT] == 3


def _event(mission: Mission, sequence: int) -> MissionEvent:
    return MissionEvent.objects.create(
        mission=mission,
        sequence=sequence,
        timestamp=NOW,
        type=EventType.LOG.value,
        state=mission.state,
        severity=Severity.INFO.value,
        message="hello",
        payload={"kind": "log", "text": "hello"},
        trace_id="trace-0000000000000000",
    )


# --- SEC-20: the on-write validation the docstrings used to claim -----------------


def test_a_malformed_gate_matrix_is_refused_on_write(mission: Mission):
    """The module docstring claimed this twice and implemented it zero times, which a
    security review caught by writing `gates={'not': 'a gate matrix'}` with a VERIFIED
    verdict and having it accepted."""
    from missions.models import Finding, PatchCandidate, VerificationRecord

    finding = Finding.objects.create(
        mission=mission,
        category="HEAP_BUFFER_OVERFLOW",
        severity="HIGH",
        tool="ADDRESS_SANITIZER",
        discovery_method="FUZZING_CAMPAIGN",
        file_path="src/decode.c",
        fingerprint="fp",
        reproducible=True,
        title="t",
        detected_at=NOW,
    )
    patch = PatchCandidate.objects.create(
        mission=mission,
        finding=finding,
        provenance="OPERATOR_SUPPLIED",
        diff="--- a\n+++ b\n",
        files_changed=1,
        lines_changed=1,
        policy_status="ACCEPTED",
        created_at=NOW,
    )

    with pytest.raises(ValidationError):
        VerificationRecord.objects.create(
            mission=mission,
            patch=patch,
            gates={"not": "a gate matrix"},
            verdict="VERIFIED",
            started_at=NOW,
            finished_at=NOW,
        )
    assert VerificationRecord.objects.count() == 0


def test_a_verdict_disagreeing_with_its_gates_is_refused_on_write(mission: Mission):
    """The same validator that refuses a malformed blob refuses a dishonest one."""
    from contracts.enums import EvidenceSource, GateName, GateStatus
    from contracts.verdict import GateMatrix, GateResult
    from missions.models import Finding, PatchCandidate, VerificationRecord

    finding = Finding.objects.create(
        mission=mission,
        category="HEAP_BUFFER_OVERFLOW",
        severity="HIGH",
        tool="ADDRESS_SANITIZER",
        discovery_method="FUZZING_CAMPAIGN",
        file_path="src/decode.c",
        fingerprint="fp",
        reproducible=True,
        title="t",
        detected_at=NOW,
    )
    patch = PatchCandidate.objects.create(
        mission=mission,
        finding=finding,
        provenance="OPERATOR_SUPPLIED",
        diff="--- a\n+++ b\n",
        files_changed=1,
        lines_changed=1,
        policy_status="ACCEPTED",
        created_at=NOW,
    )

    def gate(name, status):
        return GateResult(
            name=name,
            status=status,
            evidence_source=EvidenceSource.TOOL_EXECUTION,
            tool="ctest 3.28.3",
        )

    failing = GateMatrix(
        compile=gate(GateName.COMPILE, GateStatus.PASS),
        reproducer_eliminated=gate(GateName.REPRODUCER_ELIMINATED, GateStatus.PASS),
        regression_preserved=gate(GateName.REGRESSION_PRESERVED, GateStatus.FAIL),
    ).model_dump(mode="json")

    with pytest.raises(ValidationError):
        VerificationRecord.objects.create(
            mission=mission,
            patch=patch,
            gates=failing,
            verdict="VERIFIED",
            started_at=NOW,
            finished_at=NOW,
        )


# --- SEC-17: the freeze has a model-level backstop, like the other three models ----


def test_a_candidate_cannot_be_inserted_into_a_frozen_mission_by_any_path(
    mission: Mission,
):
    """`PatchCandidate.objects.create()` bypassed the recorder and its docstring said
    "inserting one is not a plain save()" — which is a comment, not a mechanism. The
    three other models in this file that need a write rule enforce it in `save()`."""
    from missions.lifecycle import lifecycle_write
    from missions.models import Finding, PatchCandidate

    finding = Finding.objects.create(
        mission=mission,
        category="HEAP_BUFFER_OVERFLOW",
        severity="HIGH",
        tool="ADDRESS_SANITIZER",
        discovery_method="FUZZING_CAMPAIGN",
        file_path="src/decode.c",
        fingerprint="fp",
        reproducible=True,
        title="t",
        detected_at=NOW,
    )
    with lifecycle_write():
        mission.verification_started_at = NOW
        mission.save(update_fields=["verification_started_at", "updated_at"])

    with pytest.raises(ValidationError) as excinfo:
        PatchCandidate.objects.create(
            mission=mission,
            finding=finding,
            provenance="OPERATOR_SUPPLIED",
            diff="--- a\n+++ b\n",
            files_changed=1,
            lines_changed=1,
            policy_status="ACCEPTED",
            created_at=NOW,
        )
    assert "froze its candidate set" in str(excinfo.value)
    assert PatchCandidate.objects.filter(mission=mission).count() == 0
