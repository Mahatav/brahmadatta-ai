import { useStore } from '@nanostores/react';
import { useEffect, useRef, useState } from 'react';

import { getMissionDetail, getSystemHealth, type MissionDetail } from '../lib/api/client';
import { connectMissionEvents } from '../lib/events/connection';
import {
  $activeMissionId,
  $localRepository,
  $missionSnapshot,
  $streamState,
  resetMissionSnapshot,
  setActiveMissionId,
  setMissionRepositoryContext,
  startRestFallbackPoller,
  startStaleWatcher,
} from '../lib/events/store';
import { analysisRailState, AnalysisRail } from './AnalysisRail';
import { BottomStrip } from './BottomStrip';
import { BrahmadattaCore } from './BrahmadattaCore';
import { CandidateCompareOverlay } from './CandidateCompareOverlay';
import { FindingsRail } from './FindingsRail';
import { GitHistoryBisectPanel } from './GitHistoryBisectPanel';
import { LiveEventStatus } from './LiveEventStatus';
import { LocalRepositoryIntake } from './LocalRepositoryIntake';
import { MissionControlPanel } from './MissionControlPanel';
import { ModelGatewayStatus } from './ModelGatewayStatus';
import { StageTimeline } from './StageTimeline';
import { SystemStatus } from './SystemStatus';
import { TopStrip } from './TopStrip';
import { VerdictPanel } from './VerdictPanel';

/**
 * The Command Center's composition root — assembles the five P0 panels into the frozen screen
 * layout (docs/09-company/04-design-system.md §3): a page frame, a top strip, a three-column
 * body (Stage Timeline / Brahmadatta Core + Verdict panel / Findings rail), a bottom strip
 * (resource ledger + the four controls), and the Candidate Compare overlay.
 *
 * D-100's mission-lifecycle chrome (`MissionControlPanel`) and the local-repository scanner
 * (`LocalRepositoryIntake`, `AnalysisRail`) are kept mounted but moved into a collapsible setup
 * drawer above the frame — the frozen frame's body height closes at exactly 684px with zero
 * slack (§3), so there is no room inside it for a sixth/seventh panel, and neither is named in
 * the P0-13 five-panel set. They are pre-mission operator tooling, not part of what a judge
 * reads on the scored screen; nothing about them was rebuilt.
 */
export interface MissionCommandCenterProps {
  /**
   * #273 — injection point for the structural fix to "panels fed by a separate plain
   * `getMissionDetail()` call that never routes through the provenance wrapper."
   * `PresentationMissionCommandCenter` passes `fetchMissionDetailWithDisclosure`
   * (`lib/presentation/provenance.ts`), which fetches through `getMissionDetailWithProvenance`
   * and folds the response's disclosure header into its own state before returning the same
   * `MissionDetail` this component already expects — so in a presentation build, the exact HTTP
   * response that decided the mock/real banner is the one this component's `missionDetail`
   * state (and every `refreshMissionDetail()` call) is built from, every time.
   *
   * Defaults to the ordinary `getMissionDetail` — the live/finale build never supplies this
   * prop, so its own detail fetch is byte-for-byte what #52's review already covered; nothing
   * about the live rendering path changes.
   */
  fetchMissionDetail?: (missionId: string, signal?: AbortSignal) => Promise<MissionDetail>;
}

export function MissionCommandCenter({ fetchMissionDetail = getMissionDetail }: MissionCommandCenterProps = {}) {
  const snapshot = useStore($missionSnapshot);
  const localRepository = useStore($localRepository);
  const streamState = useStore($streamState);
  const activeMissionId = useStore($activeMissionId);

  const [missionDetail, setMissionDetail] = useState<MissionDetail | null>(null);
  const [controlApiReachable, setControlApiReachable] = useState(true);
  const [compareOpen, setCompareOpen] = useState(false);
  const [setupOpen, setSetupOpen] = useState(() => !activeMissionId);
  const compareReturnFocus = useRef<HTMLElement | null>(null);
  const priorVerificationCount = useRef(0);

  const hasActiveMission = Boolean(activeMissionId);
  const analysis = analysisRailState(snapshot, streamState, localRepository);

  // A deep-linked `?mission=` query param seeds the shared $activeMissionId store once, on
  // load, so an operator can still bookmark or share a running mission's URL.
  useEffect(() => {
    const fromQuery = new URLSearchParams(window.location.search).get('mission');
    if (fromQuery && !$activeMissionId.get()) {
      setActiveMissionId(fromQuery);
    }
  }, []);

  useEffect(() => {
    if (!activeMissionId) {
      resetMissionSnapshot();
      setMissionDetail(null);
      return undefined;
    }
    const controller = new AbortController();
    fetchMissionDetail(activeMissionId, controller.signal).then((mission) => {
      setMissionRepositoryContext(mission.repository_ref);
      setMissionDetail(mission);
    }, () => undefined);
    const disconnect = connectMissionEvents(activeMissionId);

    const url = new URL(window.location.href);
    if (url.searchParams.get('mission') !== activeMissionId) {
      url.searchParams.set('mission', activeMissionId);
      window.history.replaceState({}, '', url);
    }

    return () => {
      controller.abort();
      disconnect();
    };
  }, [activeMissionId, fetchMissionDetail]);

  // §8, §12 build note 2 — the one timer in this product. It only ever degrades the display.
  useEffect(() => startStaleWatcher(), []);

  // D-114 BUG-2 defense in depth: while the shared stream is unhealthy for this mission, keep
  // $missionSnapshot catching up via REST instead of leaving it frozen at whatever the last SSE
  // event happened to be. See `startRestFallbackPoller`'s own doc comment in `lib/events/store.ts`.
  useEffect(() => {
    if (!activeMissionId) return undefined;
    return startRestFallbackPoller(activeMissionId);
  }, [activeMissionId]);

  // §3, journey step 1 — "API unreachable -> top strip shows [ x CONTROL API UNREACHABLE ]".
  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        await getSystemHealth();
        if (!cancelled) setControlApiReachable(true);
      } catch {
        if (!cancelled) setControlApiReachable(false);
      }
    }
    poll();
    const interval = window.setInterval(poll, 20000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  // §4.1 row 10 — the compare overlay opens automatically when the second VerificationRecord
  // lands, in addition to the two manual `[ OPEN COMPARE ]` entry points.
  useEffect(() => {
    if (snapshot.verifications.length >= 2 && priorVerificationCount.current < 2) {
      setCompareOpen(true);
    }
    priorVerificationCount.current = snapshot.verifications.length;
  }, [snapshot.verifications.length]);

  async function refreshMissionDetail(): Promise<void> {
    if (!activeMissionId) return;
    try {
      setMissionDetail(await fetchMissionDetail(activeMissionId));
    } catch {
      // The alert line in BottomStrip already surfaces the action's own failure; a failed
      // refresh here just means the next render uses the previous (still real) snapshot.
    }
  }

  function openCompare(): void {
    compareReturnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setCompareOpen(true);
  }

  return (
    <div className="bd-app">
      <details className="bd-setup-drawer" open={setupOpen} onToggle={(event) => setSetupOpen(event.currentTarget.open)}>
        <summary className="bd-setup-drawer__summary">
          [ {setupOpen ? '−' : '+'} MISSION SETUP · LOCAL REPOSITORY & AUTHORIZATION ]
        </summary>
        <div className="bd-setup-drawer__body">
          <LocalRepositoryIntake />
          <MissionControlPanel />
          <AnalysisRail snapshot={snapshot} localRepository={localRepository} analysis={analysis} streamState={streamState} />
          <section className="bd-control-plane" aria-labelledby="bd-control-plane-title">
            <h2 id="bd-control-plane-title" className="bd-panel__title">[ CONTROL PLANE ]</h2>
            <SystemStatus />
            <ModelGatewayStatus />
            <LiveEventStatus />
          </section>
        </div>
      </details>

      <div className="bd-frame bd-crop">
        <span className="bd-frame__rule bd-frame__rule--top" aria-hidden="true" />
        <span className="bd-frame__rule bd-frame__rule--right" aria-hidden="true" />
        <span className="bd-frame__rule bd-frame__rule--bottom" aria-hidden="true" />
        <span className="bd-frame__rule bd-frame__rule--left" aria-hidden="true" />
        <TopStrip
          snapshot={snapshot}
          streamState={streamState}
          activeMissionId={activeMissionId}
          controlApiReachable={controlApiReachable}
        />

        <div className="bd-body">
          <StageTimeline snapshot={snapshot} hasActiveMission={hasActiveMission} />

          <div className="bd-centre-col">
            <section className="bd-panel bd-crop bd-core-panel" aria-labelledby="bd-core-title">
              <h2 id="bd-core-title" className="bd-panel__title">[ BRAHMADATTA CORE ]</h2>
              <BrahmadattaCore snapshot={snapshot} streamState={streamState} hasActiveMission={hasActiveMission} />
            </section>
            <VerdictPanel snapshot={snapshot} streamState={streamState} hasActiveMission={hasActiveMission} onOpenCompare={openCompare} />
          </div>

          <FindingsRail snapshot={snapshot} streamState={streamState} hasActiveMission={hasActiveMission} />
        </div>

        <BottomStrip
          snapshot={snapshot}
          activeMissionId={activeMissionId}
          missionDetail={missionDetail}
          hasActiveMission={hasActiveMission}
          onOpenCompare={openCompare}
          onMissionRefreshed={refreshMissionDetail}
        />
      </div>

      {/* #26 — below the frozen frame, not inside it (see GitHistoryBisectPanel's own doc
          comment): the five-panel body above is fixed at zero slack (§3), and this is
          supplementary evidence-deck content the issue's own body says is "not a gate". */}
      <GitHistoryBisectPanel snapshot={snapshot} hasActiveMission={hasActiveMission} />

      <CandidateCompareOverlay
        open={compareOpen}
        onClose={() => setCompareOpen(false)}
        snapshot={snapshot}
        returnFocusRef={compareReturnFocus}
      />
    </div>
  );
}
