import { useStore } from '@nanostores/react';
import { useCallback, useEffect, useState } from 'react';

import { getMissionDetailWithProvenance } from '../lib/api/client';
import { $activeMissionId, setActiveMissionId } from '../lib/events/store';
import { discoverFixtureMission } from '../lib/presentation/discoverFixtureMission';
import {
  $presentationMockSource,
  deriveConfirmedMock,
  deriveMockSource,
  fetchMissionDetailWithDisclosure,
  resetPresentationMockSource,
  setPresentationMockSource,
  shouldRenderMissionPanels,
  type ProvenanceStatus,
} from '../lib/presentation/provenance';
import { MissionCommandCenter } from './MissionCommandCenter';
import { MockDataWatermark } from './MockDataWatermark';
import { PresentationModeChip } from './PresentationModeChip';

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
 * path"). The only things layered on top are (1) the disclosure chrome (chip + watermark),
 * driven strictly by the real `X-Brahmadatta-Fixture` header via `$presentationMockSource`
 * (`lib/presentation/provenance.ts`) — never by the mere fact that this build exists — and (2)
 * auto-binding to whatever mission the configured backend is actually serving, so an operator
 * gets a working rehearsal with zero manual setup once `sse_replay.py` is running.
 *
 * §2.2's second, independent lock lives here: even inside this build, a mission that resolves
 * without the fixture header never gets the mock chip/watermark, and `MissionCommandCenter`
 * underneath keeps rendering it exactly as ordinary live mode would — "falls back to ordinary
 * live behavior," per D-058 §2.5's state table, not a special-cased blank screen.
 *
 * #273 hardening, on top of the above:
 *
 * 1. Structural coupling — `MissionCommandCenter` is handed `fetchMissionDetailWithDisclosure`
 *    as its `fetchMissionDetail` prop, so its own `missionDetail` state (and every
 *    `refreshMissionDetail()` call it makes) is fetched through the exact same
 *    provenance-checked function this component uses for its own initial check, not a separate
 *    plain `getMissionDetail()` call that merely happens to hit the same backend today. The
 *    live SSE stream `connectMissionEvents` opens still cannot carry this header (a native
 *    `EventSource` never exposes response headers to JS — see `client.ts`'s own doc comment on
 *    `getMissionDetailWithProvenance`); (2) below bounds how much that residual gap can matter.
 * 2. Render gate — `MissionCommandCenter` (and therefore the SSE connection and REST fetches it
 *    starts) is not rendered at all while `shouldRenderMissionPanels(status)` is false, i.e.
 *    while the very first provenance check for the currently-bound mission is still in flight.
 *    Real panel content can therefore never appear on screen before the disclosure banner
 *    (which shows "CONNECTING..." during that same window, via `PresentationModeChip`) reflects
 *    reality.
 */
export function PresentationMissionCommandCenter() {
  const activeMissionId = useStore($activeMissionId);
  const presentationMockSource = useStore($presentationMockSource);
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

  // The initial/gating provenance check — re-run on every mission this page ever binds to, so
  // switching missions (or a stale `?mission=` link) always gets a fresh, real answer rather
  // than trusting whatever the previous mission resolved to. This is also what
  // `shouldRenderMissionPanels` below gates `MissionCommandCenter`'s render on (#273): that
  // component is not mounted, and therefore never opens its SSE connection or fetches mission
  // data, until this resolves for the currently-bound mission.
  useEffect(() => {
    resetPresentationMockSource();
    if (!activeMissionId) {
      setStatus('checking');
      return undefined;
    }
    setStatus('checking');
    const controller = new AbortController();
    getMissionDetailWithProvenance(activeMissionId, controller.signal)
      .then(({ fixtureHeaderValue }) => {
        const mockSource = deriveMockSource(fixtureHeaderValue);
        setPresentationMockSource(activeMissionId, mockSource);
        setStatus(mockSource === 'fixture-replay' ? 'mock' : 'real-mission-detected');
      })
      .catch(() => {
        // Unreachable backend, or the mission genuinely doesn't exist (sse_replay.py not
        // started yet, or a bad `?mission=` value) — stays 'checking' rather than guessing
        // either 'mock' or 'real' from a failed request. `MissionCommandCenter` stays gated off
        // for as long as this is true.
      });
    return () => controller.abort();
  }, [activeMissionId]);

  // #273 — the single function `MissionCommandCenter` uses for every one of its own
  // mission-detail fetches once mounted (mount-time and every `refreshMissionDetail()`), so the
  // panels and the disclosure banner keep reading the same provenance-checked response for as
  // long as this page stays on the same mission, not just at the moment it first bound to it.
  const fetchMissionDetail = useCallback(
    (missionId: string, signal?: AbortSignal) => fetchMissionDetailWithDisclosure(missionId, signal, setStatus),
    [],
  );

  const confirmedMock = deriveConfirmedMock(status, presentationMockSource);

  return (
    <>
      <PresentationModeChip
        status={confirmedMock ? 'mock' : status}
        fixtureLabel={activeMissionId ? `mission-${activeMissionId.slice(0, 8)}` : null}
      />
      {confirmedMock && <MockDataWatermark />}
      {shouldRenderMissionPanels(status) && <MissionCommandCenter fetchMissionDetail={fetchMissionDetail} />}
    </>
  );
}
