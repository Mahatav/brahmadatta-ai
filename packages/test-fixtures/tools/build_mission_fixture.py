"""Build the committed mission fixture from the real contract models.

Run this only when the fixture needs to change. The output it writes —
`packages/test-fixtures/missions/mission-pktcfg-001.events.jsonl` — is committed, and
that committed file is what the replay command and the Command Center consume. Nothing
downstream imports this script.

Why a generator instead of hand-written JSON:

*   Every event is constructed as a real `contracts.schemas.envelope.MissionEvent`. The
    cross-field validators that JSON Schema cannot express — `derive_verdict` agreeing
    with the stored verdict, `MissionVerdictSummary` counts matching its own candidate
    list, `MODEL_GENERATED` requiring `ModelProvenance`, `REPLAYED_CORPUS` requiring a
    `replay_source` — all run here. A fixture that violates one of them cannot be
    written in the first place.
*   The state transitions are checked against `contracts.state_machine.TRANSITIONS` and
    the stage ordering against D-038, so the fixture cannot drift out of the ruling that
    every Command Center panel is going to inherit.

Every number in the fixture is a measurement, not an invention. See
`missions/mission-pktcfg-001.provenance.json` for the commands that produced each one and
the machine they were produced on. That file is the audit trail for the "no decorative
fake metrics" rule: if a value here is not traceable to a line in it, it should not be
here.

Usage::

    DJANGO_SETTINGS_MODULE=config.settings.test \
    DJANGO_SECRET_KEY=fixture-build-not-a-real-secret-0123456789abcdef \
    DATABASE_URL=sqlite:///fixture-build.sqlite3 \
    PYTHONPATH=apps/control-api \
    python packages/test-fixtures/tools/build_mission_fixture.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = REPO_ROOT / "packages" / "test-fixtures" / "missions"
OUTPUT = FIXTURE_DIR / "mission-pktcfg-001.events.jsonl"

# The control API is not an installed package; it is a sibling application. Adding it to
# sys.path here rather than requiring the caller to get PYTHONPATH right keeps the
# failure mode "the contract changed" instead of "your shell was wrong".
sys.path.insert(0, str(REPO_ROOT / "apps" / "control-api"))

import django  # noqa: E402

django.setup()

from contracts.enums import (  # noqa: E402
    AnalyzerTool,
    DiscoveryMethod,
    ErrorCode,
    EventStatus,
    EventType,
    EvidenceSource,
    FindingCategory,
    FuzzingMode,
    GateName,
    GateStatus,
    MissionStage,
    MissionState,
    PatchPolicyStatus,
    PatchProvenance,
    Severity,
    Verdict,
    posture_for,
)
from contracts.schemas.common import ArtifactRef, ResourceUsage  # noqa: E402
from contracts.schemas.envelope import (  # noqa: E402
    BaselinePayload,
    EvidenceExportPayload,
    FindingPayload,
    FuzzingPayload,
    LogPayload,
    MissionEvent,
    MissionVerdictPayload,
    PatchCandidatePayload,
    PolicyViolationPayload,
    ReproducerPayload,
    ResourceUsagePayload,
    SnapshotPayload,
    StageProgressPayload,
    StateChangedPayload,
    TeardownPayload,
    VerificationPayload,
)
from contracts.schemas.evidence import (  # noqa: E402
    BaselineReport,
    CandidateVerdict,
    ExportReceipt,
    FindingSummary,
    FuzzingReport,
    MissionVerdictSummary,
    ModelProvenance,
    PatchCandidate,
    ReproducerRecord,
    SourceLocation,
    VerificationRecord,
)
from contracts.state_machine import STAGE_FOR_STATE, TRANSITIONS  # noqa: E402
from contracts.verdict import GateMatrix, GateResult  # noqa: E402

# --- identity -------------------------------------------------------------------
#
# Fixed UUIDs. A fixture that generates fresh ids on every build produces a different
# file every run, which makes `git diff` useless and makes a Command Center panel's
# stored state meaningless between two replays.

MISSION_ID = UUID("b7ad2c10-4f61-4f6d-9d2e-1c7a4b6d0e11")
FINDING_ID = UUID("2f9a5d33-8c4b-4a1e-9f70-6b2d9e5c1a04")
REPRODUCER_ID = UUID("9c1e7b52-3d08-4c6f-8a19-42f0b7d3e5c6")
PATCH_A_ID = UUID("41d0c8a7-6e35-4b92-8f4c-0d17a2e9b3f8")
PATCH_B_ID = UUID("58e3f1b9-2a47-4d80-b6e1-9c04f7a2d51e")
PATCH_Z_ID = UUID("6a72d4c8-1b59-4e3a-97f2-5d80c6b1e4a3")
VERIFY_A_ID = UUID("7b83e5d0-9c26-4f17-a48b-3e10d9f6c2b5")
VERIFY_B_ID = UUID("83c9f6e1-0d37-4a28-b59c-4f21e0a7d3c6")
EXPORT_ID = UUID("94dae7f2-1e48-4b39-a60d-5032f1b8e4d7")

TRACE_ID = "fixture-pktcfg-001"
ADAPTER = "C_CMAKE_CTEST"

T0 = datetime(2026, 8, 7, 13, 0, 0, tzinfo=UTC)

# --- measured constants ---------------------------------------------------------
#
# Each of these came off a real run on 2026-08-07; provenance.json records the exact
# command. Do not adjust one to make a panel look better — regenerate from a new run and
# update provenance.json with it.

SNAPSHOT_SHA = "3848673e21381f571831cf47b185758e89f76393687ea70932527aa42ac8b3d5"
SNAPSHOT_FILES = 31
SNAPSHOT_BYTES = 57042

CONFIGURE_SECONDS = 0.641
BUILD_SECONDS = 0.490
CTEST_SECONDS = 2.177
BASELINE_WALL_SECONDS = round(CONFIGURE_SECONDS + BUILD_SECONDS + CTEST_SECONDS, 3)
BASELINE_CPU_SECONDS = round(0.496 + 1.325 + 0.505, 3)
BASELINE_PEAK_MB = 46.7

TESTS_TOTAL = 8
TESTS_PASSED = 8
TESTS_FAILED = 0

CRASH_SHA = "7a61fe76785718f0b94e4d60033b1f4037fa79eb7fd41039895773b91bc9eb5b"
CRASH_BYTES = 22
CORPUS_SEEDS = 8  # demo/repositories/pktcfg/corpus/*.bin
CORPUS_INPUTS = CORPUS_SEEDS + 1  # the seeds plus the recorded crash input

# candidate B loses exactly one ctest: test_tab_expansion.
B_TESTS_PASSED = 7
B_TESTS_FAILED = 1

CTEST_VERSION = "ctest 4.2.1"
CLANG_VERSION = "Apple clang 17.0.0 (arm64-apple-darwin25.5.0)"
ASAN_VERSION = "AddressSanitizer (Apple clang 17.0.0)"

DIFF_A = """diff --git a/src/decode.c b/src/decode.c
--- a/src/decode.c
+++ b/src/decode.c
@@ -72,6 +72,13 @@ size_t pkt_decoded_length(const uint8_t *src, size_t len, int escaped)
             continue;
         }

+        if (c == '\\t') {
+            /* A literal tab is expanded by pkt_decode_into(); size for it. */
+            need += PKT_TAB_WIDTH;
+            i += 1;
+            continue;
+        }
+
         /* Every remaining byte is copied through as-is. */
         need += 1;
         i += 1;
"""

DIFF_B = """diff --git a/src/decode.c b/src/decode.c
--- a/src/decode.c
+++ b/src/decode.c
@@ -27,9 +27,9 @@ static uint8_t hex_val(uint8_t c)
  * the literal branch so both forms normalise identically. */
 static size_t emit_tab(char *dst, size_t out)
 {
-    for (unsigned k = 0; k < PKT_TAB_WIDTH; k++) {
-        dst[out++] = ' ';
-    }
+    /* Writing PKT_TAB_WIDTH spaces overruns the buffer pkt_parse() allocated,
+     * so write a single space instead and stay inside it. */
+    dst[out++] = ' ';
     return out;
 }
"""

DIFF_Z = """diff --git a/CMakeLists.txt b/CMakeLists.txt
--- a/CMakeLists.txt
+++ b/CMakeLists.txt
@@ -66,7 +66,6 @@ set(PKTCFG_TESTS
   test_truncation
   test_limits
   test_lookup
-  test_tab_expansion
 )
"""

SANITIZER_REPORT = """AddressSanitizer: heap-buffer-overflow
WRITE of size 1
    #0 emit_tab decode.c:43
    #1 pkt_decode_into decode.c:148
    #2 pkt_parse parse.c:126
    #3 pktcfg_fuzz_one_input fuzz_entry.c:26
0 bytes after a 4-byte region allocated at parse.c:120
SUMMARY: AddressSanitizer: heap-buffer-overflow decode.c:43 in emit_tab"""


def artifact(kind: str, name: str) -> str:
    return f"artifact://{MISSION_ID}/{kind}/{name}"


# --- builder --------------------------------------------------------------------


class Builder:
    """Accumulates events, assigning sequence numbers and checking the invariants
    every Command Center panel will assume."""

    def __init__(self) -> None:
        self.events: list[MissionEvent] = []
        self._sequence = 0
        self._elapsed = 0.0
        self._state = MissionState.CREATED
        self._stage_order: list[MissionStage] = []

    def add(
        self,
        *,
        after_seconds: float,
        type: EventType,
        state: MissionState,
        message: str,
        payload: object,
        stage: MissionStage | None = None,
        status: EventStatus = EventStatus.RUNNING,
        severity: Severity = Severity.INFO,
        evidence_refs: list[str] | None = None,
        metrics: dict[str, float] | None = None,
    ) -> None:
        self._sequence += 1
        self._elapsed += after_seconds

        if state is not self._state:
            allowed = TRANSITIONS[self._state]
            if state not in allowed:
                raise ValueError(
                    f"event {self._sequence}: {self._state} -> {state} is not a legal "
                    f"transition. Legal: {sorted(s.value for s in allowed)}"
                )
            self._state = state

        if stage is not None and (not self._stage_order or self._stage_order[-1] is not stage):
            self._stage_order.append(stage)

        self.events.append(
            MissionEvent(
                id=UUID(int=(0x5EED_0000_0000_0000 << 64) + self._sequence),
                mission_id=MISSION_ID,
                sequence=self._sequence,
                timestamp=T0 + timedelta(seconds=round(self._elapsed, 3)),
                type=type,
                stage=stage,
                state=state,
                status=status,
                severity=severity,
                message=message,
                payload=payload,  # type: ignore[arg-type]
                evidence_refs=evidence_refs or [],
                metrics=metrics or {},
                trace_id=TRACE_ID,
            )
        )

    # -- invariants ---------------------------------------------------------------

    def check(self) -> None:
        sequences = [event.sequence for event in self.events]
        expected = list(range(1, len(self.events) + 1))
        assert sequences == expected, (
            "the stored event log must be gap-free — a gap is something the transport "
            "loses, never something the server recorded. The replay command injects the "
            "gap at stream time; see sse_replay.py --drop."
        )

        timestamps = [event.timestamp for event in self.events]
        assert timestamps == sorted(timestamps), "timestamps must be non-decreasing"

        # `STAGE_FOR_STATE` says which stage executes while the mission sits in a state.
        # Every event must agree with it, with one deliberate exception: `STAGE_STARTED`
        # announces the stage that is *about to* run, and a stage runs before the state
        # transition it produces. Ingest starts while the mission is still AUTHORIZED and
        # is what moves it to SNAPSHOTTED. So a STAGE_STARTED may name a stage the current
        # state does not yet own; nothing else may.
        for event in self.events:
            if event.stage is None:
                continue
            expected_stage = STAGE_FOR_STATE[event.state]
            if event.type is EventType.STAGE_STARTED and event.stage is not expected_stage:
                continue
            assert event.stage is expected_stage, (
                f"event {event.sequence}: state {event.state} runs stage "
                f"{expected_stage}, not {event.stage}"
            )
            assert event.payload.kind  # every payload carries its discriminator

        for event in self.events:
            payload = event.payload
            if payload.kind == "state_changed":
                assert payload.posture is posture_for(payload.to_state), (
                    f"event {event.sequence}: posture must be derived from the state, "
                    f"never chosen"
                )

        # D-038: STRESS_TEST precedes CORRELATE, and PATCH follows CORRELATE.
        ruled_order = [
            MissionStage.AUTHORIZE,
            MissionStage.INGEST,
            MissionStage.BASELINE,
            MissionStage.ANALYZE,
            MissionStage.STRESS_TEST,
            MissionStage.CORRELATE,
            MissionStage.PATCH,
            MissionStage.VERIFY,
            MissionStage.EXPORT_EVIDENCE,
        ]
        first_seen: list[MissionStage] = []
        for stage in self._stage_order:
            if stage not in first_seen:
                first_seen.append(stage)
        assert first_seen == ruled_order, (
            f"stage order must follow D-038 {[s.value for s in ruled_order]}; "
            f"fixture has {[s.value for s in first_seen]}"
        )

        assert self._state is MissionState.VERIFIED, (
            f"the fixture must end VERIFIED, ended {self._state}"
        )

        kinds = {event.payload.kind for event in self.events}
        required_kinds = {
            "state_changed",
            "stage_progress",
            "snapshot",
            "baseline",
            "finding",
            "reproducer",
            "fuzzing",
            "patch_candidate",
            "verification",
            "mission_verdict",
            "evidence_export",
            "resource_usage",
            "teardown",
            "policy_violation",
            "log",
        }
        missing = required_kinds - kinds
        assert not missing, f"fixture does not exercise payload kinds: {sorted(missing)}"

        statuses = {event.status for event in self.events}
        assert EventStatus.FAILED in statuses, "fixture must include a failed stage"


def build() -> Builder:
    b = Builder()

    # -- AUTHORIZE ---------------------------------------------------------------
    b.add(
        after_seconds=0,
        type=EventType.MISSION_CREATED,
        state=MissionState.CREATED,
        stage=None,
        status=EventStatus.SUCCEEDED,
        message="Mission created for demo/repositories/pktcfg.",
        payload=StateChangedPayload(
            from_state=None,
            to_state=MissionState.CREATED,
            posture=posture_for(MissionState.CREATED),
            reason="Operator opened a mission against the authorized demo target.",
        ),
    )
    b.add(
        after_seconds=0.4,
        type=EventType.STAGE_STARTED,
        state=MissionState.CREATED,
        stage=MissionStage.AUTHORIZE,
        message="Checking the authorization record.",
        payload=StageProgressPayload(
            stage=MissionStage.AUTHORIZE,
            percent_complete=0.0,
            detail="Nothing may run before this stage completes.",
        ),
    )
    b.add(
        after_seconds=0.3,
        type=EventType.MISSION_AUTHORIZED,
        state=MissionState.AUTHORIZED,
        stage=MissionStage.AUTHORIZE,
        status=EventStatus.SUCCEEDED,
        message="Authorization active: pktcfg is a first-party target authorized in writing.",
        payload=StateChangedPayload(
            from_state=MissionState.CREATED,
            to_state=MissionState.AUTHORIZED,
            posture=posture_for(MissionState.AUTHORIZED),
            reason="Authorization record verified: unrevoked, unexpired, covers the snapshot.",
        ),
        evidence_refs=[artifact("authorization", "record-001")],
    )
    b.add(
        after_seconds=0.1,
        type=EventType.STAGE_COMPLETED,
        state=MissionState.AUTHORIZED,
        stage=MissionStage.AUTHORIZE,
        status=EventStatus.SUCCEEDED,
        message="Authorize complete.",
        payload=StageProgressPayload(
            stage=MissionStage.AUTHORIZE, percent_complete=100.0, detail="Authorized."
        ),
    )

    # -- INGEST ------------------------------------------------------------------
    b.add(
        after_seconds=0.2,
        type=EventType.STAGE_STARTED,
        state=MissionState.AUTHORIZED,
        stage=MissionStage.INGEST,
        message="Taking an immutable snapshot of the repository.",
        payload=StageProgressPayload(
            stage=MissionStage.INGEST, percent_complete=0.0, detail="Walking the tree."
        ),
    )
    b.add(
        after_seconds=1.1,
        type=EventType.SNAPSHOT_RECORDED,
        state=MissionState.SNAPSHOTTED,
        stage=MissionStage.INGEST,
        status=EventStatus.SUCCEEDED,
        message=f"Snapshot recorded: {SNAPSHOT_FILES} files, {SNAPSHOT_BYTES} bytes.",
        payload=SnapshotPayload(
            snapshot_sha256=SNAPSHOT_SHA,
            commit_sha=None,
            file_count=SNAPSHOT_FILES,
            bytes_total=SNAPSHOT_BYTES,
        ),
        evidence_refs=[artifact("snapshot", SNAPSHOT_SHA[:16])],
        metrics={"file_count": float(SNAPSHOT_FILES), "bytes_total": float(SNAPSHOT_BYTES)},
    )
    b.add(
        after_seconds=0.1,
        type=EventType.STAGE_COMPLETED,
        state=MissionState.SNAPSHOTTED,
        stage=MissionStage.INGEST,
        status=EventStatus.SUCCEEDED,
        message="Ingest complete.",
        payload=StageProgressPayload(
            stage=MissionStage.INGEST,
            percent_complete=100.0,
            detail="Snapshot is immutable; every later stage reads this digest.",
        ),
    )
    b.add(
        after_seconds=0.2,
        type=EventType.STATE_CHANGED,
        state=MissionState.VALIDATING,
        stage=MissionStage.INGEST,
        message="Running preflight.",
        payload=StateChangedPayload(
            from_state=MissionState.SNAPSHOTTED,
            to_state=MissionState.VALIDATING,
            posture=posture_for(MissionState.VALIDATING),
            reason="Validating adapter, commands and resource limits before anything runs.",
        ),
    )
    b.add(
        after_seconds=0.9,
        type=EventType.PREFLIGHT_COMPLETED,
        state=MissionState.VALIDATING,
        stage=MissionStage.INGEST,
        status=EventStatus.SUCCEEDED,
        message="Preflight passed: adapter C_CMAKE_CTEST, subprocess jail available.",
        payload=LogPayload(
            text=(
                "preflight ok — authorization active, adapter C_CMAKE_CTEST resolved from "
                "CMakeLists.txt, isolation SUBPROCESS_JAIL (weaker than a rootless "
                "container; see services/sandbox/README.md), wall-clock budget 900s."
            )
        ),
    )

    # -- BASELINE ----------------------------------------------------------------
    b.add(
        after_seconds=0.2,
        type=EventType.STATE_CHANGED,
        state=MissionState.BASELINE,
        stage=MissionStage.BASELINE,
        message="Establishing the baseline.",
        payload=StateChangedPayload(
            from_state=MissionState.VALIDATING,
            to_state=MissionState.BASELINE,
            posture=posture_for(MissionState.BASELINE),
            reason="A patch cannot be judged without a green denominator to judge it against.",
        ),
    )
    b.add(
        after_seconds=0.1,
        type=EventType.STAGE_STARTED,
        state=MissionState.BASELINE,
        stage=MissionStage.BASELINE,
        message="cmake configure.",
        payload=StageProgressPayload(
            stage=MissionStage.BASELINE,
            percent_complete=0.0,
            detail="cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug -DPKTCFG_SANITIZE=ON",
        ),
    )
    # --- the three events the replay command drops by default, to make a client
    #     exercise reconnect-and-replay. They are progress and telemetry, so a client
    #     that never recovers them still renders a coherent mission — which is the
    #     point: the gap has to be *detected*, not merely survived.
    b.add(
        after_seconds=CONFIGURE_SECONDS,
        type=EventType.STAGE_PROGRESS,
        state=MissionState.BASELINE,
        stage=MissionStage.BASELINE,
        message="Configure succeeded.",
        payload=StageProgressPayload(
            stage=MissionStage.BASELINE, percent_complete=20.0, detail="configure ok"
        ),
        metrics={"configure_seconds": CONFIGURE_SECONDS},
    )
    b.add(
        after_seconds=BUILD_SECONDS,
        type=EventType.STAGE_PROGRESS,
        state=MissionState.BASELINE,
        stage=MissionStage.BASELINE,
        message="Build succeeded with ASan and UBSan enabled.",
        payload=StageProgressPayload(
            stage=MissionStage.BASELINE, percent_complete=55.0, detail="build ok"
        ),
        metrics={"build_seconds": BUILD_SECONDS},
    )
    b.add(
        after_seconds=0.1,
        type=EventType.RESOURCE_USAGE_SAMPLED,
        state=MissionState.BASELINE,
        stage=MissionStage.BASELINE,
        message="Sandbox resource sample.",
        payload=ResourceUsagePayload(
            usage=ResourceUsage(
                cpu_seconds=round(0.496 + 1.325, 3),
                peak_memory_mb=BASELINE_PEAK_MB,
                wall_seconds=round(CONFIGURE_SECONDS + BUILD_SECONDS, 3),
                sandbox_count=1,
            )
        ),
    )
    # --- end of the dropped window ---
    b.add(
        after_seconds=CTEST_SECONDS,
        type=EventType.BASELINE_RECORDED,
        state=MissionState.BASELINE,
        stage=MissionStage.BASELINE,
        status=EventStatus.SUCCEEDED,
        message=f"Baseline recorded: {TESTS_PASSED}/{TESTS_TOTAL} tests passed.",
        payload=BaselinePayload(
            report=BaselineReport(
                mission_id=MISSION_ID,
                configure_ok=True,
                build_ok=True,
                tests_total=TESTS_TOTAL,
                tests_passed=TESTS_PASSED,
                tests_failed=TESTS_FAILED,
                duration_seconds=BASELINE_WALL_SECONDS,
                adapter=ADAPTER,
                recorded_at=T0 + timedelta(seconds=8),
                log_ref=ArtifactRef(
                    uri=artifact("baseline", "ctest-log"),
                    kind="ctest-log",
                    size_bytes=4096,
                ),
            )
        ),
        evidence_refs=[artifact("baseline", "ctest-log")],
        metrics={
            "tests_total": float(TESTS_TOTAL),
            "tests_passed": float(TESTS_PASSED),
            "tests_failed": float(TESTS_FAILED),
            "ctest_seconds": CTEST_SECONDS,
        },
    )
    b.add(
        after_seconds=0.05,
        type=EventType.BASELINE_PASSED,
        state=MissionState.BASELINE,
        stage=MissionStage.BASELINE,
        status=EventStatus.SUCCEEDED,
        message="BASELINE_PASSED — configure, build and 8 of 8 ctest cases green.",
        payload=LogPayload(
            text=(
                f"baseline passed: configure ok, build ok, {TESTS_TOTAL} tests ran, "
                f"{TESTS_FAILED} failed. This is the denominator the "
                f"REGRESSION_PRESERVED gate compares against."
            )
        ),
        metrics={
            "tests_total": float(TESTS_TOTAL),
            "tests_passed": float(TESTS_PASSED),
            "tests_failed": float(TESTS_FAILED),
        },
    )
    b.add(
        after_seconds=0.05,
        type=EventType.STAGE_COMPLETED,
        state=MissionState.BASELINE,
        stage=MissionStage.BASELINE,
        status=EventStatus.SUCCEEDED,
        message="Baseline complete.",
        payload=StageProgressPayload(
            stage=MissionStage.BASELINE, percent_complete=100.0, detail="green"
        ),
    )

    # -- ANALYZE (degraded) ------------------------------------------------------
    b.add(
        after_seconds=0.2,
        type=EventType.STATE_CHANGED,
        state=MissionState.TRIAGE,
        stage=MissionStage.ANALYZE,
        message="Static triage.",
        payload=StateChangedPayload(
            from_state=MissionState.BASELINE,
            to_state=MissionState.TRIAGE,
            posture=posture_for(MissionState.TRIAGE),
            reason="Fast deterministic pass before anything destructive runs.",
        ),
    )
    b.add(
        after_seconds=0.1,
        type=EventType.STAGE_STARTED,
        state=MissionState.TRIAGE,
        stage=MissionStage.ANALYZE,
        message="Analyze started.",
        payload=StageProgressPayload(
            stage=MissionStage.ANALYZE, percent_complete=0.0, detail="Resolving analyzers."
        ),
    )
    b.add(
        after_seconds=0.4,
        type=EventType.LOG,
        state=MissionState.TRIAGE,
        stage=MissionStage.ANALYZE,
        severity=Severity.MEDIUM,
        message="Analyze is running degraded: no static analyzer is configured.",
        payload=LogPayload(
            text=(
                "degraded — Semgrep (P1-2) and compiler-warning capture (P1-3) are cut "
                "from the seven-day build, so this stage has no analyzer to run. It "
                "completes with zero findings, which is a real result and not a failure. "
                "The STATIC_DELTA verification gate will report NOT_RUN for the same "
                "reason."
            )
        ),
    )
    b.add(
        after_seconds=0.3,
        type=EventType.STAGE_PROGRESS,
        state=MissionState.TRIAGE,
        stage=MissionStage.ANALYZE,
        severity=Severity.MEDIUM,
        message="Analyze cannot report progress.",
        payload=StageProgressPayload(
            stage=MissionStage.ANALYZE,
            percent_complete=None,
            detail=(
                "No analyzer means no denominator. percent_complete is null so the panel "
                "shows an indeterminate indicator rather than inventing a number."
            ),
        ),
    )
    b.add(
        after_seconds=0.2,
        type=EventType.STAGE_COMPLETED,
        state=MissionState.TRIAGE,
        stage=MissionStage.ANALYZE,
        status=EventStatus.SUCCEEDED,
        severity=Severity.MEDIUM,
        message="Analyze complete (degraded): 0 static findings.",
        payload=StageProgressPayload(
            stage=MissionStage.ANALYZE,
            percent_complete=100.0,
            detail="0 findings, 0 analyzers available.",
        ),
        metrics={"static_findings": 0.0, "analyzers_available": 0.0},
    )

    # -- STRESS TEST, attempt 1: FAILS ------------------------------------------
    b.add(
        after_seconds=0.2,
        type=EventType.STATE_CHANGED,
        state=MissionState.STRESS_TEST,
        stage=MissionStage.STRESS_TEST,
        message="Stress test.",
        payload=StateChangedPayload(
            from_state=MissionState.TRIAGE,
            to_state=MissionState.STRESS_TEST,
            posture=posture_for(MissionState.STRESS_TEST),
            reason="Destructive testing inside the sandbox.",
        ),
    )
    b.add(
        after_seconds=0.1,
        type=EventType.STAGE_STARTED,
        state=MissionState.STRESS_TEST,
        stage=MissionStage.STRESS_TEST,
        message="Building the libFuzzer harness.",
        payload=StageProgressPayload(
            stage=MissionStage.STRESS_TEST,
            percent_complete=0.0,
            detail="cmake -DPKTCFG_FUZZ=ON",
        ),
    )
    b.add(
        after_seconds=2.6,
        type=EventType.LOG,
        state=MissionState.STRESS_TEST,
        stage=MissionStage.STRESS_TEST,
        severity=Severity.HIGH,
        message="libFuzzer harness build failed.",
        payload=LogPayload(
            text=(
                "clang: error: unsupported option '-fsanitize=fuzzer' — the toolchain on "
                "this host does not ship the libFuzzer runtime. Apple clang does not; an "
                "LLVM clang is required. The stage fails rather than pretending a "
                "campaign ran."
            )
        ),
    )
    b.add(
        after_seconds=0.1,
        type=EventType.STAGE_COMPLETED,
        state=MissionState.STRESS_TEST,
        stage=MissionStage.STRESS_TEST,
        status=EventStatus.FAILED,
        severity=Severity.HIGH,
        message="Stress test attempt 1 failed: no libFuzzer runtime.",
        payload=StageProgressPayload(
            stage=MissionStage.STRESS_TEST,
            percent_complete=None,
            detail="Harness build failed; no campaign ran and none is reported.",
        ),
        metrics={"attempt": 1.0},
    )

    # -- STRESS TEST, attempt 2: recorded-corpus replay -------------------------
    b.add(
        after_seconds=0.3,
        type=EventType.LOG,
        state=MissionState.STRESS_TEST,
        stage=MissionStage.STRESS_TEST,
        severity=Severity.MEDIUM,
        message="Falling back to the recorded-corpus replay path.",
        payload=LogPayload(
            text=(
                "substitution REPRODUCER_REPLAY (#83): the recorded corpus is replayed "
                "through the direct harness pktcfg_replay. This is weaker than a live "
                "campaign and is reported as REPLAYED_CORPUS everywhere, including the "
                "evidence bundle's substitutions list."
            )
        ),
    )
    b.add(
        after_seconds=0.1,
        type=EventType.STAGE_STARTED,
        state=MissionState.STRESS_TEST,
        stage=MissionStage.STRESS_TEST,
        message=f"Replaying {CORPUS_INPUTS} recorded inputs through the direct harness.",
        payload=StageProgressPayload(
            stage=MissionStage.STRESS_TEST,
            percent_complete=0.0,
            detail="pktcfg_replay, ASan + UBSan build.",
        ),
        metrics={"attempt": 2.0, "corpus_size": float(CORPUS_INPUTS)},
    )
    b.add(
        after_seconds=1.8,
        type=EventType.STAGE_PROGRESS,
        state=MissionState.STRESS_TEST,
        stage=MissionStage.STRESS_TEST,
        message="6 of 9 inputs replayed.",
        payload=StageProgressPayload(
            stage=MissionStage.STRESS_TEST,
            percent_complete=66.7,
            detail="no crash yet",
        ),
    )
    b.add(
        after_seconds=1.2,
        type=EventType.STAGE_COMPLETED,
        state=MissionState.STRESS_TEST,
        stage=MissionStage.STRESS_TEST,
        status=EventStatus.SUCCEEDED,
        severity=Severity.HIGH,
        message="Stress test complete: 1 unique crash.",
        payload=FuzzingPayload(
            report=FuzzingReport(
                mission_id=MISSION_ID,
                mode=FuzzingMode.REPLAYED_CORPUS,
                harness="pktcfg_fuzz_one_input",
                engine="pktcfg_replay (direct harness)",
                runtime_seconds=3.0,
                executions=CORPUS_INPUTS,
                crashes_found=1,
                unique_crashes=1,
                corpus_size=CORPUS_INPUTS,
                sanitizers=["address", "undefined"],
                finding_ids=[FINDING_ID],
                replay_source=artifact("corpus", "pktcfg-seed-corpus"),
                recorded_at=T0 + timedelta(seconds=22),
            )
        ),
        evidence_refs=[artifact("corpus", "pktcfg-seed-corpus")],
        metrics={"executions": float(CORPUS_INPUTS), "unique_crashes": 1.0},
    )
    b.add(
        after_seconds=0.1,
        type=EventType.FINDING_RECORDED,
        state=MissionState.STRESS_TEST,
        stage=MissionStage.STRESS_TEST,
        status=EventStatus.SUCCEEDED,
        severity=Severity.CRITICAL,
        message="Heap buffer overflow in emit_tab (decode.c:43).",
        payload=FindingPayload(
            finding=FindingSummary(
                id=FINDING_ID,
                mission_id=MISSION_ID,
                category=FindingCategory.HEAP_BUFFER_OVERFLOW,
                severity=Severity.CRITICAL,
                tool=AnalyzerTool.ADDRESS_SANITIZER,
                discovery_method=DiscoveryMethod.REPLAYED_REPRODUCER,
                replay_source=artifact("corpus", "crash-literal-tab"),
                location=SourceLocation(
                    file_path="src/decode.c", line=43, function="emit_tab"
                ),
                fingerprint="asan:heap-buffer-overflow:emit_tab:pkt_decode_into:pkt_parse",
                reproducible=True,
                detected_at=T0 + timedelta(seconds=22),
                title="Out-of-bounds write when a value contains a literal tab byte",
            )
        ),
        evidence_refs=[artifact("sanitizer", "asan-report-001")],
    )
    b.add(
        after_seconds=1.4,
        type=EventType.REPRODUCER_RECORDED,
        state=MissionState.STRESS_TEST,
        stage=MissionStage.STRESS_TEST,
        status=EventStatus.SUCCEEDED,
        severity=Severity.CRITICAL,
        message=f"Minimized reproducer: {CRASH_BYTES} bytes, 5 of 5 replays fired.",
        payload=ReproducerPayload(
            reproducer=ReproducerRecord(
                id=REPRODUCER_ID,
                finding_id=FINDING_ID,
                minimized=True,
                replay_attempts=5,
                replay_successes=5,
                test_command="./build-asan/pktcfg_replay crash/crash-literal-tab.bin 5",
                artifact=ArtifactRef(
                    uri=artifact("reproducer", "crash-literal-tab.bin"),
                    kind="crash-input",
                    sha256=CRASH_SHA,
                    size_bytes=CRASH_BYTES,
                ),
                created_at=T0 + timedelta(seconds=24),
            )
        ),
        evidence_refs=[artifact("reproducer", "crash-literal-tab.bin")],
        metrics={"replay_attempts": 5.0, "replay_successes": 5.0, "input_bytes": float(CRASH_BYTES)},
    )

    # -- CORRELATE ---------------------------------------------------------------
    b.add(
        after_seconds=0.2,
        type=EventType.STATE_CHANGED,
        state=MissionState.CORRELATE,
        stage=MissionStage.CORRELATE,
        severity=Severity.HIGH,
        message="Vulnerability confirmed; correlating to source.",
        payload=StateChangedPayload(
            from_state=MissionState.STRESS_TEST,
            to_state=MissionState.CORRELATE,
            posture=posture_for(MissionState.CORRELATE),
            reason="A sanitizer-confirmed crash with a deterministic reproducer exists.",
        ),
    )
    b.add(
        after_seconds=0.1,
        type=EventType.STAGE_STARTED,
        state=MissionState.CORRELATE,
        stage=MissionStage.CORRELATE,
        message="Binding the crash to a source location.",
        payload=StageProgressPayload(
            stage=MissionStage.CORRELATE,
            percent_complete=0.0,
            detail="Reading the sanitizer frames.",
        ),
    )
    b.add(
        after_seconds=0.8,
        type=EventType.STAGE_COMPLETED,
        state=MissionState.CORRELATE,
        stage=MissionStage.CORRELATE,
        status=EventStatus.SUCCEEDED,
        severity=Severity.HIGH,
        message="Root cause: the sizing pass in pkt_decoded_length omits the literal-tab case.",
        payload=StageProgressPayload(
            stage=MissionStage.CORRELATE,
            percent_complete=100.0,
            detail=(
                "Crash site src/decode.c:43; root cause src/decode.c:75-77. Code slice "
                "bounded to 42 lines — the patch stage never receives the repository."
            ),
        ),
        evidence_refs=[artifact("sanitizer", "asan-report-001")],
        metrics={"code_slice_lines": 42.0},
    )

    # -- PATCH -------------------------------------------------------------------
    b.add(
        after_seconds=0.2,
        type=EventType.STATE_CHANGED,
        state=MissionState.PATCH,
        stage=MissionStage.PATCH,
        message="Generating patch candidates.",
        payload=StateChangedPayload(
            from_state=MissionState.CORRELATE,
            to_state=MissionState.PATCH,
            posture=posture_for(MissionState.PATCH),
            reason="One confirmed finding with a bounded code slice.",
        ),
    )
    b.add(
        after_seconds=0.1,
        type=EventType.STAGE_STARTED,
        state=MissionState.PATCH,
        stage=MissionStage.PATCH,
        message="Patch stage started.",
        payload=StageProgressPayload(
            stage=MissionStage.PATCH, percent_complete=0.0, detail="Requesting candidates."
        ),
    )
    b.add(
        after_seconds=0.5,
        type=EventType.LOG,
        state=MissionState.PATCH,
        stage=MissionStage.PATCH,
        severity=Severity.HIGH,
        message="Model host degraded: serving from a captured transcript.",
        payload=LogPayload(
            text=(
                "degraded — the local model host did not come up within its budget, so "
                "the gateway is replaying a captured transcript (#82). Every candidate "
                "below carries replayed_from_transcript, and the patch panel must render "
                "it as 'replayed', not as a live generation."
            )
        ),
    )

    replayed_model = ModelProvenance(
        model_name="qwen2.5-coder-7b-instruct-q4",
        model_revision="2026-07-11",
        served_from="http://model-gateway.internal:8081",
        prompt_sha256="c2b1a0f9e8d7c6b5a4938271605f4e3d2c1b0a9988776655443322110ffee0dd",
        context_bytes=4812,
        confidence=0.71,
        replayed_from_transcript="transcript://pktcfg-001/candidate-a",
        captured_at=T0 - timedelta(days=1),
        transcript_sha256="1f2e3d4c5b6a79887766554433221100fedcba9876543210abcdef0123456789",
    )

    b.add(
        after_seconds=6.4,
        type=EventType.PATCH_CANDIDATE_RECORDED,
        state=MissionState.PATCH,
        stage=MissionStage.PATCH,
        status=EventStatus.SUCCEEDED,
        message="Candidate A: teach the sizing pass about literal tabs.",
        payload=PatchCandidatePayload(
            patch=PatchCandidate(
                id=PATCH_A_ID,
                mission_id=MISSION_ID,
                finding_id=FINDING_ID,
                provenance=PatchProvenance.MODEL_GENERATED,
                model=replayed_model,
                diff=DIFF_A,
                files_changed=1,
                lines_changed=7,
                policy_status=PatchPolicyStatus.ACCEPTED,
                policy_detail="1 file, 7 lines, inside src/ — within policy.",
                rationale=(
                    "pkt_decoded_length and pkt_decode_into must agree byte for byte. The "
                    "writing pass expands a literal 0x09 to PKT_TAB_WIDTH spaces; the "
                    "sizing pass counts it as one byte. Sizing for the expansion makes the "
                    "allocation match what is written."
                ),
                created_at=T0 + timedelta(seconds=32),
            )
        ),
        metrics={"files_changed": 1.0, "lines_changed": 7.0, "model_confidence": 0.71},
    )
    b.add(
        after_seconds=0.2,
        type=EventType.PATCH_POLICY_EVALUATED,
        state=MissionState.PATCH,
        stage=MissionStage.PATCH,
        status=EventStatus.SUCCEEDED,
        message="Candidate A accepted by patch policy.",
        payload=LogPayload(
            text="patch policy ACCEPTED for candidate A: 1 file, 7 lines, path src/decode.c."
        ),
    )

    b.add(
        after_seconds=5.1,
        type=EventType.PATCH_CANDIDATE_RECORDED,
        state=MissionState.PATCH,
        stage=MissionStage.PATCH,
        status=EventStatus.SUCCEEDED,
        message="Candidate B: make emit_tab write a single space.",
        payload=PatchCandidatePayload(
            patch=PatchCandidate(
                id=PATCH_B_ID,
                mission_id=MISSION_ID,
                finding_id=FINDING_ID,
                provenance=PatchProvenance.MODEL_GENERATED,
                model=replayed_model.model_copy(
                    update={
                        "confidence": 0.93,
                        "replayed_from_transcript": "transcript://pktcfg-001/candidate-b",
                    }
                ),
                diff=DIFF_B,
                files_changed=1,
                lines_changed=6,
                policy_status=PatchPolicyStatus.ACCEPTED,
                policy_detail="1 file, 6 lines, inside src/ — within policy.",
                rationale=(
                    "The sanitizer names emit_tab as the writing frame. Writing one space "
                    "instead of PKT_TAB_WIDTH keeps the write inside the allocation and "
                    "eliminates the crash."
                ),
                created_at=T0 + timedelta(seconds=37),
            )
        ),
        metrics={"files_changed": 1.0, "lines_changed": 6.0, "model_confidence": 0.93},
    )
    b.add(
        after_seconds=0.2,
        type=EventType.PATCH_POLICY_EVALUATED,
        state=MissionState.PATCH,
        stage=MissionStage.PATCH,
        status=EventStatus.SUCCEEDED,
        message="Candidate B accepted by patch policy.",
        payload=LogPayload(
            text=(
                "patch policy ACCEPTED for candidate B: 1 file, 6 lines, path src/decode.c. "
                "Policy checks shape, not correctness — the gates decide correctness, and "
                "this candidate carries the highest model confidence in the mission."
            )
        ),
    )

    # A third candidate that never reaches verification: the patch policy refuses it.
    b.add(
        after_seconds=4.4,
        type=EventType.PATCH_CANDIDATE_RECORDED,
        state=MissionState.PATCH,
        stage=MissionStage.PATCH,
        status=EventStatus.SUCCEEDED,
        severity=Severity.MEDIUM,
        message="Candidate C: delete the failing test from the build.",
        payload=PatchCandidatePayload(
            patch=PatchCandidate(
                id=PATCH_Z_ID,
                mission_id=MISSION_ID,
                finding_id=FINDING_ID,
                provenance=PatchProvenance.MODEL_GENERATED,
                model=replayed_model.model_copy(
                    update={
                        "confidence": 0.44,
                        "replayed_from_transcript": "transcript://pktcfg-001/candidate-c",
                    }
                ),
                diff=DIFF_Z,
                files_changed=1,
                lines_changed=1,
                policy_status=PatchPolicyStatus.REJECTED_PATH_NOT_ALLOWED,
                policy_detail=(
                    "CMakeLists.txt is outside the allowed patch paths. A candidate that "
                    "edits the build definition can remove the evidence that judges it."
                ),
                rationale="Removing test_tab_expansion from the test list makes the suite green.",
                created_at=T0 + timedelta(seconds=42),
            )
        ),
        metrics={"files_changed": 1.0, "lines_changed": 1.0, "model_confidence": 0.44},
    )
    b.add(
        after_seconds=0.1,
        type=EventType.POLICY_VIOLATION,
        state=MissionState.PATCH,
        stage=MissionStage.PATCH,
        status=EventStatus.FAILED,
        severity=Severity.HIGH,
        message="Candidate C rejected by patch policy: path not allowed.",
        payload=PolicyViolationPayload(
            code=ErrorCode.PATCH_POLICY_REJECTED,
            detail=(
                "Candidate C edits CMakeLists.txt, which is outside the allowed patch "
                "paths. It never reaches verification, so it carries no verdict and does "
                "not appear in the mission verdict breakdown."
            ),
        ),
    )
    b.add(
        after_seconds=0.1,
        type=EventType.STAGE_COMPLETED,
        state=MissionState.PATCH,
        stage=MissionStage.PATCH,
        status=EventStatus.SUCCEEDED,
        message="Patch stage complete: 2 candidates go to verification, 1 refused by policy.",
        payload=StageProgressPayload(
            stage=MissionStage.PATCH,
            percent_complete=100.0,
            detail="2 accepted, 1 rejected by policy.",
        ),
        metrics={"candidates_total": 3.0, "candidates_accepted": 2.0},
    )

    # -- VERIFY ------------------------------------------------------------------
    b.add(
        after_seconds=0.2,
        type=EventType.STATE_CHANGED,
        state=MissionState.VERIFY,
        stage=MissionStage.VERIFY,
        message="Verifying both candidates through identical gates.",
        payload=StateChangedPayload(
            from_state=MissionState.PATCH,
            to_state=MissionState.VERIFY,
            posture=posture_for(MissionState.VERIFY),
            reason="A patch is never accepted on model confidence alone.",
        ),
    )
    b.add(
        after_seconds=0.1,
        type=EventType.STAGE_STARTED,
        state=MissionState.VERIFY,
        stage=MissionStage.VERIFY,
        message="Verification started.",
        payload=StageProgressPayload(
            stage=MissionStage.VERIFY,
            percent_complete=0.0,
            detail="Clean worktree per candidate.",
        ),
    )
    b.add(
        after_seconds=3.4,
        type=EventType.STAGE_PROGRESS,
        state=MissionState.VERIFY,
        stage=MissionStage.VERIFY,
        message="Candidate A: compile, reproducer, regression.",
        payload=StageProgressPayload(
            stage=MissionStage.VERIFY, percent_complete=35.0, detail="candidate A"
        ),
    )

    cut_reason = (
        "Not run: cut from the seven-day build (see docs/09-company/03-seven-day-plan.md)."
    )
    gates_a = GateMatrix(
        compile=GateResult(
            name=GateName.COMPILE,
            status=GateStatus.PASS,
            evidence_source=EvidenceSource.TOOL_EXECUTION,
            tool=CLANG_VERSION,
            detail="Configure and build succeeded with ASan and UBSan.",
            evidence_ref=artifact("verification", "a-build-log"),
        ),
        reproducer_eliminated=GateResult(
            name=GateName.REPRODUCER_ELIMINATED,
            status=GateStatus.PASS,
            evidence_source=EvidenceSource.TOOL_EXECUTION,
            tool=ASAN_VERSION,
            detail="pktcfg_replay crash-literal-tab.bin x5 — exit 0, no sanitizer report.",
            evidence_ref=artifact("verification", "a-repro-log"),
        ),
        regression_preserved=GateResult(
            name=GateName.REGRESSION_PRESERVED,
            status=GateStatus.PASS,
            evidence_source=EvidenceSource.TOOL_EXECUTION,
            tool=CTEST_VERSION,
            detail=f"{TESTS_PASSED} of {TESTS_TOTAL} ctest cases passed; baseline was "
            f"{TESTS_PASSED} of {TESTS_TOTAL}.",
            evidence_ref=artifact("verification", "a-ctest-log"),
        ),
        static_delta=GateResult.not_run(GateName.STATIC_DELTA, cut_reason),
        renewed_fuzzing=GateResult.not_run(GateName.RENEWED_FUZZING, cut_reason),
    )
    b.add(
        after_seconds=0.1,
        type=EventType.VERIFICATION_RECORDED,
        state=MissionState.VERIFY,
        stage=MissionStage.VERIFY,
        status=EventStatus.SUCCEEDED,
        message="Candidate A verified: crash gone, 8 of 8 tests still pass.",
        payload=VerificationPayload(
            verification=VerificationRecord(
                id=VERIFY_A_ID,
                mission_id=MISSION_ID,
                patch_id=PATCH_A_ID,
                gates=gates_a,
                verdict=Verdict.VERIFIED,
                started_at=T0 + timedelta(seconds=44),
                finished_at=T0 + timedelta(seconds=47, milliseconds=400),
                worktree_sha256=(
                    "5c8b3a17e94d62f0a1b7c4d83e26f95017ba4c8d3e62f97105bc4a8d3e26f970"
                ),
                resource_usage=ResourceUsage(
                    cpu_seconds=2.31,
                    peak_memory_mb=46.7,
                    wall_seconds=3.4,
                    sandbox_count=1,
                ),
            )
        ),
        evidence_refs=[artifact("verification", "a-ctest-log")],
        metrics={"tests_passed": 8.0, "tests_failed": 0.0},
    )
    b.add(
        after_seconds=0.2,
        type=EventType.STAGE_PROGRESS,
        state=MissionState.VERIFY,
        stage=MissionStage.VERIFY,
        message="Candidate B: compile, reproducer, regression.",
        payload=StageProgressPayload(
            stage=MissionStage.VERIFY, percent_complete=75.0, detail="candidate B"
        ),
    )

    gates_b = GateMatrix(
        compile=GateResult(
            name=GateName.COMPILE,
            status=GateStatus.PASS,
            evidence_source=EvidenceSource.TOOL_EXECUTION,
            tool=CLANG_VERSION,
            detail="Configure and build succeeded with ASan and UBSan.",
            evidence_ref=artifact("verification", "b-build-log"),
        ),
        reproducer_eliminated=GateResult(
            name=GateName.REPRODUCER_ELIMINATED,
            status=GateStatus.PASS,
            evidence_source=EvidenceSource.TOOL_EXECUTION,
            tool=ASAN_VERSION,
            detail=(
                "pktcfg_replay crash-literal-tab.bin x5 — exit 0, no sanitizer report. "
                "The crash is gone; that alone is not a repair."
            ),
            evidence_ref=artifact("verification", "b-repro-log"),
        ),
        regression_preserved=GateResult(
            name=GateName.REGRESSION_PRESERVED,
            status=GateStatus.FAIL,
            evidence_source=EvidenceSource.TOOL_EXECUTION,
            tool=CTEST_VERSION,
            detail=(
                f"{B_TESTS_PASSED} of {TESTS_TOTAL} ctest cases passed; baseline was "
                f"{TESTS_PASSED} of {TESTS_TOTAL}. test_tab_expansion failed: the "
                "candidate removed the expansion it was overflowing."
            ),
            evidence_ref=artifact("verification", "b-ctest-log"),
        ),
        static_delta=GateResult.not_run(GateName.STATIC_DELTA, cut_reason),
        renewed_fuzzing=GateResult.not_run(GateName.RENEWED_FUZZING, cut_reason),
    )
    b.add(
        after_seconds=3.2,
        type=EventType.VERIFICATION_RECORDED,
        state=MissionState.VERIFY,
        stage=MissionStage.VERIFY,
        status=EventStatus.SUCCEEDED,
        severity=Severity.HIGH,
        message="Candidate B rejected: crash gone, but test_tab_expansion now fails.",
        payload=VerificationPayload(
            verification=VerificationRecord(
                id=VERIFY_B_ID,
                mission_id=MISSION_ID,
                patch_id=PATCH_B_ID,
                gates=gates_b,
                verdict=Verdict.REJECTED,
                started_at=T0 + timedelta(seconds=47, milliseconds=600),
                finished_at=T0 + timedelta(seconds=50, milliseconds=800),
                worktree_sha256=(
                    "a41f7d92c6b30e85174a2f9d6c30b8e5741a2f9d6c30b8e5741a2f9d6c30b8e5"
                ),
                resource_usage=ResourceUsage(
                    cpu_seconds=2.28,
                    peak_memory_mb=46.7,
                    wall_seconds=3.2,
                    sandbox_count=1,
                ),
            )
        ),
        evidence_refs=[artifact("verification", "b-ctest-log")],
        metrics={"tests_passed": 7.0, "tests_failed": 1.0, "model_confidence": 0.93},
    )
    b.add(
        after_seconds=0.2,
        type=EventType.MISSION_VERDICT_RECORDED,
        state=MissionState.VERIFY,
        stage=MissionStage.VERIFY,
        status=EventStatus.SUCCEEDED,
        message="Mission verdict: VERIFIED — 1 candidate verified, 1 rejected.",
        payload=MissionVerdictPayload(
            summary=MissionVerdictSummary(
                mission_verdict=Verdict.VERIFIED,
                candidates=[
                    CandidateVerdict(
                        patch_id=PATCH_A_ID,
                        verification_id=VERIFY_A_ID,
                        verdict=Verdict.VERIFIED,
                        provenance=PatchProvenance.MODEL_GENERATED,
                        summary="all required gates passed; regression suite 8 of 8",
                    ),
                    CandidateVerdict(
                        patch_id=PATCH_B_ID,
                        verification_id=VERIFY_B_ID,
                        verdict=Verdict.REJECTED,
                        provenance=PatchProvenance.MODEL_GENERATED,
                        summary="regression suite: 1 of 8 failed (test_tab_expansion)",
                    ),
                ],
                verified_count=1,
                rejected_count=1,
                human_review_count=0,
            )
        ),
        metrics={"verified_count": 1.0, "rejected_count": 1.0},
    )
    b.add(
        after_seconds=0.1,
        type=EventType.STAGE_COMPLETED,
        state=MissionState.VERIFY,
        stage=MissionStage.VERIFY,
        status=EventStatus.SUCCEEDED,
        message="Verification complete.",
        payload=StageProgressPayload(
            stage=MissionStage.VERIFY, percent_complete=100.0, detail="2 candidates judged."
        ),
    )

    # -- EXPORT EVIDENCE ---------------------------------------------------------
    b.add(
        after_seconds=0.2,
        type=EventType.STATE_CHANGED,
        state=MissionState.EXPORTING,
        stage=MissionStage.EXPORT_EVIDENCE,
        message="Writing the evidence bundle.",
        payload=StateChangedPayload(
            from_state=MissionState.VERIFY,
            to_state=MissionState.EXPORTING,
            posture=posture_for(MissionState.EXPORTING),
            reason="The mission is not VERIFIED until the evidence that justifies it exists.",
        ),
    )
    b.add(
        after_seconds=0.1,
        type=EventType.STAGE_STARTED,
        state=MissionState.EXPORTING,
        stage=MissionStage.EXPORT_EVIDENCE,
        message="Export started.",
        payload=StageProgressPayload(
            stage=MissionStage.EXPORT_EVIDENCE,
            percent_complete=0.0,
            detail="markdown + json",
        ),
    )
    b.add(
        after_seconds=1.6,
        type=EventType.EVIDENCE_EXPORTED,
        state=MissionState.EXPORTING,
        stage=MissionStage.EXPORT_EVIDENCE,
        status=EventStatus.SUCCEEDED,
        message="Evidence bundle written.",
        payload=EvidenceExportPayload(
            receipt=ExportReceipt(
                mission_id=MISSION_ID,
                export_id=EXPORT_ID,
                formats=["markdown", "json"],
                artifacts=[
                    ArtifactRef(
                        uri=artifact("evidence", "report.md"),
                        kind="report-markdown",
                        size_bytes=18244,
                    ),
                    ArtifactRef(
                        uri=artifact("evidence", "bundle.json"),
                        kind="report-json",
                        size_bytes=39117,
                    ),
                ],
                generated_at=T0 + timedelta(seconds=54),
            )
        ),
        evidence_refs=[artifact("evidence", "report.md"), artifact("evidence", "bundle.json")],
    )
    b.add(
        after_seconds=0.4,
        type=EventType.TEARDOWN_CONFIRMED,
        state=MissionState.EXPORTING,
        stage=MissionStage.EXPORT_EVIDENCE,
        status=EventStatus.SUCCEEDED,
        message="Sandbox released.",
        payload=TeardownPayload(
            resource_kind="sandbox",
            resource_id="jail-pktcfg-001",
            released=True,
            detail="Jail directory removed; no process survived the mission.",
        ),
    )
    b.add(
        after_seconds=0.1,
        type=EventType.RESOURCE_USAGE_SAMPLED,
        state=MissionState.EXPORTING,
        stage=MissionStage.EXPORT_EVIDENCE,
        status=EventStatus.SUCCEEDED,
        message="Mission resource totals.",
        payload=ResourceUsagePayload(
            usage=ResourceUsage(
                cpu_seconds=round(BASELINE_CPU_SECONDS + 2.31 + 2.28, 3),
                peak_memory_mb=BASELINE_PEAK_MB,
                wall_seconds=round(BASELINE_WALL_SECONDS + 3.4 + 3.2 + 3.0, 3),
                sandbox_count=4,
                gpu_seconds=0.0,
            )
        ),
    )
    b.add(
        after_seconds=0.1,
        type=EventType.STAGE_COMPLETED,
        state=MissionState.EXPORTING,
        stage=MissionStage.EXPORT_EVIDENCE,
        status=EventStatus.SUCCEEDED,
        message="Export complete.",
        payload=StageProgressPayload(
            stage=MissionStage.EXPORT_EVIDENCE,
            percent_complete=100.0,
            detail="Bundle written and sealed.",
        ),
    )
    b.add(
        after_seconds=0.2,
        type=EventType.STATE_CHANGED,
        state=MissionState.VERIFIED,
        stage=None,
        status=EventStatus.SUCCEEDED,
        message="Mission VERIFIED.",
        payload=StateChangedPayload(
            from_state=MissionState.EXPORTING,
            to_state=MissionState.VERIFIED,
            posture=posture_for(MissionState.VERIFIED),
            reason=(
                "Candidate A passed every required gate and the evidence bundle exists. "
                "Candidate B is rejected and stays in the record."
            ),
        ),
    )

    return b


def main() -> int:
    builder = build()
    builder.check()

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(event.model_dump(mode="json"), separators=(",", ":"), sort_keys=True)
        for event in builder.events
    ]
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(  # noqa: T201 - this is an operator-facing build tool
        f"wrote {len(lines)} events to {OUTPUT.relative_to(REPO_ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
