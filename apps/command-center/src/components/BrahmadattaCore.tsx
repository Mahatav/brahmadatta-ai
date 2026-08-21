import { Component, type ReactNode } from 'react';

import { PHASE_LABEL, PHASE_ORDER, arcForMissionState, type ArcRunState, type CorePhase } from '../lib/design/phases';
import type { MissionSnapshot, StreamState } from '../lib/events/store';
import { sanitizeDisplayText } from '../lib/security/renderSafety.mjs';

/**
 * Panel 1 — the Brahmadatta Core (docs/09-company/04-design-system.md §6.1, §7).
 *
 * Original hairline-engraved SVG chakra. No glow, no gradient, no shadow, no raster asset, no
 * figure — every constraint in §1.1 and §2.4 applies. Replaces `AIParticleCore.tsx`'s
 * glowing-particle-sphere entirely; that file is removed by this change (see the handoff).
 *
 * Geometry is fixed at the 440 viewBox per §7's own table ("Radius @440 viewBox" column) and
 * scaled to the 380px block in CSS (`--bd-core-wheel`), so path data never needs to change if
 * the block is resized again (DS-01).
 *
 * The six phase arcs are driven from the single `PHASE_ORDER` array in
 * `src/lib/design/phases.ts` (§12 build note 8) rather than six hardcoded path definitions, so
 * the CTO's D-038 ruling (§7.1a) — or any future re-ruling — is a one-line edit there, not here.
 */

const VIEWBOX = 440;
const CENTER = VIEWBOX / 2;

const RAY_R1 = 202;
const RAY_R2 = 220;
const RAY_STROKE_COUNT = 48;
const RAY_STEP_DEG = 360 / RAY_STROKE_COUNT; // 7.5deg

const RIM_R1 = 190;
const RIM_R2 = 198;
const RIM_MID_R = (RIM_R1 + RIM_R2) / 2;

const KAVACHA_R1 = 130;
const KAVACHA_R2 = 178;
const KAVACHA_PLATE_COUNT = 12;

const YANTRA_R = 120;

const VERIFIED_RING_R = 226; // r=195 @380, converted to the 440 viewBox (195 * 440/380)
const REJECTED_SPOKE_EXTENSION = 46; // 40px @380 converted to the 440 viewBox

const GLYPH_PITCH = 4; // viewBox units — "4px at 440" (§7)
const ARC_SPAN_DEG = 60;

const RAMP_PENDING = ' ';
const RAMP_SKIPPED = '-';
const RAMP_RUNNING = ':';
const RAMP_COMPLETE = '#';
const RAMP_FAILED = 'X';

export type CoreVisualState =
  | 'empty'
  | 'loading'
  | 'running'
  | 'degraded'
  | 'verified'
  | 'rejected'
  | 'human_review'
  | 'failed'
  | 'cancelled';

interface BrahmadattaCoreProps {
  snapshot: MissionSnapshot;
  streamState: StreamState;
  hasActiveMission: boolean;
}

function polar(radius: number, angleDeg: number): { x: number; y: number } {
  const angleRad = (angleDeg * Math.PI) / 180;
  return {
    x: CENTER + radius * Math.sin(angleRad),
    y: CENTER - radius * Math.cos(angleRad),
  };
}

function arcTextPathId(index: number): string {
  return `bd-core-arc-path-${index}`;
}

function describeArc(radius: number, startDeg: number, endDeg: number): string {
  const start = polar(radius, startDeg);
  const end = polar(radius, endDeg);
  const largeArc = endDeg - startDeg > 180 ? 1 : 0;
  return `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${radius} ${radius} 0 ${largeArc} 1 ${end.x.toFixed(2)} ${end.y.toFixed(2)}`;
}

function resolveCoreVisualState(
  snapshot: MissionSnapshot,
  streamState: StreamState,
  hasActiveMission: boolean,
): CoreVisualState {
  if (!hasActiveMission) {
    return 'empty';
  }
  if (snapshot.state === 'VERIFIED') return 'verified';
  if (snapshot.state === 'REJECTED') return 'rejected';
  if (snapshot.state === 'HUMAN_REVIEW') return 'human_review';
  if (snapshot.state === 'FAILED') return 'failed';
  if (snapshot.state === 'CANCELLED') return 'cancelled';
  if (streamState === 'stale') return 'degraded';
  if (!snapshot.state && (streamState === 'connecting' || streamState === 'idle')) return 'loading';
  return 'running';
}

/** §7.2 — one arc's run state, derived only from real stage/state telemetry the store already
 * holds (completed-stage list, the currently-running stage, and the mission state). Never a
 * guess and never a client-side timer. */
function arcRunState(phase: CorePhase, snapshot: MissionSnapshot, visualState: CoreVisualState): ArcRunState {
  if (visualState === 'failed') return 'failed';
  if (visualState === 'cancelled') return 'skipped';
  if (visualState === 'verified' || visualState === 'rejected') return 'complete';

  const underlyingStage = phase === 'REMEDIATE' ? 'PATCH' : phase === 'STRESS_TEST' ? 'STRESS_TEST' : phase;
  if (snapshot.completedStages.includes(underlyingStage as never)) return 'complete';
  if (snapshot.stage === underlyingStage) return 'running';
  return 'pending';
}

function rampStringForArc(phase: CorePhase, runState: ArcRunState, snapshot: MissionSnapshot, glyphCount: number): string {
  if (runState === 'complete') return RAMP_COMPLETE.repeat(glyphCount);
  if (runState === 'failed') return RAMP_FAILED.repeat(glyphCount);
  if (runState === 'skipped') return RAMP_SKIPPED.repeat(glyphCount);
  if (runState === 'pending') return RAMP_PENDING.repeat(glyphCount);

  // running — filled to the real reported fraction only (§13 open question 1: percent_complete
  // is nullable). A null fraction never becomes a guessed number; it renders as sparse running
  // density across the whole arc instead.
  const underlyingStage = phase === 'REMEDIATE' ? 'PATCH' : phase;
  const percent = snapshot.stageProgress[underlyingStage as never];
  if (percent == null) {
    return RAMP_RUNNING.repeat(glyphCount);
  }
  const filled = Math.max(0, Math.min(glyphCount, Math.round((glyphCount * percent) / 100)));
  return RAMP_COMPLETE.repeat(filled) + RAMP_RUNNING.repeat(glyphCount - filled);
}

function glyphCountForArc(radius: number): number {
  const arcLength = radius * ((ARC_SPAN_DEG * Math.PI) / 180);
  return Math.max(8, Math.floor(arcLength / GLYPH_PITCH));
}

function centreWord(visualState: CoreVisualState, snapshot: MissionSnapshot): string {
  switch (visualState) {
    case 'empty': return 'Standby';
    case 'loading': return 'Connecting';
    case 'verified': return 'Verified';
    case 'rejected': return 'Rejected';
    case 'human_review': return 'Held';
    case 'failed': return 'Failed';
    case 'cancelled': return 'Cancelled';
    default:
      if (snapshot.state === 'BASELINE') return 'Baseline';
      if (snapshot.state === 'VALIDATING') return 'Validating';
      return activePhaseLabel(snapshot) ?? (snapshot.state ?? 'Running');
  }
}

function activePhaseLabel(snapshot: MissionSnapshot): string | null {
  const arc = arcForMissionState(snapshot.state);
  return arc ? PHASE_LABEL[arc] : null;
}

function centreWordClass(visualState: CoreVisualState): string {
  if (visualState === 'verified') return 'bd-core__word--verified';
  if (visualState === 'rejected' || visualState === 'failed') return 'bd-core__word--critical';
  if (visualState === 'human_review') return 'bd-core__word--warning';
  if (visualState === 'cancelled' || visualState === 'empty') return 'bd-core__word--secondary';
  return 'bd-core__word--text';
}

function phaseIndex(snapshot: MissionSnapshot): number | null {
  const arc = arcForMissionState(snapshot.state);
  if (!arc) return null;
  return PHASE_ORDER.indexOf(arc);
}

function labelLines(visualState: CoreVisualState, snapshot: MissionSnapshot, streamState: StreamState): [string, string] {
  const terminal = visualState === 'verified' || visualState === 'rejected' || visualState === 'failed' || visualState === 'cancelled';

  if (visualState === 'empty') {
    return ['[ NO ACTIVE MISSION ]', 'Authorize a repository to begin.'];
  }
  if (visualState === 'loading') {
    return ['[ CONNECTING ]', '[ · OPENING STREAM ]'];
  }

  const idx = phaseIndex(snapshot);
  const line1 = idx != null
    ? `[ PHASE ${String(idx + 1).padStart(2, '0')} OF 06 · ${PHASE_LABEL[PHASE_ORDER[idx]!]} ]`
    : terminal
      ? '[ PHASE 06 OF 06 · COMPLETE ]'
      : `[ ${sanitizeDisplayText(snapshot.state ?? 'PENDING', { maxLength: 40 })} ]`;

  if (!terminal) {
    if (visualState === 'degraded') {
      const idleSeconds = snapshot.latestTimestamp
        ? Math.max(0, Math.round((Date.now() - Date.parse(snapshot.latestTimestamp)) / 1000))
        : null;
      return [line1, `[ ! STREAM STALE · LAST EVENT +${idleSeconds ?? '?'}s ]`];
    }
    if (visualState === 'human_review') {
      return [line1, snapshot.failedReason ? sanitizeDisplayText(snapshot.failedReason, { maxLength: 60 }) : '[ ! HELD FOR HUMAN REVIEW ]'];
    }
    return [line1, streamState === 'open' ? '[ ● LIVE · LAST EVENT +1s ]' : `[ · STREAM ${streamState.toUpperCase()} ]`];
  }

  // Terminal — the release line replaces the liveness chip (§6.1, DS-04). This is one of the
  // three surfaces reading the exact same TEARDOWN_CONFIRMED event set as the ledger and the
  // timeline; it never keeps its own count.
  const resources = snapshot.releasedResources;
  if (resources.length === 0) {
    return [line1, '[ — RESOURCES · AWAITING TEARDOWN RECEIPT ]'];
  }
  const releasedCount = resources.filter((resource) => resource.released).length;
  if (releasedCount === resources.length) {
    return [line1, `[ + RESOURCES RELEASED · ${releasedCount} OF ${resources.length} ]`];
  }
  return [line1, `[ ! RESOURCES · ${releasedCount} OF ${resources.length} RELEASED ]`];
}

function labelLineClass(line2: string): string {
  if (line2.startsWith('[ !')) return 'bd-core__label-line--warning';
  if (line2.startsWith('[ +')) return 'bd-core__label-line--verified';
  if (line2.startsWith('[ ●')) return 'bd-core__label-line--running';
  return 'bd-core__label-line--secondary';
}

export class BrahmadattaCore extends Component<BrahmadattaCoreProps, { renderFailed: boolean }> {
  constructor(props: BrahmadattaCoreProps) {
    super(props);
    this.state = { renderFailed: false };
  }

  static getDerivedStateFromError() {
    return { renderFailed: true };
  }

  render(): ReactNode {
    if (this.state.renderFailed) {
      return <CoreRenderFallback snapshot={this.props.snapshot} />;
    }
    return <BrahmadattaCoreInner {...this.props} />;
  }
}

function CoreRenderFallback({ snapshot }: { snapshot: MissionSnapshot }) {
  return (
    <div className="bd-core bd-core--error" role="img" aria-label="Brahmadatta Core render failed; mission remains operable">
      <p className="bd-core__error-title">[ × CORE RENDER FAILED ]</p>
      <ul className="bd-core__error-list">
        {PHASE_ORDER.map((phase) => (
          <li key={phase}>[ {PHASE_LABEL[phase]} ]</li>
        ))}
      </ul>
      <p className="bd-core__error-note">Mission {snapshot.missionId ?? 'unbound'} remains operable.</p>
    </div>
  );
}

function BrahmadattaCoreInner({ snapshot, streamState, hasActiveMission }: BrahmadattaCoreProps) {
  const visualState = resolveCoreVisualState(snapshot, streamState, hasActiveMission);
  const showGeometry = visualState !== 'empty' && visualState !== 'loading';
  const [line1, line2] = labelLines(visualState, snapshot, streamState);
  const word = sanitizeDisplayText(centreWord(visualState, snapshot), { maxLength: 24, fallback: 'Standby' });
  const live = streamState === 'open' && visualState === 'running';

  const arcs = PHASE_ORDER.map((phase, index) => {
    const runState = arcRunState(phase, snapshot, visualState);
    const glyphCount = glyphCountForArc(RIM_MID_R);
    const ramp = showGeometry ? rampStringForArc(phase, runState, snapshot, glyphCount) : RAMP_PENDING.repeat(glyphCount);
    return { phase, index, runState, ramp, startDeg: index * ARC_SPAN_DEG, endDeg: (index + 1) * ARC_SPAN_DEG };
  });

  return (
    <div className={`bd-core bd-core--${visualState}`} data-stream-state={streamState}>
      <div className="bd-core__wheel" role="img" aria-label={coreAriaLabel(visualState, snapshot, line1, line2)}>
        <svg viewBox={`0 0 ${VIEWBOX} ${VIEWBOX}`} className="bd-core__svg" aria-hidden="true">
          <defs>
            {arcs.map((arc) => (
              <path key={arc.phase} id={arcTextPathId(arc.index)} d={describeArc(RIM_MID_R, arc.startDeg, arc.endDeg)} fill="none" />
            ))}
          </defs>

          {showGeometry && visualState !== 'cancelled' && (
            <g className="bd-core__rays">
              {Array.from({ length: RAY_STROKE_COUNT }, (_, k) => {
                const angle = k * RAY_STEP_DEG;
                const arcIndexForRay = Math.floor(angle / ARC_SPAN_DEG);
                const arcState = arcs[arcIndexForRay]?.runState ?? 'pending';
                const lit = arcState === 'complete';
                const p1 = polar(RAY_R1, angle);
                const p2 = polar(RAY_R2, angle);
                return (
                  <line
                    key={k}
                    x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y}
                    className={lit ? 'bd-core__ray bd-core__ray--lit' : 'bd-core__ray'}
                  />
                );
              })}
            </g>
          )}

          {/* Chakra rim — two hairline circles bounding the 8px band, plus the six radial
              spokes dividing it into arcs (§7). */}
          {showGeometry && (
            <g className="bd-core__rim">
              <circle cx={CENTER} cy={CENTER} r={RIM_R1} className="bd-core__rim-circle" />
              <circle cx={CENTER} cy={CENTER} r={RIM_R2} className="bd-core__rim-circle" />
              {PHASE_ORDER.map((_, index) => {
                const angle = index * ARC_SPAN_DEG;
                const p1 = polar(RIM_R1, angle);
                const p2 = polar(RIM_R2, angle);
                const extend = visualState === 'rejected' && PHASE_ORDER[index] === 'REMEDIATE';
                const p2Extended = extend ? polar(RIM_R2 + REJECTED_SPOKE_EXTENSION, angle) : p2;
                return (
                  <line
                    key={index}
                    x1={p1.x} y1={p1.y} x2={p2Extended.x} y2={p2Extended.y}
                    className={extend ? 'bd-core__spoke bd-core__spoke--broken' : 'bd-core__spoke'}
                  />
                );
              })}
              {arcs.map((arc) => (
                <text key={arc.phase} className={`bd-core__ramp bd-core__ramp--${arc.runState}${live && arc.runState === 'running' ? ' bd-core__ramp--live' : ''}`}>
                  <textPath href={`#${arcTextPathId(arc.index)}`} startOffset="4%">{arc.ramp}</textPath>
                </text>
              ))}
              {visualState === 'verified' && (
                <circle cx={CENTER} cy={CENTER} r={VERIFIED_RING_R} className="bd-core__verified-ring" />
              )}
            </g>
          )}

          {/* Kavacha plating — twelve trapezoidal plates, hairline outline only. Purely
              structural: never animated, never state-carrying (§7). */}
          {showGeometry && (
            <g className="bd-core__kavacha">
              {Array.from({ length: KAVACHA_PLATE_COUNT }, (_, i) => {
                const base = i * (360 / KAVACHA_PLATE_COUNT);
                const wideOuter = i % 2 === 0;
                const innerInset = wideOuter ? 4 : 1.2;
                const outerInset = wideOuter ? 1.2 : 4;
                const p1 = polar(KAVACHA_R1, base + innerInset);
                const p2 = polar(KAVACHA_R2, base + outerInset);
                const p3 = polar(KAVACHA_R2, base + 360 / KAVACHA_PLATE_COUNT - outerInset);
                const p4 = polar(KAVACHA_R1, base + 360 / KAVACHA_PLATE_COUNT - innerInset);
                const d = `M ${p1.x.toFixed(2)} ${p1.y.toFixed(2)} L ${p2.x.toFixed(2)} ${p2.y.toFixed(2)} L ${p3.x.toFixed(2)} ${p3.y.toFixed(2)} L ${p4.x.toFixed(2)} ${p4.y.toFixed(2)} Z`;
                return <path key={i} d={d} className="bd-core__plate" />;
              })}
            </g>
          )}

          {/* Yantra construction — two interpenetrating equilateral triangles inscribed in the
              circle; their overlap is the six-point star. Static, always the construction
              colour, so it can never be mistaken for data (§7, centre-word overrun rule). */}
          {showGeometry && (
            <g className="bd-core__yantra">
              <polygon points={[0, 120, 240].map((a) => { const p = polar(YANTRA_R, a); return `${p.x.toFixed(2)},${p.y.toFixed(2)}`; }).join(' ')} />
              <polygon points={[60, 180, 300].map((a) => { const p = polar(YANTRA_R, a); return `${p.x.toFixed(2)},${p.y.toFixed(2)}`; }).join(' ')} />
            </g>
          )}

          {visualState === 'human_review' && (
            <line x1={CENTER - 86} y1={CENTER} x2={CENTER + 86} y2={CENTER} className="bd-core__chord" />
          )}
        </svg>

        <div className="bd-core__centre">
          <span className={`bd-core__word ${centreWordClass(visualState)}`}>{word}</span>
        </div>
      </div>

      <div className="bd-core__label">
        <p className={`bd-core__label-line ${labelLineClass(line1)}`}>{line1}</p>
        <p className={`bd-core__label-line ${labelLineClass(line2)}`}>{line2}</p>
      </div>
    </div>
  );
}

function coreAriaLabel(visualState: CoreVisualState, snapshot: MissionSnapshot, line1: string, line2: string): string {
  return sanitizeDisplayText(
    `Brahmadatta Core. ${centreWord(visualState, snapshot)}. ${line1}. ${line2}.`,
    { maxLength: 260, fallback: 'Brahmadatta Core' },
  );
}
