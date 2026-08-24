import { sanitizeDisplayText } from '../lib/security/renderSafety.mjs';

/**
 * #52 / D-058 §2.3 — the primary disclosure. A dedicated band fixed above `.bd-top-strip`,
 * full viewport width, not dismissible, never animated (§8's rule for a non-critical
 * persistent state — only a genuine critical alert may pulse, and even then just once).
 *
 * Renders exactly one of two states, per D-058 §2.5's state table — never both, never neither,
 * whenever this component is mounted at all (it is never mounted outside a
 * `command-center:presentation` build — see `PresentationMissionCommandCenter`):
 *
 * - `status: 'mock'` — the ordinary rehearsal state, citing the fixture by name.
 * - `status: 'real-mission-detected'` — the independent runtime refusal (§2.2's second lock):
 *   a presentation build that resolved a mission with no fixture-replay header on it. Critical
 *   tone, replaces the mock chip rather than appearing alongside it.
 */
export function PresentationModeChip({
  status,
  fixtureLabel,
}: {
  status: 'checking' | 'mock' | 'real-mission-detected';
  fixtureLabel: string | null;
}) {
  if (status === 'checking') {
    return (
      <div className="bd-presentation-strip bd-presentation-strip--idle" role="status">
        <span className="bd-chip">[ · PRESENTATION MODE BUILD · CONNECTING TO FIXTURE REPLAY ]</span>
      </div>
    );
  }

  if (status === 'real-mission-detected') {
    return (
      <div className="bd-presentation-strip bd-presentation-strip--critical" role="alert">
        <span className="bd-chip bd-chip--critical">
          [ × PRESENTATION MODE BUILD — REAL MISSION DETECTED, MOCK DISABLED ]
        </span>
      </div>
    );
  }

  const label = fixtureLabel
    ? sanitizeDisplayText(fixtureLabel, { fallback: 'unknown fixture', maxLength: 80 })
    : 'unknown fixture';

  return (
    <div className="bd-presentation-strip bd-presentation-strip--warning" role="status">
      <span className="bd-chip bd-chip--warning">
        [ ! MOCK DATA · REHEARSAL, NOT LIVE · fixture: {label} ]
      </span>
    </div>
  );
}
