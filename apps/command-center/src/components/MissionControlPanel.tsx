import { useStore } from '@nanostores/react';
import { useEffect, useMemo, useState } from 'react';
import type { FormEvent } from 'react';

import {
  authorizeMission,
  cancelMission,
  createMission,
  getMissionDetail,
  pauseMission,
  preflightMission,
  snapshotLocalRepository,
  startMission,
  type LanguageAdapter,
  type MissionDetail,
  type PreflightReport,
} from '../lib/api/client';
import { $activeMissionId, $localRepository, $missionSnapshot, setActiveMissionId } from '../lib/events/store';
import {
  defaultForm,
  describeApiError,
  validateForm,
  type DisplayError,
  type FormState,
} from '../lib/missionControl/formLogic';
import { sanitizeDisplayText } from '../lib/security/renderSafety.mjs';
import { ConfirmDialog } from './ConfirmDialog';
import '../styles/mission-control-panel.css';

type StepKey = 'CREATE' | 'AUTHORIZE' | 'SNAPSHOT' | 'PREFLIGHT';
type StepStatus = 'pending' | 'running' | 'ok' | 'warn' | 'fail';

interface StepRecord {
  key: StepKey;
  status: StepStatus;
  detail: string;
}

const STEP_ORDER: StepKey[] = ['CREATE', 'AUTHORIZE', 'SNAPSHOT', 'PREFLIGHT'];

const ADAPTER_OPTIONS: { value: LanguageAdapter; label: string }[] = [
  { value: 'C_CMAKE_CTEST', label: 'C — CMake + ctest' },
  { value: 'C_MAKE_CTEST', label: 'C — Make + ctest' },
];

const GLYPH: Record<StepStatus, string> = {
  pending: '·',
  running: '>',
  ok: '+',
  warn: '!',
  fail: '×',
};

const STATUS_WORD: Record<StepStatus, string> = {
  pending: 'QUEUED',
  running: 'RUNNING',
  ok: 'OK',
  warn: 'WARN',
  fail: 'FAIL',
};

function initialSteps(): StepRecord[] {
  return STEP_ORDER.map((key) => ({ key, status: 'pending', detail: '' }));
}

/**
 * `MissionControlPanel` — the P0-blocking gap this task closes: a real way to create,
 * authorize, snapshot, preflight, start, pause and cancel a mission from the UI, per
 * docs/09-company/04-design-system.md §4.1 (primary journey) and §4.2 (operator intervenes).
 * Deliberately built as new, self-contained chrome against the rev-2 token system
 * (`packages/ui-components/tokens.css`) rather than the surrounding legacy panels' visual
 * language — the Core/timeline/findings-rail/compare/verdict visual rebuild is a separate,
 * later pass (out of this task's scope); this panel only has to be real and correct.
 */
export function MissionControlPanel() {
  const activeMissionId = useStore($activeMissionId);
  const localRepository = useStore($localRepository);
  const liveSnapshot = useStore($missionSnapshot);

  const [form, setForm] = useState<FormState>(defaultForm());
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [steps, setSteps] = useState<StepRecord[]>(initialSteps());
  const [busy, setBusy] = useState(false);
  const [lastError, setLastError] = useState<DisplayError | null>(null);
  const [preflight, setPreflight] = useState<PreflightReport | null>(null);
  const [missionDetail, setMissionDetail] = useState<MissionDetail | null>(null);
  const [confirmAction, setConfirmAction] = useState<'launch' | 'cancel' | 'teardown' | null>(null);

  // Prefill from LocalRepositoryIntake's local scan when present and the operator has not
  // already typed something — wires that panel's output into the real mission-creation flow
  // instead of it staying a disconnected local nanostore.
  useEffect(() => {
    if (!localRepository) return;
    setForm((current) => ({
      ...current,
      name: current.name || `local: ${localRepository.name}`,
      repositoryRef: current.repositoryRef || localRepository.name,
      grantedBy: current.grantedBy || localRepository.authorizedBy,
    }));
  }, [localRepository]);

  const liveState = liveSnapshot.state ?? missionDetail?.state ?? null;
  const allowedTransitions = missionDetail?.allowed_transitions ?? [];
  const canStart = allowedTransitions.includes('VALIDATING');
  const canPause = allowedTransitions.includes('PAUSED');
  const canCancel = allowedTransitions.includes('CANCELLING') || (!!activeMissionId && liveState !== 'CANCELLED');
  const isPausedWithNoResumeRoute = liveState === 'PAUSED';

  async function refreshMissionDetail(missionId: string): Promise<MissionDetail | null> {
    try {
      const detail = await getMissionDetail(missionId);
      setMissionDetail(detail);
      return detail;
    } catch {
      return null;
    }
  }

  function updateStep(key: StepKey, status: StepStatus, detail: string): void {
    setSteps((current) => current.map((step) => (step.key === key ? { key, status, detail } : step)));
  }

  async function runCreationFlow(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const errors = validateForm(form);
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) {
      return;
    }

    setBusy(true);
    setLastError(null);
    setSteps(initialSteps());
    setPreflight(null);

    try {
      updateStep('CREATE', 'running', '');
      const mission = await createMission({
        name: form.name.trim(),
        repository_ref: form.repositoryRef.trim(),
        adapter: form.adapter,
        idempotency_key: crypto.randomUUID(),
      });
      updateStep('CREATE', 'ok', `mission ${mission.id.slice(0, 8)} created`);

      updateStep('AUTHORIZE', 'running', '');
      await authorizeMission(mission.id, {
        statement: form.statement.trim(),
        granted_by: form.grantedBy.trim(),
        repository_ref: form.repositoryRef.trim(),
        valid_for_minutes: form.validForMinutes,
      });
      updateStep('AUTHORIZE', 'ok', `granted by ${sanitizeDisplayText(form.grantedBy.trim(), { maxLength: 120 })}`);

      updateStep('SNAPSHOT', 'running', '');
      const snapshotRecord = await snapshotLocalRepository(mission.id);
      updateStep(
        'SNAPSHOT',
        'ok',
        `${snapshotRecord.file_count} files, ${snapshotRecord.bytes_total} bytes, sha256 ${snapshotRecord.archive_sha256.slice(0, 12)}…`,
      );

      updateStep('PREFLIGHT', 'running', '');
      const report = await preflightMission(mission.id);
      setPreflight(report);
      updateStep(
        'PREFLIGHT',
        report.passed ? 'ok' : 'warn',
        report.passed
          ? `${report.checks.length} checks passed`
          : `blocked: ${(report.blocking_codes ?? []).join(', ') || 'see checks below'}`,
      );

      setActiveMissionId(mission.id);
      await refreshMissionDetail(mission.id);
    } catch (error) {
      const info = describeApiError(error);
      setLastError(info);
      const runningStep = steps.find((step) => step.status === 'running');
      updateStep(runningStep?.key ?? 'CREATE', 'fail', info.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleStart(): Promise<void> {
    if (!activeMissionId) return;
    setBusy(true);
    setLastError(null);
    try {
      await startMission(activeMissionId, { confirm_authorized: true });
      await refreshMissionDetail(activeMissionId);
    } catch (error) {
      setLastError(describeApiError(error));
    } finally {
      setBusy(false);
      setConfirmAction(null);
    }
  }

  async function handlePause(): Promise<void> {
    if (!activeMissionId) return;
    setBusy(true);
    setLastError(null);
    try {
      await pauseMission(activeMissionId, { reason: 'operator requested pause from the Command Center' });
      await refreshMissionDetail(activeMissionId);
    } catch (error) {
      setLastError(describeApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function handleCancel(emergency: boolean): Promise<void> {
    if (!activeMissionId) return;
    setBusy(true);
    setLastError(null);
    try {
      await cancelMission(activeMissionId, {
        confirm: true,
        reason: emergency
          ? 'operator-triggered emergency teardown from the Command Center'
          : 'operator cancelled the mission from the Command Center',
      });
      await refreshMissionDetail(activeMissionId);
    } catch (error) {
      setLastError(describeApiError(error));
    } finally {
      setBusy(false);
      setConfirmAction(null);
    }
  }

  function startNewMission(): void {
    setActiveMissionId(null);
    setMissionDetail(null);
    setPreflight(null);
    setSteps(initialSteps());
    setLastError(null);
    setForm(defaultForm());
  }

  const repositoryRefDisplay = sanitizeDisplayText(form.repositoryRef || missionDetail?.repository_ref || '', {
    fallback: 'not set',
    maxLength: 200,
  });

  const launchConsequence = useMemo(() => {
    const snapshotHash = missionDetail?.snapshot?.archive_sha256?.slice(0, 16) ?? 'unknown';
    return `Starts the autonomous workflow against ${repositoryRefDisplay} at snapshot ${snapshotHash}…, egress denied for the whole run. This begins real sandboxed execution.`;
  }, [missionDetail, repositoryRefDisplay]);

  return (
    <section className="bd-mission-control" aria-labelledby="mission-control-title">
      <h2 id="mission-control-title" className="bd-panel-title">
        [ MISSION CONTROL ]
      </h2>

      {!activeMissionId && (
        <form className="bd-form" onSubmit={runCreationFlow} noValidate>
          <p className="bd-form-lede">
            Point the Command Center at an authorized target. The repository reference must
            resolve to a directory the Control API host already has under its snapshot source
            allowlist (for example <code>pktcfg</code> for the bundled demo repository).
          </p>

          <label className="bd-field">
            <span>[ MISSION NAME ]</span>
            <input
              type="text"
              value={form.name}
              maxLength={200}
              disabled={busy}
              onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
              aria-invalid={Boolean(fieldErrors.name)}
            />
            {fieldErrors.name && <em className="bd-field-error">{fieldErrors.name}</em>}
          </label>

          <label className="bd-field">
            <span>[ REPOSITORY REF ]</span>
            <input
              type="text"
              value={form.repositoryRef}
              maxLength={500}
              disabled={busy}
              placeholder="pktcfg"
              onChange={(event) => setForm((current) => ({ ...current, repositoryRef: event.target.value }))}
              aria-invalid={Boolean(fieldErrors.repositoryRef)}
            />
            {fieldErrors.repositoryRef && <em className="bd-field-error">{fieldErrors.repositoryRef}</em>}
          </label>

          <label className="bd-field">
            <span>[ ADAPTER ]</span>
            <select
              value={form.adapter}
              disabled={busy}
              onChange={(event) => setForm((current) => ({ ...current, adapter: event.target.value as LanguageAdapter }))}
            >
              {ADAPTER_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="bd-field">
            <span>[ GRANTED BY ]</span>
            <input
              type="text"
              value={form.grantedBy}
              maxLength={200}
              disabled={busy}
              placeholder="named human accountable for this authorization"
              onChange={(event) => setForm((current) => ({ ...current, grantedBy: event.target.value }))}
              aria-invalid={Boolean(fieldErrors.grantedBy)}
            />
            {fieldErrors.grantedBy && <em className="bd-field-error">{fieldErrors.grantedBy}</em>}
          </label>

          <label className="bd-field">
            <span>[ VALID FOR MINUTES ]</span>
            <input
              type="number"
              min={1}
              max={1440}
              value={form.validForMinutes}
              disabled={busy}
              onChange={(event) => setForm((current) => ({ ...current, validForMinutes: Number(event.target.value) }))}
              aria-invalid={Boolean(fieldErrors.validForMinutes)}
            />
            {fieldErrors.validForMinutes && <em className="bd-field-error">{fieldErrors.validForMinutes}</em>}
          </label>

          <label className="bd-field bd-field--wide">
            <span>[ AUTHORIZATION STATEMENT ]</span>
            <textarea
              value={form.statement}
              maxLength={4000}
              rows={3}
              disabled={busy}
              placeholder="Operator's declaration of authority and scope over this repository (minimum 20 characters)."
              onChange={(event) => setForm((current) => ({ ...current, statement: event.target.value }))}
              aria-invalid={Boolean(fieldErrors.statement)}
            />
            {fieldErrors.statement && <em className="bd-field-error">{fieldErrors.statement}</em>}
          </label>

          <button type="submit" className="bd-bracket-control bd-bracket-control--primary" disabled={busy}>
            [ {busy ? 'WORKING…' : 'CREATE + AUTHORIZE + SNAPSHOT'} ]
          </button>
        </form>
      )}

      {(activeMissionId || steps.some((step) => step.status !== 'pending')) && (
        <ol className="bd-step-log" aria-label="Mission creation steps">
          {steps.map((step) => (
            <li key={step.key} className={`bd-step-log__row bd-step-log__row--${step.status}`}>
              <span className="bd-glyph" aria-hidden="true">
                {GLYPH[step.status]}
              </span>
              <span className="bd-step-log__label">
                [ {step.key} · {STATUS_WORD[step.status]} ]
              </span>
              <span className="bd-step-log__detail">{step.detail}</span>
            </li>
          ))}
        </ol>
      )}

      {preflight && (
        <div className="bd-preflight">
          <p className="bd-panel-title">
            [ PREFLIGHT · {preflight.passed ? 'PASS' : 'BLOCKED'} ]
          </p>
          <ul>
            {preflight.checks.map((check) => (
              <li key={check.name} className={check.passed ? 'bd-check--ok' : 'bd-check--fail'}>
                [ {check.passed ? '+' : '×'} {sanitizeDisplayText(check.name, { maxLength: 120 })} ]{' '}
                {check.detail && <span>{sanitizeDisplayText(check.detail, { maxLength: 240 })}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {lastError && (
        <p className="bd-alert-line" role="alert">
          [ × {lastError.code} ] {lastError.message}
          {lastError.traceId && <span> · trace {lastError.traceId}</span>}
        </p>
      )}

      {activeMissionId && (
        <div className="bd-controls">
          <p className="bd-mission-id">
            [ MISSION {activeMissionId.slice(0, 8)} · {sanitizeDisplayText(liveState ?? 'UNKNOWN', { maxLength: 40 })} ]
          </p>

          <div className="bd-control-row">
            <button
              type="button"
              className="bd-bracket-control"
              disabled={busy || !canStart}
              onClick={() => setConfirmAction('launch')}
            >
              [ START MISSION ]
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
              className="bd-bracket-control bd-bracket-control--critical"
              disabled={busy}
              onClick={() => setConfirmAction('teardown')}
            >
              [ EMERGENCY TEARDOWN ]
            </button>
            <button type="button" className="bd-bracket-control" disabled={busy} onClick={startNewMission}>
              [ NEW MISSION ]
            </button>
          </div>

          {isPausedWithNoResumeRoute && (
            <p className="bd-note">
              Mission is paused. No resume endpoint exists on the Control API yet (contract gap —
              see handoff); cancel and start a new mission to continue.
            </p>
          )}
        </div>
      )}

      {confirmAction === 'launch' && (
        <ConfirmDialog
          title={`Start mission ${activeMissionId?.slice(0, 8) ?? ''}.`}
          consequence={launchConsequence}
          confirmLabel="START"
          busy={busy}
          onConfirm={handleStart}
          onCancel={() => setConfirmAction(null)}
        />
      )}

      {confirmAction === 'cancel' && (
        <ConfirmDialog
          title={`Cancel mission ${activeMissionId?.slice(0, 8) ?? ''}.`}
          consequence="The sandbox is destroyed and any unexported evidence is lost. This cannot be undone."
          confirmLabel="CANCEL MISSION"
          destructive
          busy={busy}
          onConfirm={() => handleCancel(false)}
          onCancel={() => setConfirmAction(null)}
        />
      )}

      {confirmAction === 'teardown' && (
        <ConfirmDialog
          title="Emergency teardown."
          consequence="Every held resource for this mission — sandbox and model-host lease — is torn down immediately and any unexported evidence is lost. This cannot be undone."
          confirmLabel="EMERGENCY TEARDOWN"
          destructive
          busy={busy}
          onConfirm={() => handleCancel(true)}
          onCancel={() => setConfirmAction(null)}
        />
      )}
    </section>
  );
}
