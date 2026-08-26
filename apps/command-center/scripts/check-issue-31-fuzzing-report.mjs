import { readFile } from 'node:fs/promises';
import path from 'node:path';

// Regression test for the static FuzzingReport panel (#31), cut down from the issue body's
// live/virtualized telemetry panel by the CTO's technical review
// (docs/09-company/05-cto-technical-review.md §2.1, D-021 C4) and confirmed by the repo owner's
// own comment on #31. Guards the four things that make this the reduced panel and not the
// original: no new live/streaming mechanism, real data sourced from the existing STAGE_COMPLETED
// event (never fabricated), all three honest states present, and it never grows into a sixth
// panel (docs/09-company/04-design-system.md §6: "P0-13 names five and this document still
// builds five").

const appRoot = path.resolve(import.meta.dirname, '..');
const panelPath = path.join(appRoot, 'src/components/FuzzingReportPanel.tsx');
const timelinePath = path.join(appRoot, 'src/components/StageTimeline.tsx');
const storePath = path.join(appRoot, 'src/lib/events/store.ts');
const cssPath = path.join(appRoot, 'src/styles/command-center-frame.css');

async function main() {
  const [panel, timeline, store, css] = await Promise.all([
    readFile(panelPath, 'utf8'),
    readFile(timelinePath, 'utf8'),
    readFile(storePath, 'utf8'),
    readFile(cssPath, 'utf8'),
  ]);

  assertNoLiveFeedMechanism(panel);
  assertNoNewEventChannel(panel, timeline);
  assertRealDataOnly(panel);
  assertFourCounters(panel);
  assertThreeHonestStates(panel);
  assertRendersOnceOnCompletion(panel);
  assertWiredIntoStressTestRowOnly(timeline);
  assertSourcedFromExistingFuzzingField(store);
  assertNotASixthPanel(timeline, panel);
  assertCssStatesPresent(css);

  console.warn('fuzzing report panel ok: static, real data, three honest states, no live feed, no sixth panel');
}

function assertNoLiveFeedMechanism(panel) {
  for (const forbidden of ['setInterval', 'setTimeout', 'EventSource', 'WebSocket', 'fetch(', 'useEffect']) {
    assert(!panel.includes(forbidden), (
      `FuzzingReportPanel must not contain "${forbidden}" — it is a static render of one already-` +
      'delivered event, never a live/polling feed (owner comment cutting #31\'s body)'
    ));
  }
}

function assertNoNewEventChannel(panel, timeline) {
  assert(timeline.includes('import { FuzzingReportPanel }'), 'StageTimeline must import and wire in FuzzingReportPanel');
  assert(!panel.includes('new EventSource'), 'FuzzingReportPanel must not open its own EventSource — one shared connection only (C5)');
  assert(!panel.includes('connectMissionEvents'), (
    'FuzzingReportPanel must not open its own mission-event connection — it reads the shared snapshot only'
  ));
}

function assertRealDataOnly(panel) {
  assert(!panel.includes('Math.random'), 'the panel must never fabricate a value');
  assert(panel.includes('fuzzing.executions'), 'executions must come from the real FuzzingReport field');
  assert(panel.includes('fuzzing.runtime_seconds'), 'runtime must come from the real FuzzingReport field');
  assert(panel.includes('fuzzing.unique_crashes'), 'crashes must come from the real FuzzingReport field');
  assert(panel.includes('fuzzing.corpus_size'), 'corpus size must come from the real FuzzingReport field');
}

function assertFourCounters(panel) {
  for (const label of ['EXECS', 'RUNTIME', 'CRASHES', 'CORPUS']) {
    assert(panel.includes(label), `the panel must render the ${label} counter (owner comment: "executions, runtime, crashes, corpus size")`);
  }
}

function assertThreeHonestStates(panel) {
  assert(panel.includes('NOT YET RUN'), 'must have a not-yet-run state, distinct from a zero (§5)');
  assert(panel.includes('IN PROGRESS'), 'must have an in-progress state that does not invent partial numbers');
  assert(panel.includes("mode === 'NOT_RUN'"), 'must disclose a real NOT_RUN reason rather than rendering zeros as a completed report');
}

function assertRendersOnceOnCompletion(panel) {
  assert(panel.includes('reached'), 'the panel must distinguish "stage never started" from "stage started"');
  assert(panel.includes('running'), 'the panel must distinguish "running" from "awaiting result" without polling');
  // The completed branch must be reachable only once `fuzzing` (the terminal report) is non-null —
  // i.e. it is gated on the STAGE_COMPLETED-derived value already in the snapshot, not a timer.
  assert(panel.includes('if (!fuzzing)'), 'numbers must be gated on the real terminal FuzzingReport, not rendered speculatively');
}

function assertWiredIntoStressTestRowOnly(timeline) {
  const match = timeline.match(/stage === 'STRESS_TEST' && \(\s*<FuzzingReportPanel/);
  assert(match, 'FuzzingReportPanel must be scoped to the STRESS_TEST row only, matching the FuzzingReport payload\'s own stage');
  assert(timeline.includes('fuzzing={snapshot.fuzzing}'), 'must be wired to the real mission snapshot, not a mock prop');
  assert(timeline.includes('reached={Boolean(snapshot.stageStartedAt.STRESS_TEST)}'), 'reached must derive from a real STAGE_STARTED timestamp');
}

function assertSourcedFromExistingFuzzingField(store) {
  assert(store.includes("event.payload.kind === 'fuzzing'"), (
    'the store must already fold the fuzzing payload kind into the snapshot — #31 must not add a new payload kind or event type'
  ));
  assert(store.includes('sanitizeFuzzingReport'), 'the fuzzing report must be sanitized before it reaches the snapshot, same as every other panel');
}

function assertNotASixthPanel(timeline, panel) {
  assert(!panel.includes("className=\"bd-panel"), (
    'FuzzingReportPanel must not render as its own bd-panel — it is a chip block inside the existing Stage Timeline panel (§6, "still builds five")'
  ));
  assert(timeline.includes('bd-timeline__body'), 'the panel must be rendered inside the timeline row body, not a new top-level region');
}

function assertCssStatesPresent(css) {
  for (const selector of ['.bd-fuzzing-report', '.bd-fuzzing-report--pending', '.bd-fuzzing-report--critical']) {
    assert(css.includes(selector), `CSS missing ${selector}`);
  }
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
