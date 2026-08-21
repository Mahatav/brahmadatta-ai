import { useState } from 'react';

import { STAGE_ROWS, formatElapsed, formatDurationSeconds } from '../lib/design/phases';
import type { MissionSnapshot, MissionStage } from '../lib/events/store';
import { sanitizeDisplayText } from '../lib/security/renderSafety.mjs';

/**
 * Panel 2 — the Stage Timeline (docs/09-company/04-design-system.md §6.2). Left rail, ten fixed
 * rows AUTHORIZE→TEARDOWN, always all present regardless of what the backend happens to have
 * emitted yet. Row 10 (TEARDOWN) has no `MissionStage` of its own (§7.2) — it is derived from
 * `releasedResources`, the same `TEARDOWN_CONFIRMED` event set the resource ledger and the
 * Core's release line read (DS-04, "one teardown count, three renderings").
 */

type RowState = 'queued' | 'running' | 'ok' | 'fail' | 'not_reached' | 'warn';

const GLYPH: Record<RowState, string> = {
  queued: '·',
  running: '>',
  ok: '+',
  fail: '×',
  not_reached: '·',
  warn: '!',
};

export function StageTimeline({ snapshot, hasActiveMission }: { snapshot: MissionSnapshot; hasActiveMission: boolean }) {
  const [expanded, setExpanded] = useState<Set<MissionStage>>(() => new Set());

  if (!hasActiveMission) {
    return (
      <section className="bd-panel bd-crop bd-timeline" aria-labelledby="bd-timeline-title">
        <h2 id="bd-timeline-title" className="bd-panel__title">[ STAGE TIMELINE ]</h2>
        <p className="bd-panel__empty">
          <span className="bd-panel__empty-label">[ NO MISSION ]</span>
          Start a mission to populate the timeline.
        </p>
      </section>
    );
  }

  const failingIndex = snapshot.state === 'FAILED'
    ? STAGE_ROWS.findIndex((row) => row.stage === snapshot.stage)
    : -1;

  return (
    <section className="bd-panel bd-crop bd-timeline" aria-labelledby="bd-timeline-title">
      <h2 id="bd-timeline-title" className="bd-panel__title">[ STAGE TIMELINE ]</h2>
      <ol className="bd-timeline__list">
        {STAGE_ROWS.map((row, index) => {
          if (row.stage === 'TEARDOWN') {
            return <TeardownRow key="TEARDOWN" snapshot={snapshot} />;
          }
          const stage = row.stage as MissionStage;
          const rowState = deriveRowState(stage, snapshot, index, failingIndex);
          const detail = rowDetail(stage, rowState, snapshot);
          const elapsed = formatElapsed(snapshot.stageStartedAt[stage] ?? null, snapshot.stageCompletedAt[stage] ?? null);
          const events = snapshot.stageEvents[stage] ?? [];
          const overflow = snapshot.stageEventOverflow[stage] ?? 0;
          const isExpanded = expanded.has(stage);

          return (
            <li key={stage} className={`bd-timeline__row bd-timeline__row--${rowState}`}>
              <button
                type="button"
                className="bd-timeline__row-toggle"
                onClick={() => toggle(stage, expanded, setExpanded)}
                aria-expanded={isExpanded}
                disabled={events.length === 0}
              >
                <span className="bd-timeline__index">[ {String(row.index).padStart(2, '0')} ]</span>
                <span className="bd-timeline__body">
                  <span className={`bd-timeline__label${rowState === 'running' ? ' bd-timeline__label--running' : ''}`}>
                    {row.label}
                  </span>
                  <span className="bd-timeline__chip">
                    [ {GLYPH[rowState]} {stateWord(rowState)} ]
                  </span>
                  <small className="bd-timeline__detail">
                    {sanitizeDisplayText(detail, { maxLength: 160, fallback: '—' })} · {elapsed}
                  </small>
                </span>
              </button>
              {isExpanded && events.length > 0 && (
                <ul className="bd-timeline__events" aria-label={`${row.label} event log`}>
                  {overflow > 0 && (
                    <li className="bd-timeline__event bd-timeline__event--overflow">[ … {overflow} EARLIER EVENTS ]</li>
                  )}
                  {events.map((event) => (
                    <li key={event.sequence} className="bd-timeline__event">
                      {formatDurationSeconds((Date.parse(event.timestamp) - Date.parse(snapshot.firstTimestamp ?? event.timestamp)) / 1000)}
                      {'  '}
                      {sanitizeDisplayText(event.message, { maxLength: 200, fallback: '' })}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ol>
      <p className="bd-timeline__pin" aria-hidden="true">↕ autoscroll pinned to newest</p>
    </section>
  );
}

function toggle(stage: MissionStage, expanded: Set<MissionStage>, setExpanded: (next: Set<MissionStage>) => void): void {
  const next = new Set(expanded);
  if (next.has(stage)) {
    next.delete(stage);
  } else {
    next.add(stage);
  }
  setExpanded(next);
}

function deriveRowState(stage: MissionStage, snapshot: MissionSnapshot, index: number, failingIndex: number): RowState {
  if (failingIndex >= 0 && index > failingIndex) {
    return 'not_reached';
  }
  if (failingIndex >= 0 && index === failingIndex) {
    return 'fail';
  }
  if (stage === 'BASELINE' && snapshot.baseline && !snapshot.baseline.passed) {
    return 'fail';
  }
  if (snapshot.completedStages.includes(stage) || (stage === 'VERIFY' && (snapshot.state === 'VERIFIED' || snapshot.state === 'REJECTED'))) {
    return 'ok';
  }
  if (snapshot.stage === stage) {
    return 'running';
  }
  // A `STATE_CHANGED` transition event is tagged with the stage it is entering, not the one it
  // just finished (the orchestrator's own convention — see the message text on e.g. the
  // BASELINE->ANALYZE transition, which reports "BASELINE job ... -> SUCCEEDED" while tagged
  // `stage: ANALYZE`). Only a handful of stages (ANALYZE/TRIAGE today) additionally emit a
  // dedicated `STAGE_COMPLETED` event tagged to themselves, so `completedStages` above is
  // incomplete for the rest. Since the backend only ever advances `snapshot.stage` forward
  // through `STAGE_ROWS` order, any row strictly before the mission's current stage has
  // necessarily already completed — found live 2026-08-21 via a real mission run showing
  // AUTHORIZE/INGEST/BASELINE/STRESS_TEST/CORRELATE stuck at QUEUED despite the mission having
  // reached PATCH.
  const currentIndex = snapshot.stage ? STAGE_ROWS.findIndex((row) => row.stage === snapshot.stage) : -1;
  if (currentIndex >= 0 && index < currentIndex) {
    return 'ok';
  }
  return 'queued';
}

function stateWord(state: RowState): string {
  switch (state) {
    case 'queued': return 'QUEUED';
    case 'running': return 'RUNNING';
    case 'ok': return stateWordOk;
    case 'fail': return 'FAIL';
    case 'not_reached': return 'NOT REACHED';
    case 'warn': return 'WARN';
    default: return 'QUEUED';
  }
}
const stateWordOk = 'OK';

function rowDetail(stage: MissionStage, state: RowState, snapshot: MissionSnapshot): string {
  if (state === 'not_reached') {
    return 'stage not reached';
  }
  if (stage === 'AUTHORIZE') {
    if (snapshot.snapshotSha256) {
      return `snapshot ${snapshot.snapshotSha256.slice(0, 12)}…`;
    }
    return snapshot.stageMessage.AUTHORIZE ?? (state === 'queued' ? 'awaiting authorization' : 'authorizing');
  }
  if (stage === 'BASELINE' && snapshot.baseline) {
    const b = snapshot.baseline;
    return `ctest ${b.tests_passed}/${b.tests_total} passed`;
  }
  if (stage === 'ANALYZE') {
    // The backend's own LOG string, rendered verbatim (§6.2, C8) — never composed here.
    return snapshot.stageMessage.ANALYZE ?? (state === 'ok' ? 'no static analyzer configured in this build' : 'awaiting analyze stage');
  }
  if (stage === 'STRESS_TEST' && snapshot.fuzzing) {
    const f = snapshot.fuzzing;
    return `${f.engine} · ${formatCount(f.executions)} execs · ${f.unique_crashes} unique crashes`;
  }
  if (stage === 'PATCH') {
    if (snapshot.patchCandidates.length > 0) {
      const passing = snapshot.patchCandidates.filter((patch) => patch.policy_status === 'ACCEPTED').length;
      return `${snapshot.patchCandidates.length} candidate${snapshot.patchCandidates.length === 1 ? '' : 's'} · ${passing} policy-passing`;
    }
    return snapshot.stageMessage.PATCH ?? (state === 'queued' ? 'awaiting patch generation' : 'generating candidates');
  }
  if (stage === 'VERIFY') {
    if (snapshot.verdictSummary) {
      const total = snapshot.verifications.length;
      return `${snapshot.verdictSummary.mission_verdict} · ${total} candidate${total === 1 ? '' : 's'} verified`;
    }
    return snapshot.stageMessage.VERIFY ?? (state === 'queued' ? 'awaiting verification' : 'running verification gates');
  }
  if (stage === 'EXPORT_EVIDENCE') {
    return snapshot.stageMessage.EXPORT_EVIDENCE ?? (state === 'ok' ? 'evidence exported' : state === 'queued' ? 'awaiting export' : 'exporting evidence');
  }
  return snapshot.stageMessage[stage] ?? (state === 'queued' ? 'waiting' : state === 'running' ? 'in progress' : 'complete');
}

function TeardownRow({ snapshot }: { snapshot: MissionSnapshot }) {
  const resources = snapshot.releasedResources;
  const releasedCount = resources.filter((resource) => resource.released).length;
  const state: RowState = resources.length === 0
    ? 'queued'
    : releasedCount === resources.length
      ? 'ok'
      : resources.some((resource) => !resource.released)
        ? 'warn'
        : 'running';

  // §6.2: teardown auto-expands its event rows on terminal states — the one exception to
  // "event rows render only when a stage is expanded" — because the release receipt is a scored
  // deliverable and must not be behind a click during the demo.
  return (
    <li className={`bd-timeline__row bd-timeline__row--${state}`}>
      <div className="bd-timeline__row-toggle bd-timeline__row-toggle--static">
        <span className="bd-timeline__index">[ 10 ]</span>
        <span className="bd-timeline__body">
          <span className="bd-timeline__label">TEARDOWN</span>
          <span className="bd-timeline__chip">[ {GLYPH[state]} {stateWord(state)} ]</span>
          <small className="bd-timeline__detail">
            {resources.length === 0 ? 'no resources leased yet' : `${releasedCount} of ${resources.length} resources released`}
          </small>
        </span>
      </div>
      {resources.length > 0 && (
        <ul className="bd-timeline__events" aria-label="Teardown receipts">
          {resources.map((resource) => (
            <li key={resource.id} className="bd-timeline__event">
              {resource.released ? '[ + ' : '[ ● '}
              {sanitizeDisplayText(resource.kind, { maxLength: 40 })} released
              {resource.released ? ' ]' : ' PENDING ]'}
              {' · '}
              {sanitizeDisplayText(resource.id, { maxLength: 80 })}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

function formatCount(value: number): string {
  return new Intl.NumberFormat('en-US').format(value);
}
