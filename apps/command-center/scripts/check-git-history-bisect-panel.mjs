// Behavioral tests for #26's git-history/bisect panel logic
// (src/lib/gitHistory/{bisectTimeline,riskyChangeSummary}.ts). Run with
// `node --experimental-strip-types`, same pattern as check-mission-control-form.mjs.
//
// Covers the issue's three acceptance criteria against real code paths:
//   1. "Renders sensibly before any bisect has run" — the idle case, which is also
//      confirmed here to be the ONLY reachable case in the shipped app today (no
//      envelope source calls deriveBisectTimelineState with anything but []).
//   2. "Bisect steps render live from events as the search narrows" — proven against a
//      fixture shaped exactly like the real, merged
//      `workers/git_analysis/bisect_run.py::emit_bisect_events` output (the #5 fixture's
//      own mission, mission-pktcfg-001, carries no bisect events — verified directly
//      against packages/test-fixtures/missions/mission-pktcfg-001.events.jsonl, which
//      has zero `payload.kind` values of "bisect"/"bisect_step" among its 60 real rows —
//      so this test constructs the fixture from the backend module's own documented
//      output shape instead of pretending the demo mission already has one).
//   3. "First-bad-commit called out clearly when found" — the converged case, plus its
//      sibling not-converged case (never silently drops a failed bisect).

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  deriveBisectTimelineState,
  IDLE_BISECT_TIMELINE,
  shortSha,
} from '../src/lib/gitHistory/bisectTimeline.ts';
import {
  hasAnalyzeStageBeenReached,
  summarizeRiskyChanges,
} from '../src/lib/gitHistory/riskyChangeSummary.ts';

const GOOD = '1fe6d02d4209f256d5436a661fb7b9698a6ba745'; // demo/repositories/pktcfg's real seeded good ref
const BAD = '114383dd517e49e1285b53608184cb744adb2aaa'; // demo/repositories/pktcfg's real seeded defect commit

function startEnvelope() {
  return {
    id: 'evt-1',
    sequence: 1,
    type: 'STAGE_STARTED',
    stage: 'ANALYZE',
    state: 'TRIAGE',
    status: 'RUNNING',
    payload: { kind: 'bisect', good_commit: GOOD, bad_commit: BAD },
  };
}

function stepEnvelope(sequence, sha, verdict, subject) {
  return {
    id: `evt-${sequence}`,
    sequence,
    type: 'STAGE_PROGRESS',
    stage: 'ANALYZE',
    state: 'TRIAGE',
    status: 'RUNNING',
    payload: { kind: 'bisect_step', sha, verdict, subject },
  };
}

function completedEnvelope(sequence, report) {
  return {
    id: `evt-${sequence}`,
    sequence,
    type: 'STAGE_COMPLETED',
    stage: 'ANALYZE',
    state: 'TRIAGE',
    status: report.succeeded ? 'COMPLETED' : 'FAILED',
    payload: { kind: 'bisect', report },
  };
}

function testIdleBeforeAnyBisectHasRun() {
  const state = deriveBisectTimelineState([]);
  assert.deepEqual(state, IDLE_BISECT_TIMELINE, 'no envelopes must render the calm idle state, not a broken-looking blank');
  assert.equal(state.status, 'idle');
  assert.equal(state.steps.length, 0);
  assert.equal(state.culpritCommit, null);
}

function testTheOnlyLiveCallSiteIsAlwaysEmptyToday() {
  // Structural guard, not just a behavioral one: assert the shipped component never
  // fabricates a live feed. If this ever fails, someone wired a fake/mocked bisect
  // stream into production, which is exactly what #26's task brief prohibits.
  const source = readFileSync(new URL('../src/components/GitHistoryBisectPanel.tsx', import.meta.url), 'utf8');
  assert.ok(
    source.includes('bisectEnvelopes = []'),
    'GitHistoryBisectPanel must default bisectEnvelopes to [] — no real source exists yet (D-151)',
  );
  assert.ok(
    !source.includes('setInterval') && !source.includes('setTimeout'),
    'the bisect timeline must never fake progress with a client-side timer',
  );
  const missionCommandCenter = readFileSync(new URL('../src/components/MissionCommandCenter.tsx', import.meta.url), 'utf8');
  assert.ok(
    !missionCommandCenter.includes('bisectEnvelopes='),
    'MissionCommandCenter must not pass a fabricated bisectEnvelopes prop — only a real future data source may',
  );
}

function testStepsRenderLiveAsTheSearchNarrows() {
  // Shaped exactly like emit_bisect_events()'s real, merged output (BisectStepLogEntry.as_dict()
  // -> {"kind": "bisect_step", **step.as_dict()}), proving forward-compatibility against the
  // real backend contract even though nothing wires it through today.
  const afterStart = deriveBisectTimelineState([startEnvelope()]);
  assert.equal(afterStart.status, 'running');
  assert.equal(afterStart.goodCommit, GOOD);
  assert.equal(afterStart.badCommit, BAD);
  assert.equal(afterStart.steps.length, 0);

  const afterOneStep = deriveBisectTimelineState([
    startEnvelope(),
    stepEnvelope(2, 'abc1234567890abc1234567890abc1234567890', 'BAD', 'sizing pass regresses on malformed literal-tab input'),
  ]);
  assert.equal(afterOneStep.steps.length, 1);
  assert.equal(afterOneStep.steps[0].verdict, 'BAD');

  const afterTwoSteps = deriveBisectTimelineState([
    startEnvelope(),
    stepEnvelope(2, 'abc1234567890abc1234567890abc1234567890', 'BAD', 'sizing pass regresses'),
    stepEnvelope(3, 'def4567890def4567890def4567890def4567890', 'GOOD', 'unrelated cleanup'),
  ]);
  assert.equal(afterTwoSteps.steps.length, 2, 'each new step envelope must narrow the timeline further, not replace it');
  assert.equal(afterTwoSteps.steps[1].verdict, 'GOOD');
}

function testFirstBadCommitCalledOutClearlyWhenFound() {
  const report = {
    mission_id: 'mission-1',
    repo_path: '/repos/pktcfg',
    good_commit: GOOD,
    bad_commit: BAD,
    culprit_commit: BAD,
    culprit_subject: 'introduce literal-tab sizing omission',
    steps: [],
    steps_tested: 4,
    duration_seconds: 12.5,
    recorded_at: '2026-08-24T00:00:00Z',
    succeeded: true,
    error: null,
  };
  const state = deriveBisectTimelineState([startEnvelope(), completedEnvelope(2, report)]);
  assert.equal(state.status, 'converged');
  assert.equal(state.culpritCommit, BAD, 'the real first-bad-commit sha must be surfaced, not a placeholder');
  assert.equal(state.culpritSubject, 'introduce literal-tab sizing omission');
  assert.equal(state.errorDetail, null);
}

function testNonConvergedBisectIsNeverSilentlyDroppedAsSuccess() {
  const report = {
    good_commit: GOOD,
    bad_commit: BAD,
    culprit_commit: null,
    culprit_subject: '',
    steps: [],
    succeeded: false,
    error: 'git bisect run exited 1; culprit_found=False.',
  };
  const state = deriveBisectTimelineState([startEnvelope(), completedEnvelope(2, report)]);
  assert.equal(state.status, 'not_converged');
  assert.equal(state.culpritCommit, null, 'a failed bisect must never report a culprit commit');
  assert.ok(state.errorDetail && state.errorDetail.length > 0, 'a failed bisect must surface why, not go silent');
}

function testMalformedOrUnrecognisedEnvelopesAreSkippedNotThrown() {
  assert.doesNotThrow(() => {
    const state = deriveBisectTimelineState([
      { payload: { kind: 'finding' } }, // a real, unrelated payload kind — must be ignored
      { payload: { kind: 'bisect_step', sha: 'not-hex', verdict: 'MAYBE' } }, // malformed
      null,
      'not an object',
      startEnvelope(),
    ]);
    assert.equal(state.status, 'running');
    assert.equal(state.steps.length, 0, 'the malformed step must not be admitted as a real step');
  });
}

function testShortShaTruncatesToTwelveCharsLikeTheRestOfTheApp() {
  assert.equal(shortSha(BAD), BAD.slice(0, 12));
  assert.equal(shortSha(BAD).length, 12);
}

function testRiskyChangeSummaryOnlyCountsStaticAnalysisFindings() {
  const findings = [
    finding('sizing.c', 10, 'HIGH', 'STATIC_ANALYSIS', 'Semgrep: unchecked size_t subtraction'),
    finding('sizing.c', 42, 'CRITICAL', 'STATIC_ANALYSIS', 'compiler: -Wformat-truncation'),
    finding('parser.c', 7, 'MEDIUM', 'STATIC_ANALYSIS', 'Semgrep: possible off-by-one'),
    finding('fuzz_target.c', 1, 'CRITICAL', 'FUZZING_CAMPAIGN', 'ASan heap-buffer-overflow'),
  ];
  const groups = summarizeRiskyChanges(findings);
  assert.equal(groups.length, 2, 'the fuzzer-discovered finding must be excluded — it is not a "risky change" signal in the git-history sense');
  assert.equal(groups[0].filePath, 'sizing.c', 'the file with the highest severity must sort first');
  assert.equal(groups[0].topSeverity, 'CRITICAL');
  assert.equal(groups[0].findingCount, 2);
  assert.equal(groups[1].filePath, 'parser.c');
}

function testRiskyChangeSummaryIsEmptyOnAGenuinelyCleanRun() {
  assert.deepEqual(summarizeRiskyChanges([]), []);
}

function testAnalyzeStageReachedDistinguishesNotRunFromCleanZero() {
  const notReached = { completedStages: [], stage: 'BASELINE' };
  const reachedViaCompletedStages = { completedStages: ['ANALYZE'], stage: 'STRESS_TEST' };
  const reachedViaLaterStage = { completedStages: [], stage: 'CORRELATE' };
  assert.equal(hasAnalyzeStageBeenReached(notReached), false, 'ANALYZE not yet reached must read as "awaiting", not a false clean zero');
  assert.equal(hasAnalyzeStageBeenReached(reachedViaCompletedStages), true);
  assert.equal(hasAnalyzeStageBeenReached(reachedViaLaterStage), true, 'a mission past ANALYZE must count it complete even without an explicit STAGE_COMPLETED row (StageTimeline\'s own documented gap)');
}

function testFixtureMissionHasNoBisectEventsYetConfirmingIdleIsTheRealCase() {
  // Verifies the task brief's own premise directly against the real fixture file, rather
  // than assuming it: mission-pktcfg-001 (#5/#52) carries zero bisect-kind events.
  const path = new URL('../../../packages/test-fixtures/missions/mission-pktcfg-001.events.jsonl', import.meta.url);
  const lines = readFileSync(path, 'utf8').split('\n').filter((line) => line.trim().length > 0);
  const kinds = lines.map((line) => JSON.parse(line).payload?.kind);
  assert.ok(lines.length > 0, 'fixture file must not be empty');
  assert.ok(
    !kinds.includes('bisect') && !kinds.includes('bisect_step'),
    'mission-pktcfg-001 fixture has no recorded bisect events as of this writing — if this ' +
      'assertion ever fails, the fixture gained real bisect data and this panel should be ' +
      'wired to it directly instead of only exercising the synthetic fixture above',
  );
}

function finding(filePath, line, severity, discoveryMethod, title) {
  return {
    id: `finding-${filePath}-${line}`,
    mission_id: 'mission-1',
    category: 'OTHER',
    severity,
    tool: 'COMPILER_DIAGNOSTIC',
    discovery_method: discoveryMethod,
    replay_source: null,
    location: { file_path: filePath, line, function: null },
    fingerprint: `${filePath}:${line}`,
    crash_count: 1,
    reproducible: false,
    detected_at: '2026-08-24T00:00:00Z',
    title,
  };
}

function main() {
  testIdleBeforeAnyBisectHasRun();
  testTheOnlyLiveCallSiteIsAlwaysEmptyToday();
  testStepsRenderLiveAsTheSearchNarrows();
  testFirstBadCommitCalledOutClearlyWhenFound();
  testNonConvergedBisectIsNeverSilentlyDroppedAsSuccess();
  testMalformedOrUnrecognisedEnvelopesAreSkippedNotThrown();
  testShortShaTruncatesToTwelveCharsLikeTheRestOfTheApp();
  testRiskyChangeSummaryOnlyCountsStaticAnalysisFindings();
  testRiskyChangeSummaryIsEmptyOnAGenuinelyCleanRun();
  testAnalyzeStageReachedDistinguishesNotRunFromCleanZero();
  testFixtureMissionHasNoBisectEventsYetConfirmingIdleIsTheRealCase();
  console.warn(
    'git history / bisect panel ok: idle is the only reachable state today (verified against ' +
      'the real fixture), step-by-step live narrowing and first-bad-commit callout both proven ' +
      "against emit_bisect_events()'s real shape, risky-change summary honestly scoped to " +
      'STATIC_ANALYSIS findings only',
  );
}

main();
