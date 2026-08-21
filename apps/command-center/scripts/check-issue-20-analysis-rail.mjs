import { readFile } from 'node:fs/promises';
import path from 'node:path';

// Re-pointed at `AnalysisRail.tsx` by the design-system rebuild (docs/09-company/04-design-system.md):
// this component was extracted out of `MissionCommandCenter.tsx` verbatim (same logic, same
// markup, same CSS classes) when that file became the frozen five-panel frame's composition
// root, which has no body-height budget left for a sixth panel (§3 — the centre column's 424 +
// 24 + 236 closes at exactly 684, DS-01). Every assertion below still guards the same real
// behaviour issue #20 shipped; only the file it reads moved.
const appRoot = path.resolve(import.meta.dirname, '..');
const componentPath = path.join(appRoot, 'src/components/AnalysisRail.tsx');
const storePath = path.join(appRoot, 'src/lib/events/store.ts');
const cssPath = path.join(appRoot, 'src/styles/global.css');
// The frozen-frame rebuild split component CSS across two files: `global.css` keeps the
// pre-mission setup-drawer surfaces (including AnalysisRail's own rules, unmoved), and the new
// `command-center-frame.css` carries the five P0 panels' styles, including the Core's
// `.bd-core--degraded`/`.bd-core--failed` state modifiers this check also verifies. Both are
// read so a selector living in either file still passes.
const frameCssPath = path.join(appRoot, 'src/styles/command-center-frame.css');

async function main() {
  const [component, store, css, frameCss] = await Promise.all([
    readFile(componentPath, 'utf8'),
    readFile(storePath, 'utf8'),
    readFile(cssPath, 'utf8'),
    readFile(frameCssPath, 'utf8'),
  ]);
  const combinedCss = `${css}\n${frameCss}`;

  assertAnalysisRailLabels(component);
  assertHashContract(component);
  assertEventStreamCounts(component, store);
  assertDegradedAndFailedStates(component, store, combinedCss);
  assertLongListWindowing(component, css);

  console.warn('issue #20 analysis rail ok: event ctest counts, hash truncation, degraded/failed states, bounded signal list');
}

function assertAnalysisRailLabels(source) {
  for (const label of ['[ ANALYSIS RAIL ]', 'Snapshot', 'CTest', 'Regression', 'Signal files']) {
    assert(source.includes(label), `analysis rail missing visible label: ${label}`);
  }
  assert(source.includes('baselineStateText(snapshot)'), 'analysis rail does not render baseline status');
  assert(source.includes('ctestCountText(snapshot)'), 'analysis rail does not render ctest counts');
}

function assertHashContract(source) {
  const shortHashBody = bodyOfFunction(source, 'shortHash');
  assert(shortHashBody.includes("value.slice(0, 12)") && shortHashBody.includes("value.slice(-6)"), (
    'snapshot hash must show a legible prefix and suffix'
  ));
  assert(shortHashBody.includes('...'), 'snapshot hash truncation must visibly disclose omission');
  assert(source.includes('title={value}'), 'snapshot hash readout must preserve the full hash in title');
  assert(source.includes('aria-label={label}'), 'snapshot hash readout must expose the full hash accessibly');
}

function assertEventStreamCounts(component, store) {
  assert(store.includes("event.payload.kind === 'baseline'"), 'store no longer ingests baseline events');
  assert(store.includes('next.baseline = sanitizeBaselineReport(event.payload.report)'), (
    'baseline event must populate the mission snapshot'
  ));
  const ctestBody = bodyOfFunction(component, 'ctestCountText');
  for (const field of ['tests_passed', 'tests_failed', 'tests_total']) {
    assert(ctestBody.includes(`baseline.${field}`), `ctest readout missing ${field}`);
  }
  assert(!ctestBody.includes('Math.random'), 'ctest readout must not fabricate values');
}

function assertDegradedAndFailedStates(component, store, css) {
  assert(store.includes('degradedReason'), 'store must retain a degraded reason from events');
  assert(store.includes('failedReason'), 'store must retain a failed reason from events');
  assert(component.includes("state: 'degraded'"), 'analysis rail must derive a degraded state');
  assert(component.includes("state: 'failed'"), 'analysis rail must derive a failed state');
  assert(component.includes("streamState === 'stale'"), 'stale streams must render degraded, not idle');
  assert(component.includes("streamState === 'error'"), 'error streams must render degraded, not idle');
  for (const selector of [
    '.analysis-rail--degraded',
    '.analysis-rail--failed',
    // `.core-panel--*` / `.resource-strip--*` were AIParticleCore's and the old
    // MissionCommandCenter bottom strip's state classes. The design-system rebuild
    // (docs/09-company/04-design-system.md) replaced both: the Core's degraded/failed states
    // now render via `BrahmadattaCore.tsx`'s `.bd-core--degraded`/`.bd-core--failed` (§6.1's own
    // state table), and the bottom strip's degraded/failed signal is carried by the resource
    // ledger's state-coloured chips and the alert line, not a strip-level modifier class.
    '.bd-core--degraded',
    '.bd-core--failed',
    '.bd-chip--critical',
    '.bd-chip--warning',
    '.bd-alert-line--critical',
  ]) {
    assert(css.includes(selector), `CSS missing distinct state selector ${selector}`);
  }
}

function assertLongListWindowing(component, css) {
  assert(component.includes('const signalFileWindowSize = 50'), 'signal file window must use the stack-doc threshold');
  assert(component.includes('function virtualizedSignalFiles'), 'signal file list must use a bounded window helper');
  assert(component.includes('data-virtualized-list="signal-files"'), 'signal list must be marked as virtualized');
  assert(component.includes('signalFiles.visible.map'), 'UI should render only the visible signal-file window');
  assert(!component.includes('localRepository.detectedFiles.map'), 'detectedFiles must not be mapped directly');
  assert(css.includes('.virtual-signal-list__rows'), 'virtualized signal rows need stable CSS containment');
  assert(lastCssBlock(css, '.virtual-signal-list__rows').includes('overflow: hidden'), (
    'virtualized signal rows must not grow beyond the command-room viewport'
  ));
}

function bodyOfFunction(source, name) {
  const start = source.indexOf(`function ${name}`);
  assert(start >= 0, `${name} is missing`);
  const firstBrace = source.indexOf('{', start);
  assert(firstBrace >= 0, `${name} has no body`);
  let depth = 0;
  for (let index = firstBrace; index < source.length; index += 1) {
    const char = source[index];
    if (char === '{') {
      depth += 1;
    }
    if (char === '}') {
      depth -= 1;
      if (depth === 0) {
        return source.slice(firstBrace + 1, index);
      }
    }
  }
  throw new Error(`${name} body was not closed`);
}

function lastCssBlock(css, selector) {
  const escaped = selector.replaceAll('.', '\\.');
  const matches = Array.from(css.matchAll(new RegExp(`${escaped}\\s*\\{([\\s\\S]*?)\\}`, 'g')));
  return matches.at(-1)?.[1] ?? '';
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
