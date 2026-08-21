import { useEffect, useRef, useState } from 'react';

import type { GateMatrix, GateResult, MissionSnapshot, PatchCandidate, VerificationRecord } from '../lib/events/store';
import { sanitizeDisplayText } from '../lib/security/renderSafety.mjs';

/**
 * Panel 4 — the Candidate Compare overlay (docs/09-company/04-design-system.md §6.4). Replaces
 * the previous `VerdictComparePanel.tsx`, which rendered the same comparison inline in a 2 × 292
 * grid that could not fit a 72px verdict word or a five-row gate matrix (DS-02, the review's
 * C3). This component reuses that file's data-shaping logic (candidate pairing, provenance
 * chips, gate labels) but restructures the layout entirely: a full-content-width (1328 × 684)
 * overlay with two 652px columns, opened by `[ OPEN COMPARE ]`, a finding-row selection, or
 * automatically when the second `VerificationRecord` lands.
 */

const GATE_ORDER: Array<keyof GateMatrix> = ['compile', 'reproducer_eliminated', 'regression_preserved', 'static_delta', 'renewed_fuzzing'];
const GATE_TITLE: Record<keyof GateMatrix, string> = {
  compile: 'COMPILE',
  reproducer_eliminated: 'REPRODUCER ELIMINATED',
  regression_preserved: 'REGRESSION PRESERVED',
  static_delta: 'STATIC DELTA',
  renewed_fuzzing: 'RENEWED FUZZING',
};
const DIFF_COLLAPSE_LINES = 8;
const DIFF_MAX_LINES = 200; // reachable only on the policy-failure path (§6.4.5)

interface CandidateColumn {
  index: number;
  patch: PatchCandidate;
  verification: VerificationRecord | null;
}

export function CandidateCompareOverlay({
  open,
  onClose,
  snapshot,
  returnFocusRef,
}: {
  open: boolean;
  onClose: () => void;
  snapshot: MissionSnapshot;
  returnFocusRef: React.RefObject<HTMLElement | null>;
}) {
  const closeRef = useRef<HTMLButtonElement | null>(null);
  const [fullDiffColumn, setFullDiffColumn] = useState<number | null>(null);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    closeRef.current?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose();
      }
    }
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      returnFocusRef.current?.focus();
    };
  }, [open, onClose, returnFocusRef]);

  if (!open) {
    return null;
  }

  const columns: CandidateColumn[] = snapshot.patchCandidates.map((patch, index) => ({
    index,
    patch,
    verification: snapshot.verifications.find((record) => record.patch_id === patch.id) ?? null,
  }));

  return (
    <div className="bd-overlay-scrim" role="presentation" onClick={onClose}>
      <div
        className="bd-overlay bd-crop"
        role="dialog"
        aria-modal="true"
        aria-labelledby="bd-compare-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="bd-overlay__header">
          <div>
            <p id="bd-compare-title" className="bd-panel__title">
              [ FINDING {snapshot.finding ? '01' : '—'} · EVIDENCE ]
            </p>
            {snapshot.finding && (
              <p className="bd-overlay__finding-line">
                {snapshot.finding.category.replaceAll('_', ' ')}
                {' · '}{sanitizeDisplayText(snapshot.finding.location.file_path, { maxLength: 60 })}
                {snapshot.finding.location.line ? `:${snapshot.finding.location.line}` : ''}
              </p>
            )}
          </div>
          <button ref={closeRef} type="button" className="bd-bracket-control" onClick={onClose}>
            [ ESC CLOSE ]
          </button>
        </header>

        {columns.length === 0 && (
          <p className="bd-panel__empty">
            <span className="bd-panel__empty-label">[ NO PATCH CANDIDATE ]</span>
            A diff appears when the patch stage produces a candidate.
          </p>
        )}

        {columns.length === 1 && (
          <div className="bd-overlay__grid bd-overlay__grid--degraded">
            <CandidateColumnView
              column={columns[0]!}
              fullDiff={fullDiffColumn === 0}
              onOpenFullDiff={() => setFullDiffColumn(0)}
              onBackToCompare={() => setFullDiffColumn(null)}
            />
            <EvidenceColumn snapshot={snapshot} />
          </div>
        )}

        {columns.length >= 2 && (
          <div className="bd-overlay__grid">
            {columns.slice(-2).map((column) => (
              <CandidateColumnView
                key={column.patch.id}
                column={column}
                fullDiff={fullDiffColumn === column.index}
                onOpenFullDiff={() => setFullDiffColumn(column.index)}
                onBackToCompare={() => setFullDiffColumn(null)}
              />
            ))}
          </div>
        )}
        {columns.length > 2 && (
          <p className="bd-overlay__overflow-note">
            [ {columns.length} CANDIDATES · SHOWING {String(columns.length - 1).padStart(2, '0')}, {String(columns.length).padStart(2, '0')} ]
          </p>
        )}
      </div>
    </div>
  );
}

function CandidateColumnView({
  column,
  fullDiff,
  onOpenFullDiff,
  onBackToCompare,
}: {
  column: CandidateColumn;
  fullDiff: boolean;
  onOpenFullDiff: () => void;
  onBackToCompare: () => void;
}) {
  const { index, patch, verification } = column;
  const provenance = provenanceValue(patch);
  const policyFailed = patch.policy_status !== 'ACCEPTED';

  if (!provenance) {
    return (
      <article className={`bd-compare-col${fullDiff ? ' bd-compare-col--full' : ''}`}>
        <p className="bd-compare-col__candidate">[ CANDIDATE {String(index + 1).padStart(2, '0')} ]</p>
        <p className="bd-chip bd-chip--critical">[ × PROVENANCE MISSING ]</p>
        <p className="bd-compare-col__suppressed">This candidate&rsquo;s provenance is not recorded. Its verdict is withheld.</p>
      </article>
    );
  }

  const verdictWord = policyFailed ? 'Not verified' : verdictWordFor(verification);
  const verdictTone = policyFailed ? 'secondary' : verdictToneFor(verification);
  const gatesRan = verification ? GATE_ORDER.filter((gate) => verification.gates[gate]?.status !== 'NOT_RUN').length : 0;

  return (
    <article className={`bd-compare-col${fullDiff ? ' bd-compare-col--full' : ''}`}>
      <p className="bd-compare-col__candidate">[ CANDIDATE {String(index + 1).padStart(2, '0')} ]</p>
      <p className="bd-compare-col__provenance">[ PROVENANCE · {provenance} ]</p>
      <p className={`bd-compare-col__policy${policyFailed ? ' bd-compare-col__policy--fail' : ''}`}>
        [ POLICY · {policyFailed ? 'FAIL' : 'PASS'}{policyFailed && patch.policy_detail ? ` · ${sanitizeDisplayText(patch.policy_detail, { maxLength: 80 })}` : ` · ${patch.lines_changed}/25 lines`} ]
      </p>

      <div className={`bd-compare-col__verdict-block bd-compare-col__verdict-block--${verdictTone}`}>
        <p className="bd-compare-col__verdict-word">{verdictWord}</p>
        <div className="bd-compare-col__verdict-underline" />
        {!policyFailed && (
          <p className="bd-compare-col__gates-ran">[ {gatesRan} OF {GATE_ORDER.length} GATES RAN ]</p>
        )}
      </div>

      <dl className="bd-gate-matrix">
        {GATE_ORDER.map((name) => (
          <CompareGateRow key={name} name={name} gate={verification?.gates[name]} policyFailed={policyFailed} />
        ))}
      </dl>

      <DiffBlock patch={patch} policyFailed={policyFailed} fullDiff={fullDiff} onOpenFullDiff={onOpenFullDiff} onBackToCompare={onBackToCompare} />

      <div className="bd-compare-col__self-report">
        <p className="bd-panel__title">[ MODEL SELF-REPORT ]</p>
        <p>{modelSelfReport(patch)}</p>
      </div>
    </article>
  );
}

function CompareGateRow({ name, gate, policyFailed }: { name: keyof GateMatrix; gate: GateResult | undefined; policyFailed: boolean }) {
  const status = policyFailed ? 'NOT_RUN' : gate?.status ?? 'NOT_RUN';
  const reason = policyFailed ? 'refused by patch policy' : gate?.detail;
  const glyph = status === 'PASS' ? '+' : status === 'FAIL' ? '×' : status === 'ERROR' ? '!' : '—';
  const tone = status === 'PASS' ? 'verified' : status === 'FAIL' ? 'critical' : status === 'ERROR' ? 'warning' : reason ? 'not-run' : 'critical';
  const detail = status === 'NOT_RUN'
    ? `NOT RUN · ${reason && reason.length > 0 ? reason : 'REASON NOT SUPPLIED'}`
    : gate?.detail || gate?.tool || status;

  return (
    <div className={`bd-gate-row bd-gate-row--${tone}`}>
      <dt className="bd-gate-row__label">[ {glyph} {GATE_TITLE[name]} ]</dt>
      <dd className="bd-gate-row__detail">{sanitizeDisplayText(detail, { maxLength: 200 })}</dd>
    </div>
  );
}

function EvidenceColumn({ snapshot }: { snapshot: MissionSnapshot }) {
  return (
    <article className="bd-compare-col bd-compare-col--evidence">
      <p className="bd-compare-col__candidate">[ EVIDENCE · FINDING 01 ]</p>
      {snapshot.finding ? (
        <>
          <p className="bd-compare-col__policy">
            {sanitizeDisplayText(snapshot.finding.title, { maxLength: 120 })}
          </p>
          <p className="bd-evidence__line">
            {sanitizeDisplayText(snapshot.finding.location.file_path, { maxLength: 80 })}
            {snapshot.finding.location.line ? `:${snapshot.finding.location.line}` : ''}
          </p>
          {snapshot.reproducer && (
            <p className="bd-evidence__line">
              replay {snapshot.reproducer.replay_successes}/{snapshot.reproducer.replay_attempts} from a clean build
            </p>
          )}
        </>
      ) : (
        <p className="bd-panel__empty">No finding bound to this mission yet.</p>
      )}
    </article>
  );
}

function DiffBlock({
  patch,
  policyFailed,
  fullDiff,
  onOpenFullDiff,
  onBackToCompare,
}: {
  patch: PatchCandidate;
  policyFailed: boolean;
  fullDiff: boolean;
  onOpenFullDiff: () => void;
  onBackToCompare: () => void;
}) {
  const lines = parseDiff(patch.diff);
  const cap = policyFailed ? DIFF_MAX_LINES : lines.length;
  const truncated = policyFailed && lines.length > DIFF_MAX_LINES;
  const visibleCount = fullDiff ? Math.min(lines.length, cap) : Math.min(DIFF_COLLAPSE_LINES, lines.length);
  const visible = lines.slice(0, visibleCount);
  const hiddenCount = lines.length - visible.length;

  return (
    <div className={`bd-diff${policyFailed ? ' bd-diff--refused' : ''}`}>
      <p className="bd-panel__title">[ DIFF · patch ]</p>
      <p className="bd-diff__meta">files {patch.files_changed}/1 · changed lines {patch.lines_changed}/25</p>
      {truncated && (
        <p className="bd-chip bd-chip--warning">[ ! TRUNCATED · {DIFF_MAX_LINES} OF {lines.length} LINES ]</p>
      )}
      {lines.length === 0 ? (
        <p className="bd-panel__empty">diff pending</p>
      ) : (
        <ol className="bd-diff__body" aria-label={`${patch.id} unified diff`}>
          {visible.map((line, index) => (
            <li key={index} className={`bd-diff__line bd-diff__line--${line.kind}`}>
              <span className="bd-diff__gutter">{line.gutter}</span>
              <span className="bd-diff__text">{sanitizeDisplayText(line.text, { maxLength: 240 })}</span>
            </li>
          ))}
        </ol>
      )}
      {hiddenCount > 0 && !fullDiff && (
        <p className="bd-diff__disclosure">
          <span>[ … {hiddenCount} LINES ]</span>
          <button type="button" className="bd-bracket-control bd-bracket-control--inline" onClick={onOpenFullDiff}>[ OPEN FULL ]</button>
        </p>
      )}
      {fullDiff && (
        <button type="button" className="bd-bracket-control bd-bracket-control--inline" onClick={onBackToCompare}>[ ← BACK TO COMPARE ]</button>
      )}
    </div>
  );
}

interface DiffLine {
  kind: 'added' | 'removed' | 'context';
  gutter: string;
  text: string;
}

function parseDiff(diff: string): DiffLine[] {
  if (!diff) {
    return [];
  }
  return diff.split('\n')
    .filter((line) => !line.startsWith('+++') && !line.startsWith('---') && !line.startsWith('diff --git') && !line.startsWith('index '))
    .map((line) => {
      if (line.startsWith('+')) {
        return { kind: 'added' as const, gutter: '+', text: line.slice(1) };
      }
      if (line.startsWith('-')) {
        return { kind: 'removed' as const, gutter: '−', text: line.slice(1) };
      }
      return { kind: 'context' as const, gutter: ' ', text: line.replace(/^ /, '') };
    });
}

function provenanceValue(patch: PatchCandidate): string | null {
  if (patch.provenance === 'MODEL_GENERATED') return 'MODEL-GENERATED';
  if (patch.provenance === 'OPERATOR_SUPPLIED') return 'OPERATOR-SUPPLIED';
  return null;
}

function verdictWordFor(verification: VerificationRecord | null): string {
  if (!verification) return 'Running';
  if (verification.verdict === 'VERIFIED') return 'Verified';
  if (verification.verdict === 'REJECTED') return 'Rejected';
  return 'Held';
}

function verdictToneFor(verification: VerificationRecord | null): 'secondary' | 'running' | 'verified' | 'critical' | 'warning' {
  if (!verification) return 'running';
  if (verification.verdict === 'VERIFIED') return 'verified';
  if (verification.verdict === 'REJECTED') return 'critical';
  return 'warning';
}

function modelSelfReport(patch: PatchCandidate): string {
  if (patch.provenance !== 'MODEL_GENERATED' || !patch.model) {
    return 'n/a · operator-supplied';
  }
  const confidence = patch.model.confidence;
  return confidence != null
    ? `confidence ${confidence.toFixed(2)} · not a verdict · no gate reads this value`
    : 'confidence not reported · not a verdict · no gate reads this value';
}
