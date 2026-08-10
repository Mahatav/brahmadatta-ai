import { atom } from 'nanostores';
import type { components } from '../api/schema';

export type MissionEventEnvelope = components['schemas']['MissionEvent'];
export type MissionStage = components['schemas']['MissionStage'];
export type MissionState = components['schemas']['MissionState'];
export type MissionPosture = components['schemas']['MissionPosture'];
export type BaselineReport = components['schemas']['BaselineReport'];
export type FindingSummary = components['schemas']['FindingSummary'];
export type ReproducerRecord = components['schemas']['ReproducerRecord'];
export type ResourceUsage = components['schemas']['ResourceUsage'];

export type StreamState = 'idle' | 'connecting' | 'open' | 'stale' | 'closed' | 'error';

export interface MissionEvent {
  id: string;
  event: string;
  data: string;
}

export interface ReleasedResource {
  kind: string;
  id: string;
  released: boolean;
}

export interface LocalRepositoryContext {
  name: string;
  authorizedBy: string;
  authorizedAt: string;
  fileCount: number;
  totalBytes: number;
  manifestSha256: string;
  detectedFiles: string[];
  primaryStack: string;
  localOnly: boolean;
}

export interface MissionSnapshot {
  missionId: string | null;
  firstTimestamp: string | null;
  latestTimestamp: string | null;
  latestSequence: number | null;
  latestMessage: string | null;
  traceId: string | null;
  state: MissionState | null;
  posture: MissionPosture | null;
  stage: MissionStage | null;
  completedStages: MissionStage[];
  stageProgress: Partial<Record<MissionStage, number | null>>;
  repositoryRef: string | null;
  snapshotSha256: string | null;
  commitSha: string | null;
  baseline: BaselineReport | null;
  finding: FindingSummary | null;
  reproducer: ReproducerRecord | null;
  resourceUsage: ResourceUsage | null;
  releasedResources: ReleasedResource[];
}

export const emptyMissionSnapshot: MissionSnapshot = {
  missionId: null,
  firstTimestamp: null,
  latestTimestamp: null,
  latestSequence: null,
  latestMessage: null,
  traceId: null,
  state: null,
  posture: null,
  stage: null,
  completedStages: [],
  stageProgress: {},
  repositoryRef: null,
  snapshotSha256: null,
  commitSha: null,
  baseline: null,
  finding: null,
  reproducer: null,
  resourceUsage: null,
  releasedResources: [],
};

export const $streamState = atom<StreamState>('idle');
export const $latestMissionEvent = atom<MissionEvent | null>(null);
export const $missionSnapshot = atom<MissionSnapshot>(emptyMissionSnapshot);
export const $localRepository = atom<LocalRepositoryContext | null>(null);

export function resetMissionSnapshot(): void {
  $missionSnapshot.set(emptyMissionSnapshot);
  $latestMissionEvent.set(null);
}

export function ingestMissionEvent(event: MissionEventEnvelope): void {
  $missionSnapshot.set(reduceMissionSnapshot($missionSnapshot.get(), event));
}

export function setMissionRepositoryContext(repositoryRef: string): void {
  $missionSnapshot.set({
    ...$missionSnapshot.get(),
    repositoryRef,
  });
}

export function setLocalRepositoryContext(repository: LocalRepositoryContext): void {
  $localRepository.set(repository);
  $missionSnapshot.set({
    ...$missionSnapshot.get(),
    repositoryRef: `local:${repository.name}`,
    snapshotSha256: repository.manifestSha256,
  });
}

function reduceMissionSnapshot(snapshot: MissionSnapshot, event: MissionEventEnvelope): MissionSnapshot {
  const next: MissionSnapshot = {
    ...snapshot,
    missionId: event.mission_id,
    firstTimestamp: snapshot.firstTimestamp ?? event.timestamp,
    latestTimestamp: event.timestamp,
    latestSequence: event.sequence,
    latestMessage: event.message,
    traceId: event.trace_id,
    state: event.state,
    stage: event.stage ?? snapshot.stage,
  };

  if (event.payload.kind === 'state_changed') {
    next.state = event.payload.to_state;
    next.posture = event.payload.posture;
  }

  if (event.payload.kind === 'stage_progress') {
    next.stage = event.payload.stage;
    next.stageProgress = {
      ...snapshot.stageProgress,
      [event.payload.stage]: event.payload.percent_complete ?? null,
    };
  }

  if (event.type === 'STAGE_COMPLETED' && event.stage && !snapshot.completedStages.includes(event.stage)) {
    next.completedStages = [...snapshot.completedStages, event.stage];
  }

  if (event.payload.kind === 'snapshot') {
    next.snapshotSha256 = event.payload.snapshot_sha256;
    next.commitSha = event.payload.commit_sha ?? null;
  }

  if (event.payload.kind === 'baseline') {
    next.baseline = event.payload.report;
  }

  if (event.payload.kind === 'finding') {
    next.finding = event.payload.finding;
  }

  if (event.payload.kind === 'reproducer') {
    next.reproducer = event.payload.reproducer;
  }

  if (event.payload.kind === 'resource_usage') {
    next.resourceUsage = event.payload.usage;
  }

  if (event.payload.kind === 'teardown') {
    const resource: ReleasedResource = {
      kind: event.payload.resource_kind,
      id: event.payload.resource_id,
      released: event.payload.released,
    };
    next.releasedResources = [
      ...snapshot.releasedResources.filter((item) => item.id !== resource.id),
      resource,
    ];
  }

  return next;
}
