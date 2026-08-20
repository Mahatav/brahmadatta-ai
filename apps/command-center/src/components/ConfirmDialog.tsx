import { useEffect, useRef } from 'react';

/**
 * `ConfirmationDialog` — kept in the P0 component inventory (design-system doc §11), required
 * for every destructive control (§2.7): "Destructive controls … require a confirmation dialog
 * naming the consequence in a full sentence, and render their label in `--bd-state-critical`.
 * They are never the default focus target." Shared here because `MissionControlPanel` uses it
 * three times (launch, cancel, emergency teardown) — one primitive, not three ad hoc dialogs.
 */
export function ConfirmDialog(props: {
  title: string;
  consequence: string;
  confirmLabel: string;
  destructive?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { title, consequence, confirmLabel, destructive = false, busy = false, onConfirm, onCancel } = props;
  const cancelRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    // Never the default focus target (§2.7) — focus lands on the safe action, not the one
    // being confirmed.
    cancelRef.current?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onCancel();
      }
    }
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onCancel]);

  return (
    <div className="bd-confirm-scrim" role="presentation" onClick={onCancel}>
      <div
        className="bd-confirm-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="bd-confirm-title"
        aria-describedby="bd-confirm-consequence"
        onClick={(event) => event.stopPropagation()}
      >
        <p id="bd-confirm-title" className="bd-confirm-title">
          {title}
        </p>
        <p id="bd-confirm-consequence" className="bd-confirm-consequence">
          {consequence}
        </p>
        <div className="bd-confirm-actions">
          <button ref={cancelRef} type="button" className="bd-bracket-control" onClick={onCancel} disabled={busy}>
            [ CANCEL ]
          </button>
          <button
            type="button"
            className={`bd-bracket-control${destructive ? ' bd-bracket-control--critical' : ''}`}
            onClick={onConfirm}
            disabled={busy}
          >
            [ {busy ? 'WORKING…' : confirmLabel} ]
          </button>
        </div>
      </div>
    </div>
  );
}
