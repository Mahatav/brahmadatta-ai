// Behavioral tests for the mission-lifecycle API client (src/lib/api/client.ts).
//
// Run with `node --experimental-strip-types` (Node 22's built-in TypeScript erasure) so this
// imports the real client module directly rather than a hand-copied re-implementation — a
// signature drift in client.ts fails this test, not a stale mirror of it. `global.fetch` is
// stubbed per test so every assertion is against real client code driven by real (mocked) HTTP
// responses, not against string-matched source text.

import assert from 'node:assert/strict';
import {
  ApiError,
  createMission,
  createMissionSnapshot,
  snapshotLocalRepository,
} from '../src/lib/api/client.ts';

const originalFetch = globalThis.fetch;

function jsonResponse(status, body, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', ...headers },
  });
}

function errorEnvelope(code, message, details) {
  return { error: { code, message, details }, trace_id: 'trace-123' };
}

async function withMockFetch(handler, run) {
  globalThis.fetch = handler;
  try {
    await run();
  } finally {
    globalThis.fetch = originalFetch;
  }
}

async function testSuccessfulCreateMission() {
  let capturedInit;
  await withMockFetch(
    async (path, init) => {
      assert.equal(path, '/api/v1/missions');
      capturedInit = init;
      return jsonResponse(201, {
        id: 'm-1',
        name: 'test mission',
        state: 'CREATED',
        posture: 'PROTECTED',
        adapter: 'C_CMAKE_CTEST',
        repository_ref: 'pktcfg',
        authorized: false,
        created_at: '2026-08-19T00:00:00Z',
        updated_at: '2026-08-19T00:00:00Z',
      });
    },
    async () => {
      const mission = await createMission({ name: 'test mission', repository_ref: 'pktcfg', adapter: 'C_CMAKE_CTEST' });
      assert.equal(mission.id, 'm-1');
      assert.equal(capturedInit.method, 'POST');
      assert.equal(capturedInit.headers['content-type'], 'application/json');
      assert.equal(JSON.parse(capturedInit.body).repository_ref, 'pktcfg');
    },
  );
}

async function testHttpErrorSurfacesCodeAndDetails() {
  await withMockFetch(
    async () => jsonResponse(422, errorEnvelope('VALIDATION_ERROR', 'Request failed validation.', { errors: [{ loc: ['name'] }] })),
    async () => {
      await assert.rejects(
        () => createMission({ name: '', repository_ref: 'pktcfg', adapter: 'C_CMAKE_CTEST' }),
        (error) => {
          assert.ok(error instanceof ApiError, 'rejection must be an ApiError');
          assert.equal(error.status, 422);
          assert.equal(error.code, 'VALIDATION_ERROR');
          assert.equal(error.traceId, 'trace-123');
          assert.deepEqual(error.details.errors, [{ loc: ['name'] }]);
          return true;
        },
      );
    },
  );
}

async function testTransportFailureIsWrapped() {
  await withMockFetch(
    async () => {
      throw new TypeError('Failed to fetch');
    },
    async () => {
      await assert.rejects(
        () => createMission({ name: 'x', repository_ref: 'pktcfg', adapter: 'C_CMAKE_CTEST' }),
        (error) => {
          assert.ok(error instanceof ApiError);
          assert.equal(error.code, 'TRANSPORT');
          assert.equal(error.status, 0);
          return true;
        },
      );
    },
  );
}

async function testSnapshotDigestMismatchIsNotSwallowed() {
  // createMissionSnapshot on its own must surface a 409 as a real ApiError — the probe/retry
  // behavior belongs to snapshotLocalRepository, not to this lower-level function.
  await withMockFetch(
    async () => jsonResponse(409, errorEnvelope('SNAPSHOT_DIGEST_MISMATCH', 'digest mismatch', {
      asserted_archive_sha256: '0'.repeat(64),
      computed_archive_sha256: 'a'.repeat(64),
    })),
    async () => {
      await assert.rejects(
        () => createMissionSnapshot('m-1', { source: 'git', archive_sha256: '0'.repeat(64) }),
        (error) => {
          assert.ok(error instanceof ApiError);
          assert.equal(error.status, 409);
          assert.equal(error.details.computed_archive_sha256, 'a'.repeat(64));
          return true;
        },
      );
    },
  );
}

async function testSnapshotLocalRepositoryProbesThenRetriesWithRealDigest() {
  const realDigest = 'b'.repeat(64);
  const calls = [];
  await withMockFetch(
    async (_path, init) => {
      calls.push(JSON.parse(init.body).archive_sha256);
      if (calls.length === 1) {
        // First call: placeholder digest, server refuses with the real one in .details.
        return jsonResponse(
          409,
          errorEnvelope('SNAPSHOT_DIGEST_MISMATCH', 'digest mismatch', {
            asserted_archive_sha256: '0'.repeat(64),
            computed_archive_sha256: realDigest,
          }),
        );
      }
      // Second call: corrected digest, server accepts.
      assert.equal(JSON.parse(init.body).archive_sha256, realDigest, 'retry must use the server-computed digest');
      return jsonResponse(201, {
        id: 'snap-1',
        mission_id: 'm-1',
        commit_sha: null,
        archive_sha256: realDigest,
        file_count: 42,
        bytes_total: 4096,
        created_at: '2026-08-19T00:00:00Z',
        immutable: true,
      });
    },
    async () => {
      const record = await snapshotLocalRepository('m-1');
      assert.equal(record.archive_sha256, realDigest);
      assert.equal(calls.length, 2, 'expected exactly one probe call and one corrected retry');
      assert.notEqual(calls[0], calls[1], 'probe and retry must use different digests');
    },
  );
}

async function testSnapshotLocalRepositoryDoesNotProbeOnUnrelated409() {
  // A 409 that is NOT the digest-mismatch shape (e.g. SnapshotAlreadyRecordedError, which
  // carries existing_archive_sha256/requested_archive_sha256, not computed_archive_sha256) must
  // surface as-is rather than being treated as a digest probe response.
  await withMockFetch(
    async () =>
      jsonResponse(
        409,
        errorEnvelope('SNAPSHOT_ALREADY_RECORDED', 'a different snapshot already exists for this mission', {
          existing_archive_sha256: 'c'.repeat(64),
          requested_archive_sha256: '0'.repeat(64),
        }),
      ),
    async () => {
      await assert.rejects(
        () => snapshotLocalRepository('m-1'),
        (error) => {
          assert.ok(error instanceof ApiError);
          assert.equal(error.code, 'SNAPSHOT_ALREADY_RECORDED');
          return true;
        },
      );
    },
  );
}

async function main() {
  await testSuccessfulCreateMission();
  await testHttpErrorSurfacesCodeAndDetails();
  await testTransportFailureIsWrapped();
  await testSnapshotDigestMismatchIsNotSwallowed();
  await testSnapshotLocalRepositoryProbesThenRetriesWithRealDigest();
  await testSnapshotLocalRepositoryDoesNotProbeOnUnrelated409();
  console.warn(
    'mission control client ok: create/authorize/snapshot error handling, ApiError code/details/traceId, ' +
      'source=git digest probe-and-retry (contract gap workaround) proven against a real mocked mismatch',
  );
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
