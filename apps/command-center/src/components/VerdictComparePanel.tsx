import type {
  GateMatrix,
  GateResult,
  MissionSnapshot,
  PatchCandidate,
  VerificationRecord,
} from '../lib/events/store';
import { sanitizeDisplayText } from '../lib/security/renderSafety.mjs';

interface CandidateColumn {
  patch: PatchCandidate | null;
  verification: VerificationRecord | null;
}

const gateOrder: Array<keyof GateMatrix> = [
  'compile',
  'reproducer_eliminated',
  'regression_preserved',
  'static_delta',
  'renewed_fuzzing',
];

export function VerdictComparePanel({ snapshot }: { snapshot: MissionSnapshot }) {
  const columns = compareColumns(snapshot);
  const summary = verdictSummaryText(snapshot);

  return (
    <section className="verdict-compare" aria-labelledby="verdict-compare-title">
      <header>
        <h2 id="verdict-compare-title">[ D6 VERDICT LOOP ]</h2>
        <strong>{summary}</strong>
      </header>
      <div className="verdict-compare__grid">
        {columns.map((column, index) => (
          <CandidateVerdictColumn key={column.patch?.id ?? `candidate-${index}`} column={column} index={index} />
        ))}
      </div>
    </section>
  );
}

function CandidateVerdictColumn({ column, index }: { column: CandidateColumn; index: number }) {
  const provenance = provenanceChip(column.patch);
  const missingProvenance = provenance === '[ × PROVENANCE MISSING ]';
  const verdict = column.verification?.verdict ?? 'HUMAN_REVIEW_REQUIRED';
  const diff = column.patch?.diff ?? '';

  return (
    <article className={`candidate-card candidate-card--${verdict.toLowerCase()}`}>
      <header>
        <span>Candidate {index + 1}</span>
        <strong>{verdictLabel(verdict, column.verification)}</strong>
        <small className={missingProvenance ? 'candidate-card__provenance-missing' : ''}>
          {provenance}
        </small>
      </header>

      {missingProvenance ? (
        <div className="candidate-card__blocked">candidate body suppressed until provenance is present</div>
      ) : (
        <>
          <pre className="candidate-diff" aria-label={`Candidate ${index + 1} unified diff`}>
            {renderDiff(diff)}
          </pre>
          <GateMatrixRows gates={column.verification?.gates ?? null} />
          <footer>
            <span>policy {column.patch?.policy_status ?? 'pending'}</span>
            <span>{confidenceText(column.patch)}</span>
          </footer>
        </>
      )}
    </article>
  );
}

function GateMatrixRows({ gates }: { gates: GateMatrix | null }) {
  return (
    <dl className="gate-matrix">
      {gateOrder.map((name) => {
        const gate = gates?.[name] as GateResult | undefined;
        return (
          <div key={name} className={`gate-matrix__row gate-matrix__row--${(gate?.status ?? 'NOT_RUN').toLowerCase()}`}>
            <dt>{gateLabel(name)}</dt>
            <dd>
              <strong>{statusLabel(gate)}</strong>
              <span>{gateDetail(gate)}</span>
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

function compareColumns(snapshot: MissionSnapshot): CandidateColumn[] {
  const pairs = snapshot.patchCandidates.map((patch) => ({
    patch,
    verification: snapshot.verifications.find((record) => record.patch_id === patch.id) ?? null,
  }));
  const sorted = pairs.sort((a, b) => verdictWeight(a.verification?.verdict) - verdictWeight(b.verification?.verdict));
  return [sorted[0] ?? { patch: null, verification: null }, sorted[1] ?? { patch: null, verification: null }];
}

function verdictSummaryText(snapshot: MissionSnapshot): string {
  const summary = snapshot.verdictSummary;
  if (!summary) {
    return 'waiting for two candidate verdicts';
  }
  const ran = snapshot.verifications.reduce((total, record) => (
    total + gateOrder.filter((gate) => record.gates[gate]?.status !== 'NOT_RUN').length
  ), 0);
  const total = snapshot.verifications.length * gateOrder.length;
  return `${summary.mission_verdict} - ${ran} of ${total} gates ran - ${summary.verified_count} of ${summary.candidates?.length ?? 0} candidates verified`;
}

function provenanceChip(patch: PatchCandidate | null): string {
  if (!patch?.provenance) {
    return '[ × PROVENANCE MISSING ]';
  }
  if (patch.provenance === 'MODEL_GENERATED') {
    const replayedAt = patch.model?.captured_at;
    if (replayedAt) {
      return `[ PROVENANCE · MODEL-GENERATED · REPLAYED ${dateOnly(replayedAt)} ]`;
    }
    return '[ PROVENANCE · MODEL-GENERATED ]';
  }
  if (patch.provenance === 'OPERATOR_SUPPLIED') {
    return '[ PROVENANCE · OPERATOR-SUPPLIED ]';
  }
  return '[ × PROVENANCE MISSING ]';
}

function verdictLabel(verdict: string, verification: VerificationRecord | null): string {
  if (!verification) {
    return 'PENDING';
  }
  const ran = gateOrder.filter((gate) => verification.gates[gate]?.status !== 'NOT_RUN').length;
  return `${verdict} - ${ran} of ${gateOrder.length} gates ran`;
}

function renderDiff(diff: string): string {
  if (!diff) {
    return 'diff pending';
  }
  return sanitizeDisplayText(diff, { fallback: 'diff unavailable', maxLength: 3200 })
    .split('\n')
    .slice(0, 16)
    .join('\n');
}

function statusLabel(gate: GateResult | undefined): string {
  return gate?.status ?? 'NOT_RUN';
}

function gateDetail(gate: GateResult | undefined): string {
  if (!gate) {
    return 'waiting for this gate to run';
  }
  if (gate.status === 'NOT_RUN') {
    return gate.detail || 'not run; reason missing';
  }
  if (gate.status === 'ERROR') {
    return gate.detail || 'error; detail missing';
  }
  return gate.detail || gate.tool || 'recorded';
}

function gateLabel(name: keyof GateMatrix): string {
  return name.toUpperCase().replaceAll('_', ' ');
}

function confidenceText(patch: PatchCandidate | null): string {
  const confidence = patch?.model?.confidence;
  return typeof confidence === 'number'
    ? `model confidence ${Math.round(confidence * 100)}% - display only`
    : 'model confidence not used';
}

function verdictWeight(verdict: string | undefined): number {
  if (verdict === 'VERIFIED') {
    return 0;
  }
  if (verdict === 'REJECTED') {
    return 1;
  }
  return 2;
}

function dateOnly(value: string): string {
  return value.slice(0, 10);
}
