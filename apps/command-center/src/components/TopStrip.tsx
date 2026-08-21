import { useEffect, useState } from 'react';

import { formatDurationSeconds, formatUtcClock } from '../lib/design/phases';
import type { MissionSnapshot, StreamState } from '../lib/events/store';
import { sanitizeDisplayText } from '../lib/security/renderSafety.mjs';

/**
 * The top strip (§3): the Brahmadatta wordmark, the mission/state/repo chips, and the mission
 * clock. `[ ELAPSED ]` and `[ UTC ]` are real wall-clock displays — a ticking clock is not the
 * "nothing advances on a timer" rule's target (§2.6 rule 2 is about *progress* indicators
 * implying work that has not been confirmed by an event; a clock is just the current time).
 */
export function TopStrip({
  snapshot,
  streamState,
  activeMissionId,
  controlApiReachable,
}: {
  snapshot: MissionSnapshot;
  streamState: StreamState;
  activeMissionId: string | null;
  controlApiReachable: boolean;
}) {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const interval = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(interval);
  }, []);

  const stateChip = missionStateChip(snapshot, streamState, activeMissionId);
  const elapsed = snapshot.firstTimestamp
    ? formatDurationSeconds((now.getTime() - Date.parse(snapshot.firstTimestamp)) / 1000)
    : '—';

  return (
    <header className="bd-top-strip">
      <div className="bd-top-strip__brand">
        <span className="bd-top-strip__wordmark">Brahmadatta</span>
      </div>
      <div className="bd-top-strip__chips">
        {!controlApiReachable && (
          <span className="bd-chip bd-chip--critical">[ × CONTROL API UNREACHABLE ]</span>
        )}
        {activeMissionId && (
          <span className="bd-chip">[ MISSION {activeMissionId.slice(0, 8).toUpperCase()} ]</span>
        )}
        <span className={`bd-chip bd-chip--${stateChip.tone}`}>[ {stateChip.glyph} {stateChip.word} ]</span>
        {snapshot.repositoryRef && (
          <span className="bd-chip">
            [ REPO {sanitizeDisplayText(snapshot.repositoryRef, { maxLength: 60 })}
            {snapshot.snapshotSha256 ? `@${snapshot.snapshotSha256.slice(0, 8)}` : ''} ]
          </span>
        )}
      </div>
      <div className="bd-top-strip__clock">
        <span className="bd-chip">[ ELAPSED {elapsed} ]</span>
        <span className="bd-chip">[ UTC {formatUtcClock(now.toISOString())} ]</span>
      </div>
    </header>
  );
}

function missionStateChip(
  snapshot: MissionSnapshot,
  streamState: StreamState,
  activeMissionId: string | null,
): { glyph: string; word: string; tone: 'idle' | 'running' | 'verified' | 'critical' | 'warning' } {
  if (!activeMissionId) {
    return { glyph: '·', word: 'STANDBY', tone: 'idle' };
  }
  if (snapshot.state === 'VERIFIED') return { glyph: '+', word: 'VERIFIED', tone: 'verified' };
  if (snapshot.state === 'REJECTED') return { glyph: '×', word: 'REJECTED', tone: 'critical' };
  if (snapshot.state === 'FAILED') return { glyph: '×', word: 'FAILED', tone: 'critical' };
  if (snapshot.state === 'CANCELLED') return { glyph: '·', word: 'CANCELLED', tone: 'idle' };
  if (snapshot.state === 'HUMAN_REVIEW') return { glyph: '!', word: 'HELD', tone: 'warning' };
  if (streamState === 'stale') return { glyph: '!', word: 'STREAM STALE', tone: 'warning' };
  if (snapshot.state) return { glyph: '●', word: 'RUNNING', tone: 'running' };
  return { glyph: '·', word: 'CONNECTING', tone: 'idle' };
}
