import { useEffect, useRef } from 'react';

import { trapTabKey } from '../lib/a11y/focusTrap';

/**
 * `ConfirmationDialog` — kept in the P0 component inventory (design-system doc §11), required
 * for every destructive control (§2.7): "Destructive controls … require a confirmation dialog
 * naming the consequence in a full sentence, and render their label in `--bd-state-critical`.
 * They are never the default focus target." Shared here because `MissionControlPanel` uses it
 * three times (launch, cancel, emergency teardown) — one primitive, not three ad hoc dialogs.
 *
 * #56 / D-059 §3.3 — the confirm dialog is a deliberate, escapable focus trap: `Tab`/`Shift+Tab`
 * cycle only between its own two buttons while it is open (`trapTabKey`, shared with
 * `CandidateCompareOverlay`), and `Escape` — or either button — always returns focus to
 * whichever control opened the dialog, the same overlay-return rule design system §9 already
 * establishes for every overlay in this app.
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
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const openerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    // Capture the control that opened this dialog before moving focus onto the dialog's own
    // safe default, so it can be restored the moment the dialog closes — by Escape, by Cancel,
    // or by Confirm succeeding.
    openerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    // Never the default focus target (§2.7) — focus lands on the safe action, not the one
    // being confirmed.
    cancelRef.current?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onCancel();
        return;
      }
      if (dialogRef.current) {
        trapTabKey(dialogRef.current, event);
      }
    }
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      openerRef.current?.focus();
    };
  }, [onCancel]);

  return (
    <div className="bd-confirm-scrim" role="presentation" onClick={onCancel}>
      <div
        ref={dialogRef}
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
