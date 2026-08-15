import { useStore } from '@nanostores/react';
import { useEffect, useMemo, useState } from 'react';

import { AIParticleCore } from './AIParticleCore';
import { VerdictComparePanel } from './VerdictComparePanel';
import { getMissionDetail } from '../lib/api/client';
import { connectMissionEvents } from '../lib/events/connection';
import {
  $localRepository,
  $missionSnapshot,
  $streamState,
  setMissionRepositoryContext,
  type LocalRepositoryContext,
  type MissionStage,
  type MissionSnapshot,
  type StreamState,
} from '../lib/events/store';

const signalFileWindowSize = 50;
const visibleSignalFileRows = 12;

export function MissionCommandCenter() {
  const snapshot = useStore($missionSnapshot);
  const localRepository = useStore($localRepository);
  const streamState = useStore($streamState);
  const [missionId, setMissionId] = useState<string | null>(null);

  useEffect(() => {
    const selectedMission = new URLSearchParams(window.location.search).get('mission');
    setMissionId(selectedMission);
    if (!selectedMission) {
      return undefined;
    }
    const controller = new AbortController();
    getMissionDetail(selectedMission, controller.signal).then(
      (mission) => setMissionRepositoryContext(mission.repository_ref),
      () => undefined,
    );
    const disconnect = connectMissionEvents(selectedMission);

    return () => {
      controller.abort();
      disconnect();
    };
  }, []);

  const release = useMemo(() => releaseChip(snapshot), [snapshot]);
  const commandState = commandStateCopy(snapshot, localRepository, streamState);
  const progressRows = missionProgressRows(snapshot);
  const analysis = analysisRailState(snapshot, streamState, localRepository);

  return (
    <section className="mission-shell" aria-labelledby="mission-shell-title">
      <div className="command-bar command-bar--mythic">
        <div>
          <p className="eyebrow">AI STATUS</p>
          <strong>{commandState.ai}</strong>
        </div>
        <div>
          <p className="eyebrow">AUTHORITY</p>
          <strong>{authorityLabel(snapshot, localRepository)}</strong>
        </div>
        <div>
          <p className="eyebrow">FILES MAPPED</p>
          <strong>{localRepository ? formatCount(localRepository.fileCount) : 'scan needed'}</strong>
        </div>
        <div>
          <p className="eyebrow">REPOSITORY</p>
          <strong>{snapshot.repositoryRef ?? formatLocalRepository(localRepository)}</strong>
        </div>
        <div>
          <p className="eyebrow">AUTOMATION</p>
          <strong>{snapshot.state ?? 'not running'}</strong>
        </div>
        <div>
          <p className="eyebrow">LAST UPDATE</p>
          <strong>{formatUtc(snapshot.latestTimestamp) ?? 'local only'}</strong>
        </div>
      </div>

      <div className="mission-frame">
        <div className={`core-panel core-panel--${postureClass(snapshot)}`}>
          <h2 id="mission-shell-title">[ LOCAL AI CORE ]</h2>
          <AIParticleCore snapshot={snapshot} localRepository={localRepository} streamState={streamState} />
          <div className="core-readout">
            <strong>{commandState.headline}</strong>
            <span>{commandState.detail}</span>
          </div>
        </div>

        <div className="mission-panels">
          <VerdictComparePanel snapshot={snapshot} />

          <AnalysisRail snapshot={snapshot} localRepository={localRepository} analysis={analysis} />

          <section aria-labelledby="automation-progress">
            <h2 id="automation-progress">{release.label}</h2>
            <ul className="progress-track progress-track--stages">
              {progressRows.map((row) => (
                <li key={row.stage} className={`progress-track__row progress-track__row--${row.state}`}>
                  <span>{row.glyph}</span>
                  <div>
                    <strong>{row.label}</strong>
                    <small>{row.detail}</small>
                  </div>
                </li>
              ))}
            </ul>
          </section>

          <section aria-labelledby="live-work">
            <h2 id="live-work">[ LIVE WORK ]</h2>
            <div className="work-readout">
              <strong>{liveWorkTitle(snapshot)}</strong>
              <span>{liveWorkDetail(snapshot, streamState)}</span>
            </div>
          </section>
        </div>
      </div>

      <div className={`resource-strip resource-strip--${release.state} resource-strip--${analysis.state}`}>
        <strong>{release.label}</strong>
        <span>
          stream {streamState} / mission {missionId ?? 'none'} / repo {localRepository?.name ?? 'none'} / event {snapshot.latestSequence ?? 'none'} / gpu {gpuUsageText(snapshot)}
        </span>
      </div>
    </section>
  );
}

function AnalysisRail({
  snapshot,
  localRepository,
  analysis,
}: {
  snapshot: MissionSnapshot;
  localRepository: LocalRepositoryContext | null;
  analysis: AnalysisRail;
}) {
  const signalFiles = virtualizedSignalFiles(localRepository?.detectedFiles ?? [], visibleSignalFileRows);

  return (
    <section className={`analysis-rail analysis-rail--${analysis.state}`} aria-labelledby="analysis-rail-title">
      <header>
        <h2 id="analysis-rail-title">[ ANALYSIS RAIL ]</h2>
        <strong>{analysis.label}</strong>
      </header>

      <dl className="status-matrix analysis-rail__metrics">
        <div><dt>Repository</dt><dd>{snapshot.repositoryRef ?? formatLocalRepository(localRepository)}</dd></div>
        <div><dt>Snapshot</dt><dd><HashReadout value={snapshot.snapshotSha256} /></dd></div>
        <div><dt>Baseline</dt><dd>{baselineStateText(snapshot)}</dd></div>
        <div><dt>CTest</dt><dd>{ctestCountText(snapshot)}</dd></div>
        <div><dt>Regression</dt><dd>{regressionStateText(snapshot)}</dd></div>
        <div><dt>Size</dt><dd>{localRepository ? formatBytes(localRepository.totalBytes) : 'scan a repo'}</dd></div>
        <div><dt>Signal files</dt><dd>{localRepository ? `${signalFiles.total} mapped signals / ${formatCount(localRepository.fileCount)} files` : 'scan a repo'}</dd></div>
      </dl>

      <div className="analysis-rail__state">
        <strong>{analysis.detail}</strong>
        <span>{analysis.source}</span>
      </div>

      <div className="virtual-signal-list" data-virtualized-list="signal-files">
        <div className="virtual-signal-list__head">
          <span>Repository signal window</span>
          <strong>{signalFiles.total > signalFiles.visible.length ? `[ ${signalFiles.hidden} MORE ]` : '[ FULL WINDOW ]'}</strong>
        </div>
        <ol
          className="virtual-signal-list__rows"
          aria-label={`Virtualized repository signal files, ${signalFiles.visible.length} of ${signalFiles.total} rendered`}
        >
          {signalFiles.visible.length > 0 ? signalFiles.visible.map((file) => (
            <li key={file}>{file}</li>
          )) : (
            <li>no signal files mapped yet</li>
          )}
        </ol>
      </div>
    </section>
  );
}

function gpuUsageText(snapshot: MissionSnapshot): string {
  if (!snapshot.resourceUsage || snapshot.resourceUsage.gpu_seconds === 0) {
    return 'not applicable - no leased GPU (see D-015)';
  }
  return `${snapshot.resourceUsage.gpu_seconds}s`;
}

function formatLocalRepository(repository: LocalRepositoryContext | null): string {
  return repository ? `local:${repository.name}` : 'no repo selected';
}

function authorityLabel(snapshot: MissionSnapshot, repository: LocalRepositoryContext | null): string {
  if (snapshot.state && snapshot.state !== 'CREATED') {
    return 'MISSION';
  }
  if (repository) {
    return 'LOCAL';
  }
  return 'NO';
}

function postureClass(snapshot: MissionSnapshot): string {
  if (snapshot.state === 'CANCELLED' || snapshot.posture === 'CANCELLED') {
    return 'cancelled';
  }
  if (snapshot.degradedReason) {
    return 'degraded';
  }
  if (snapshot.state === 'FAILED' || snapshot.posture === 'FAILED') {
    return 'failed';
  }
  if (snapshot.state === 'REJECTED' || snapshot.posture === 'REJECTED') {
    return 'rejected';
  }
  if (snapshot.state === 'VERIFIED' || snapshot.posture === 'VERIFIED') {
    return 'verified';
  }
  return snapshot.stage ? 'running' : 'empty';
}

function formatUtc(timestamp: string | null): string | null {
  if (!timestamp) {
    return null;
  }
  return new Intl.DateTimeFormat('en-CA', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZone: 'UTC',
    hour12: false,
  }).format(new Date(timestamp));
}

function shortHash(value: string | null): string {
  return value ? `${value.slice(0, 12)}...${value.slice(-6)}` : 'not created';
}

function HashReadout(props: { value: string | null }) {
  const { value } = props;
  if (!value) {
    return <span>not created</span>;
  }
  const label = `snapshot sha256 ${value}`;
  return <span title={value} aria-label={label}>{shortHash(value)}</span>;
}

function formatCount(value: number): string {
  return new Intl.NumberFormat('en-US').format(value);
}

function formatBytes(bytes: number | null): string {
  if (bytes == null) {
    return 'size empty';
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  return `${Math.round(bytes / 1024)} KiB`;
}

function releaseChip(snapshot: MissionSnapshot): { state: 'pending' | 'released'; label: string } {
  if (snapshot.releasedResources.length === 0 || snapshot.releasedResources.some((resource) => !resource.released)) {
    return { state: 'pending', label: snapshot.state ? '[ AUTOMATION ACTIVE ]' : '[ NO AUTOMATED ACTION RUNNING ]' };
  }

  const counts = snapshot.releasedResources.reduce<Record<string, number>>((accumulator, resource) => {
    accumulator[resource.kind] = (accumulator[resource.kind] ?? 0) + 1;
    return accumulator;
  }, {});

  const detail = Object.entries(counts)
    .map(([kind, count]) => `${count} ${kind.toUpperCase()}`)
    .join(' / ');

  return { state: 'released', label: `[ + ALL RESOURCES RELEASED / ${detail} ]` };
}

interface AnalysisRail {
  state: 'idle' | 'ready' | 'running' | 'degraded' | 'failed' | 'passed';
  label: string;
  detail: string;
  source: string;
}

function analysisRailState(
  snapshot: MissionSnapshot,
  streamState: StreamState,
  repository: LocalRepositoryContext | null,
): AnalysisRail {
  const failedDetail = failedAnalysisReason(snapshot);
  if (failedDetail) {
    return {
      state: 'failed',
      label: '[ FAILED ]',
      detail: failedDetail,
      source: snapshot.latestSequence ? `event stream #${snapshot.latestSequence}` : 'event stream',
    };
  }

  const degradedDetail = degradedAnalysisReason(snapshot, streamState);
  if (degradedDetail) {
    return {
      state: 'degraded',
      label: '[ DEGRADED ]',
      detail: degradedDetail,
      source: snapshot.latestSequence ? `event stream #${snapshot.latestSequence}` : `stream ${streamState}`,
    };
  }

  if (snapshot.baseline?.passed) {
    return {
      state: 'passed',
      label: '[ BASELINE GREEN ]',
      detail: 'configure, build and ctest baseline passed',
      source: snapshot.latestSequence ? `event stream #${snapshot.latestSequence}` : 'event stream',
    };
  }

  if (snapshot.state || snapshot.stage) {
    return {
      state: 'running',
      label: '[ RUNNING ]',
      detail: snapshot.latestMessage || `${snapshot.stage ?? snapshot.state} in progress`,
      source: snapshot.latestSequence ? `event stream #${snapshot.latestSequence}` : 'event stream',
    };
  }

  if (repository) {
    return {
      state: 'ready',
      label: '[ REPO READY ]',
      detail: `${formatCount(repository.fileCount)} local files mapped; mission not started`,
      source: 'browser-local scan',
    };
  }

  return {
    state: 'idle',
    label: '[ IDLE ]',
    detail: 'no repository or mission stream bound',
    source: 'local UI only',
  };
}

function failedAnalysisReason(snapshot: MissionSnapshot): string | null {
  if (snapshot.failedReason) {
    return snapshot.failedReason;
  }
  if (snapshot.state === 'FAILED') {
    return snapshot.latestMessage || 'mission failed';
  }
  if (snapshot.state === 'REJECTED') {
    return snapshot.latestMessage || 'mission rejected';
  }
  if (snapshot.baseline && !snapshot.baseline.passed) {
    if (!snapshot.baseline.configure_ok) {
      return 'baseline configure failed';
    }
    if (!snapshot.baseline.build_ok) {
      return 'baseline build failed';
    }
    if (snapshot.baseline.tests_failed > 0) {
      return `${snapshot.baseline.tests_failed} ctest failures in baseline`;
    }
    return 'baseline did not pass';
  }
  return null;
}

function degradedAnalysisReason(snapshot: MissionSnapshot, streamState: StreamState): string | null {
  if (streamState === 'stale') {
    return 'mission event stream is stale';
  }
  if (streamState === 'error') {
    return 'mission event stream is degraded';
  }
  return snapshot.degradedReason;
}

function baselineStateText(snapshot: MissionSnapshot): string {
  if (!snapshot.baseline) {
    return 'waiting for BASELINE_RECORDED';
  }
  if (snapshot.baseline.passed) {
    return 'passed from event stream';
  }
  return 'failed from event stream';
}

function ctestCountText(snapshot: MissionSnapshot): string {
  const baseline = snapshot.baseline;
  if (!baseline) {
    return 'no ctest counts yet';
  }
  return `${formatCount(baseline.tests_passed)} passed / ${formatCount(baseline.tests_failed)} failed / ${formatCount(baseline.tests_total)} total`;
}

function regressionStateText(snapshot: MissionSnapshot): string {
  const regressionGate = snapshot.verifications.at(-1)?.gates.regression_preserved;
  if (!regressionGate) {
    return snapshot.baseline ? 'baseline denominator ready' : 'waiting for ctest baseline';
  }
  return `${regressionGate.status} - ${regressionGate.tool || 'no tool recorded'}`;
}

function virtualizedSignalFiles(files: string[], visibleRows = signalFileWindowSize): {
  visible: string[];
  hidden: number;
  total: number;
} {
  const windowSize = Math.min(Math.max(1, visibleRows), signalFileWindowSize);
  return {
    visible: files.slice(0, windowSize),
    hidden: Math.max(0, files.length - windowSize),
    total: files.length,
  };
}

function commandStateCopy(
  snapshot: MissionSnapshot,
  repository: LocalRepositoryContext | null,
  streamState: string,
): { ai: string; headline: string; detail: string } {
  if (snapshot.state) {
    return {
      ai: 'RUNNING',
      headline: snapshot.stage ?? snapshot.state,
      detail: snapshot.latestMessage ?? `Mission stream is ${streamState}.`,
    };
  }
  if (repository) {
    return {
      ai: 'READY',
      headline: 'Repo context loaded',
      detail: `${formatCount(repository.fileCount)} files mapped locally. Ask the core what to inspect first.`,
    };
  }
  return {
    ai: 'WAITING',
    headline: 'No code loaded',
    detail: 'Scan a local path to give the core repository context.',
  };
}

const missionStages: Array<{ stage: MissionStage; label: string }> = [
  { stage: 'AUTHORIZE', label: 'Authorize' },
  { stage: 'INGEST', label: 'Ingest' },
  { stage: 'BASELINE', label: 'Baseline' },
  { stage: 'ANALYZE', label: 'Analyze' },
  { stage: 'STRESS_TEST', label: 'Stress' },
  { stage: 'CORRELATE', label: 'Correlate' },
  { stage: 'PATCH', label: 'Patch' },
  { stage: 'VERIFY', label: 'Verify' },
  { stage: 'EXPORT_EVIDENCE', label: 'Export' },
];

function missionProgressRows(
  snapshot: MissionSnapshot,
): Array<{ stage: MissionStage; label: string; detail: string; state: 'done' | 'idle' | 'running'; glyph: string }> {
  return missionStages.map(({ stage, label }) => {
    if (snapshot.completedStages.includes(stage)) {
      const replaySkippedFuzzing = stage === 'STRESS_TEST' && snapshot.fuzzing?.mode === 'NOT_RUN';
      return {
        stage,
        label,
        detail: replaySkippedFuzzing ? 'skipped' : 'complete',
        state: 'done',
        glyph: replaySkippedFuzzing ? '-' : '+',
      };
    }
    if (snapshot.stage === stage) {
      const progress = snapshot.stageProgress[stage];
      return {
        stage,
        label,
        detail: progress == null ? 'running' : `${Math.round(progress)}%`,
        state: 'running',
        glyph: '>',
      };
    }
    return { stage, label, detail: 'waiting', state: 'idle', glyph: '·' };
  });
}

function liveWorkTitle(snapshot: MissionSnapshot): string {
  if (snapshot.finding) {
    return snapshot.finding.title;
  }
  if (snapshot.baseline) {
    return `${snapshot.baseline.tests_passed} tests passing / ${snapshot.baseline.tests_failed} failing`;
  }
  return snapshot.state ? snapshot.state : 'Nothing running yet';
}

function liveWorkDetail(snapshot: MissionSnapshot, streamState: string): string {
  if (snapshot.finding) {
    const line = snapshot.finding.location.line ? `:${snapshot.finding.location.line}` : '';
    const method = discoveryMethodLabel(snapshot.finding.discovery_method);
    const replaySource = snapshot.finding.replay_source ? ` / ${snapshot.finding.replay_source}` : '';
    return `${method} / ${snapshot.finding.severity} / ${snapshot.finding.category} / ${snapshot.finding.location.file_path}${line}${replaySource}`;
  }
  if (snapshot.latestMessage) {
    return snapshot.latestMessage;
  }
  return `Local UI ready. Mission stream is ${streamState}.`;
}

function discoveryMethodLabel(method: string): string {
  if (method === 'REPLAYED_REPRODUCER') {
    return 'replayed reproducer';
  }
  if (method === 'FUZZING_CAMPAIGN') {
    return 'fuzzed';
  }
  if (method === 'DIRECT_HARNESS') {
    return 'direct harness';
  }
  return method.toLowerCase().replaceAll('_', ' ');
}
