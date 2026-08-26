/**
 * Pure logic behind the Analysis Rail's #25 extension (`SeverityFindingsList.tsx`) — severity
 * grouping and the "has this producer actually run" coverage computation. Split out of the
 * component (which is `.tsx`/JSX) so it can be imported and tested directly with Node's built-in
 * TypeScript stripping (`node --experimental-strip-types`), without a JSX toolchain, mirroring
 * `formLogic.ts`'s own reason for existing — see
 * `scripts/check-issue-25-analysis-rail-findings.mjs`.
 */

import type { FindingSummary, MissionSnapshot, MissionStage, Severity } from '../events/store.ts';

export const SEVERITY_ORDER: Severity[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];

export interface SeverityGroup {
  severity: Severity;
  findings: FindingSummary[];
}

/**
 * Real buckets only — a severity with zero findings gets no header. Fabricating an empty
 * "CRITICAL · 0" row next to real populated ones would look more thoroughly audited than the
 * scan actually was (docs/09-company/13-cut-pullback-design-spec.md §1.2: "nothing here
 * fabricates empty severity buckets to look comprehensive"). Sort within a bucket is discovery
 * order (`detected_at` ascending), matching §1.4's "severity, then discovery order."
 */
export function groupFindingsBySeverity(findings: FindingSummary[]): SeverityGroup[] {
  const buckets = new Map<Severity, FindingSummary[]>();
  for (const finding of findings) {
    const bucket = buckets.get(finding.severity);
    if (bucket) {
      bucket.push(finding);
    } else {
      buckets.set(finding.severity, [finding]);
    }
  }
  for (const bucket of buckets.values()) {
    bucket.sort((a, b) => a.detected_at.localeCompare(b.detected_at));
  }
  return SEVERITY_ORDER.filter((severity) => buckets.has(severity)).map((severity) => ({
    severity,
    findings: buckets.get(severity) ?? [],
  }));
}

export type CoverageState = 'not-started' | 'partial' | 'complete';

export interface StaticAnalysisCoverage {
  /** Whether the ANALYZE stage (Semgrep, #22) has completed for this mission. */
  analyzeComplete: boolean;
  /** Whether the BASELINE stage (compiler diagnostics parsed from its own build, #23) has
   * completed for this mission. */
  baselineComplete: boolean;
  staticFindings: FindingSummary[];
  compilerFindings: FindingSummary[];
  /**
   * `not-started`: neither producer has run yet — the count is not-measured, never a zero.
   * `partial`: one producer has completed and the other has not — any findings so far are real,
   * but the total is not final, so it is never presented as a completed clean scan.
   * `complete`: both producers have run — the count, including zero, is a genuine result
   * (D-009/§2.6: "a zero is a result. It is never a placeholder.").
   */
  state: CoverageState;
}

const STATIC_ANALYSIS_STAGES: readonly MissionStage[] = ['BASELINE', 'ANALYZE'];

export function computeStaticAnalysisCoverage(snapshot: MissionSnapshot): StaticAnalysisCoverage {
  const analyzeComplete = snapshot.completedStages.includes('ANALYZE');
  const baselineComplete = snapshot.completedStages.includes('BASELINE');
  const completedCount = STATIC_ANALYSIS_STAGES.filter((stage) => snapshot.completedStages.includes(stage)).length;
  const staticFindings = snapshot.findings.filter((finding) => finding.discovery_method === 'STATIC_ANALYSIS');
  const compilerFindings = staticFindings.filter((finding) => finding.tool === 'COMPILER_DIAGNOSTIC');

  const state: CoverageState =
    completedCount === 0 ? 'not-started' : completedCount < STATIC_ANALYSIS_STAGES.length ? 'partial' : 'complete';

  return { analyzeComplete, baselineComplete, staticFindings, compilerFindings, state };
}

export function severityHeaderText(coverage: StaticAnalysisCoverage): string {
  if (coverage.state === 'not-started') {
    return '—';
  }
  if (coverage.state === 'partial') {
    return coverage.staticFindings.length > 0 ? `${coverage.staticFindings.length} SO FAR` : '—';
  }
  return String(coverage.staticFindings.length);
}

export function severityChipClass(severity: Severity): string {
  if (severity === 'CRITICAL' || severity === 'HIGH') return 'bd-chip bd-chip--critical';
  if (severity === 'MEDIUM') return 'bd-chip bd-chip--warning';
  return 'bd-chip';
}

export function toolLabel(tool: FindingSummary['tool']): string {
  return tool === 'COMPILER_DIAGNOSTIC' ? 'COMPILER' : tool === 'SEMGREP' ? 'SEMGREP' : tool;
}
