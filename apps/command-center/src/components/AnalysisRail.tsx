import type { LocalRepositoryContext, MissionSnapshot, StreamState } from '../lib/events/store';
import {
  CompilerHealthRow,
  computeStaticAnalysisCoverage,
  NotRunCoverageRow,
  SeverityFindingsList,
} from './SeverityFindingsList';

/**
 * The Analysis Rail — baseline/ctest/regression readouts plus the bounded, virtualized local
 * signal-file list. This is issue #20's own regression-tested surface
 * (`scripts/check-issue-20-analysis-rail.mjs`), extracted verbatim (behavior unchanged) out of
 * `MissionCommandCenter.tsx` as part of the frozen design-system rebuild
 * (docs/09-company/04-design-system.md).
 *
 * WHY IT MOVED RATHER THAN STAYING IN THE MAIN FRAME: the design system's five P0 panels close
 * the 1440×900 body height with zero slack (§3 — "684, with zero slack"; the centre column's own
 * 424 + 24 + 236 = 684 budget, DS-01). There is no sixth panel's worth of room for this rail's
 * baseline/ctest/local-signal-file content inside the frozen frame — that content is instead
 * carried by the spec's own designated surfaces (the Stage Timeline's BASELINE row for ctest
 * counts, the Verdict panel's REGRESSION PRESERVED gate for the regression readout). This
 * component keeps the local-repository-scan diagnostic value the current build already has, in
 * the pre-mission setup area alongside `LocalRepositoryIntake` and `MissionControlPanel`, rather
 * than deleting it outright — the task's own instruction was "check the spec directly rather
 * than assuming" before removing chrome, and this rail (unlike `AIParticleCore`) is not
 * mentioned anywhere in `docs/02-design/` or the frozen spec as something to cut; it predates
 * both and is genuinely useful operator diagnostics.
 */

const signalFileWindowSize = 50;

export interface AnalysisRailState {
  state: 'idle' | 'ready' | 'running' | 'degraded' | 'failed' | 'passed';
  label: string;
  detail: string;
  source: string;
}

export function analysisRailState(
  snapshot: MissionSnapshot,
  streamState: StreamState,
  repository: LocalRepositoryContext | null,
): AnalysisRailState {
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

export function AnalysisRail({
  snapshot,
  localRepository,
  analysis,
  streamState = 'idle',
}: {
  snapshot: MissionSnapshot;
  localRepository: LocalRepositoryContext | null;
  analysis: AnalysisRailState;
  streamState?: StreamState;
}) {
  const signalFiles = virtualizedSignalFiles(localRepository?.detectedFiles ?? []);
  const staticCoverage = computeStaticAnalysisCoverage(snapshot);

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

      {/* #25 — findings by severity, dependency health and compiler health (D-057,
          docs/09-company/13-cut-pullback-design-spec.md §1). Extends this rail rather than
          adding a sixth panel — the frozen scored frame has zero body-height slack (§3), and
          this rail already lives in the pre-mission setup drawer, outside that budget. */}
      <div className="analysis-rail__coverage">
        <SeverityFindingsList snapshot={snapshot} streamState={streamState} coverage={staticCoverage} />
        <CompilerHealthRow coverage={staticCoverage} />
        <NotRunCoverageRow label="DEPENDENCY HEALTH" reason="no dependency scanner in this build" />
      </div>
    </section>
  );
}

function formatLocalRepository(repository: LocalRepositoryContext | null): string {
  return repository ? `local:${repository.name}` : 'no repo selected';
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

function virtualizedSignalFiles(files: string[]): {
  visible: string[];
  hidden: number;
  total: number;
} {
  const windowSize = signalFileWindowSize;
  return {
    visible: files.slice(0, windowSize),
    hidden: Math.max(0, files.length - windowSize),
    total: files.length,
  };
}
