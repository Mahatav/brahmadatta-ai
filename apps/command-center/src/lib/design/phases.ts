/**
 * Six-arc Brahmadatta Core geometry and the ten-row stage timeline — shared derivation so the
 * Core, the Stage Timeline and the Verdict panel never disagree about phase order or which
 * `MissionStage` maps to which row/arc.
 *
 * docs/09-company/04-design-system.md §7.1a / §7.2 / §12 build note 8:
 *   "Drive the Core's six arcs from one PHASE_ORDER array... Hardcoding the sequence into six
 *   path definitions makes it a day [to re-derive when the CTO rules]."
 *
 * §7.1a was RESOLVED by D-038 (.project/decisions.md, 2026-08-07): STRESS_TEST is arc 3,
 * CORRELATE is arc 4. `tokens.css` §10 records the same resolution
 * (`--bd-phase-order-status: "RESOLVED-D-038"`). PHASE_ORDER is still kept as a single array,
 * per the build note's instruction, so a future re-derivation stays a one-line edit.
 */
import type { MissionStage, MissionState } from '../events/store';

/** One 60° arc per phase, clockwise from 12 o'clock. Six is a design constant (§7.2) — a
 * seventh workflow step gets a timeline row, never a seventh arc. */
export type CorePhase = 'INGEST' | 'ANALYZE' | 'STRESS_TEST' | 'CORRELATE' | 'REMEDIATE' | 'VERIFY';

export const PHASE_ORDER: CorePhase[] = [
  'INGEST',
  'ANALYZE',
  'STRESS_TEST',
  'CORRELATE',
  'REMEDIATE',
  'VERIFY',
];

export const PHASE_LABEL: Record<CorePhase, string> = {
  INGEST: 'INGEST',
  ANALYZE: 'ANALYZE',
  STRESS_TEST: 'STRESS TEST',
  CORRELATE: 'CORRELATE',
  REMEDIATE: 'REMEDIATE',
  VERIFY: 'VERIFY',
};

export type ArcRunState = 'pending' | 'running' | 'complete' | 'failed' | 'skipped';

/** §7.2 — the orchestrator's MissionState does not map one-to-one onto six arcs. This table is
 * the one place that mapping lives. */
export function arcForMissionState(state: MissionState | null): CorePhase | null {
  switch (state) {
    case 'SNAPSHOTTED':
    case 'BASELINE':
      return 'INGEST';
    case 'TRIAGE':
      return 'ANALYZE';
    case 'CORRELATE':
      return 'CORRELATE';
    case 'STRESS_TEST':
      return 'STRESS_TEST';
    case 'PATCH':
      return 'REMEDIATE';
    case 'VERIFY':
    case 'VERIFIED':
    case 'REJECTED':
      return 'VERIFY';
    default:
      return null;
  }
}

/** The ten fixed stage-timeline rows (§6.2). Rows 01-09 are `MissionStage` values; row 10
 * (TEARDOWN) has no `MissionStage` of its own — it is derived from `TEARDOWN_CONFIRMED`/
 * `releasedResources` events instead (§6.2: "Teardown does not gain a Core spoke... the timeline
 * gains a row and the wheel does not"). */
export const STAGE_ROWS: Array<{ index: number; stage: MissionStage | 'TEARDOWN'; label: string }> = [
  { index: 1, stage: 'AUTHORIZE', label: 'AUTHORIZE' },
  { index: 2, stage: 'INGEST', label: 'INGEST' },
  { index: 3, stage: 'BASELINE', label: 'BASELINE' },
  { index: 4, stage: 'ANALYZE', label: 'ANALYZE' },
  { index: 5, stage: 'STRESS_TEST', label: 'STRESS TEST' },
  { index: 6, stage: 'CORRELATE', label: 'CORRELATE' },
  { index: 7, stage: 'PATCH', label: 'REMEDIATE' },
  { index: 8, stage: 'VERIFY', label: 'VERIFY' },
  { index: 9, stage: 'EXPORT_EVIDENCE', label: 'EXPORT EVIDENCE' },
  { index: 10, stage: 'TEARDOWN', label: 'TEARDOWN' },
];

/** State-vocabulary glyph/word pairs (§5). Colour is applied by the caller via CSS class, never
 * inferred here — this module only carries the non-colour channels. */
export const STATE_GLYPH = {
  idle: '·',
  loading: '·',
  running: '>',
  pass: '+',
  warn: '!',
  fail: '×',
  notRun: '—',
  notMeasured: '—',
} as const;

export function formatElapsed(startIso: string | null, endIso: string | null): string {
  if (!startIso || !endIso) {
    return '—';
  }
  const startMs = Date.parse(startIso);
  const endMs = Date.parse(endIso);
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs < startMs) {
    return '—';
  }
  return formatDurationSeconds(Math.round((endMs - startMs) / 1000));
}

export function formatDurationSeconds(totalSeconds: number): string {
  const clamped = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(clamped / 3600);
  const minutes = Math.floor((clamped % 3600) / 60);
  const seconds = clamped % 60;
  return [hours, minutes, seconds].map((part) => String(part).padStart(2, '0')).join(':');
}

export function formatUtcClock(iso: string | null): string {
  if (!iso) {
    return '—';
  }
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) {
    return '—';
  }
  return new Intl.DateTimeFormat('en-CA', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZone: 'UTC',
    hour12: false,
  }).format(parsed);
}
