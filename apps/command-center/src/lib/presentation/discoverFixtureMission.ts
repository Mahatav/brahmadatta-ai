/**
 * #52 §2.3 — "If a different fixture is ever used, the string is generated from that fixture's
 * own filename, never hand-typed." Extended here to the mission id itself: rather than hardcode
 * `mission-pktcfg-001`'s id in this app, the presentation composition root asks whatever backend
 * it is actually pointed at (the fixture-replay server, in every supported presentation-mode
 * workflow) which mission it is serving. Regenerating the fixture, or pointing `--fixture` at a
 * different committed mission log, needs no change here.
 *
 * CONTRACT GAP, disclosed rather than worked around silently (frontend-developer, #52 — same
 * convention `api/client.ts`'s own `snapshotLocalRepository` doc comment already uses for a
 * different gap): `packages/test-fixtures/sse_replay.py`'s `GET /missions` response
 * (`mission_summary()`) keys the id as `mission_id`, but the real contract
 * (`schema.d.ts`'s `MissionSummary`) names it `id`. The fixture tool's own README says only its
 * *events* are validated against `packages/schemas/openapi.json` — the summary/detail endpoints
 * were built "enough... to render a panel header," not schema-conformant. `listMissions()`
 * (typed against the real schema) would silently read `undefined` for `.id` against this
 * backend, so this function deliberately does its own untyped fetch and reads whichever of
 * `id`/`mission_id` is present, instead of asserting a contract the fixture tool doesn't
 * actually keep. Flagged to `backend-developer`/`security-research-engineer` (test-fixtures'
 * owners) rather than edited here.
 *
 * Returns `null` on any failure (unreachable backend, empty list, unrecognized shape) — the
 * caller's job, not this function's, to decide what an operator sees when there is nothing to
 * auto-bind to.
 */
export async function discoverFixtureMission(signal?: AbortSignal): Promise<string | null> {
  try {
    const response = await fetch('/api/v1/missions?limit=1', { headers: { Accept: 'application/json' }, ...(signal ? { signal } : {}) });
    if (!response.ok) {
      return null;
    }
    const body: unknown = await response.json();
    if (typeof body !== 'object' || body === null || !('items' in body)) {
      return null;
    }
    const items = (body as { items: unknown }).items;
    if (!Array.isArray(items) || items.length === 0) {
      return null;
    }
    const first = items[0] as Record<string, unknown>;
    const id = first['id'] ?? first['mission_id'];
    return typeof id === 'string' && id.length > 0 ? id : null;
  } catch {
    return null;
  }
}
