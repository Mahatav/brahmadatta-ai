import type { GateMatrix, GateResult, MissionSnapshot, StreamState, VerificationRecord } from '../lib/events/store';
import { sanitizeDisplayText } from '../lib/security/renderSafety.mjs';

/**
 * Panel 5 — the Verdict panel (docs/09-company/04-design-system.md §6.5). Centre column, below
 * the Core, 608 × 236. Shows the MISSION verdict (`derive_mission_outcome` over the candidate
 * set) — the per-candidate verdicts live side by side in the Candidate Compare overlay (§6.4).
 *
 * The five-row gate matrix is reserved from first paint (§12 build note 10): all five rows
 * always render, `NOT_RUN` with a reason before anything has executed, so the matrix never grows
 * underneath a judge reading it.
 */

const GATE_ORDER: Array<keyof GateMatrix> = ['compile', 'reproducer_eliminated', 'regression_preserved', 'static_delta', 'renewed_fuzzing'];
const GATE_TITLE: Record<keyof GateMatrix, string> = {
  compile: 'COMPILE',
  reproducer_eliminated: 'REPRODUCER ELIMINATED',
  regression_preserved: 'REGRESSION PRESERVED',
  static_delta: 'STATIC DELTA',
  renewed_fuzzing: 'RENEWED FUZZING',
};

export function VerdictPanel({
  snapshot,
  streamState,
  hasActiveMission,
  onOpenCompare,
}: {
  snapshot: MissionSnapshot;
  streamState: StreamState;
  hasActiveMission: boolean;
  onOpenCompare: () => void;
}) {
  if (!hasActiveMission) {
    return (
      <section className="bd-panel bd-crop bd-verdict" aria-labelledby="bd-verdict-title">
        <h2 id="bd-verdict-title" className="bd-panel__title">[ VERDICT ]</h2>
        <VerdictWord word="Pending" tone="secondary" />
        <p className="bd-verdict__denominator">[ — GATES · NONE RAN ]</p>
        <GateRows gates={null} verdictWord="Pending" />
      </section>
    );
  }

  const candidateCount = snapshot.patchCandidates.length;
  const winning = pickWinningVerification(snapshot);
  const winningIndex = winning ? snapshot.patchCandidates.findIndex((patch) => patch.id === winning.patch_id) : -1;
  const degraded = streamState === 'stale';

  const label = candidateCount >= 2
    ? `[ VERDICT · ${candidateCount} CANDIDATES${winningIndex >= 0 ? ` · MATRIX: CANDIDATE ${String(winningIndex + 1).padStart(2, '0')}` : ''} ]`
    : '[ VERDICT ]';

  const { word, tone, denominator } = verdictWordFor(snapshot, winning);

  return (
    <section className="bd-panel bd-crop bd-verdict" aria-labelledby="bd-verdict-title">
      <header className="bd-verdict__header">
        <h2 id="bd-verdict-title" className="bd-panel__title">
          {degraded ? '[ ! VERDICT MAY BE STALE · RELOAD ]' : label}
        </h2>
        {candidateCount >= 2 && (
          <button type="button" className="bd-bracket-control bd-bracket-control--inline" onClick={onOpenCompare}>
            [ OPEN COMPARE ]
          </button>
        )}
      </header>

      <VerdictWord word={word} tone={tone} />
      <p className="bd-verdict__denominator">{denominator}</p>
      <GateRows gates={winning?.gates ?? null} verdictWord={word} humanReviewReason={humanReviewReason(snapshot)} />
    </section>
  );
}

function VerdictWord({ word, tone }: { word: string; tone: 'secondary' | 'running' | 'verified' | 'critical' | 'warning' }) {
  return (
    <div className={`bd-verdict__word-block bd-verdict__word-block--${tone}`}>
      <p className="bd-verdict__word">{word}</p>
      <div className="bd-verdict__underline" />
    </div>
  );
}

function pickWinningVerification(snapshot: MissionSnapshot): VerificationRecord | null {
  if (snapshot.verifications.length === 0) {
    return null;
  }
  const missionVerdict = snapshot.verdictSummary?.mission_verdict;
  if (missionVerdict) {
    const match = snapshot.verifications.find((record) => record.verdict === missionVerdict);
    if (match) {
      return match;
    }
  }
  return snapshot.verifications[snapshot.verifications.length - 1] ?? null;
}

function verdictWordFor(
  snapshot: MissionSnapshot,
  winning: VerificationRecord | null,
): { word: string; tone: 'secondary' | 'running' | 'verified' | 'critical' | 'warning'; denominator: string } {
  if (snapshot.state === 'HUMAN_REVIEW') {
    return { word: 'Held', tone: 'warning', denominator: gatesRanDenominator(winning) };
  }
  if (snapshot.state === 'FAILED') {
    return { word: 'Failed', tone: 'critical', denominator: '[ 0 OF 5 GATES RAN ]' };
  }
  if (snapshot.verdictSummary?.mission_verdict === 'VERIFIED' || snapshot.state === 'VERIFIED') {
    return { word: 'Verified', tone: 'verified', denominator: gatesRanDenominator(winning) };
  }
  if (snapshot.verdictSummary?.mission_verdict === 'REJECTED' || snapshot.state === 'REJECTED') {
    return { word: 'Rejected', tone: 'critical', denominator: gatesRanDenominator(winning) };
  }
  if (snapshot.patchCandidates.length > 0 && !winning) {
    return { word: 'Running', tone: 'running', denominator: '[ — GATES · 0 OF 5 RESOLVED ]' };
  }
  if (winning) {
    return { word: winning.verdict === 'HUMAN_REVIEW_REQUIRED' ? 'Held' : winning.verdict === 'VERIFIED' ? 'Verified' : 'Rejected', tone: winning.verdict === 'VERIFIED' ? 'verified' : winning.verdict === 'REJECTED' ? 'critical' : 'warning', denominator: gatesRanDenominator(winning) };
  }
  return { word: 'Pending', tone: 'secondary', denominator: '[ — GATES · NONE RAN ]' };
}

function gatesRanDenominator(winning: VerificationRecord | null): string {
  if (!winning) {
    return '[ — GATES · NONE RAN ]';
  }
  const ran = GATE_ORDER.filter((gate) => winning.gates[gate]?.status && winning.gates[gate]?.status !== 'NOT_RUN').length;
  return `[ ${ran} OF ${GATE_ORDER.length} GATES RAN ]`;
}

function humanReviewReason(snapshot: MissionSnapshot): string | null {
  if (snapshot.state !== 'HUMAN_REVIEW') {
    return null;
  }
  return snapshot.failedReason ?? snapshot.latestMessage;
}

function GateRows({ gates, verdictWord, humanReviewReason }: { gates: GateMatrix | null; verdictWord: string; humanReviewReason?: string | null }) {
  return (
    <dl className="bd-gate-matrix">
      {GATE_ORDER.map((name) => {
        const gate = gates?.[name] as GateResult | undefined;
        return <GateRow key={name} name={name} gate={gate} />;
      })}
      {verdictWord === 'Held' && humanReviewReason && (
        <p className="bd-verdict__policy-note">[ ! HELD FOR HUMAN REVIEW ] {sanitizeDisplayText(humanReviewReason, { maxLength: 200 })}</p>
      )}
    </dl>
  );
}

function GateRow({ name, gate }: { name: keyof GateMatrix; gate: GateResult | undefined }) {
  const status = gate?.status ?? 'NOT_RUN';
  const reasonMissing = status === 'NOT_RUN' && !(gate?.detail && gate.detail.length > 0);
  const glyph = status === 'PASS' ? '+' : status === 'FAIL' ? '×' : status === 'ERROR' ? '!' : '—';
  const tone = status === 'PASS'
    ? 'verified'
    : status === 'FAIL' || reasonMissing
      ? 'critical'
      : status === 'ERROR'
        ? 'warning'
        : 'not-run';
  const detail = gateDetail(gate, status);

  return (
    <div className={`bd-gate-row bd-gate-row--${tone}`}>
      <dt className="bd-gate-row__label">[ {glyph} {GATE_TITLE[name]} ]</dt>
      <dd className="bd-gate-row__detail">{sanitizeDisplayText(detail, { maxLength: 200, fallback: '' })}</dd>
    </div>
  );
}

function gateDetail(gate: GateResult | undefined, status: string): string {
  if (!gate || status === 'NOT_RUN') {
    const reason = gate?.detail;
    return reason && reason.length > 0 ? `NOT RUN · ${reason}` : 'NOT RUN · REASON NOT SUPPLIED';
  }
  return gate.detail || gate.tool || status;
}
