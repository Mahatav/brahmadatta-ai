"""Fixtures for the persisted state machine.

Everything here writes real rows through the real code paths. There is no fixture that
sets `Mission.state` directly, because the whole point of `orchestrator.transitions` is
that it is the only writer — a fixture that bypassed it would let a test pass against
a state no transition could actually produce.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from contracts.enums import (
    AnalyzerTool,
    DiscoveryMethod,
    EvidenceSource,
    FindingCategory,
    GateName,
    GateStatus,
    LanguageAdapter,
    MissionState,
    Severity,
)
from contracts.verdict import GateMatrix, GateResult
from missions.models import Authorization, Finding, Mission, Snapshot
from orchestrator import transitions

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
SNAPSHOT_SHA = "a" * 64
TRACE = "test-trace-0000000000000000"

#: The controlled C target from #74. Its two committed candidate diffs are what let the
#: fan-out be tested end to end today, with no model and no fuzzer.
DEMO_ROOT = (
    Path(__file__).resolve().parents[4] / "demo" / "repositories" / "pktcfg" / "patches"
)
CANDIDATE_A = DEMO_ROOT / "candidate-a-correct-bounds-fix.patch"
CANDIDATE_B = DEMO_ROOT / "candidate-b-rejected-crash-only-fix.patch"


@pytest.fixture
def mission(db) -> Mission:
    row = Mission.objects.create(
        name="pktcfg demo",
        repository_ref="file:///demo/repositories/pktcfg",
        adapter=LanguageAdapter.C_CMAKE_CTEST.value,
        policy={},
    )
    Authorization.objects.create(
        mission=row,
        statement="I am authorized to test this repository on behalf of the owner.",
        granted_by="Mahatav Arora",
        granted_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(hours=8),
        repository_ref="file:///demo/repositories/pktcfg",
    )
    Snapshot.objects.create(
        mission=row,
        commit_sha="0" * 40,
        archive_sha256=SNAPSHOT_SHA,
        file_count=31,
        bytes_total=120_000,
    )
    return row


@pytest.fixture
def finding(mission: Mission) -> Finding:
    return Finding.objects.create(
        mission=mission,
        category=FindingCategory.HEAP_BUFFER_OVERFLOW.value,
        severity=Severity.HIGH.value,
        tool=AnalyzerTool.ADDRESS_SANITIZER.value,
        discovery_method=DiscoveryMethod.FUZZING_CAMPAIGN.value,
        file_path="src/decode.c",
        line=74,
        function="pkt_decoded_length",
        fingerprint="pktcfg-literal-tab-overflow",
        reproducible=True,
        title="heap-buffer-overflow expanding a literal tab",
        detected_at=NOW,
    )


def walk_to(mission: Mission, target: MissionState, now=NOW) -> None:
    """Drive the mission along the happy path to `target`, one real transition each."""
    path = [
        MissionState.AUTHORIZED,
        MissionState.SNAPSHOTTED,
        MissionState.VALIDATING,
        MissionState.BASELINE,
        MissionState.TRIAGE,
        MissionState.STRESS_TEST,
        MissionState.CORRELATE,
        MissionState.PATCH,
        MissionState.VERIFY,
        MissionState.EXPORTING,
    ]
    for state in path:
        transitions.transition(mission.id, state, trace_id=TRACE, now=now)
        mission.refresh_from_db()
        if state is target:
            return
    if mission.state_enum is not target:  # pragma: no cover - test wiring guard
        raise AssertionError(f"{target} is not on the happy path")


def gate_matrix(
    *,
    compile_=GateStatus.PASS,
    reproducer=GateStatus.PASS,
    regression=GateStatus.PASS,
) -> GateMatrix:
    def gate(name: GateName, status: GateStatus) -> GateResult:
        if status is GateStatus.NOT_RUN:
            return GateResult.not_run(name, "not run in this scope")
        return GateResult(
            name=name,
            status=status,
            evidence_source=EvidenceSource.TOOL_EXECUTION,
            tool="ctest 3.28.3",
        )

    return GateMatrix(
        compile=gate(GateName.COMPILE, compile_),
        reproducer_eliminated=gate(GateName.REPRODUCER_ELIMINATED, reproducer),
        regression_preserved=gate(GateName.REGRESSION_PRESERVED, regression),
    )
