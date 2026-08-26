/**
 * Pure state derivation for the bisect half of the Git History / Bisect Timeline panel
 * (#26). No network call, no store subscription — a plain fold over event envelopes into
 * something the panel can render, exercised directly by
 * `scripts/check-git-history-bisect-panel.mjs` under `node --experimental-strip-types`.
 *
 * WHY THIS TAKES `unknown[]`, NOT `MissionEventEnvelope[]` (READ BEFORE "FIXING"):
 *
 * `apps/control-api/contracts/schemas/envelope.py` defines `MissionEvent.payload` as a
 * discriminated union on `kind` with fifteen variants today (§ D1 frozen contract,
 * `docs/03-technical/21-api-specification.md`). Neither `"bisect"` nor `"bisect_step"` is
 * one of them. `git bisect` itself is real and merged (#24,
 * `workers/git_analysis/bisect_run.py::emit_bisect_events`, 42 passing tests) but is a
 * standalone, callable driver with no orchestrator wiring: nothing in this codebase calls
 * `orchestrator.events.emit()` with the envelopes that function builds, and even if
 * something did, django-ninja/Pydantic would reject the row before it reached
 * `GET .../events` or `.../events/replay` — an unrecognised `payload.kind` fails schema
 * validation and D-116's malformed-row resilience logs and skips it, silently, by design.
 * `.project/decisions.md` D-151 (search "TRIAGE/ANALYZE composition after #22/#23/#24")
 * is the software-architect ruling this module is built against: bisect is a separate,
 * operator-triggered capability, not automatic for any mission, and wiring a real
 * `JobKind.BISECT` dispatch executor plus the two missing payload schema variants is
 * named there as explicit future work, not done in this pass.
 *
 * So: as of this file, nothing in the running product can ever produce a value this
 * module's exported type union would recognise. That is not a reason to leave the render
 * logic unbuilt — it is exactly why this module is written against the *real* wire shape
 * `emit_bisect_events` already produces (checked directly against that file, not guessed),
 * with `unknown[]` input and defensive parsing, rather than against the typed, generated
 * `MissionEventEnvelope` union `openapi-typescript` renders from the frozen contract. Doing
 * the latter would either (a) require inventing a contract addition that is the
 * backend/architect's call, not mine, or (b) not typecheck at all, since TypeScript flags a
 * literal comparison against a union member that does not exist. The day a real
 * `BisectPayload`/`BisectStepPayload` lands in `envelope.py` and gets threaded through
 * `reduceMissionSnapshot` (`lib/events/store.ts`), wiring real envelopes into this function
 * is a one-line change at the call site — the render logic and its tests already exist.
 */

export type BisectVerdict = 'GOOD' | 'BAD' | 'SKIP';

export interface BisectStepView {
  sha: string;
  verdict: BisectVerdict;
  subject: string;
}

export type BisectTimelineStatus = 'idle' | 'running' | 'converged' | 'not_converged';

export interface BisectTimelineState {
  status: BisectTimelineStatus;
  goodCommit: string | null;
  badCommit: string | null;
  steps: BisectStepView[];
  culpritCommit: string | null;
  culpritSubject: string | null;
  errorDetail: string | null;
}

export const IDLE_BISECT_TIMELINE: BisectTimelineState = {
  status: 'idle',
  goodCommit: null,
  badCommit: null,
  steps: [],
  culpritCommit: null,
  culpritSubject: null,
  errorDetail: null,
};

const SHA_PATTERN = /^[0-9a-f]{7,40}$/i;
const VERDICTS: readonly BisectVerdict[] = ['GOOD', 'BAD', 'SKIP'];

/**
 * Folds a real (or, today, always empty) list of bisect-shaped event envelopes into
 * render state. Envelopes that do not match `emit_bisect_events`'s real shape are
 * skipped rather than thrown — this parses a wire format nothing in production emits
 * yet, so tolerance of the unexpected is the correct default, not a contract this
 * module can enforce on a caller.
 */
export function deriveBisectTimelineState(envelopes: readonly unknown[]): BisectTimelineState {
  if (envelopes.length === 0) {
    return IDLE_BISECT_TIMELINE;
  }

  let state: BisectTimelineState = { ...IDLE_BISECT_TIMELINE, status: 'running' };

  for (const raw of envelopes) {
    const envelope = asRecord(raw);
    const payload = envelope ? asRecord(envelope.payload) : null;
    if (!payload || payload.kind === undefined) {
      continue;
    }

    if (payload.kind === 'bisect' && isStartShape(payload)) {
      state = {
        ...state,
        status: 'running',
        goodCommit: String(payload.good_commit),
        badCommit: String(payload.bad_commit),
      };
      continue;
    }

    if (payload.kind === 'bisect_step' && isStepShape(payload)) {
      state = {
        ...state,
        steps: [
          ...state.steps,
          {
            sha: String(payload.sha),
            verdict: payload.verdict as BisectVerdict,
            subject: typeof payload.subject === 'string' ? payload.subject : '',
          },
        ],
      };
      continue;
    }

    if (payload.kind === 'bisect' && isReportShape(payload)) {
      const report = payload.report;
      const succeeded = report.succeeded === true;
      state = {
        ...state,
        status: succeeded ? 'converged' : 'not_converged',
        culpritCommit: succeeded && typeof report.culprit_commit === 'string' ? report.culprit_commit : null,
        culpritSubject: succeeded && typeof report.culprit_subject === 'string' ? report.culprit_subject : null,
        errorDetail: succeeded ? null : describeError(report.error),
      };
    }
  }

  return state;
}

function describeError(error: unknown): string {
  return typeof error === 'string' && error.length > 0 ? error : 'bisect did not converge';
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : null;
}

function isStartShape(payload: Record<string, unknown>): payload is Record<string, unknown> & { good_commit: string; bad_commit: string } {
  return (
    typeof payload.good_commit === 'string' &&
    SHA_PATTERN.test(payload.good_commit) &&
    typeof payload.bad_commit === 'string' &&
    SHA_PATTERN.test(payload.bad_commit)
  );
}

function isStepShape(payload: Record<string, unknown>): payload is Record<string, unknown> & { sha: string; verdict: BisectVerdict } {
  return (
    typeof payload.sha === 'string' &&
    SHA_PATTERN.test(payload.sha) &&
    typeof payload.verdict === 'string' &&
    (VERDICTS as readonly string[]).includes(payload.verdict)
  );
}

interface RawBisectReport {
  succeeded: unknown;
  culprit_commit: unknown;
  culprit_subject: unknown;
  error: unknown;
}

function isReportShape(payload: Record<string, unknown>): payload is Record<string, unknown> & { report: RawBisectReport } {
  const report = asRecord(payload.report);
  return report !== null && 'succeeded' in report;
}

/** 12-char short SHA, matching the convention `StageTimeline`/`FindingsRail` already use
 * for `snapshotSha256`/fingerprints — never the full 40-char hash in a compact row. */
export function shortSha(sha: string): string {
  return sha.slice(0, 12);
}
