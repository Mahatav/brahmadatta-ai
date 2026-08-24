import { useStore } from '@nanostores/react';
import { useEffect, useState } from 'react';

import { getMissionDetailWithProvenance } from '../lib/api/client';
import {
  $activeMissionId,
  $missionSnapshot,
  deriveMockSource,
  setActiveMissionId,
  setMockSource,
} from '../lib/events/store';
import { discoverFixtureMission } from '../lib/presentation/discoverFixtureMission';
import { MissionCommandCenter } from './MissionCommandCenter';
import { MockDataWatermark } from './MockDataWatermark';
import { PresentationModeChip } from './PresentationModeChip';

type ProvenanceStatus = 'checking' | 'mock' | 'real-mission-detected';

/**
 * #52 / D-058 — the presentation-mode composition root. Mounted from exactly one place,
 * `src/presentation/presentation.astro`, which is itself only ever reachable from a
 * `command-center:presentation` build (`astro.config.mjs`'s conditional `injectRoute` — see
 * that file). The finale/production build's `index.astro` never imports this module, directly
 * or transitively; that absence is #52's acceptance criterion 1, checked by
 * `scripts/check-presentation-build-exclusion.sh`.
 *
 * Renders the exact same `<MissionCommandCenter />` every live/finale build renders — zero
 * duplicated panel code, per the task brief ("feed the SAME store... not a parallel rendering
 * path"). The only two things layered on top are (1) the disclosure chrome (chip + watermark),
 * driven strictly by the real `X-Brahmadatta-Fixture` header via `$missionSnapshot.mockSource`
 * — never by the mere fact that this build exists — and (2) auto-binding to whatever mission
 * the configured backend is actually serving, so an operator gets a working rehearsal with zero
 * manual setup once `sse_replay.py` is running.
 *
 * §2.2's second, independent lock lives here: even inside this build, a mission that resolves
 * without the fixture header never gets the mock chip/watermark, and `MissionCommandCenter`
 * underneath keeps rendering it exactly as ordinary live mode would — "falls back to ordinary
 * live behavior," per D-058 §2.5's state table, not a special-cased blank screen.
 */
export function PresentationMissionCommandCenter() {
  const activeMissionId = useStore($activeMissionId);
  const snapshot = useStore($missionSnapshot);
  const [status, setStatus] = useState<ProvenanceStatus>('checking');

  // Auto-bind to whatever mission the backend serves, unless a `?mission=` deep link
  // (MissionCommandCenter's own effect, which runs synchronously on mount — before this
  // effect's async discovery call can resolve) already claimed one first.
  useEffect(() => {
    if ($activeMissionId.get()) {
      return undefined;
    }
    const controller = new AbortController();
    discoverFixtureMission(controller.signal).then((missionId) => {
      if (missionId && !$activeMissionId.get()) {
        setActiveMissionId(missionId);
      }
    });
    return () => controller.abort();
  }, []);

  // The provenance check itself — re-run on every mission this page ever binds to, so
  // switching missions (or a stale `?mission=` link) always gets a fresh, real answer rather
  // than trusting whatever the previous mission resolved to.
  useEffect(() => {
    if (!activeMissionId) {
      setStatus('checking');
      return undefined;
    }
    setStatus('checking');
    const controller = new AbortController();
    getMissionDetailWithProvenance(activeMissionId, controller.signal)
      .then(({ fixtureHeaderValue }) => {
        const mockSource = deriveMockSource(fixtureHeaderValue);
        setMockSource(activeMissionId, mockSource);
        setStatus(mockSource === 'fixture-replay' ? 'mock' : 'real-mission-detected');
      })
      .catch(() => {
        // Unreachable backend, or the mission genuinely doesn't exist (sse_replay.py not
        // started yet, or a bad `?mission=` value) — stays 'checking' rather than guessing
        // either 'mock' or 'real' from a failed request.
      });
    return () => controller.abort();
  }, [activeMissionId]);

  // Belt-and-braces against a render landing between `setStatus` and the store write above:
  // the watermark/chip's "mock" rendering reads the store field directly, not just local state.
  const confirmedMock = status === 'mock' && snapshot.mockSource === 'fixture-replay' && snapshot.missionId === activeMissionId;

  return (
    <>
      <PresentationModeChip
        status={confirmedMock ? 'mock' : status}
        fixtureLabel={activeMissionId ? `mission-${activeMissionId.slice(0, 8)}` : null}
      />
      {confirmedMock && <MockDataWatermark />}
      <MissionCommandCenter />
    </>
  );
}
