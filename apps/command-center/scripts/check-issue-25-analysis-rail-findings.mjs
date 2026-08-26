// Regression test for #25 — Analysis Rail: findings by severity, dependency and compiler
// health (docs/09-company/13-cut-pullback-design-spec.md §1, D-057). Two halves:
//
// 1. Real behavioral tests against the pure grouping/coverage logic
//    (`src/lib/missionControl/severityFindings.ts`), run with `node --experimental-strip-types`
//    against the real module — not a hand-copied re-implementation.
// 2. Static-source assertions guarding the design-honesty invariants that logic alone can't
//    check from outside a component: severity colours come from the shared token set, the
//    dependency-health row never gains any state but NOT RUN, the drill-down control is a real
//    button wired to the real `GET /findings/{id}` endpoint, and no CSS class is missing.

import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import {
  computeStaticAnalysisCoverage,
  groupFindingsBySeverity,
  severityChipClass,
  severityHeaderText,
} from '../src/lib/missionControl/severityFindings.ts';

const appRoot = path.resolve(import.meta.dirname, '..');

function finding(overrides = {}) {
  return {
    id: 'f-1',
    mission_id: 'm-1',
    category: 'OTHER',
    severity: 'MEDIUM',
    tool: 'SEMGREP',
    discovery_method: 'STATIC_ANALYSIS',
    fingerprint: 'fp-1',
    crash_count: 1,
    reproducible: false,
    replay_source: null,
    title: 'dangerous function',
    location: { file_path: 'src/decode.c', line: 118, function: null },
    detected_at: '2026-08-24T00:00:00Z',
    ...overrides,
  };
}

function snapshot(overrides = {}) {
  return {
    missionId: 'm-1',
    completedStages: [],
    findings: [],
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// 1. Real behavioral tests
// ---------------------------------------------------------------------------

function testGroupingSortsBySeverityThenDiscoveryOrder() {
  const findings = [
    finding({ id: 'f-low', severity: 'LOW', detected_at: '2026-08-24T00:00:02Z' }),
    finding({ id: 'f-crit-2', severity: 'CRITICAL', detected_at: '2026-08-24T00:00:03Z' }),
    finding({ id: 'f-crit-1', severity: 'CRITICAL', detected_at: '2026-08-24T00:00:01Z' }),
    finding({ id: 'f-high', severity: 'HIGH', detected_at: '2026-08-24T00:00:00Z' }),
  ];
  const groups = groupFindingsBySeverity(findings);
  assert.deepEqual(groups.map((g) => g.severity), ['CRITICAL', 'HIGH', 'LOW'], 'buckets must follow CRITICAL -> HIGH -> MEDIUM -> LOW -> INFO order');
  assert.deepEqual(groups[0].findings.map((f) => f.id), ['f-crit-1', 'f-crit-2'], 'within a severity, findings must be discovery-ordered (detected_at ascending)');
}

function testGroupingNeverFabricatesEmptyBuckets() {
  const groups = groupFindingsBySeverity([finding({ severity: 'MEDIUM' })]);
  assert.equal(groups.length, 1, 'a severity with zero findings must not get a bucket header at all');
  assert.equal(groups[0].severity, 'MEDIUM');
}

function testCoverageIsNotStartedBeforeEitherProducerRuns() {
  const coverage = computeStaticAnalysisCoverage(snapshot());
  assert.equal(coverage.state, 'not-started');
  assert.equal(severityHeaderText(coverage), '—', 'an unstarted scan must render the not-measured em dash, never a zero');
}

function testCoverageIsPartialWhileOnlyOneProducerHasCompleted() {
  const coverage = computeStaticAnalysisCoverage(snapshot({ completedStages: ['BASELINE'] }));
  assert.equal(coverage.state, 'partial');
  assert.equal(coverage.baselineComplete, true);
  assert.equal(coverage.analyzeComplete, false);
}

function testCoverageWithFindingsMidRunIsSoFarNotFinal() {
  const coverage = computeStaticAnalysisCoverage(
    snapshot({ completedStages: ['BASELINE'], findings: [finding({ tool: 'COMPILER_DIAGNOSTIC' })] }),
  );
  assert.equal(coverage.state, 'partial');
  assert.equal(severityHeaderText(coverage), '1 SO FAR', 'a mid-run count must be disclosed as provisional, never as a final total');
}

function testCoverageCompleteWithZeroFindingsIsAGenuineCleanScan() {
  const coverage = computeStaticAnalysisCoverage(snapshot({ completedStages: ['BASELINE', 'ANALYZE'] }));
  assert.equal(coverage.state, 'complete');
  assert.equal(severityHeaderText(coverage), '0', 'zero is a real result only once both producers have completed (D-009)');
}

function testCoverageOnlyCountsStaticAnalysisDiscoveryMethod() {
  const coverage = computeStaticAnalysisCoverage(
    snapshot({
      completedStages: ['BASELINE', 'ANALYZE'],
      findings: [
        finding({ id: 'f-static', discovery_method: 'STATIC_ANALYSIS' }),
        finding({ id: 'f-fuzz', discovery_method: 'FUZZING_CAMPAIGN', tool: 'ADDRESS_SANITIZER' }),
      ],
    }),
  );
  assert.equal(coverage.staticFindings.length, 1, 'a fuzzing-confirmed crash finding must never be counted as a static-analysis result');
  assert.equal(coverage.staticFindings[0].id, 'f-static');
}

function testCompilerFindingsAreDistinguishedFromSemgrepByTool() {
  const coverage = computeStaticAnalysisCoverage(
    snapshot({
      completedStages: ['BASELINE', 'ANALYZE'],
      findings: [
        finding({ id: 'f-semgrep', tool: 'SEMGREP' }),
        finding({ id: 'f-compiler', tool: 'COMPILER_DIAGNOSTIC' }),
      ],
    }),
  );
  assert.equal(coverage.staticFindings.length, 2, 'both tools contribute to the severity-grouped total');
  assert.deepEqual(coverage.compilerFindings.map((f) => f.id), ['f-compiler'], 'compiler diagnostics must be separable from Semgrep findings for the compiler-health row');
}

function testSeverityChipColoursFollowTheThreeStateTokenSetOnly() {
  assert.equal(severityChipClass('CRITICAL'), 'bd-chip bd-chip--critical');
  assert.equal(severityChipClass('HIGH'), 'bd-chip bd-chip--critical');
  assert.equal(severityChipClass('MEDIUM'), 'bd-chip bd-chip--warning');
  assert.equal(severityChipClass('LOW'), 'bd-chip', 'LOW must not use a state colour at all — only green/amber/red are meaningful state colours');
  assert.equal(severityChipClass('INFO'), 'bd-chip');
}

// ---------------------------------------------------------------------------
// 2. Static-source design-invariant assertions
// ---------------------------------------------------------------------------

async function testDependencyHealthIsAlwaysNotRun(component, railSource) {
  assert.ok(component.includes('export function NotRunCoverageRow'), 'dependency health must use the shared NOT RUN component (D-057)');
  assert.ok(
    railSource.includes('label="DEPENDENCY HEALTH" reason="no dependency scanner in this build"'),
    'dependency health must disclose the real reason there is no producer, not a vague placeholder',
  );
}

function testDrillDownUsesTheRealFindingDetailEndpoint(source) {
  assert.ok(source.includes('getFinding(missionId, finding.id)'), 'drill-down must fetch the real GET /findings/{id} endpoint, never fabricate detail from the summary alone');
  assert.ok(source.includes('ApiError'), 'a failed drill-down fetch must be handled as a real API error, not swallowed');
  assert.ok(source.includes('[ RETRY ]'), 'a failed evidence fetch must offer a real retry control');
  assert.ok(source.includes('<button type="button"'), 'the drill-down control must be a real <button>, never a synthetic onClick on a bare div/span (#56)');
  assert.ok(source.includes('aria-expanded={expanded}'), 'the drill-down control must expose its expanded state to assistive tech');
}

function testFindingRowShowsFileAndLine(source) {
  assert.ok(source.includes('finding.location.line'), 'the row must render the real file:line the AC calls for');
  assert.ok(source.includes('sanitizeDisplayText(finding.location.file_path'), 'the file path must be sanitized before reaching the DOM');
}

function testCompilerHealthRendersRealCountsNotAPermanentNotRun(source) {
  assert.ok(source.includes('coverage.compilerFindings.length'), 'compiler health must render a real, computed count once BASELINE completes');
  assert.ok(source.includes('waiting for the BASELINE build to complete'), 'compiler health must disclose a pending producer distinctly from a permanently absent one');
  assert.ok(!/COMPILER HEALTH.*NOT RUN/s.test(source), 'compiler health must not use the permanent NOT RUN treatment now that #23 makes it a real producer');
}

function testNoFabricatedValues(...sources) {
  for (const source of sources) {
    assert.ok(!source.includes('Math.random'), 'no analysis-rail source may fabricate a value');
  }
}

function testCssStatesPresent(css) {
  for (const selector of [
    '.analysis-rail__coverage',
    '.analysis-rail__severity-group',
    '.analysis-rail__finding-row',
    '.analysis-rail__coverage-empty',
  ]) {
    assert.ok(css.includes(selector), `CSS missing ${selector}`);
  }
}

async function main() {
  testGroupingSortsBySeverityThenDiscoveryOrder();
  testGroupingNeverFabricatesEmptyBuckets();
  testCoverageIsNotStartedBeforeEitherProducerRuns();
  testCoverageIsPartialWhileOnlyOneProducerHasCompleted();
  testCoverageWithFindingsMidRunIsSoFarNotFinal();
  testCoverageCompleteWithZeroFindingsIsAGenuineCleanScan();
  testCoverageOnlyCountsStaticAnalysisDiscoveryMethod();
  testCompilerFindingsAreDistinguishedFromSemgrepByTool();
  testSeverityChipColoursFollowTheThreeStateTokenSetOnly();

  const [component, railSource, css] = await Promise.all([
    readFile(path.join(appRoot, 'src/components/SeverityFindingsList.tsx'), 'utf8'),
    readFile(path.join(appRoot, 'src/components/AnalysisRail.tsx'), 'utf8'),
    readFile(path.join(appRoot, 'src/styles/global.css'), 'utf8'),
  ]);

  await testDependencyHealthIsAlwaysNotRun(component, railSource);
  testDrillDownUsesTheRealFindingDetailEndpoint(component);
  testFindingRowShowsFileAndLine(component);
  testCompilerHealthRendersRealCountsNotAPermanentNotRun(component);
  testNoFabricatedValues(component);
  testCssStatesPresent(css);

  console.warn(
    'issue #25 analysis rail findings ok: severity grouping/discovery order, not-started vs so-far vs complete ' +
      'coverage states, static-analysis-only scope, compiler/semgrep distinguished, real drill-down fetch, ' +
      'dependency health permanently NOT RUN, compiler health real once BASELINE completes',
  );
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
