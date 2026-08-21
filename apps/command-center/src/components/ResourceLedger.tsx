import type { MissionSnapshot } from '../lib/events/store';
import { sanitizeDisplayText } from '../lib/security/renderSafety.mjs';

/**
 * The resource ledger (§6.6, DS-04) — teardown's surface on the success path. Bottom strip,
 * left region. Every chip here follows a receipt, never an intention (architecture spec §6.7):
 * "released" is displayed only once a `TEARDOWN_CONFIRMED` event with `released=true` exists.
 *
 * This is the same `releasedResources` set the Stage Timeline's row 10 and the Core's terminal
 * release line read — one teardown count, three renderings (§12 build note 9), never three
 * separate counters that could disagree on stage.
 */
export function ResourceLedger({ snapshot, hasActiveMission }: { snapshot: MissionSnapshot; hasActiveMission: boolean }) {
  const sandbox = findResource(snapshot, /sandbox/i);
  const modelHost = findResource(snapshot, /model.?host/i);
  const knownKinds = new Set(snapshot.releasedResources.map((resource) => resource.kind));
  if (hasActiveMission && (snapshot.resourceUsage?.sandbox_count ?? 0) > 0) {
    knownKinds.add('sandbox');
  }
  const releasedCount = snapshot.releasedResources.filter((resource) => resource.released).length;
  const anyFailed = snapshot.releasedResources.some((resource) => !resource.released && isTerminal(snapshot));

  return (
    <div className="bd-ledger">
      <p className="bd-ledger__line">
        <span className="bd-chip">[ LOCAL · LOOPBACK ONLY ]</span>{' '}
        <span className="bd-chip">[ EGRESS DENIED ]</span>{' '}
        <span className={`bd-chip bd-chip--${rollupTone(knownKinds.size, releasedCount, anyFailed)}`}>
          {rollupText(knownKinds.size, releasedCount, anyFailed, hasActiveMission)}
        </span>
      </p>
      <p className="bd-ledger__line">
        <span className="bd-chip">[ EVENTS {snapshot.latestSequence != null ? formatCount(snapshot.latestSequence) : '—'} ]</span>{' '}
        <ResourceChip label="SANDBOX" resource={sandbox} known={knownKinds.has('sandbox') || Boolean(sandbox)} />{' '}
        <ResourceChip label="MODEL HOST" resource={modelHost} known={Boolean(modelHost)} />
      </p>
    </div>
  );
}

function ResourceChip({ label, resource, known }: { label: string; resource: MissionSnapshot['releasedResources'][number] | null; known: boolean }) {
  if (!resource) {
    if (!known) {
      return <span className="bd-chip">[ — {label} · NOT LEASED ]</span>;
    }
    return <span className="bd-chip bd-chip--running">[ ● {label} · RUNNING ]</span>;
  }
  if (resource.released) {
    return <span className="bd-chip bd-chip--verified">[ + {sanitizeDisplayText(resource.kind, { maxLength: 20 }).toUpperCase()} · RELEASED ]</span>;
  }
  return <span className="bd-chip bd-chip--critical">[ × {sanitizeDisplayText(resource.kind, { maxLength: 20 }).toUpperCase()} · RELEASE FAILED ]</span>;
}

function findResource(snapshot: MissionSnapshot, pattern: RegExp): MissionSnapshot['releasedResources'][number] | null {
  return snapshot.releasedResources.find((resource) => pattern.test(resource.kind)) ?? null;
}

function isTerminal(snapshot: MissionSnapshot): boolean {
  return snapshot.state === 'VERIFIED' || snapshot.state === 'REJECTED' || snapshot.state === 'FAILED' || snapshot.state === 'CANCELLED' || snapshot.state === 'HUMAN_REVIEW';
}

function rollupTone(known: number, released: number, anyFailed: boolean): 'secondary' | 'running' | 'verified' | 'warning' | 'critical' {
  if (anyFailed) return 'critical';
  if (known === 0) return 'secondary';
  if (released === known) return 'verified';
  if (released > 0) return 'warning';
  return 'running';
}

function rollupText(known: number, released: number, anyFailed: boolean, hasActiveMission: boolean): string {
  if (!hasActiveMission || known === 0) {
    return '[ RESOURCES · — ]';
  }
  if (anyFailed) {
    return `[ × RESOURCE RELEASE FAILED · ${released} OF ${known} ]`;
  }
  if (released === known) {
    return `[ + ALL RESOURCES RELEASED · ${released} OF ${known} ]`;
  }
  if (released > 0) {
    return `[ ! RESOURCES · ${released} OF ${known} RELEASED ]`;
  }
  return `[ RESOURCES · ${known} HELD ]`;
}

function formatCount(value: number): string {
  return new Intl.NumberFormat('en-US').format(value);
}
