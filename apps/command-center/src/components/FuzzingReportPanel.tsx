import type { FuzzingReport } from '../lib/events/store';
import { formatDurationSeconds } from '../lib/design/phases';
import { sanitizeDisplayText } from '../lib/security/renderSafety.mjs';

/**
 * The static fuzzing report (#31), reduced from the issue body's live/virtualized telemetry
 * panel by the CTO's technical review (`docs/09-company/05-cto-technical-review.md` §2.1,
 * D-021 §C4) and confirmed by the repo owner's own comment on #31: a live high-frequency feed
 * pushed through the same durable, gap-free mission-event sequence is the direct cause of the
 * event-rate problem C4 flags, is the most expensive UI item left, and no gate depends on it.
 * Replaced by this — four real numbers, rendered once, when the stage is done.
 *
 * Not a sixth panel. §6 of `docs/09-company/04-design-system.md` is explicit: "P0-13 names
 * five and this document still builds five." This is a chip group inside the Stage Timeline's
 * existing STRESS_TEST row, the same "sized in chips, not body height" idiom §6.6 already uses
 * for the resource ledger and §6.3a uses for the findings evidence block, so the frame's
 * 684px-with-zero-slack body height (§3) is untouched.
 *
 * Sourced from data that already exists: `run_fuzzing_stage`/`emit_fuzzing_events`
 * (`workers/fuzzing/run.py`) emit the real `FuzzingReport` on the STRESS_TEST stage's own
 * `STAGE_COMPLETED` (or `MISSION_FAILED`) event, `payload.kind === 'fuzzing'` — the exact same
 * durable, sequenced, one-writer-per-mission channel every other mission event travels on
 * (C3's single-writer rule). `reduceMissionSnapshot` (`lib/events/store.ts`) already folds
 * that into `MissionSnapshot.fuzzing`; this component only renders it. No new event type, no
 * new endpoint, no second live stream connection, no polling — the cut's whole point.
 *
 * `fuzzing` is `null` until that one event lands, so the three states below are mutually
 * exclusive and exhaustive by construction, matching §5's "empty is not loading and loading is
 * not zero" rule: not-yet-run (stage never started), in-progress (stage started, report not in
 * yet — a real STAGE_STARTED exists on `snapshot.stageStartedAt.STRESS_TEST`, honestly labelled
 * with no invented partial numbers), and the terminal report (real numbers, or a disclosed
 * `NOT_RUN` reason when the campaign could not run at all, e.g. the #83 replay fallback path).
 */
export function FuzzingReportPanel({
  fuzzing,
  reached,
  running,
  notRunMessage,
}: {
  fuzzing: FuzzingReport | null;
  reached: boolean;
  running: boolean;
  notRunMessage: string | undefined;
}) {
  if (!fuzzing) {
    if (!reached) {
      return (
        <p className="bd-fuzzing-report bd-fuzzing-report--pending">
          [ · FUZZING REPORT · NOT YET RUN ]
        </p>
      );
    }
    return (
      <p className="bd-fuzzing-report bd-fuzzing-report--pending">
        [ {running ? '>' : '·'} FUZZING REPORT · {running ? 'IN PROGRESS' : 'AWAITING RESULT'} — renders once the stage completes ]
      </p>
    );
  }

  if (fuzzing.mode === 'NOT_RUN') {
    return (
      <p className="bd-fuzzing-report bd-fuzzing-report--critical">
        [ × FUZZING REPORT · NOT RUN ·{' '}
        {sanitizeDisplayText(notRunMessage, { fallback: 'reason not disclosed', maxLength: 200 })} ]
      </p>
    );
  }

  return (
    <p className="bd-fuzzing-report" aria-label="Fuzzing report">
      <span className="bd-chip">[ + EXECS {formatCount(fuzzing.executions)} ]</span>
      <span className="bd-chip">[ + RUNTIME {formatDurationSeconds(fuzzing.runtime_seconds)} ]</span>
      <span className={`bd-chip ${fuzzing.unique_crashes > 0 ? 'bd-chip--warning' : 'bd-chip--verified'}`}>
        [ {fuzzing.unique_crashes > 0 ? '!' : '+'} CRASHES {formatCount(fuzzing.unique_crashes)} ]
      </span>
      <span className="bd-chip">[ + CORPUS {formatCount(fuzzing.corpus_size)} ]</span>
      {fuzzing.mode === 'REPLAYED_CORPUS' && (
        <span className="bd-chip">
          [ REPLAYED ·{' '}
          {sanitizeDisplayText(fuzzing.replay_source, { fallback: 'source unavailable', maxLength: 120 })} ]
        </span>
      )}
    </p>
  );
}

function formatCount(value: number): string {
  return new Intl.NumberFormat('en-US').format(value);
}
