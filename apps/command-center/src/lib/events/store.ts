import { atom } from 'nanostores';

export type StreamState = 'idle' | 'connecting' | 'open' | 'stale' | 'closed' | 'error';

export interface MissionEvent {
  id: string;
  event: string;
  data: string;
}

export const $streamState = atom<StreamState>('idle');
export const $latestMissionEvent = atom<MissionEvent | null>(null);
