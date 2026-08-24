/**
 * Control API client — the full mission-lifecycle and evidence surface.
 *
 * Extends the original two-endpoint client (`getSystemHealth`, `getMissionDetail`) to cover
 * the eleven mission-lifecycle endpoints (`POST /missions` through
 * `POST /missions/{id}/cancel`) and the evidence/export surface (`api/routers/evidence.py`),
 * so the Command Center can create, authorize, snapshot, preflight, start, pause and cancel a
 * real mission instead of only ever reading one by a hand-typed `?mission=` id.
 *
 * Every function is typed directly against `./schema.d.ts`, generated from
 * `packages/schemas/openapi.json` (`npm run generate:api`; verified with `npm run check:api`).
 * Nothing here hand-declares a request or response shape — a contract change fails the
 * generated-types check before it fails silently at runtime.
 *
 * Auth: nginx injects the operator bearer token on every `/api/` request (D-088, T0 —
 * `infrastructure/compose/nginx/templates.dev(or finale)/brahmadatta.conf.template`). The
 * browser never attaches an `Authorization` header itself; every call below is a same-origin,
 * credential-free fetch by design, not an oversight.
 */

import type { operations, components } from './schema';

export type SystemHealth = operations['getSystemHealth']['responses'][200]['content']['application/json'];
export type MissionDetail = operations['getMission']['responses'][200]['content']['application/json'];
export type MissionSummary = components['schemas']['MissionSummary'];
export type MissionCreateRequest = components['schemas']['MissionCreateRequest'];
export type MissionPolicy = components['schemas']['MissionPolicy'];
export type LanguageAdapter = components['schemas']['LanguageAdapter'];
export type AuthorizationRequest = components['schemas']['AuthorizationRequest'];
export type AuthorizationRecord = components['schemas']['AuthorizationRecord'];
export type SnapshotRequest = components['schemas']['SnapshotRequest'];
export type SnapshotRecord = components['schemas']['SnapshotRecord'];
export type PreflightReport = components['schemas']['PreflightReport'];
export type StartRequest = components['schemas']['StartRequest'];
export type PauseRequest = components['schemas']['PauseRequest'];
export type CancelRequest = components['schemas']['CancelRequest'];
export type Acknowledgement = components['schemas']['Acknowledgement'];
export type FindingSummary = components['schemas']['FindingSummary'];
export type FindingDetail = components['schemas']['FindingDetail'];
export type BaselineReport = components['schemas']['BaselineReport'];
export type FuzzingReport = components['schemas']['FuzzingReport'];
export type PatchCandidate = components['schemas']['PatchCandidate'];
export type OperatorPatchCandidateRequest = components['schemas']['OperatorPatchCandidateRequest'];
export type VerificationRecord = components['schemas']['VerificationRecord'];
export type EvidenceBundle = components['schemas']['EvidenceBundle'];
export type ExportRequest = components['schemas']['ExportRequest'];
export type ExportReceipt = components['schemas']['ExportReceipt'];
export type MissionEventEnvelope = components['schemas']['MissionEvent'];
export type Page<T> = { items: T[]; total: number; limit: number; offset: number };

export interface ModelGatewayStatus {
  backend: 'ollama';
  status: 'ready' | 'missing-model' | 'unreachable';
  endpoint: string;
  model: string;
  modelPresent: boolean;
  models?: string[];
  latencyMs: number;
  message: string;
}

/**
 * One error shape for every failure this client can raise: a real HTTP failure from the
 * Control API's `ErrorEnvelope` (carrying `code`/`details`/`traceId` for the UI to surface),
 * or a transport failure (network unreachable, non-JSON body) reported as `code: 'TRANSPORT'`.
 * Callers branch on `.code` and `.details` rather than parsing `.message` — the error string
 * itself is UI-facing copy, not a machine-readable contract.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly traceId: string | null;

  constructor(
    status: number,
    message: string,
    options: { code?: string; details?: Record<string, unknown>; traceId?: string } = {},
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = options.code ?? 'UNKNOWN';
    this.details = options.details ?? {};
    this.traceId = options.traceId ?? null;
  }
}

interface ErrorEnvelopeBody {
  error?: { code?: string; message?: string; details?: Record<string, unknown> };
  trace_id?: string;
}

/** Adds `signal` to an init object only when one was supplied — never assigns `undefined` to a
 * DOM type field, which `exactOptionalPropertyTypes` (tsconfig) treats as a distinct error from
 * omitting the key entirely. */
function withSignal(init: RequestInit, signal?: AbortSignal): RequestInit {
  return signal ? { ...init, signal } : init;
}

/**
 * Shared by `request` (the ordinary typed-JSON path) and `requestWithProvenance` below (#52 —
 * the one caller that also needs the raw `Response` to read a header off it). One fetch/error
 * implementation either way; nothing about the ordinary request path changes.
 */
async function requestWithResponse<T>(path: string, init: RequestInit = {}): Promise<{ data: T; response: Response }> {
  let response: Response;
  try {
    response = await fetch(path, {
      headers: {
        Accept: 'application/json',
        ...(init.body ? { 'content-type': 'application/json' } : {}),
        ...(init.headers ?? {}),
      },
      ...init,
    });
  } catch (cause) {
    throw new ApiError(0, 'Control API is unreachable from this browser.', {
      code: 'TRANSPORT',
      details: { path, cause: cause instanceof Error ? cause.message : String(cause) },
    });
  }

  if (!response.ok) {
    let body: ErrorEnvelopeBody | null = null;
    try {
      body = (await response.json()) as ErrorEnvelopeBody;
    } catch {
      // Non-JSON error body (e.g. an nginx-generated error page) — fall through with body=null.
    }
    throw new ApiError(response.status, body?.error?.message ?? `Control API returned HTTP ${response.status}.`, {
      code: body?.error?.code ?? 'HTTP_ERROR',
      ...(body?.error?.details ? { details: body.error.details } : {}),
      ...(body?.trace_id ? { traceId: body.trace_id } : {}),
    });
  }

  if (response.status === 202 || response.status === 204) {
    // Acknowledgement-shaped responses always carry a body in this API (202 = Acknowledgement),
    // but guard the truly-empty 204 case rather than assume every non-200 has JSON to parse.
    const text = await response.text();
    return { data: (text ? JSON.parse(text) : (undefined as T)) as T, response };
  }

  return { data: (await response.json()) as T, response };
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  return (await requestWithResponse<T>(path, init)).data;
}

function jsonBody(payload: unknown): RequestInit {
  return { body: JSON.stringify(payload) };
}

function queryString(params: Record<string, number | string | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value != null) query.set(key, String(value));
  }
  const serialized = query.toString();
  return serialized ? `?${serialized}` : '';
}

// ---------------------------------------------------------------------------
// System
// ---------------------------------------------------------------------------

export async function getSystemHealth(signal?: AbortSignal): Promise<SystemHealth> {
  return request<SystemHealth>('/api/v1/system/health', withSignal({}, signal));
}

export async function getModelGatewayStatus(signal?: AbortSignal): Promise<ModelGatewayStatus> {
  return request<ModelGatewayStatus>('/__local/model-gateway-status', withSignal({}, signal));
}

// ---------------------------------------------------------------------------
// Mission lifecycle — POST /missions through POST /missions/{id}/cancel
// ---------------------------------------------------------------------------

export async function listMissions(
  params: { limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<Page<MissionSummary>> {
  const suffix = queryString({ limit: params.limit, offset: params.offset });
  return request<Page<MissionSummary>>(`/api/v1/missions${suffix}`, withSignal({}, signal));
}

export async function createMission(payload: MissionCreateRequest, signal?: AbortSignal): Promise<MissionSummary> {
  return request<MissionSummary>(
    '/api/v1/missions',
    withSignal({ method: 'POST', ...jsonBody(payload) }, signal),
  );
}

export async function getMissionDetail(missionId: string, signal?: AbortSignal): Promise<MissionDetail> {
  return request<MissionDetail>(`/api/v1/missions/${encodeURIComponent(missionId)}`, withSignal({}, signal));
}

/**
 * #52 / D-058 §2.4 — the header `packages/test-fixtures/sse_replay.py` sets on literally every
 * response it serves (`ReplayHandler._json`, and the SSE stream's own headers). A native
 * `EventSource` never exposes response headers to JS, so the SSE stream itself cannot be the
 * thing presentation mode reads this off of — this mission-detail fetch is a same-origin,
 * same-backend request (the dev proxy/nginx location that fronts `/api/v1/missions/*` fronts
 * both), so its header is exactly as trustworthy a signal as the stream's own header would be,
 * without requiring a hand-rolled fetch-based SSE reader duplicating `connectMissionEvents`.
 * Documented as a deliberate, disclosed implementation choice — flagged to `ui-ux-designer` in
 * the PR, since D-058's text says "the SSE connection's response" specifically.
 */
export const FIXTURE_REPLAY_HEADER = 'X-Brahmadatta-Fixture';
export const FIXTURE_REPLAY_HEADER_VALUE = 'replay';

export interface MissionProvenance {
  mission: MissionDetail;
  fixtureHeaderValue: string | null;
}

/**
 * Presentation-mode-only (`PresentationMissionCommandCenter`'s provenance check, #52). Never
 * called from `MissionCommandCenter`/the live path — this is additive, not a replacement for
 * `getMissionDetail`, so the ordinary live-mission flow is byte-for-byte unchanged.
 */
export async function getMissionDetailWithProvenance(missionId: string, signal?: AbortSignal): Promise<MissionProvenance> {
  const { data, response } = await requestWithResponse<MissionDetail>(
    `/api/v1/missions/${encodeURIComponent(missionId)}`,
    withSignal({}, signal),
  );
  return { mission: data, fixtureHeaderValue: response.headers.get(FIXTURE_REPLAY_HEADER) };
}

/**
 * `GET /missions/{id}/events/replay` — D-114 BUG-2's fix. Built server-side as "gap recovery
 * for the SSE stream" (`api/routers/missions.py::replay_events`): reads the exact same
 * persisted `MissionEvent` log the live stream tails, through the same schema conversion, so a
 * client replaying from `sinceSequence` reconstructs identical state to one that received every
 * event live. `src/lib/events/store.ts`'s `hydrateMissionSnapshot` is the only caller — see that
 * function's own doc comment for why this exists (the SSE stream had zero REST-based recovery
 * path before this).
 */
export async function replayMissionEvents(
  missionId: string,
  params: { sinceSequence?: number; limit?: number } = {},
  signal?: AbortSignal,
): Promise<Page<MissionEventEnvelope>> {
  const suffix = queryString({ since_sequence: params.sinceSequence, limit: params.limit });
  return request<Page<MissionEventEnvelope>>(
    `/api/v1/missions/${encodeURIComponent(missionId)}/events/replay${suffix}`,
    withSignal({}, signal),
  );
}

export async function authorizeMission(
  missionId: string,
  payload: AuthorizationRequest,
  signal?: AbortSignal,
): Promise<AuthorizationRecord> {
  return request<AuthorizationRecord>(
    `/api/v1/missions/${encodeURIComponent(missionId)}/authorize`,
    withSignal({ method: 'POST', ...jsonBody(payload) }, signal),
  );
}

/**
 * Single-attempt snapshot ingest. Use this directly only when the caller already knows the
 * server-computed `archive_sha256` (the `upload` path, once an archive has been staged — see
 * `snapshotLocalRepository` below for `source: 'git'`, where the digest cannot be known in
 * advance). Throws `ApiError` (HTTP 409) with the real digest in
 * `.details.computed_archive_sha256` on a mismatch, exactly as `authorization/service.py`
 * documents.
 */
export async function createMissionSnapshot(
  missionId: string,
  payload: SnapshotRequest,
  signal?: AbortSignal,
): Promise<SnapshotRecord> {
  return request<SnapshotRecord>(
    `/api/v1/missions/${encodeURIComponent(missionId)}/snapshot`,
    withSignal({ method: 'POST', ...jsonBody(payload) }, signal),
  );
}

/**
 * `source: 'git'` snapshot of a repository already present on the Control API host under
 * `SNAPSHOT_SOURCE_ROOT` (`demo/repositories/pktcfg` in the dev/finale stack) — the local-repo
 * path this Command Center actually drives.
 *
 * CONTRACT GAP, recorded here rather than worked around silently (frontend-developer's D-098,
 * `.project/decisions.md`): `SnapshotRequest.archive_sha256` is required and is checked
 * server-side against a digest the server computes from a deterministic tar it builds itself
 * (`authorization/service.py::_materialize_source` calling `archive.build_tar_from_directory`).
 * A browser has no way to reproduce that exact tar byte-for-byte, so it cannot know the correct
 * digest before the first call — there is no "compute digest" endpoint. This function uses the
 * two-step pattern the API's own error contract already supports, without needing a new
 * endpoint: POST once with a syntactically-valid placeholder digest, read the real digest back
 * out of the guaranteed `SnapshotDigestMismatchError.details.computed_archive_sha256`
 * (`ContractError` details are always returned to the caller, `api/errors.py::envelope`), then
 * retry once with the corrected value. A mission's snapshot is created at most once
 * (`create_mission_snapshot` is idempotent on a matching digest and refuses a second, different
 * one), so this never double-ingests. If the backend adds a real digest-preview endpoint, this
 * probe should be replaced with a single call — flagged to backend-developer as the cleaner fix.
 */
export async function snapshotLocalRepository(
  missionId: string,
  options: { commitSha?: string | null; idempotencyKey?: string | null } = {},
  signal?: AbortSignal,
): Promise<SnapshotRecord> {
  const placeholderDigest = '0'.repeat(64);
  const basePayload: SnapshotRequest = {
    source: 'git',
    archive_sha256: placeholderDigest,
    commit_sha: options.commitSha ?? null,
    idempotency_key: options.idempotencyKey ?? null,
  };

  try {
    return await createMissionSnapshot(missionId, basePayload, signal);
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 409) {
      throw error;
    }
    const computed = error.details['computed_archive_sha256'];
    if (typeof computed !== 'string' || !/^[0-9a-f]{64}$/.test(computed)) {
      // Not the digest-mismatch shape (e.g. SnapshotAlreadyRecordedError on a real replay) —
      // surface the original error rather than guessing.
      throw error;
    }
    return createMissionSnapshot(missionId, { ...basePayload, archive_sha256: computed }, signal);
  }
}

export async function preflightMission(missionId: string, signal?: AbortSignal): Promise<PreflightReport> {
  return request<PreflightReport>(
    `/api/v1/missions/${encodeURIComponent(missionId)}/preflight`,
    withSignal({ method: 'POST' }, signal),
  );
}

export async function startMission(
  missionId: string,
  payload: StartRequest = { confirm_authorized: true },
  signal?: AbortSignal,
): Promise<Acknowledgement> {
  return request<Acknowledgement>(
    `/api/v1/missions/${encodeURIComponent(missionId)}/start`,
    withSignal({ method: 'POST', ...jsonBody(payload) }, signal),
  );
}

export async function pauseMission(
  missionId: string,
  payload: PauseRequest = { reason: '' },
  signal?: AbortSignal,
): Promise<Acknowledgement> {
  return request<Acknowledgement>(
    `/api/v1/missions/${encodeURIComponent(missionId)}/pause`,
    withSignal({ method: 'POST', ...jsonBody(payload) }, signal),
  );
}

export async function cancelMission(
  missionId: string,
  payload: CancelRequest,
  signal?: AbortSignal,
): Promise<Acknowledgement> {
  return request<Acknowledgement>(
    `/api/v1/missions/${encodeURIComponent(missionId)}/cancel`,
    withSignal({ method: 'POST', ...jsonBody(payload) }, signal),
  );
}

// ---------------------------------------------------------------------------
// Evidence surface — api/routers/evidence.py
// ---------------------------------------------------------------------------

export async function listFindings(
  missionId: string,
  params: { limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<Page<FindingSummary>> {
  const suffix = queryString({ limit: params.limit, offset: params.offset });
  return request<Page<FindingSummary>>(
    `/api/v1/missions/${encodeURIComponent(missionId)}/findings${suffix}`,
    withSignal({}, signal),
  );
}

export async function getFinding(missionId: string, findingId: string, signal?: AbortSignal): Promise<FindingDetail> {
  return request<FindingDetail>(
    `/api/v1/missions/${encodeURIComponent(missionId)}/findings/${encodeURIComponent(findingId)}`,
    withSignal({}, signal),
  );
}

export async function getBaselineReport(missionId: string, signal?: AbortSignal): Promise<BaselineReport> {
  return request<BaselineReport>(
    `/api/v1/missions/${encodeURIComponent(missionId)}/baseline`,
    withSignal({}, signal),
  );
}

export async function getFuzzingReport(missionId: string, signal?: AbortSignal): Promise<FuzzingReport> {
  return request<FuzzingReport>(`/api/v1/missions/${encodeURIComponent(missionId)}/fuzzing`, withSignal({}, signal));
}

export async function listPatchCandidates(
  missionId: string,
  params: { limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<Page<PatchCandidate>> {
  const suffix = queryString({ limit: params.limit, offset: params.offset });
  return request<Page<PatchCandidate>>(
    `/api/v1/missions/${encodeURIComponent(missionId)}/patches${suffix}`,
    withSignal({}, signal),
  );
}

/**
 * `POST /missions/{id}/patches` — T-3, D-008. Submits an operator-authored unified diff for a
 * finding; the server always sets `provenance=OPERATOR_SUPPLIED` and runs it through the same
 * deterministic policy gate and verification pipeline a model-generated candidate uses.
 */
export async function submitOperatorPatchCandidate(
  missionId: string,
  payload: OperatorPatchCandidateRequest,
  signal?: AbortSignal,
): Promise<PatchCandidate> {
  return request<PatchCandidate>(
    `/api/v1/missions/${encodeURIComponent(missionId)}/patches`,
    withSignal({ method: 'POST', ...jsonBody(payload) }, signal),
  );
}

export async function getPatchVerification(
  missionId: string,
  patchId: string,
  signal?: AbortSignal,
): Promise<VerificationRecord> {
  return request<VerificationRecord>(
    `/api/v1/missions/${encodeURIComponent(missionId)}/patches/${encodeURIComponent(patchId)}/verification`,
    withSignal({}, signal),
  );
}

export async function getEvidenceBundle(missionId: string, signal?: AbortSignal): Promise<EvidenceBundle> {
  return request<EvidenceBundle>(`/api/v1/missions/${encodeURIComponent(missionId)}/evidence`, withSignal({}, signal));
}

export async function exportEvidence(
  missionId: string,
  payload: ExportRequest = { formats: ['markdown', 'json'], include_artifacts: false },
  signal?: AbortSignal,
): Promise<ExportReceipt> {
  return request<ExportReceipt>(
    `/api/v1/missions/${encodeURIComponent(missionId)}/export`,
    withSignal({ method: 'POST', ...jsonBody(payload) }, signal),
  );
}
