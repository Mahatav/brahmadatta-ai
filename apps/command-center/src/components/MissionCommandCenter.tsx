import { useStore } from '@nanostores/react';
import { useEffect, useMemo, useState } from 'react';

import { AIParticleCore } from './AIParticleCore';
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
} from '../lib/events/store';

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
          <section className="context-panel context-panel--primary" aria-labelledby="what-this-does">
            <h2 id="what-this-does">[ SITUATION ]</h2>
            <p>
              {localRepository
                ? 'Code context is loaded. Ask the core what to inspect, what to run, or where risk is concentrated.'
                : 'Load a local repository first. Until code is mapped, the core is waiting for context.'}
            </p>
          </section>

          <section aria-labelledby="repo-context">
            <h2 id="repo-context">[ REPO INTEL ]</h2>
            <dl className="status-matrix">
              <div><dt>Path</dt><dd>{formatLocalRepository(localRepository)}</dd></div>
              <div><dt>Stack</dt><dd>{localRepository?.primaryStack ?? 'scan a repo'}</dd></div>
              <div><dt>Files</dt><dd>{localRepository ? formatCount(localRepository.fileCount) : 'scan a repo'}</dd></div>
              <div><dt>Size</dt><dd>{localRepository ? formatBytes(localRepository.totalBytes) : 'scan a repo'}</dd></div>
              <div><dt>Fingerprint</dt><dd>{shortHash(snapshot.snapshotSha256)}</dd></div>
            </dl>
          </section>

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

      <div className={`resource-strip resource-strip--${release.state}`}>
        <strong>{release.label}</strong>
        <span>
          stream {streamState} / mission {missionId ?? 'none'} / repo {localRepository?.name ?? 'none'} / event {snapshot.latestSequence ?? 'none'}
        </span>
      </div>
    </section>
  );
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
  return value ? value.slice(0, 12) : 'not created';
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
      return { stage, label, detail: 'complete', state: 'done', glyph: '+' };
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
    return `${snapshot.finding.severity} / ${snapshot.finding.category} / ${snapshot.finding.location.file_path}${line}`;
  }
  if (snapshot.latestMessage) {
    return snapshot.latestMessage;
  }
  return `Local UI ready. Mission stream is ${streamState}.`;
}
