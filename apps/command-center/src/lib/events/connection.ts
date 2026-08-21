import {
  $latestMissionEvent,
  $streamState,
  hydrateMissionSnapshot,
  ingestMissionEvent,
  resetMissionSnapshot,
  type MissionEventEnvelope,
} from './store';
import type { components } from '../api/schema';

type EventType = components['schemas']['EventType'];

const eventTypes: Record<EventType, true> = {
  MISSION_CREATED: true,
  MISSION_AUTHORIZED: true,
  SNAPSHOT_RECORDED: true,
  PREFLIGHT_COMPLETED: true,
  STATE_CHANGED: true,
  STAGE_STARTED: true,
  STAGE_PROGRESS: true,
  STAGE_COMPLETED: true,
  BASELINE_RECORDED: true,
  BASELINE_PASSED: true,
  BASELINE_FAILED: true,
  FINDING_RECORDED: true,
  REPRODUCER_RECORDED: true,
  PATCH_CANDIDATE_RECORDED: true,
  PATCH_POLICY_EVALUATED: true,
  VERIFICATION_RECORDED: true,
  MISSION_VERDICT_RECORDED: true,
  EVIDENCE_EXPORTED: true,
  RESOURCE_USAGE_SAMPLED: true,
  TEARDOWN_CONFIRMED: true,
  POLICY_VIOLATION: true,
  MISSION_PAUSED: true,
  MISSION_RESUMED: true,
  MISSION_CANCELLED: true,
  MISSION_FAILED: true,
  LOG: true,
};

let source: EventSource | undefined;
let hydrationAbort: AbortController | undefined;

export function connectMissionEvents(missionId: string): () => void {
  disconnectMissionEvents();
  resetMissionSnapshot();
  $streamState.set('connecting');

  // D-114 BUG-2: seed the snapshot from the REST replay log immediately, rather than only ever
  // waiting for the first live SSE event to arrive — closes the gap where a fresh page load (or
  // a reconnect after the stream had been down) showed an empty/stale snapshot with no way to
  // catch up short of a real event landing on the wire. See `hydrateMissionSnapshot`'s own doc
  // comment in `./store.ts`. Fire-and-forget: a failed hydration just means the snapshot starts
  // empty and waits for the live stream, exactly as this function behaved before this fix.
  hydrationAbort = new AbortController();
  hydrateMissionSnapshot(missionId, hydrationAbort.signal).catch(() => undefined);

  const encodedMissionId = encodeURIComponent(missionId);
  source = new EventSource(`/api/v1/missions/${encodedMissionId}/events`);
  source.onopen = () => $streamState.set('open');
  source.onerror = () => $streamState.set('error');
  for (const eventType of Object.keys(eventTypes) as EventType[]) {
    source.addEventListener(eventType, (event) => {
      $latestMissionEvent.set({
        id: event.lastEventId,
        event: eventType,
        data: event.data,
      });
      try {
        ingestMissionEvent(JSON.parse(event.data) as MissionEventEnvelope);
      } catch {
        $streamState.set('error');
      }
    });
  }

  return disconnectMissionEvents;
}

export function disconnectMissionEvents(): void {
  source?.close();
  source = undefined;
  hydrationAbort?.abort();
  hydrationAbort = undefined;
  $streamState.set('closed');
}
