// Behavioral tests for #52 (presentation mode, D-058) — the parts that are checkable without a
// mounted component: the header -> MockSource mapping (acceptance criterion 2), the store
// guard that writes it, `getMissionDetailWithProvenance`'s header plumbing, and
// `discoverFixtureMission`'s tolerance of the fixture tool's non-conformant `mission_id`/`id`
// list shape (documented CONTRACT GAP in that module). Same convention
// `check-mission-snapshot-hydration.mjs` established: `node --experimental-strip-types`
// against the real modules, `global.fetch` mocked with real `Response` objects so header
// reads are exercised for real, not string-matched.

import assert from 'node:assert/strict';
import { getMissionDetailWithProvenance } from '../src/lib/api/client.ts';
import {
  $missionSnapshot,
  deriveMockSource,
  resetMissionSnapshot,
  setMockSource,
} from '../src/lib/events/store.ts';
import { discoverFixtureMission } from '../src/lib/presentation/discoverFixtureMission.ts';

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
// Acceptance criterion 2: "mockSource is set only when a test double's [response] includes
// X-Brahmadatta-Fixture: replay, and never otherwise."
// ---------------------------------------------------------------------------

function testDeriveMockSourceOnlyAcceptsTheExactHeaderValue() {
  assert.equal(deriveMockSource('replay'), 'fixture-replay');
  assert.equal(deriveMockSource(null), null, 'no header at all must never be treated as mock data');
  assert.equal(deriveMockSource(''), null);
  assert.equal(deriveMockSource('REPLAY'), null, 'case must not be inferred/normalized — the server sends an exact literal');
  assert.equal(deriveMockSource('replayed'), null, 'a near-miss value must not pass');
  assert.equal(deriveMockSource('true'), null, 'a boolean-flavoured value must not be confused with the real header contract');
}

async function testGetMissionDetailWithProvenanceReadsTheRealHeader() {
  let requestedPath;
  await withMockFetch(
    async (path) => {
      requestedPath = path;
      return jsonResponse(200, { id: 'm-fixture', state: 'VERIFIED' }, { 'X-Brahmadatta-Fixture': 'replay' });
    },
    async () => {
      const result = await getMissionDetailWithProvenance('m-fixture');
      assert.equal(requestedPath, '/api/v1/missions/m-fixture');
      assert.equal(result.fixtureHeaderValue, 'replay');
      assert.equal(deriveMockSource(result.fixtureHeaderValue), 'fixture-replay');
    },
  );

  await withMockFetch(
    async () => jsonResponse(200, { id: 'm-real', state: 'VERIFIED' }),
    async () => {
      const result = await getMissionDetailWithProvenance('m-real');
      assert.equal(result.fixtureHeaderValue, null, 'a real control-api response never carries this header');
      assert.equal(deriveMockSource(result.fixtureHeaderValue), null);
    },
  );
}

// ---------------------------------------------------------------------------
// The store guard — same cross-mission shape as `applyMissionEvent`'s existing guard.
// ---------------------------------------------------------------------------

function testSetMockSourceIsGuardedByTheCurrentMission() {
  resetMissionSnapshot();
  assert.equal($missionSnapshot.get().mockSource, null, 'a fresh snapshot must never claim mock data by default');

  // No mission bound yet (missionId still null) — the write is accepted; it will be preserved
  // once the first event lands and sets missionId, via `reduceMissionSnapshot`'s spread.
  setMockSource('m-1', 'fixture-replay');
  assert.equal($missionSnapshot.get().mockSource, 'fixture-replay');

  // A late-resolving provenance check for a DIFFERENT mission than the one the store now
  // belongs to (operator switched missions mid-flight) must never overwrite the current
  // mission's disclosure state.
  $missionSnapshot.set({ ...$missionSnapshot.get(), missionId: 'm-1' });
  setMockSource('m-2', null);
  assert.equal($missionSnapshot.get().mockSource, 'fixture-replay', 'a stale write for a different mission id must be dropped');
  assert.equal($missionSnapshot.get().missionId, 'm-1');

  // The real refusal path: the CURRENT mission's own provenance check resolves to "no header."
  setMockSource('m-1', null);
  assert.equal($missionSnapshot.get().mockSource, null, 'a confirmed real mission must clear a previously-set mock flag');

  resetMissionSnapshot();
}

// ---------------------------------------------------------------------------
// discoverFixtureMission — tolerates the fixture tool's own `mission_id`/`id` shape mismatch,
// documented in the module itself as a CONTRACT GAP rather than asserted away.
// ---------------------------------------------------------------------------

async function testDiscoverFixtureMissionReadsTheFixtureToolsMissionIdShape() {
  await withMockFetch(
    async (path) => {
      assert.match(path, /\/api\/v1\/missions\?limit=1/);
      return jsonResponse(200, { items: [{ mission_id: 'b7ad2c10-4f61-4f6d-9d2e-1c7a4b6d0e11' }], total: 1, limit: 1, offset: 0 });
    },
    async () => {
      assert.equal(await discoverFixtureMission(), 'b7ad2c10-4f61-4f6d-9d2e-1c7a4b6d0e11');
    },
  );
}

async function testDiscoverFixtureMissionAlsoAcceptsTheRealContractShape() {
  await withMockFetch(
    async () => jsonResponse(200, { items: [{ id: 'm-real-1' }], total: 1, limit: 1, offset: 0 }),
    async () => {
      assert.equal(await discoverFixtureMission(), 'm-real-1');
    },
  );
}

async function testDiscoverFixtureMissionReturnsNullRatherThanThrowingWhenUnreachable() {
  await withMockFetch(
    async () => {
      throw new TypeError('network unreachable');
    },
    async () => {
      assert.equal(await discoverFixtureMission(), null);
    },
  );

  await withMockFetch(
    async () => jsonResponse(200, { items: [], total: 0, limit: 1, offset: 0 }),
    async () => {
      assert.equal(await discoverFixtureMission(), null, 'an empty missions list must not be mistaken for a discovered mission');
    },
  );
}

async function main() {
  testDeriveMockSourceOnlyAcceptsTheExactHeaderValue();
  await testGetMissionDetailWithProvenanceReadsTheRealHeader();
  testSetMockSourceIsGuardedByTheCurrentMission();
  await testDiscoverFixtureMissionReadsTheFixtureToolsMissionIdShape();
  await testDiscoverFixtureMissionAlsoAcceptsTheRealContractShape();
  await testDiscoverFixtureMissionReturnsNullRatherThanThrowingWhenUnreachable();
  console.warn(
    'presentation mode ok: mockSource is derived only from the exact X-Brahmadatta-Fixture: replay header value, ' +
      'the store guard drops stale cross-mission writes, and fixture-mission discovery tolerates the fixture ' +
      "tool's own mission_id/id shape mismatch without asserting a contract it doesn't keep",
  );
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
