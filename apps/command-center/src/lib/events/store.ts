import { atom } from 'nanostores';
// Explicit `.ts` extension (`allowImportingTsExtensions` in tsconfig.json, via
// `astro/tsconfigs/base`): a real runtime import, unlike the type-only `./schema` import below,
// so it needs to resolve under plain `node --experimental-strip-types` too (this module is
// exercised directly by scripts/check-mission-snapshot-hydration.mjs, Node ESM resolution has no
// bundler-style extension inference) as well as under Astro/Vite's bundler resolution.
import { replayMissionEvents } from '../api/client.ts';
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

export interface StageEventRow {
  sequence: number;
  timestamp: string;
  message: string;
}

export const EVENT_WINDOW = 50;

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
  /** Real per-stage boundary timestamps, from `STAGE_STARTED`/`STAGE_COMPLETED` events (§6.2 —
   * the stage timeline's "00:02:11" elapsed figures are derived from these, never a client-side
   * timer: §2.6 rule 2, "nothing advances on a timer"). Absent means genuinely unknown, rendered
   * as the not-measured em dash rather than guessed. */
  stageStartedAt: Partial<Record<MissionStage, string>>;
  stageCompletedAt: Partial<Record<MissionStage, string>>;
  /** The most recent LOG-carrying event's message observed while that stage was current. This is
   * how the ANALYZE row ends up rendering the backend's own
   * "no static analyzer configured in this build" string verbatim (§6.2, C8) without the
   * frontend composing it. */
  stageMessage: Partial<Record<MissionStage, string>>;
  /** Bounded per-stage event log for the timeline's expandable event rows (§6.2). Capped to the
   * most recent `EVENT_WINDOW` (50, matching `--bd-event-window` in tokens.css) entries per
   * stage — "no windowing machinery... an expanded stage renders its most recent 50 event rows
   * and states the count of what it is not showing." Never trimmed silently: the count of what
   * was dropped travels alongside (see `stageEventOverflow`). */
  stageEvents: Partial<Record<MissionStage, StageEventRow[]>>;
  stageEventOverflow: Partial<Record<MissionStage, number>>;
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
  stageStartedAt: {},
  stageCompletedAt: {},
  stageMessage: {},
  stageEvents: {},
  stageEventOverflow: {},
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

/** The mission the Command Center is currently bound to. Set either by a deep-linked
 * `?mission=` query param (read once, on load) or by `MissionControlPanel` after a real
 * `create → authorize → snapshot → preflight` sequence completes. This is the single source of
 * truth for "which mission" — `MissionCommandCenter` opens the one shared SSE connection
 * (§12 build note 1, docs/09-company/04-design-system.md) whenever this changes, rather than
 * each panel resolving the id on its own. */
export const $activeMissionId = atom<string | null>(null);

export function setActiveMissionId(missionId: string | null): void {
  $activeMissionId.set(missionId);
}

export function resetMissionSnapshot(): void {
  $missionSnapshot.set(emptyMissionSnapshot);
  $latestMissionEvent.set(null);
  $lastEventReceivedAt.set(null);
}

/** Wall-clock time (client-side `Date.now()`, not a server timestamp) the browser last actually
 * received an event on the shared SSE connection. This is the ONLY input to the stale detector
 * (§6.1 Degraded state, §8: "the stale detector is the one timer, and it only ever *degrades*
 * the display"). It never advances anything — it is read by `startStaleWatcher` below to decide
 * whether to flip `$streamState` to `'stale'`, and that is its only consumer. */
export const $lastEventReceivedAt = atom<number | null>(null);

/**
 * The one place any event — live SSE or REST-replayed (`hydrateMissionSnapshot` below) — is
 * actually folded into `$missionSnapshot`. Two guards make it safe for both sources to call
 * this for overlapping data without coordinating with each other:
 *
 * 1. Cross-mission guard: if the store already belongs to a different mission than this event
 *    (the operator switched missions and `resetMissionSnapshot`/a fresh `connectMissionEvents`
 *    call moved the store on), the event is dropped. Without this, a slow REST replay response
 *    for mission A that resolves after the operator has already switched to mission B would
 *    fold A's event onto B's snapshot.
 * 2. Sequence guard: `sequence` is gap-free and monotonic per mission (the replay endpoint's
 *    own doc comment, `api/routers/missions.py`), so an event whose sequence is not newer than
 *    what the store already reflects has already been applied — by the live stream, by a
 *    previous replay page, or both — and re-applying it would double-append to the
 *    non-idempotent accumulators (`stageEvents`), not just waste work.
 */
function applyMissionEvent(event: MissionEventEnvelope): void {
  const current = $missionSnapshot.get();
  if (current.missionId != null && current.missionId !== event.mission_id) {
    return;
  }
  if (current.latestSequence != null && event.sequence <= current.latestSequence) {
    return;
  }
  $missionSnapshot.set(reduceMissionSnapshot(current, event));
}

export function ingestMissionEvent(event: MissionEventEnvelope): void {
  $lastEventReceivedAt.set(Date.now());
  if ($streamState.get() === 'stale') {
    $streamState.set('open');
  }
  applyMissionEvent(event);
}

/** How many events `hydrateMissionSnapshot` asks for per page — matches
 * `replay_events`'s own `le=500` ceiling (`api/routers/missions.py`) exactly, so a mission
 * with more events than that is still fully recoverable, just over more than one round trip. */
const REPLAY_PAGE_LIMIT = 500;

/**
 * REST-based hydration/recovery for `$missionSnapshot` (D-114 BUG-2, the rejection's BLOCKER
 * finding). Before this function existed, the entire visual layer — Core, Stage Timeline,
 * Findings rail, Verdict panel, Candidate Compare, Resource Ledger — had exactly one source of
 * truth, the live SSE stream, and zero recovery path when it dropped: QA reproduced the stream
 * failing after ~3 seconds on a real mission, live, twice, with no recovery even across a full
 * page reload, while the mission kept progressing correctly server-side the whole time.
 *
 * `GET /missions/{id}/events/replay` is not a new endpoint built for this fix — it already
 * existed as "gap recovery for the SSE stream" (`api/routers/missions.py::replay_events`),
 * reading the same persisted `MissionEvent` log through the same schema conversion the live
 * path uses. Folding its output through the exact same `applyMissionEvent`/
 * `reduceMissionSnapshot` the live path uses means there is one definition of what this
 * mission's state looks like, not a hand-reconstructed approximation stitched from several
 * other REST resources that could drift from what live events would have produced.
 *
 * Resumable: starts from the current snapshot's own `latestSequence` (0 only for a mission this
 * store has never seen), so calling it repeatedly — once on connect, then again on every tick
 * of `startRestFallbackPoller` while the stream is unhealthy — only ever fetches the gap. Safe
 * to race against a live SSE event landing mid-fetch: `applyMissionEvent`'s sequence guard means
 * whichever source applies a given sequence number first wins and the other is a no-op for it.
 *
 * Deliberately does NOT touch `$streamState` or `$lastEventReceivedAt` — a successful REST
 * catch-up means the DATA is fresh, not that the live connection is healthy, and the design's
 * honest degraded-state labelling (§6.1/§8 of the design spec, explicitly praised in D-114) is
 * preserved by keeping those two concerns orthogonal: the operator still sees `[ STREAM ERROR ]`
 * when the stream really is down, just no longer paired with data that stopped updating three
 * seconds into the mission.
 */
export async function hydrateMissionSnapshot(missionId: string, signal?: AbortSignal): Promise<void> {
  const initial = $missionSnapshot.get();
  let cursor = initial.missionId === missionId && initial.latestSequence != null ? initial.latestSequence : 0;

  for (;;) {
    const page = await replayMissionEvents(missionId, { sinceSequence: cursor, limit: REPLAY_PAGE_LIMIT }, signal);
    if (page.items.length === 0) {
      return;
    }
    for (const event of page.items) {
      applyMissionEvent(event);
      cursor = event.sequence;
    }
    if (page.items.length < REPLAY_PAGE_LIMIT) {
      return;
    }
  }
}

/**
 * Defense in depth for D-114 BUG-2's transport-layer half: a real, reproduced HTTP/2 framing
 * error (`net::ERR_HTTP2_PROTOCOL_ERROR` client-side, `CURLE_HTTP2_STREAM` independently via
 * `curl --http2`) that can leave the SSE connection cycling failed reconnects indefinitely — see
 * the D-115 decision record for the transport-layer investigation and why this ships regardless
 * of whether that root cause is separately fixed. While `$streamState` is anything other than a
 * healthy live connection, this keeps `$missionSnapshot` catching up to real server state by
 * polling the same replay endpoint `hydrateMissionSnapshot` uses on a fixed interval — turning
 * "the stream is broken and nothing ever recovers it, reload included" into "the stream is
 * honestly labelled degraded, and the data underneath that label keeps getting fresher." Stops
 * being consulted the moment a real SSE event lands and flips `$streamState` off `'error'`/
 * `'stale'` — this is a fallback path, not a replacement for the live stream, matching the same
 * "only ever degrades/recovers the display, never fakes progress" rule `startStaleWatcher`
 * already follows.
 */
export function startRestFallbackPoller(missionId: string, intervalMs = 5000): () => void {
  const interval = window.setInterval(() => {
    const state = $streamState.get();
    if (state !== 'error' && state !== 'stale') {
      return;
    }
    hydrateMissionSnapshot(missionId).catch(() => {
      // A failed poll just means the next tick tries again; `$streamState` already carries the
      // honest degraded label, so a failed catch-up attempt never claims data is fresher than
      // it actually is.
    });
  }, intervalMs);
  return () => window.clearInterval(interval);
}

/**
 * The one timer in this product (§8, §12 build note 2). Every `--bd-stale-threshold` (10s,
 * `tokens.css`) it checks whether an event has arrived recently; if the stream has been open for
 * more than that with nothing on it, it flips `$streamState` to `'stale'`, which the Core, the
 * Stage Timeline and the top strip all read to freeze their live indicators and say so (§6.1).
 * It never sets anything to a value implying progress — only ever the stale/degraded direction,
 * and `ingestMissionEvent` above is what clears it again on the next real event.
 */
export function startStaleWatcher(thresholdMs = 10000): () => void {
  const interval = window.setInterval(() => {
    const state = $streamState.get();
    if (state !== 'open' && state !== 'stale') {
      return;
    }
    const lastReceived = $lastEventReceivedAt.get();
    if (lastReceived == null) {
      return;
    }
    const idleFor = Date.now() - lastReceived;
    if (idleFor > thresholdMs && state === 'open') {
      $streamState.set('stale');
    }
  }, 2000);
  return () => window.clearInterval(interval);
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

  if (event.type === 'STAGE_STARTED' && event.stage) {
    next.stageStartedAt = { ...snapshot.stageStartedAt, [event.stage]: event.timestamp };
  }

  if (event.type === 'STAGE_COMPLETED' && event.stage) {
    next.stageCompletedAt = { ...snapshot.stageCompletedAt, [event.stage]: event.timestamp };
  }

  if (event.stage && event.message) {
    next.stageMessage = { ...snapshot.stageMessage, [event.stage]: next.latestMessage };

    const existing = snapshot.stageEvents[event.stage] ?? [];
    const appended = [...existing, { sequence: event.sequence, timestamp: event.timestamp, message: next.latestMessage }];
    const overflowBefore = snapshot.stageEventOverflow[event.stage] ?? 0;
    if (appended.length > EVENT_WINDOW) {
      next.stageEvents = { ...snapshot.stageEvents, [event.stage]: appended.slice(appended.length - EVENT_WINDOW) };
      next.stageEventOverflow = { ...snapshot.stageEventOverflow, [event.stage]: overflowBefore + (appended.length - EVENT_WINDOW) };
    } else {
      next.stageEvents = { ...snapshot.stageEvents, [event.stage]: appended };
    }
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
