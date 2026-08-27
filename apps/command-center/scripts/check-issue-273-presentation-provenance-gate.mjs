// Behavioral tests for #273 — the two hardening fixes on top of #52/D-058's presentation mode:
//
// 1. The render gate: `PresentationMissionCommandCenter` must not render `MissionCommandCenter`
//    (and therefore must not open its SSE connection or fetch mission data) while the
//    provenance check for the currently-bound mission is still in flight — otherwise real panel
//    content can populate before the disclosure banner (which shows "CONNECTING..." during that
//    window) reflects reality. `shouldRenderMissionPanels` (`lib/presentation/provenance.ts`) is
//    the exact predicate the component's JSX gates on; this file both tests it directly AND
//    greps the component source to confirm it is actually wired to that predicate, since
//    `.tsx` files can't be imported into a plain Node script (JSX is not strippable TypeScript
//    syntax — see `check-presentation-mode.mjs`'s own convention of only ever importing `.ts`
//    modules).
//
// 2. The shared fetch path: `fetchMissionDetailWithDisclosure` must be the single function that
//    determines BOTH the `MissionDetail` handed to the panels and the `MockSource` handed to
//    the disclosure banner, for a given HTTP response — proven by asserting that one mocked
//    response always produces a mutually consistent pair (mission data + disclosure status),
//    never a mismatched one, across every header value this system distinguishes.
//
// Run with `node --experimental-strip-types`, same convention as `check-presentation-mode.mjs`.

import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';

import { setActiveMissionId } from '../src/lib/events/store.ts';
import {
  $presentationMockSource,
  deriveConfirmedMock,
  fetchMissionDetailWithDisclosure,
  resetPresentationMockSource,
  shouldRenderMissionPanels,
} from '../src/lib/presentation/provenance.ts';

const originalFetch = globalThis.fetch;

function jsonResponse(status, body, headers = {}) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json', ...headers } });
}

async function withMockFetch(handler, run) {
  globalThis.fetch = handler;
  try {
    await run();
  } finally {
    globalThis.fetch = originalFetch;
  }
}

// ---------------------------------------------------------------------------
// 1a. `shouldRenderMissionPanels` — the pure gate predicate.
// ---------------------------------------------------------------------------

function testShouldRenderMissionPanelsBlocksOnlyTheCheckingState() {
  assert.equal(shouldRenderMissionPanels('checking'), false, 'panels must not render while the provenance check is in flight');
  assert.equal(shouldRenderMissionPanels('mock'), true, 'a confirmed mock mission must render its panels (with the mock chip/watermark)');
  assert.equal(
    shouldRenderMissionPanels('real-mission-detected'),
    true,
    'a confirmed real mission must still render its panels — #52/D-058 §2.5 falls through to ordinary live behaviour, it does not blank the screen',
  );
}

// ---------------------------------------------------------------------------
// 1b. Source-level confirmation that `PresentationMissionCommandCenter` actually gates
// `MissionCommandCenter`'s render on that same predicate, rather than the predicate above being
// correct in isolation but disconnected from the mounted component. (`.tsx` files can't be
// imported directly into this Node script — see file header — so this is a structural grep, the
// same technique `check-issue-20-analysis-rail.mjs` already uses for component-source
// assertions in this app.)
// ---------------------------------------------------------------------------

async function testPresentationMissionCommandCenterActuallyUsesTheGate() {
  const appRoot = path.resolve(import.meta.dirname, '..');
  const componentPath = path.join(appRoot, 'src/components/PresentationMissionCommandCenter.tsx');
  const source = await readFile(componentPath, 'utf8');

  assert.match(
    source,
    /shouldRenderMissionPanels\(status\)\s*&&\s*<MissionCommandCenter/,
    'MissionCommandCenter must be rendered conditionally on shouldRenderMissionPanels(status), not unconditionally from mount',
  );
  assert.match(
    source,
    /fetchMissionDetail=\{fetchMissionDetail\}/,
    'MissionCommandCenter must receive the provenance-checked fetchMissionDetail prop, not fall back to its own plain getMissionDetail default',
  );
  assert.match(
    source,
    /fetchMissionDetailWithDisclosure/,
    'the fetchMissionDetail prop passed down must be built from fetchMissionDetailWithDisclosure, the shared provenance-checked fetcher',
  );
}

// ---------------------------------------------------------------------------
// 2. `fetchMissionDetailWithDisclosure` — proving panel data and the disclosure banner cannot
// structurally diverge, because both are read off the one response this function fetches.
// ---------------------------------------------------------------------------

async function testFetchMissionDetailWithDisclosureCannotDiverge() {
  setActiveMissionId('m-1');
  resetPresentationMockSource();

  // Case A: the fixture-replay header is present. The returned mission data AND the status
  // reported to the caller must both reflect "mock" — never one without the other.
  await withMockFetch(
    async () => jsonResponse(200, { id: 'm-1', state: 'RUNNING', repository_ref: 'demo/pktcfg' }, { 'X-Brahmadatta-Fixture': 'replay' }),
    async () => {
      let reportedStatus;
      const mission = await fetchMissionDetailWithDisclosure('m-1', undefined, (status) => {
        reportedStatus = status;
      });
      assert.equal(mission.id, 'm-1', 'the panel-facing mission data must be the same response the header was read from');
      assert.equal(reportedStatus, 'mock', 'a fixture-replay header must resolve the disclosure status to mock');
      assert.equal($presentationMockSource.get(), 'fixture-replay', 'the store write must agree with the status reported to the caller');
      assert.equal(
        deriveConfirmedMock(reportedStatus, $presentationMockSource.get()),
        true,
        'the mock chip/watermark predicate must agree that this mission is confirmed mock',
      );
    },
  );

  // Case B: no fixture-replay header (a real mission). The returned mission data AND the
  // status must both reflect "real" — the mock chip/watermark must never be shown for it.
  await withMockFetch(
    async () => jsonResponse(200, { id: 'm-1', state: 'RUNNING', repository_ref: 'demo/pktcfg' }),
    async () => {
      let reportedStatus;
      const mission = await fetchMissionDetailWithDisclosure('m-1', undefined, (status) => {
        reportedStatus = status;
      });
      assert.equal(mission.id, 'm-1');
      assert.equal(reportedStatus, 'real-mission-detected', 'no header must resolve the disclosure status to real-mission-detected');
      assert.equal($presentationMockSource.get(), null, 'the store write must agree — no mock source for a real mission');
      assert.equal(
        deriveConfirmedMock(reportedStatus, $presentationMockSource.get()),
        false,
        'the mock chip/watermark predicate must never fire for a confirmed real mission',
      );
    },
  );

  // A late-resolving fetch for a mission this page has since moved on from must not overwrite
  // the current mission's disclosure state — same cross-mission guard `check-presentation-mode.mjs`
  // already exercises directly on `setPresentationMockSource`, re-verified here through the
  // higher-level function `MissionCommandCenter` actually calls.
  setActiveMissionId('m-1');
  await withMockFetch(
    async () => jsonResponse(200, { id: 'm-1', state: 'RUNNING', repository_ref: 'demo/pktcfg' }, { 'X-Brahmadatta-Fixture': 'replay' }),
    async () => {
      await fetchMissionDetailWithDisclosure('m-1', undefined, () => {});
    },
  );
  assert.equal($presentationMockSource.get(), 'fixture-replay');

  setActiveMissionId('m-2'); // operator switches missions mid-flight
  let staleCallbackFired = false;
  await withMockFetch(
    async () => jsonResponse(200, { id: 'm-1', state: 'RUNNING', repository_ref: 'demo/pktcfg' }),
    async () => {
      await fetchMissionDetailWithDisclosure('m-1', undefined, () => {
        staleCallbackFired = true;
      });
    },
  );
  assert.equal(staleCallbackFired, false, 'a stale resolution for a mission the page has moved on from must not report a status at all');
  assert.equal($presentationMockSource.get(), 'fixture-replay', 'the stale resolution must not overwrite the current mission\'s disclosure state');

  resetPresentationMockSource();
  setActiveMissionId(null);
}

async function main() {
  testShouldRenderMissionPanelsBlocksOnlyTheCheckingState();
  await testPresentationMissionCommandCenterActuallyUsesTheGate();
  await testFetchMissionDetailWithDisclosureCannotDiverge();
  console.warn(
    'issue #273 presentation provenance gate ok: MissionCommandCenter never renders before the first provenance ' +
      'check resolves, and panel data / the disclosure banner are read off the same provenance-checked response ' +
      'so they cannot structurally diverge',
  );
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
