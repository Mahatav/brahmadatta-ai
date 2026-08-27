/**
 * #52 / D-058 §2.4 — the presentation-mode disclosure signal.
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
 * `scripts/check-presentation-mode.mjs`), which are themselves excluded from the finale build
 * the same way `discoverFixtureMission.ts` is — see that file's own doc comment and
 * `scripts/check-presentation-build-exclusion.sh`. Moving the field here means the finale
 * bundle no longer contains the name at all, not merely an unused reference to it.
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
import { $activeMissionId } from '../events/store.ts';

export type MockSource = 'fixture-replay' | null;

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
 * stop. Exported so `scripts/check-presentation-mode.mjs` can assert the mapping directly,
 * without needing a mounted component or a live fetch.
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
