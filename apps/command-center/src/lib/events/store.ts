import { atom } from 'nanostores';
import { sanitizeDisplayList, sanitizeDisplayText } from '../security/renderSafety.mjs';
import type { components } from '../api/schema';

export type MissionEventEnvelope = components['schemas']['MissionEvent'];
export type MissionStage = components['schemas']['MissionStage'];
export type MissionState = components['schemas']['MissionState'];
export type MissionPosture = components['schemas']['MissionPosture'];
export type EventStatus = components['schemas']['EventStatus'];
export type Severity = components['schemas']['Severity'];
export type BaselineReport = components['schemas']['BaselineReport'];
export type FindingSummary = components['schemas']['FindingSummary'];
export type FuzzingReport = components['schemas']['FuzzingReport'];
export type GateMatrix = components['schemas']['GateMatrix'];
export type GateResult = components['schemas']['GateResult'];
export type MissionVerdictSummary = components['schemas']['MissionVerdictSummary'];
export type PatchCandidate = components['schemas']['PatchCandidate'];
export type ReproducerRecord = components['schemas']['ReproducerRecord'];
export type ResourceUsage = components['schemas']['ResourceUsage'];
export type VerificationRecord = components['schemas']['VerificationRecord'];

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
  latestStatus: EventStatus | null;
  latestSeverity: Severity | null;
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
  fuzzing: FuzzingReport | null;
  finding: FindingSummary | null;
  reproducer: ReproducerRecord | null;
  patchCandidates: PatchCandidate[];
  verifications: VerificationRecord[];
  verdictSummary: MissionVerdictSummary | null;
  resourceUsage: ResourceUsage | null;
  releasedResources: ReleasedResource[];
  degradedReason: string | null;
  failedReason: string | null;
}

export const emptyMissionSnapshot: MissionSnapshot = {
  missionId: null,
  firstTimestamp: null,
  latestTimestamp: null,
  latestSequence: null,
  latestMessage: null,
  latestStatus: null,
  latestSeverity: null,
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
  fuzzing: null,
  finding: null,
  reproducer: null,
  patchCandidates: [],
  verifications: [],
  verdictSummary: null,
  resourceUsage: null,
  releasedResources: [],
  degradedReason: null,
  failedReason: null,
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
    repositoryRef: sanitizeDisplayText(repositoryRef, { fallback: 'unknown repository', maxLength: 180 }),
  });
}

export function setLocalRepositoryContext(repository: LocalRepositoryContext): void {
  const sanitizedRepository = sanitizeLocalRepositoryContext(repository);
  $localRepository.set(sanitizedRepository);
  $missionSnapshot.set({
    ...$missionSnapshot.get(),
    repositoryRef: sanitizeDisplayText(`local:${sanitizedRepository.name}`, { maxLength: 180 }),
    snapshotSha256: sanitizeDisplayText(sanitizedRepository.manifestSha256, { fallback: 'not created', maxLength: 80 }),
  });
}

function reduceMissionSnapshot(snapshot: MissionSnapshot, event: MissionEventEnvelope): MissionSnapshot {
  const next: MissionSnapshot = {
    ...snapshot,
    missionId: event.mission_id,
    firstTimestamp: snapshot.firstTimestamp ?? event.timestamp,
    latestTimestamp: event.timestamp,
    latestSequence: event.sequence,
    latestMessage: sanitizeDisplayText(event.message, { fallback: '', maxLength: 360 }),
    latestStatus: event.status,
    latestSeverity: event.severity,
    traceId: sanitizeDisplayText(event.trace_id, { fallback: 'unknown trace', maxLength: 120 }),
    state: event.state,
    stage: event.stage ?? snapshot.stage,
  };

  if (event.status === 'FAILED') {
    next.failedReason = sanitizeDisplayText(event.message, { fallback: 'event failed', maxLength: 240 });
  }

  if (degradedMetricKey(event.metrics) || /\b(degraded|unavailable|timeout|oom)\b/i.test(event.message)) {
    next.degradedReason = sanitizeDisplayText(event.message, { fallback: 'degraded mode active', maxLength: 240 });
  }

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
    next.snapshotSha256 = sanitizeDisplayText(event.payload.snapshot_sha256, { fallback: 'not created', maxLength: 80 });
    next.commitSha = event.payload.commit_sha
      ? sanitizeDisplayText(event.payload.commit_sha, { fallback: 'unknown commit', maxLength: 80 })
      : null;
  }

  if (event.payload.kind === 'baseline') {
    next.baseline = sanitizeBaselineReport(event.payload.report);
  }

  if (event.payload.kind === 'fuzzing') {
    next.fuzzing = sanitizeFuzzingReport(event.payload.report);
  }

  if (event.payload.kind === 'finding') {
    next.finding = sanitizeFindingSummary(event.payload.finding);
  }

  if (event.payload.kind === 'reproducer') {
    next.reproducer = sanitizeReproducerRecord(event.payload.reproducer);
  }

  if (event.payload.kind === 'patch_candidate') {
    const patch = sanitizePatchCandidate(event.payload.patch);
    next.patchCandidates = [
      ...snapshot.patchCandidates.filter((item) => item.id !== patch.id),
      patch,
    ];
  }

  if (event.payload.kind === 'verification') {
    const verification = event.payload.verification;
    next.verifications = [
      ...snapshot.verifications.filter((item) => item.id !== verification.id),
      verification,
    ];
  }

  if (event.payload.kind === 'mission_verdict') {
    next.verdictSummary = event.payload.summary;
  }

  if (event.payload.kind === 'resource_usage') {
    next.resourceUsage = event.payload.usage;
  }

  if (event.payload.kind === 'teardown') {
    const resource: ReleasedResource = {
      kind: sanitizeDisplayText(event.payload.resource_kind, { fallback: 'resource', maxLength: 80 }),
      id: sanitizeDisplayText(event.payload.resource_id, { fallback: 'unknown resource', maxLength: 140 }),
      released: event.payload.released,
    };
    next.releasedResources = [
      ...snapshot.releasedResources.filter((item) => item.id !== resource.id),
      resource,
    ];
  }

  return next;
}

function sanitizeLocalRepositoryContext(repository: LocalRepositoryContext): LocalRepositoryContext {
  return {
    ...repository,
    name: sanitizeDisplayText(repository.name, { fallback: 'local repository', maxLength: 120 }),
    authorizedBy: sanitizeDisplayText(repository.authorizedBy, { fallback: 'authorized operator', maxLength: 120 }),
    authorizedAt: sanitizeDisplayText(repository.authorizedAt, { fallback: 'unknown time', maxLength: 80 }),
    manifestSha256: sanitizeDisplayText(repository.manifestSha256, { fallback: 'not created', maxLength: 80 }),
    detectedFiles: sanitizeDisplayList(repository.detectedFiles, { fallback: 'unknown file', maxLength: 240, maxItems: 5000 }),
    primaryStack: sanitizeDisplayText(repository.primaryStack, { fallback: 'unknown stack', maxLength: 120 }),
  };
}

function degradedMetricKey(metrics: MissionEventEnvelope['metrics']): string | null {
  if (!metrics) {
    return null;
  }
  return Object.entries(metrics).find(([key, value]) => (
    value > 0 && /degraded|timeout|oom/i.test(key)
  ))?.[0] ?? null;
}

function sanitizeBaselineReport(report: BaselineReport): BaselineReport {
  const sanitized: BaselineReport = {
    ...report,
    adapter: sanitizeDisplayText(report.adapter, { fallback: 'unknown adapter', maxLength: 120 }),
    mission_id: sanitizeDisplayText(report.mission_id, { fallback: 'unknown mission', maxLength: 120 }),
    recorded_at: sanitizeDisplayText(report.recorded_at, { fallback: 'unknown time', maxLength: 80 }),
  };
  if (report.log_ref !== undefined) {
    sanitized.log_ref = report.log_ref
      ? {
          ...report.log_ref,
          kind: sanitizeDisplayText(report.log_ref.kind, { fallback: 'artifact', maxLength: 80 }),
          sha256: report.log_ref.sha256
            ? sanitizeDisplayText(report.log_ref.sha256, { fallback: 'unknown hash', maxLength: 80 })
            : null,
          uri: sanitizeDisplayText(report.log_ref.uri, { fallback: 'artifact unavailable', maxLength: 240 }),
        }
      : null;
  }
  return sanitized;
}

function sanitizeFuzzingReport(report: FuzzingReport): FuzzingReport {
  return {
    ...report,
    engine: sanitizeDisplayText(report.engine, { fallback: 'unknown engine', maxLength: 100 }),
    harness: sanitizeDisplayText(report.harness, { fallback: 'unknown harness', maxLength: 200 }),
    mission_id: sanitizeDisplayText(report.mission_id, { fallback: 'unknown mission', maxLength: 120 }),
    replay_source: report.replay_source
      ? sanitizeDisplayText(report.replay_source, { fallback: 'replay source unavailable', maxLength: 240 })
      : null,
    recorded_at: sanitizeDisplayText(report.recorded_at, { fallback: 'unknown time', maxLength: 80 }),
    sanitizers: sanitizeDisplayList(report.sanitizers ?? [], { fallback: 'unknown sanitizer', maxLength: 80, maxItems: 12 }),
  };
}

function sanitizeFindingSummary(finding: FindingSummary): FindingSummary {
  return {
    ...finding,
    fingerprint: sanitizeDisplayText(finding.fingerprint, { fallback: 'unknown fingerprint', maxLength: 180 }),
    id: sanitizeDisplayText(finding.id, { fallback: 'unknown finding', maxLength: 120 }),
    mission_id: sanitizeDisplayText(finding.mission_id, { fallback: 'unknown mission', maxLength: 120 }),
    replay_source: finding.replay_source
      ? sanitizeDisplayText(finding.replay_source, { fallback: 'replay source unavailable', maxLength: 240 })
      : null,
    title: sanitizeDisplayText(finding.title, { fallback: 'Untitled finding', maxLength: 240 }),
    location: {
      ...finding.location,
      file_path: sanitizeDisplayText(finding.location.file_path, { fallback: 'unknown file', maxLength: 240 }),
      function: finding.location.function
        ? sanitizeDisplayText(finding.location.function, { fallback: 'unknown function', maxLength: 160 })
        : null,
    },
  };
}

function sanitizeReproducerRecord(reproducer: ReproducerRecord): ReproducerRecord {
  return {
    ...reproducer,
    created_at: sanitizeDisplayText(reproducer.created_at, { fallback: 'unknown time', maxLength: 80 }),
    finding_id: sanitizeDisplayText(reproducer.finding_id, { fallback: 'unknown finding', maxLength: 120 }),
    id: sanitizeDisplayText(reproducer.id, { fallback: 'unknown reproducer', maxLength: 120 }),
    test_command: sanitizeDisplayText(reproducer.test_command, { fallback: 'test command unavailable', maxLength: 240 }),
    artifact: {
      ...reproducer.artifact,
      kind: sanitizeDisplayText(reproducer.artifact.kind, { fallback: 'artifact', maxLength: 80 }),
      sha256: reproducer.artifact.sha256
        ? sanitizeDisplayText(reproducer.artifact.sha256, { fallback: 'unknown hash', maxLength: 80 })
        : null,
      uri: sanitizeDisplayText(reproducer.artifact.uri, { fallback: 'artifact unavailable', maxLength: 240 }),
    },
  };
}

function sanitizePatchCandidate(patch: PatchCandidate): PatchCandidate {
  return {
    ...patch,
    diff: sanitizeDisplayText(patch.diff, { fallback: 'diff unavailable', maxLength: 200000 }),
    id: sanitizeDisplayText(patch.id, { fallback: 'unknown patch', maxLength: 120 }),
    mission_id: sanitizeDisplayText(patch.mission_id, { fallback: 'unknown mission', maxLength: 120 }),
    finding_id: sanitizeDisplayText(patch.finding_id, { fallback: 'unknown finding', maxLength: 120 }),
    policy_detail: sanitizeDisplayText(patch.policy_detail, { fallback: '', maxLength: 240 }),
    rationale: sanitizeDisplayText(patch.rationale, { fallback: '', maxLength: 1200 }),
  };
}
