import { useEffect, useState } from 'react';

import { getFinding, ApiError, type FindingDetail } from '../lib/api/client';
import type { MissionSnapshot, StreamState } from '../lib/events/store';
import { sanitizeDisplayText } from '../lib/security/renderSafety.mjs';

/**
 * Panel 3 — Findings list, plus the always-expanded evidence block (§6.3, §6.3a). The rail
 * carries only `FindingSummary` over SSE; the sanitizer stack trace and the reproducer record
 * live on `FindingDetail`, fetched once per finding via `GET /findings/{id}` — the same pattern
 * `MissionCommandCenter` already uses to hydrate `repository_ref` from `GET /missions/{id}`.
 */

const FRAME_PREVIEW_COUNT = 3; // --bd-evidence-frames

export function FindingsRail({
  snapshot,
  streamState,
  hasActiveMission,
}: {
  snapshot: MissionSnapshot;
  streamState: StreamState;
  hasActiveMission: boolean;
}) {
  const [detail, setDetail] = useState<FindingDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [showAllFrames, setShowAllFrames] = useState(false);
  const findingId = snapshot.finding?.id ?? null;

  useEffect(() => {
    setDetail(null);
    setDetailError(null);
    setShowAllFrames(false);
    if (!findingId || !snapshot.missionId) {
      return undefined;
    }
    const controller = new AbortController();
    setLoadingDetail(true);
    getFinding(snapshot.missionId, findingId, controller.signal)
      .then((result) => setDetail(result))
      .catch((error) => {
        if (error instanceof ApiError) {
          setDetailError(error.message);
        } else if (!(error instanceof DOMException)) {
          setDetailError('finding detail request failed');
        }
      })
      .finally(() => setLoadingDetail(false));
    return () => controller.abort();
  }, [findingId, snapshot.missionId]);

  if (!hasActiveMission) {
    return (
      <section className="bd-panel bd-crop bd-findings" aria-labelledby="bd-findings-title">
        <h2 id="bd-findings-title" className="bd-panel__title">[ FINDINGS · — ]</h2>
        <p className="bd-panel__empty">
          <span className="bd-panel__empty-label">[ NO MISSION ]</span>
          Findings appear when a sanitizer report is captured.
        </p>
      </section>
    );
  }

  const header = findingsHeader(snapshot);
  const degraded = streamState === 'stale';

  return (
    <section className="bd-panel bd-crop bd-findings" aria-labelledby="bd-findings-title">
      <header className="bd-findings__header">
        <h2 id="bd-findings-title" className="bd-panel__title">{header}</h2>
        {degraded && <span className="bd-chip bd-chip--warning">[ ! MAY BE INCOMPLETE ]</span>}
      </header>

      {!snapshot.finding && (
        <p className="bd-panel__empty">
          <span className="bd-panel__empty-label">
            {header === '[ FINDINGS · 0 ]' ? '[ CLEAN RUN ]' : '[ AWAITING FINDING ]'}
          </span>
          {header === '[ FINDINGS · 0 ]'
            ? 'Stress test completed. No sanitizer-confirmed defect in this snapshot within the fuzzing budget.'
            : 'Findings appear when a sanitizer report is captured.'}
        </p>
      )}

      {snapshot.finding && (
        <>
          <ol className="bd-findings__list">
            <li className="bd-findings__row bd-findings__row--selected">
              <span className="bd-findings__index">[ FINDING 01 ]</span>
              <span className="bd-findings__title">{sanitizeDisplayText(snapshot.finding.title, { maxLength: 80 })}</span>
              <span className="bd-chip bd-chip--verified">[ ● CONFIRMED ]</span>
              <small className="bd-findings__location">
                {sanitizeDisplayText(snapshot.finding.location.file_path, { maxLength: 80 })}
                {snapshot.finding.location.line ? `:${snapshot.finding.location.line}` : ''}
                {' · '}{snapshot.finding.severity} · {snapshot.finding.category}
              </small>
            </li>
          </ol>

          <EvidenceBlock
            loading={loadingDetail}
            error={detailError}
            detail={detail}
            showAllFrames={showAllFrames}
            onShowAllFrames={() => setShowAllFrames(true)}
            onRetry={() => setDetail((current) => current)}
          />
        </>
      )}
    </section>
  );
}

function findingsHeader(snapshot: MissionSnapshot): string {
  if (snapshot.finding) {
    return '[ FINDINGS · 1 ]';
  }
  const stressComplete = snapshot.completedStages.includes('STRESS_TEST') || (snapshot.fuzzing != null && snapshot.fuzzing.crashes_found === 0);
  if (stressComplete) {
    return '[ FINDINGS · 0 ]';
  }
  return '[ FINDINGS · — ]';
}

function EvidenceBlock(props: {
  loading: boolean;
  error: string | null;
  detail: FindingDetail | null;
  showAllFrames: boolean;
  onShowAllFrames: () => void;
  onRetry: () => void;
}) {
  const { loading, error, detail, showAllFrames, onShowAllFrames, onRetry } = props;

  if (loading) {
    return (
      <div className="bd-evidence bd-evidence--loading" aria-hidden="true">
        <div className="bd-placeholder-rule bd-placeholder-rule--65" />
        <div className="bd-placeholder-rule bd-placeholder-rule--40" />
        <div className="bd-placeholder-rule bd-placeholder-rule--65" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="bd-evidence bd-evidence--failed">
        <p className="bd-panel__title">[ EVIDENCE · SANITIZER ]</p>
        <p className="bd-evidence__error" role="alert">[ × EVIDENCE UNAVAILABLE ] {sanitizeDisplayText(error, { maxLength: 200 })}</p>
        <button type="button" className="bd-bracket-control" onClick={onRetry}>[ RETRY ]</button>
      </div>
    );
  }

  if (!detail || !detail.sanitizer_report) {
    return (
      <div className="bd-evidence bd-evidence--pending">
        <p className="bd-panel__title">[ EVIDENCE · SANITIZER ]</p>
        <p className="bd-evidence__pending">[ — REPORT · NOT YET CAPTURED ]</p>
      </div>
    );
  }

  const { errorLines, frames } = parseSanitizerReport(detail.sanitizer_report);
  const visibleFrames = showAllFrames ? frames : frames.slice(0, FRAME_PREVIEW_COUNT);

  return (
    <div className="bd-evidence">
      <div className="bd-evidence__block">
        <p className="bd-panel__title">[ EVIDENCE · SANITIZER ]</p>
        {errorLines.map((line, index) => (
          <p key={index} className="bd-evidence__line">{sanitizeDisplayText(line, { maxLength: 160 })}</p>
        ))}
        {frames.length === 0 && (
          <p className="bd-evidence__raw">{sanitizeDisplayText(detail.sanitizer_report, { maxLength: 600 })}</p>
        )}
        {frames.length > 0 && (
          <>
            <ul className="bd-evidence__frames">
              {visibleFrames.map((frame) => (
                <li key={frame.index} className="bd-evidence__frame">
                  {'  #'}{frame.index}{'  '}
                  {sanitizeDisplayText(frame.function, { maxLength: 20 })}
                  {'  '}
                  {sanitizeDisplayText(frame.location, { maxLength: 40 })}
                </li>
              ))}
            </ul>
            {frames.length > FRAME_PREVIEW_COUNT && (
              <p className="bd-evidence__frame-count">
                <span>[ FRAMES {visibleFrames.length} OF {frames.length} ]</span>
                {!showAllFrames && (
                  <button type="button" className="bd-bracket-control bd-bracket-control--inline" onClick={onShowAllFrames}>
                    [ FULL TRACE ]
                  </button>
                )}
              </p>
            )}
          </>
        )}
      </div>

      <div className="bd-evidence__block">
        <p className="bd-panel__title">[ EVIDENCE · REPRODUCER ]</p>
        <ReproducerEvidence detail={detail} />
      </div>
    </div>
  );
}

function ReproducerEvidence({ detail }: { detail: FindingDetail }) {
  const reproducer = detail.reproducer;
  if (!reproducer) {
    return (
      <>
        <p className="bd-evidence__line">[ — REPLAY · NOT RUN ]</p>
        <p className="bd-evidence__line">replay — / —</p>
      </>
    );
  }

  const artifactSize = reproducer.artifact.size_bytes;
  return (
    <>
      <p className="bd-evidence__line">
        {reproducer.minimized
          ? `minimized artifact${artifactSize != null ? ` · ${artifactSize} bytes` : ''}`
          : 'not yet minimized'}
      </p>
      <p className="bd-evidence__line">
        replay {reproducer.replay_attempts > 0 ? `${reproducer.replay_successes}/${reproducer.replay_attempts}` : '— / —'} from a clean build
      </p>
      <DeterminismChip attempts={reproducer.replay_attempts} successes={reproducer.replay_successes} />
    </>
  );
}

function DeterminismChip({ attempts, successes }: { attempts: number; successes: number }) {
  if (attempts === 0) {
    return null;
  }
  if (successes === attempts) {
    return <p className="bd-chip bd-chip--verified">[ + DETERMINISTIC · {successes}/{attempts} ]</p>;
  }
  if (successes === 0) {
    return <p className="bd-chip bd-chip--critical">[ × NOT REPRODUCIBLE · 0/{attempts} ]</p>;
  }
  return <p className="bd-chip bd-chip--warning">[ ! NON-DETERMINISTIC · {successes}/{attempts} ]</p>;
}

interface ParsedFrame {
  index: string;
  function: string;
  location: string;
}

function parseSanitizerReport(report: string): { errorLines: string[]; frames: ParsedFrame[] } {
  const lines = report.split('\n').map((line) => line.trim()).filter(Boolean);
  const frameLinePattern = /^#(\d+)\s+(?:0x[0-9a-f]+\s+in\s+)?(\S+)\s+(\S+:\d+(?::\d+)?)/i;
  const frames: ParsedFrame[] = [];
  const errorLines: string[] = [];

  for (const line of lines) {
    const match = frameLinePattern.exec(line);
    if (match) {
      frames.push({ index: match[1] ?? '', function: match[2] ?? 'unknown', location: match[3] ?? 'unknown' });
    } else if (frames.length === 0) {
      errorLines.push(line);
    }
    if (errorLines.length >= 2) {
      continue;
    }
  }

  return { errorLines: errorLines.slice(0, 2), frames };
}
