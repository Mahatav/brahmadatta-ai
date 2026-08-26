import {
  deriveBisectTimelineState,
  shortSha,
  type BisectTimelineState,
} from '../lib/gitHistory/bisectTimeline';
import { hasAnalyzeStageBeenReached, summarizeRiskyChanges, type RiskyFileGroup } from '../lib/gitHistory/riskyChangeSummary';
import type { MissionSnapshot } from '../lib/events/store';
import { sanitizeDisplayText } from '../lib/security/renderSafety.mjs';

/**
 * #26 — Lower evidence deck: git history summary + bisect timeline (docs/02-design/
 * 00-ui-design-direction.md, "Lower evidence deck"). Sits below the frozen five-panel
 * `.bd-frame` (docs/09-company/04-design-system.md §3 fixes that layout at exactly five
 * panels with zero slack) rather than inside it — this is supplementary evidence, not a
 * scored P0 panel, and the issue's own body agrees: "Not a gate — nothing blocks on it."
 *
 * Two sub-panels:
 *
 * 1. GIT HISTORY — real data only. `missions/models.py::Snapshot` records exactly one
 *    ingested commit per mission (D-151); there is no multi-commit log or diff endpoint in
 *    the contract (`GET .../git-bisect` is explicitly cut at D1, enforced by a test
 *    asserting its absence from the OpenAPI document). So this renders the one real commit
 *    under test, plus a "risky-change summary" built from `snapshot.findings`'s real
 *    `STATIC_ANALYSIS`-discovered rows (Semgrep + compiler diagnostics) grouped by file —
 *    see `lib/gitHistory/riskyChangeSummary.ts` for why that is the honest reading of
 *    "risky-change summary" against what this system actually tracks. `snapshot.findings`
 *    is #25's accumulator (`lib/events/store.ts`, upserted from every real `FINDING_RECORDED`
 *    event and already reconstructed on load/reconnect by `hydrateMissionSnapshot`) — reused
 *    here rather than this panel adding a second, redundant fetch of the same data through
 *    `GET .../findings` (that endpoint is real too, but #25 already established "no new event
 *    kind or REST call is needed to build the list").
 *
 * 2. BISECT TIMELINE — idle by default, and today idle is not a fallback case, it is the
 *    ONLY reachable case: no `JobKind.BISECT` executor exists, no endpoint triggers one
 *    for a live mission, and no payload schema variant for a bisect event exists in the
 *    frozen contract for a hypothetical one to travel through (see
 *    `lib/gitHistory/bisectTimeline.ts`'s module doc for the full chain, checked directly
 *    against the code, not assumed). `bisectEnvelopes` is accepted as a prop specifically
 *    so wiring a real source later is additive, not a rewrite — no caller passes anything
 *    into it today, which is itself the honest state of the product, not an oversight.
 */
export function GitHistoryBisectPanel({
  snapshot,
  hasActiveMission,
  bisectEnvelopes = [],
}: {
  snapshot: MissionSnapshot;
  hasActiveMission: boolean;
  /** See module doc above — always `[]` in the shipped app today; the prop exists so a
   * future real event source has somewhere to plug in without touching this component. */
  bisectEnvelopes?: readonly unknown[];
}) {
  if (!hasActiveMission) {
    return (
      <section className="bd-evidence-deck" aria-labelledby="bd-evidence-deck-title">
        <h2 id="bd-evidence-deck-title" className="bd-panel__title">[ EVIDENCE DECK · GIT HISTORY &amp; BISECT ]</h2>
        <p className="bd-panel__empty">
          <span className="bd-panel__empty-label">[ NO MISSION ]</span>
          Git history and bisect evidence appear once a mission is active.
        </p>
      </section>
    );
  }

  const bisectState = deriveBisectTimelineState(bisectEnvelopes);

  return (
    <section className="bd-evidence-deck" aria-labelledby="bd-evidence-deck-title">
      <h2 id="bd-evidence-deck-title" className="bd-panel__title">[ EVIDENCE DECK · GIT HISTORY &amp; BISECT ]</h2>
      <div className="bd-evidence-deck__grid">
        <GitHistorySubPanel snapshot={snapshot} />
        <BisectTimelineSubPanel state={bisectState} />
      </div>
    </section>
  );
}

function GitHistorySubPanel({ snapshot }: { snapshot: MissionSnapshot }) {
  const groups = summarizeRiskyChanges(snapshot.findings);
  const analyzeReached = hasAnalyzeStageBeenReached(snapshot);

  return (
    <section className="bd-panel bd-crop bd-git-history" aria-labelledby="bd-git-history-title">
      <h2 id="bd-git-history-title" className="bd-panel__title">[ GIT HISTORY ]</h2>

      <dl className="bd-git-history__commit">
        <dt>repository</dt>
        <dd>{sanitizeDisplayText(snapshot.repositoryRef, { fallback: 'unknown repository', maxLength: 120 })}</dd>
        <dt>commit under test</dt>
        <dd>{snapshot.commitSha ? shortSha(sanitizeDisplayText(snapshot.commitSha, { maxLength: 64 })) : '— not yet ingested'}</dd>
        <dt>snapshot</dt>
        <dd>{snapshot.snapshotSha256 ? shortSha(sanitizeDisplayText(snapshot.snapshotSha256, { maxLength: 64 })) : '— not created'}</dd>
      </dl>

      <h3 className="bd-git-history__subtitle">RISKY-CHANGE SUMMARY</h3>
      {groups.length === 0 ? (
        <p className="bd-panel__empty">
          <span className="bd-panel__empty-label">{analyzeReached ? '[ CLEAN ]' : '[ AWAITING ANALYZE ]'}</span>
          {analyzeReached
            ? 'ANALYZE completed. No static-analysis-flagged file in this snapshot.'
            : 'Static analysis (Semgrep, compiler diagnostics) has not run for this mission yet.'}
        </p>
      ) : (
        <ol className="bd-risk__list">
          {groups.map((group) => (
            <RiskyFileRow key={group.filePath} group={group} />
          ))}
        </ol>
      )}
    </section>
  );
}

function RiskyFileRow({ group }: { group: RiskyFileGroup }) {
  return (
    <li className={`bd-risk__row bd-risk__row--${group.topSeverity.toLowerCase()}`}>
      <span className="bd-chip bd-chip--warning">[ {group.topSeverity} ]</span>
      <span className="bd-risk__file">{sanitizeDisplayText(group.filePath, { maxLength: 120, fallback: 'unknown file' })}</span>
      <small className="bd-risk__detail">
        {group.findingCount} finding{group.findingCount === 1 ? '' : 's'} · {sanitizeDisplayText(group.sampleTitle, { maxLength: 100, fallback: '' })}
      </small>
    </li>
  );
}

function BisectTimelineSubPanel({ state }: { state: BisectTimelineState }) {
  return (
    <section className="bd-panel bd-crop bd-bisect" aria-labelledby="bd-bisect-title">
      <h2 id="bd-bisect-title" className="bd-panel__title">[ BISECT TIMELINE ]</h2>

      {state.status === 'idle' && (
        <p className="bd-panel__empty">
          <span className="bd-panel__empty-label">[ — NOT TRIGGERED ]</span>
          <code>git bisect</code> is an operator-triggered, off-critical-path capability (#24) —
          it does not run automatically for any mission and has not been started for this one.
        </p>
      )}

      {state.status !== 'idle' && (
        <>
          <p className="bd-bisect__range">
            range {state.goodCommit ? shortSha(state.goodCommit) : '—'} (good) …{' '}
            {state.badCommit ? shortSha(state.badCommit) : '—'} (bad)
          </p>
          <ol className="bd-bisect__steps" aria-label="Bisect steps tested">
            {state.steps.map((step, index) => (
              <li key={`${step.sha}-${index}`} className={`bd-bisect__step bd-bisect__step--${step.verdict.toLowerCase()}`}>
                [ {step.verdict} ] {shortSha(step.sha)}
                {step.subject ? ` — ${sanitizeDisplayText(step.subject, { maxLength: 100 })}` : ''}
              </li>
            ))}
          </ol>

          {state.status === 'converged' && state.culpritCommit && (
            <p className="bd-chip bd-chip--critical bd-bisect__culprit">
              [ ✕ FIRST BAD COMMIT · {shortSha(state.culpritCommit)} ]{' '}
              {sanitizeDisplayText(state.culpritSubject ?? '', { maxLength: 120 })}
            </p>
          )}

          {state.status === 'not_converged' && (
            <p className="bd-evidence__error" role="alert">
              [ × BISECT DID NOT CONVERGE ] {sanitizeDisplayText(state.errorDetail ?? '', { maxLength: 200 })}
            </p>
          )}

          {state.status === 'running' && (
            <p className="bd-chip bd-chip--running">[ &gt; SEARCHING · {state.steps.length} STEP{state.steps.length === 1 ? '' : 'S'} TESTED ]</p>
          )}
        </>
      )}
    </section>
  );
}
