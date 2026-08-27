/**
 * #52 / D-058 §2.4 — the presentation-mode disclosure signal, and #273's structural fix for how
 * it reaches both the disclosure chrome and the panel data it describes.
 *
 * #272 moved this OUT of `../events/store.ts`'s `MissionSnapshot`/`emptyMissionSnapshot`
 * entirely (it used to be a `mockSource: MockSource` field there). That file is imported by
 * every build (`MissionCommandCenter` imports it directly), so the literal object property
 * `mockSource: null` in `emptyMissionSnapshot` compiled into the finale/production bundle's JS
 * even though the finale build never reads or writes it — bundlers don't tree-shake unused
 * *properties* out of an object literal that is itself genuinely used (only unused *exports*),
 * so the field's mere presence in the shared type was enough to leak its name into an artifact
 * whose acceptance criterion is "zero references to presentation-mode code" (cybersecurity's
 * #52/D-148 review). This module is only ever imported by presentation-mode files
 * (`PresentationMissionCommandCenter.tsx` and this file's own test,
 * `scripts/check-issue-273-presentation-provenance-gate.mjs`), which are themselves excluded
 * from the finale build the same way `discoverFixtureMission.ts` is — see that file's own doc
 * comment and `scripts/check-presentation-build-exclusion.sh`. Moving the field here means the
 * finale bundle no longer contains the name at all, not merely an unused reference to it.
 *
 * `'fixture-replay'` only ever comes from a real HTTP response header
 * (`X-Brahmadatta-Fixture: replay`, set by `packages/test-fixtures/sse_replay.py` on every one
 * of its responses), never inferred from a build flag or a URL alone — see `deriveMockSource`
 * below, the one place that mapping happens. `null` covers both "not yet known" and "confirmed
 * real"; `PresentationMissionCommandCenter`'s own local `status` state tracks which of those two
 * a caller is looking at, because that distinction is presentation-mode-only and (as of #272)
 * doesn't belong anywhere near the mission snapshot every panel reads.
 */

import { atom } from 'nanostores';
// Explicit `.ts` extension — same reason `events/store.ts` gives for its own `api/client.ts`
// import: a real runtime import that also needs to resolve under plain
// `node --experimental-strip-types` (this module is exercised directly by
// `scripts/check-presentation-mode.mjs` and `scripts/check-issue-273-presentation-provenance-gate.mjs`,
// Node ESM resolution has no bundler-style extension inference), not just Astro/Vite's bundler
// resolution.
import {
  getMissionDetailWithProvenance,
  type MissionDetail,
} from '../api/client.ts';
import { $activeMissionId } from '../events/store.ts';

export type MockSource = 'fixture-replay' | null;

/** Mirrors `PresentationModeChip`'s own prop union — defined once here so the component, the
 * gating predicate below, and this module's tests all share one definition rather than three
 * copies that could drift. */
export type ProvenanceStatus = 'checking' | 'mock' | 'real-mission-detected';

/**
 * The disclosure signal for whichever mission `$activeMissionId` currently names. Deliberately
 * NOT part of `$missionSnapshot` (see this module's own doc comment above) — presentation mode
 * is the only reader, via `PresentationMissionCommandCenter`.
 */
export const $presentationMockSource = atom<MockSource>(null);

/** Call whenever `$activeMissionId` changes, before starting a fresh provenance check for the
 * new id — otherwise a stale 'fixture-replay' from the PREVIOUS mission could render the mock
 * chip/watermark for one frame against the new mission's real data. */
export function resetPresentationMockSource(): void {
  $presentationMockSource.set(null);
}

/**
 * #52 §2.4 acceptance criterion 2 — the one place a raw HTTP header value becomes `MockSource`.
 * Pure and total: any header value other than the exact literal `'replay'` is real data, full
 * stop. Exported so `scripts/check-issue-273-presentation-provenance-gate.mjs` (and the
 * pre-#272 `scripts/check-presentation-mode.mjs`) can assert the mapping directly, without
 * needing a mounted component or a live fetch.
 */
export function deriveMockSource(fixtureHeaderValue: string | null): MockSource {
  return fixtureHeaderValue === 'replay' ? 'fixture-replay' : null;
}

/**
 * Guarded the same way `applyMissionEvent`/the pre-#272 `setMockSource` guarded every write: a
 * response for a mission this build has already moved on from (operator switched missions
 * mid-flight, or a stale racing request resolves late) must never overwrite the current
 * mission's disclosure state. Presentation-mode-only — the live/finale build never calls this.
 */
export function setPresentationMockSource(missionId: string, source: MockSource): void {
  if ($activeMissionId.get() !== missionId) {
    return;
  }
  $presentationMockSource.set(source);
}

/**
 * #273 — the gating predicate for "panel content can never appear before the disclosure banner
 * reflects reality." `PresentationMissionCommandCenter` renders `MissionCommandCenter` (and
 * therefore lets it open its SSE connection and fetch real data) if and only if this returns
 * true. Pure and total so it is directly testable without mounting anything — see
 * `scripts/check-issue-273-presentation-provenance-gate.mjs`.
 */
export function shouldRenderMissionPanels(status: ProvenanceStatus): boolean {
  return status !== 'checking';
}

/**
 * #273 — derives whether the CONFIRMED mock state (chip + full-bleed watermark) should render.
 * Reads both the local `status` (this render's own belief) and the store's `$presentationMockSource`
 * value (the last write any in-flight check actually committed) so a render landing between
 * `setStatus` and the store write above never shows the watermark for data that was never
 * actually confirmed as fixture-replay.
 */
export function deriveConfirmedMock(status: ProvenanceStatus, mockSource: MockSource): boolean {
  return status === 'mock' && mockSource === 'fixture-replay';
}

/**
 * #273 — the structural fix for "panels fed by `connectMissionEvents` (SSE) and a separate
 * plain `getMissionDetail()` call, neither of which routes through the provenance wrapper."
 *
 * This is now the ONLY function `PresentationMissionCommandCenter` uses to fetch a mission's
 * detail — both for its own initial/gating check AND, wired as `MissionCommandCenter`'s
 * `fetchMissionDetail` prop, for every fetch that component makes to populate the panels
 * (mount-time and every `refreshMissionDetail()`). Because it is the single function underneath
 * both call sites, the `MissionDetail` handed to the panels and the `MockSource` handed to the
 * disclosure banner are read off the exact same HTTP response, every time — not two independent
 * requests to two different functions that merely happen to hit the same backend today. See
 * `MissionCommandCenter.tsx`'s own doc comment on `fetchMissionDetail` for the live/finale side
 * of this: that build's default fetcher is plain `getMissionDetail`, so nothing about the
 * live/finale rendering path changes, and this function itself is never imported outside
 * presentation-mode files, so it stays out of the finale bundle exactly as `getMissionDetailWithProvenance`
 * already does.
 *
 * Residual, disclosed gap (unchanged from #52's original design, `client.ts`'s own doc comment
 * on `getMissionDetailWithProvenance`): the live SSE stream `connectMissionEvents` opens cannot
 * carry this header at all — a native `EventSource` never exposes response headers to JS — so
 * this only closes the REST-detail half of the divergence risk. #273's other half (never render
 * panels before the FIRST provenance check for a mission resolves, `shouldRenderMissionPanels`
 * above) means the SSE connection itself never even opens until this function has already run at
 * least once for that mission id, which is the most a browser-only fix can structurally
 * guarantee without a backend change annotating the SSE stream itself. Flagged to
 * backend-developer/software-architect as a follow-up, not worked around silently.
 */
export async function fetchMissionDetailWithDisclosure(
  missionId: string,
  signal: AbortSignal | undefined,
  onStatusResolved: (status: 'mock' | 'real-mission-detected') => void,
): Promise<MissionDetail> {
  const { mission, fixtureHeaderValue } = await getMissionDetailWithProvenance(missionId, signal);
  const mockSource = deriveMockSource(fixtureHeaderValue);
  setPresentationMockSource(missionId, mockSource);
  if ($activeMissionId.get() === missionId) {
    onStatusResolved(mockSource === 'fixture-replay' ? 'mock' : 'real-mission-detected');
  }
  return mission;
}
