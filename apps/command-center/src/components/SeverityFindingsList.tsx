import { useState } from 'react';

import { ApiError, getFinding, type FindingDetail } from '../lib/api/client';
import type { FindingSummary, MissionSnapshot, StreamState } from '../lib/events/store';
import {
  computeStaticAnalysisCoverage,
  groupFindingsBySeverity,
  severityChipClass,
  severityHeaderText,
  toolLabel,
  type StaticAnalysisCoverage,
} from '../lib/missionControl/severityFindings';
import { sanitizeDisplayText } from '../lib/security/renderSafety.mjs';

export { computeStaticAnalysisCoverage };
export type { StaticAnalysisCoverage };

/**
 * #25 — the Analysis Rail's findings-by-severity, dependency-health and compiler-health
 * extension (docs/09-company/13-cut-pullback-design-spec.md §1, D-057). Reuses the existing
 * finding-row/evidence-block vocabulary the design system already specifies for the fuzzing
 * findings rail (§6.3, §6.3a — `FindingsRail.tsx`'s own `getFinding`/`ApiError`/evidence
 * pattern) rather than inventing a second one; the only genuinely new pieces are the
 * severity-first grouping and the two coverage rows. Grouping/coverage logic itself lives in
 * `../lib/missionControl/severityFindings.ts` so it is testable without a JSX toolchain — see
 * that module's own doc comment.
 *
 * Scope: `DiscoveryMethod.STATIC_ANALYSIS` findings only (Semgrep, #22, and compiler
 * diagnostics, #23) — the fuzzing-confirmed crash finding already has its own dedicated rail
 * and evidence block (`FindingsRail.tsx`) and is deliberately not duplicated here. #25's own
 * body names "the static-analysis findings summary" specifically.
 */

export function SeverityFindingsList({
  snapshot,
  streamState,
  coverage,
}: {
  snapshot: MissionSnapshot;
  streamState: StreamState;
  coverage: StaticAnalysisCoverage;
}) {
  const groups = groupFindingsBySeverity(coverage.staticFindings);
  const degraded = streamState === 'stale' || streamState === 'error';

  return (
    <section className="analysis-rail__coverage-block" aria-labelledby="analysis-rail-severity-title">
      <header className="analysis-rail__coverage-header">
        <h3 id="analysis-rail-severity-title" className="analysis-rail__coverage-title">[ FINDINGS BY SEVERITY ]</h3>
        <strong>{severityHeaderText(coverage)}</strong>
        {degraded && <span className="bd-chip bd-chip--warning">[ ! MAY BE INCOMPLETE ]</span>}
      </header>

      {coverage.state === 'not-started' && (
        <p className="analysis-rail__coverage-empty">
          Static analysis findings appear once BASELINE and ANALYZE complete.
        </p>
      )}

      {coverage.state !== 'not-started' && coverage.staticFindings.length === 0 && (
        <p className="analysis-rail__coverage-empty">
          {coverage.state === 'complete'
            ? 'Semgrep and compiler diagnostics completed with no findings.'
            : 'Static analysis is still running; no findings recorded yet.'}
        </p>
      )}

      {groups.map((group) => (
        <div key={group.severity} className="analysis-rail__severity-group">
          <p className="analysis-rail__severity-header">
            [ {group.severity} · {group.findings.length} ]
          </p>
          <ol className="analysis-rail__finding-rows">
            {group.findings.map((finding, index) => (
              <SeverityFindingRow key={finding.id} finding={finding} missionId={snapshot.missionId} index={index + 1} />
            ))}
          </ol>
        </div>
      ))}
    </section>
  );
}

function SeverityFindingRow({
  finding,
  missionId,
  index,
}: {
  finding: FindingSummary;
  missionId: string | null;
  index: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const [detail, setDetail] = useState<FindingDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleToggle() {
    if (expanded) {
      setExpanded(false);
      return;
    }
    setExpanded(true);
    if (detail || !missionId) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setDetail(await getFinding(missionId, finding.id));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'finding detail request failed');
    } finally {
      setLoading(false);
    }
  }

  const location = `${sanitizeDisplayText(finding.location.file_path, { maxLength: 80 })}${finding.location.line ? `:${finding.location.line}` : ''}`;

  return (
    <li className="analysis-rail__finding-row">
      <div className="analysis-rail__finding-row-line">
        <span className="analysis-rail__finding-index">[ FINDING {String(index).padStart(2, '0')} ]</span>
        <span className="analysis-rail__finding-title">{sanitizeDisplayText(finding.title, { maxLength: 60 })}</span>
        <span className={severityChipClass(finding.severity)}>[ {toolLabel(finding.tool)} ]</span>
      </div>
      <div className="analysis-rail__finding-row-meta">
        <small>{location}</small>
        <button type="button" className="bd-bracket-control bd-bracket-control--inline" onClick={handleToggle} aria-expanded={expanded}>
          {expanded ? '[ HIDE EVIDENCE ]' : '[ VIEW EVIDENCE ]'}
        </button>
      </div>
      {expanded && (
        <div className="analysis-rail__finding-evidence">
          {loading && (
            <div className="bd-evidence bd-evidence--loading" aria-hidden="true">
              <div className="bd-placeholder-rule bd-placeholder-rule--65" />
              <div className="bd-placeholder-rule bd-placeholder-rule--40" />
            </div>
          )}
          {!loading && error && (
            <div className="bd-evidence bd-evidence--failed">
              <p className="bd-evidence__error" role="alert">[ × EVIDENCE UNAVAILABLE ] {sanitizeDisplayText(error, { maxLength: 200 })}</p>
              <button type="button" className="bd-bracket-control bd-bracket-control--inline" onClick={handleToggle}>[ RETRY ]</button>
            </div>
          )}
          {!loading && !error && detail && (
            <div className="bd-evidence">
              <div className="bd-evidence__block">
                <p className="bd-panel__title">[ EVIDENCE · {toolLabel(finding.tool)} ]</p>
                {detail.code_slice ? (
                  <p className="bd-evidence__raw">{sanitizeDisplayText(detail.code_slice, { maxLength: 600, preserveWhitespace: true })}</p>
                ) : (
                  <p className="bd-evidence__pending">[ — CODE SLICE · NOT CAPTURED ]</p>
                )}
                {detail.sanitizer_report && (
                  <p className="bd-evidence__line">{sanitizeDisplayText(detail.sanitizer_report, { maxLength: 300 })}</p>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

/** #1.3/D-057 — the shared "this class of check never ran" row. One component, every caller
 * that renders a permanently-absent producer, so the word/colour/reason rule can't drift
 * between them. Distinct from a pending real producer (see `CompilerHealthRow` below), which
 * uses the quiet not-measured-value treatment instead (D-023/DS-03) because it genuinely will
 * complete, not because it never runs. */
export function NotRunCoverageRow({ label, reason }: { label: string; reason: string }) {
  return (
    <div className="analysis-rail__coverage-block">
      <p className="analysis-rail__coverage-title">[ {label} ]</p>
      <p className="bd-chip bd-chip--not-run">
        [ — {label} · NOT RUN · {sanitizeDisplayText(reason, { maxLength: 200 })} ]
      </p>
    </div>
  );
}

export function CompilerHealthRow({ coverage }: { coverage: StaticAnalysisCoverage }) {
  if (!coverage.baselineComplete) {
    return (
      <div className="analysis-rail__coverage-block">
        <p className="analysis-rail__coverage-title">[ COMPILER HEALTH ]</p>
        <p className="analysis-rail__coverage-empty">— waiting for the BASELINE build to complete</p>
      </div>
    );
  }

  const count = coverage.compilerFindings.length;
  return (
    <div className="analysis-rail__coverage-block">
      <p className="analysis-rail__coverage-title">[ COMPILER HEALTH ]</p>
      <p className={count > 0 ? 'bd-chip bd-chip--warning' : 'bd-chip bd-chip--verified'}>
        [ {count} DIAGNOSTIC{count === 1 ? '' : 'S'}{count === 0 ? ' · CLEAN BUILD' : ''} ]
      </p>
    </div>
  );
}
