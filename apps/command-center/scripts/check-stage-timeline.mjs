import { readFile } from 'node:fs/promises';
import path from 'node:path';

// Regression test for the Stage Timeline (docs/09-company/04-design-system.md §6.2): ten fixed
// rows, real per-stage timing derived from actual STAGE_STARTED/STAGE_COMPLETED events (never a
// client timer), the ANALYZE row rendering the backend's own LOG string verbatim (C8), and
// TEARDOWN's auto-expanded receipts as the one exception to "events render only when expanded".

const appRoot = path.resolve(import.meta.dirname, '..');
const timelinePath = path.join(appRoot, 'src/components/StageTimeline.tsx');
const phasesPath = path.join(appRoot, 'src/lib/design/phases.ts');
const storePath = path.join(appRoot, 'src/lib/events/store.ts');
const cssPath = path.join(appRoot, 'src/styles/command-center-frame.css');

async function main() {
  const [timeline, phases, store, css] = await Promise.all([
    readFile(timelinePath, 'utf8'),
    readFile(phasesPath, 'utf8'),
    readFile(storePath, 'utf8'),
    readFile(cssPath, 'utf8'),
  ]);

  assertTenFixedRows(phases);
  assertRealStageTiming(store, timeline);
  assertAnalyzeRowVerbatim(timeline);
  assertFailurePropagation(timeline);
  assertTeardownAutoExpanded(timeline);
  assertEventWindowBounded(store);
  assertCssStatesPresent(css);

  console.warn('stage timeline ok: ten fixed rows, real per-stage timing, ANALYZE verbatim, teardown auto-expanded, bounded event window');
}

function assertTenFixedRows(phases) {
  const match = phases.match(/export const STAGE_ROWS[\s\S]*?= \[([\s\S]*?)\];/);
  assert(match, 'STAGE_ROWS is missing');
  const rows = Array.from(match[1].matchAll(/label: '([A-Z ]+)'/g), ([, label]) => label);
  const expected = [
    'AUTHORIZE', 'INGEST', 'BASELINE', 'ANALYZE', 'STRESS TEST',
    'CORRELATE', 'REMEDIATE', 'VERIFY', 'EXPORT EVIDENCE', 'TEARDOWN',
  ];
  assert(JSON.stringify(rows) === JSON.stringify(expected), (
    `STAGE_ROWS must be the ten fixed rows AUTHORIZE..TEARDOWN in order; got ${rows.join(',')}`
  ));
}

function assertRealStageTiming(store, timeline) {
  assert(store.includes("event.type === 'STAGE_STARTED'"), 'store must record real STAGE_STARTED timestamps');
  assert(store.includes("event.type === 'STAGE_COMPLETED'"), 'store must record real STAGE_COMPLETED timestamps');
  assert(timeline.includes('formatElapsed(snapshot.stageStartedAt[stage]'), 'row elapsed time must be derived from real stage timestamps');
  assert(!timeline.includes('setInterval'), 'the timeline must not run its own timer — §2.6 rule 2');
}

function assertAnalyzeRowVerbatim(timeline) {
  assert(timeline.includes('snapshot.stageMessage.ANALYZE'), (
    'the ANALYZE row must render the backend\'s own LOG string, never compose one (§6.2, C8)'
  ));
  assert(!timeline.includes("'0 FINDINGS'") && !timeline.includes('"0 FINDINGS"'), (
    'ANALYZE must never claim a static-analysis finding count — no analyzer ran (C8)'
  ));
}

function assertFailurePropagation(timeline) {
  assert(timeline.includes("'not_reached'"), 'rows after a failure must render NOT REACHED, not FAIL (§6.2)');
  assert(timeline.includes('failingIndex'), 'failure propagation must be computed from the real failing stage index');
}

function assertTeardownAutoExpanded(timeline) {
  const teardownBody = bodyOfFunction(timeline, 'TeardownRow');
  assert(teardownBody.includes('resources.length > 0'), 'TeardownRow must render receipts whenever resources exist');
  assert(!teardownBody.includes('isExpanded'), 'TEARDOWN must auto-expand, not gate behind the same click-to-expand state other stages use (§6.2 exception)');
  assert(teardownBody.includes('resource.id'), 'teardown event rows must carry the real resource id as its receipt');
}

function assertEventWindowBounded(store) {
  assert(store.includes('export const EVENT_WINDOW = 50'), 'the event window constant must match --bd-event-window (50)');
  assert(store.includes('stageEventOverflow'), 'overflow must be tracked and disclosed, never silently dropped');
}

function assertCssStatesPresent(css) {
  for (const selector of ['.bd-timeline__row--running', '.bd-timeline__row--fail', '.bd-timeline__row--not_reached', '.bd-timeline__events']) {
    assert(css.includes(selector), `CSS missing ${selector}`);
  }
}

// Finds a function's real body, correctly skipping over TypeScript destructured-parameter type
// annotations like `({ a }: { a: T })`, which contain `{`/`}` pairs that a naive
// first-brace-after-name search would mistake for the body itself.
function bodyOfFunction(source, name) {
  const start = source.indexOf(`function ${name}`);
  assert(start >= 0, `${name} is missing`);
  const parenStart = source.indexOf('(', start);
  assert(parenStart >= 0, `${name} has no parameter list`);
  let parenDepth = 0;
  let parenEnd = -1;
  for (let index = parenStart; index < source.length; index += 1) {
    const char = source[index];
    if (char === '(') parenDepth += 1;
    if (char === ')') {
      parenDepth -= 1;
      if (parenDepth === 0) {
        parenEnd = index;
        break;
      }
    }
  }
  assert(parenEnd >= 0, `${name} parameter list was not closed`);
  const firstBrace = source.indexOf('{', parenEnd);
  assert(firstBrace >= 0, `${name} has no body`);
  let depth = 0;
  for (let index = firstBrace; index < source.length; index += 1) {
    const char = source[index];
    if (char === '{') depth += 1;
    if (char === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(firstBrace + 1, index);
    }
  }
  throw new Error(`${name} body was not closed`);
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
