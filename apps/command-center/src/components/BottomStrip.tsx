import { useState } from 'react';

import { ApiError, cancelMission, exportEvidence, pauseMission, type ExportReceipt, type MissionDetail } from '../lib/api/client';
import type { MissionSnapshot } from '../lib/events/store';
import { sanitizeDisplayText } from '../lib/security/renderSafety.mjs';
import { ConfirmDialog } from './ConfirmDialog';
import { ResourceLedger } from './ResourceLedger';

/**
 * The bottom strip's control row (§3, §6.6, §2.7): `[ OPEN COMPARE ]` `[ PAUSE ]`
 * `[ CANCEL MISSION ]` `[ EXPORT EVIDENCE ]`, one 44px hit-target row, plus the resource ledger
 * to its left on two `mono-2xs` lines.
 *
 * `PAUSE` and `CANCEL MISSION` call the same tested `pauseMission`/`cancelMission` client
 * functions `MissionControlPanel.tsx` (D-100) already wires — that file is left untouched
 * (out of this task's scope) so this is a second, spec-mandated surface for the same two
 * real endpoints rather than a duplicate implementation of the mission-lifecycle logic itself.
 * `EXPORT EVIDENCE` is new: no UI control called `POST /missions/{id}/export` anywhere before
 * this change, even though `src/lib/api/client.ts` already typed it.
 */
export function BottomStrip({
  snapshot,
  activeMissionId,
  missionDetail,
  hasActiveMission,
  onOpenCompare,
  onMissionRefreshed,
}: {
  snapshot: MissionSnapshot;
  activeMissionId: string | null;
  missionDetail: MissionDetail | null;
  hasActiveMission: boolean;
  onOpenCompare: () => void;
  onMissionRefreshed: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [confirmAction, setConfirmAction] = useState<'cancel' | 'export' | null>(null);
  const [alert, setAlert] = useState<{ tone: 'critical' | 'verified' | 'warning'; text: string } | null>(null);
  const [exportReceipt, setExportReceipt] = useState<ExportReceipt | null>(null);

  const allowedTransitions = missionDetail?.allowed_transitions ?? [];
  const canPause = allowedTransitions.includes('PAUSED');
  const canCancel = Boolean(activeMissionId) && !['CANCELLED', 'VERIFIED', 'REJECTED', 'FAILED'].includes(snapshot.state ?? '');
  const canExport = Boolean(activeMissionId);
  const canCompare = snapshot.patchCandidates.length > 0;

  async function handlePause(): Promise<void> {
    if (!activeMissionId) return;
    setBusy(true);
    setAlert(null);
    try {
      await pauseMission(activeMissionId, { reason: 'operator requested pause from the bottom strip' });
      setAlert({ tone: 'warning', text: '[ ● PAUSED ]' });
      onMissionRefreshed();
    } catch (error) {
      setAlert({ tone: 'critical', text: `[ × PAUSE FAILED ] ${describeError(error)}` });
    } finally {
      setBusy(false);
    }
  }

  async function handleCancel(): Promise<void> {
    if (!activeMissionId) return;
    setBusy(true);
    setAlert(null);
    try {
      await cancelMission(activeMissionId, { confirm: true, reason: 'operator cancelled the mission from the bottom strip' });
      setAlert({ tone: 'warning', text: '[ ● CANCELLING ]' });
      onMissionRefreshed();
    } catch (error) {
      setAlert({ tone: 'critical', text: `[ × CANCEL FAILED ] ${describeError(error)}` });
    } finally {
      setBusy(false);
      setConfirmAction(null);
    }
  }

  async function handleExport(): Promise<void> {
    if (!activeMissionId) return;
    setBusy(true);
    setAlert({ tone: 'warning', text: '[ ● EXPORTING ]' });
    try {
      const receipt = await exportEvidence(activeMissionId, { formats: ['markdown', 'json'], include_artifacts: false });
      setExportReceipt(receipt);
      const paths = receipt.artifacts.map((artifact) => artifact.uri.split('/').pop()).filter(Boolean).join(', ');
      setAlert({ tone: 'verified', text: `[ + EXPORTED · ${paths || receipt.formats.join(', ')} ]` });
    } catch (error) {
      setAlert({ tone: 'critical', text: `[ × EXPORT FAILED ] ${describeError(error)}` });
    } finally {
      setBusy(false);
      setConfirmAction(null);
    }
  }

  return (
    <div className="bd-bottom-strip">
      <ResourceLedger snapshot={snapshot} hasActiveMission={hasActiveMission} />

      <div className="bd-bottom-strip__controls">
        {alert && (
          <p className={`bd-alert-line bd-alert-line--${alert.tone}`} role="alert">{alert.text}</p>
        )}
        <button type="button" className="bd-bracket-control" disabled={!canCompare} onClick={onOpenCompare}>
          [ OPEN COMPARE ]
        </button>
        <button type="button" className="bd-bracket-control" disabled={busy || !canPause} onClick={handlePause}>
          [ PAUSE ]
        </button>
        <button
          type="button"
          className="bd-bracket-control bd-bracket-control--critical"
          disabled={busy || !canCancel}
          onClick={() => setConfirmAction('cancel')}
        >
          [ CANCEL MISSION ]
        </button>
        <button
          type="button"
          className="bd-bracket-control"
          disabled={busy || !canExport}
          onClick={() => setConfirmAction('export')}
        >
          [ EXPORT EVIDENCE ]
        </button>
      </div>

      {confirmAction === 'cancel' && (
        <ConfirmDialog
          title={`Cancel mission ${activeMissionId?.slice(0, 8) ?? ''}.`}
          consequence="The sandbox is destroyed and any unexported evidence is lost. This cannot be undone."
          confirmLabel="CANCEL MISSION"
          destructive
          busy={busy}
          onConfirm={handleCancel}
          onCancel={() => setConfirmAction(null)}
        />
      )}

      {confirmAction === 'export' && (
        <ConfirmDialog
          title={`Export evidence for mission ${activeMissionId?.slice(0, 8) ?? ''}.`}
          consequence="Writes a markdown and JSON evidence report from this mission's real gates, findings and reproducer records to the Control API host."
          confirmLabel="EXPORT"
          busy={busy}
          onConfirm={handleExport}
          onCancel={() => setConfirmAction(null)}
        />
      )}

      {exportReceipt && (
        <p className="bd-bottom-strip__export-receipt">
          export {sanitizeDisplayText(exportReceipt.export_id.slice(0, 8), { maxLength: 8 })} ·{' '}
          {exportReceipt.artifacts.map((artifact) => sanitizeDisplayText(artifact.uri, { maxLength: 120 })).join(' · ')}
        </p>
      )}
    </div>
  );
}

function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return sanitizeDisplayText(error.message, { maxLength: 160 });
  }
  return 'request failed';
}
