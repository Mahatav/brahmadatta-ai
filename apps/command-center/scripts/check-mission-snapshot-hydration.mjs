// Behavioral tests for D-114 BUG-2's fix: REST-based hydration/recovery for `$missionSnapshot`
// (src/lib/events/store.ts's `hydrateMissionSnapshot`/`startRestFallbackPoller`, and the
// cross-mission/sequence guards `applyMissionEvent` now applies to every event regardless of
// source). Run with `node --experimental-strip-types` so this drives the real store module
// against a mocked `global.fetch`, the same convention `check-mission-control-client.mjs`
// already established, rather than a hand-copied re-implementation of the reducer.
//
// `window.setInterval`/`clearInterval` (used by `startRestFallbackPoller`, mirroring
// `startStaleWatcher`'s existing convention) need a `window` global — plain Node has none, so
// this file aliases it to `globalThis` before importing anything that could call them. Every
// other exported function under test here (`hydrateMissionSnapshot`, `ingestMissionEvent`,
// `resetMissionSnapshot`) never touches `window` at all.
globalThis.window ??= globalThis;

import assert from 'node:assert/strict';
import {
  $missionSnapshot,
  $streamState,
  hydrateMissionSnapshot,
  ingestMissionEvent,
  resetMissionSnapshot,
  startRestFallbackPoller,
} from '../src/lib/events/store.ts';

const originalFetch = globalThis.fetch;

function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

async function withMockFetch(handler, run) {
  globalThis.fetch = handler;
  try {
    await run();
  } finally {
    globalThis.fetch = originalFetch;
  }
}

function replayPage(items, { total, limit = 500, offset = 0 } = {}) {
  return { items, total: total ?? items.length, limit, offset };
}

function missionEvent(overrides = {}) {
  return {
    id: `evt-${overrides.sequence ?? 1}`,
    mission_id: 'm-1',
    message: 'event',
    sequence: 1,
    severity: 'INFO',
    state: 'TRIAGE',
    status: 'SUCCEEDED',
    timestamp: '2026-08-21T00:00:00Z',
    trace_id: 'trace-1',
    type: 'STATE_CHANGED',
    payload: { kind: 'state_changed', from_state: 'BASELINE', to_state: 'TRIAGE', posture: 'PROTECTED', reason: '' },
    ...overrides,
  };
}

function findingEvent(overrides = {}) {
  return missionEvent({
    type: 'FINDING_RECORDED',
    message: 'finding recorded',
    payload: {
      kind: 'finding',
      finding: {
        id: 'f-1',
        mission_id: 'm-1',
        fingerprint: 'fp-1',
        title: 'heap-buffer-overflow',
        severity: 'HIGH',
        reproducible: true,
        location: { file_path: 'src/x.c', line: 12, function: 'parse' },
        replay_source: null,
      },
    },
    ...overrides,
  });
}

function resetForTest() {
  resetMissionSnapshot();
  $streamState.set('idle');
}

async function testHydrateAppliesReplayedEventsInOrder() {
  resetForTest();
  let requestedUrl;
  await withMockFetch(
    async (path) => {
      requestedUrl = path;
      return jsonResponse(
        200,
        replayPage([
          missionEvent({ sequence: 1 }),
          findingEvent({ sequence: 2 }),
        ]),
      );
    },
    async () => {
      await hydrateMissionSnapshot('m-1');
    },
  );
  assert.match(requestedUrl, /since_sequence=0/, 'first hydration for a mission never seen before must start at sequence 0');
  const snapshot = $missionSnapshot.get();
  assert.equal(snapshot.missionId, 'm-1');
  assert.equal(snapshot.state, 'TRIAGE');
  assert.equal(snapshot.latestSequence, 2);
  assert.equal(snapshot.finding?.id, 'f-1', 'a finding delivered only via REST replay must render exactly like a live one');
}

async function testHydrateIsResumableFromLastKnownSequence() {
  resetForTest();
  await withMockFetch(
    async () => jsonResponse(200, replayPage([missionEvent({ sequence: 5 })])),
    async () => hydrateMissionSnapshot('m-1'),
  );
  assert.equal($missionSnapshot.get().latestSequence, 5);

  let requestedUrl;
  await withMockFetch(
    async (path) => {
      requestedUrl = path;
      return jsonResponse(200, replayPage([]));
    },
    async () => hydrateMissionSnapshot('m-1'),
  );
  assert.match(requestedUrl, /since_sequence=5/, 'a second hydration call must resume from the snapshot\'s own latestSequence, not refetch the whole mission');
}

async function testHydratePaginatesUntilAShortPage() {
  resetForTest();
  const fullPage = Array.from({ length: 500 }, (_, index) => missionEvent({ sequence: index + 1 }));
  const secondPage = [missionEvent({ sequence: 501, payload: { kind: 'state_changed', from_state: 'TRIAGE', to_state: 'STRESS_TEST', posture: 'PROTECTED', reason: '' }, state: 'STRESS_TEST' })];
  let calls = 0;
  await withMockFetch(
    async (path) => {
      calls += 1;
      assert.match(path, calls === 1 ? /since_sequence=0/ : /since_sequence=500/);
      return jsonResponse(200, replayPage(calls === 1 ? fullPage : secondPage));
    },
    async () => hydrateMissionSnapshot('m-1'),
  );
  assert.equal(calls, 2, 'a full first page (exactly the request limit) must trigger a second fetch rather than assuming that was everything');
  assert.equal($missionSnapshot.get().latestSequence, 501);
  assert.equal($missionSnapshot.get().state, 'STRESS_TEST');
}

async function testSequenceGuardPreventsRegressionAndDuplication() {
  resetForTest();
  ingestMissionEvent(missionEvent({ sequence: 10, state: 'PATCH', payload: { kind: 'state_changed', from_state: 'STRESS_TEST', to_state: 'PATCH', posture: 'PROTECTED', reason: '' } }));
  assert.equal($missionSnapshot.get().state, 'PATCH');

  // A replay page carrying only OLDER events (e.g. a slow REST response that lands after live
  // SSE events already advanced the store further) must never roll the displayed state back.
  await withMockFetch(
    async () => jsonResponse(200, replayPage([missionEvent({ sequence: 3 })], { offset: 0 })),
    async () => hydrateMissionSnapshot('m-1'),
  );
  assert.equal($missionSnapshot.get().state, 'PATCH', 'an older/duplicate sequence number must never overwrite newer already-applied state');
  assert.equal($missionSnapshot.get().latestSequence, 10);

  const eventsBefore = $missionSnapshot.get().stageEvents;
  ingestMissionEvent(missionEvent({ sequence: 10, stage: 'PATCH', message: 'duplicate delivery' }));
  assert.deepEqual($missionSnapshot.get().stageEvents, eventsBefore, 're-delivering the exact same sequence number must be a no-op, not a duplicate stageEvents row');
}

async function testCrossMissionEventsAreDropped() {
  resetForTest();
  ingestMissionEvent(missionEvent({ mission_id: 'm-1', sequence: 1 }));
  assert.equal($missionSnapshot.get().missionId, 'm-1');

  ingestMissionEvent(missionEvent({ mission_id: 'm-2', sequence: 99, message: 'foreign mission event' }));
  assert.equal($missionSnapshot.get().missionId, 'm-1', 'an event for a mission the store has moved on from must be dropped, not folded in');
  assert.equal($missionSnapshot.get().latestSequence, 1);
}

async function testFallbackPollerOnlyPollsWhileStreamIsUnhealthy() {
  resetForTest();
  $streamState.set('open');
  let fetchCount = 0;
  const stop = await new Promise((resolve) => {
    globalThis.fetch = async () => {
      fetchCount += 1;
      resolve(); // first tick observed
      return jsonResponse(200, replayPage([]));
    };
    const cancel = startRestFallbackPoller('m-1', 5);
    setTimeout(() => resolve(cancel), 40);
  });
  globalThis.fetch = originalFetch;
  if (typeof stop === 'function') stop();
  assert.equal(fetchCount, 0, 'the fallback poller must not touch the network while $streamState is healthy');

  resetForTest();
  $streamState.set('error');
  let errorStateFetchCount = 0;
  let cancel2;
  await new Promise((resolve) => {
    globalThis.fetch = async () => {
      errorStateFetchCount += 1;
      resolve();
      return jsonResponse(200, replayPage([]));
    };
    cancel2 = startRestFallbackPoller('m-1', 5);
    setTimeout(resolve, 60);
  });
  cancel2();
  globalThis.fetch = originalFetch;
  assert.ok(errorStateFetchCount > 0, 'the fallback poller must poll via REST while $streamState is error/stale');
}

async function main() {
  await testHydrateAppliesReplayedEventsInOrder();
  await testHydrateIsResumableFromLastKnownSequence();
  await testHydratePaginatesUntilAShortPage();
  await testSequenceGuardPreventsRegressionAndDuplication();
  await testCrossMissionEventsAreDropped();
  await testFallbackPollerOnlyPollsWhileStreamIsUnhealthy();
  console.warn(
    'mission snapshot hydration ok: REST replay seeds/resumes $missionSnapshot, pagination past the 500-event ' +
      'page limit, sequence guard blocks regression/duplication, cross-mission events dropped, fallback poller ' +
      'only touches the network while the stream is unhealthy',
  );
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
