/**
 * #56 — the modal focus trap shared by `ConfirmDialog` and `CandidateCompareOverlay`.
 *
 * D-059 §3.3/§3.4 (`docs/09-company/13-cut-pullback-design-spec.md`) requires every overlay
 * that is deliberately modal (the confirm dialog, the Candidate Compare overlay) to trap
 * `Tab`/`Shift+Tab` between its own focusable controls while it is open, and to release that
 * trap on close — a real, escapable focus scope, not the "no keyboard trap in any panel"
 * violation #56's acceptance criteria forbid. This module is the one place that boundary logic
 * lives, so both call sites implement it identically rather than two ad hoc copies drifting.
 *
 * Deliberately narrow: it only intervenes at the two wrap-around boundaries (`Tab` on the last
 * focusable element, `Shift+Tab` on the first). Every other `Tab` press is left entirely to the
 * browser's own native tab order — this never manages focus itself in the middle of the
 * sequence, so DOM order inside the dialog is still what determines tab order (§9's "tab order
 * matches visual order" rule keeps applying inside an overlay, not just outside one).
 */

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

export function getFocusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (element) => !element.hasAttribute('disabled') && element.getClientRects().length > 0,
  );
}

/**
 * Call from a `keydown` listener scoped to the open dialog/overlay. No-ops for any key other
 * than `Tab`. When the container has no focusable element at all, every `Tab` press is
 * swallowed (there is nowhere for focus to go inside the trap, and it must not leak out).
 */
export function trapTabKey(container: HTMLElement, event: KeyboardEvent): void {
  if (event.key !== 'Tab') {
    return;
  }

  const focusable = getFocusableElements(container);
  if (focusable.length === 0) {
    event.preventDefault();
    return;
  }

  const first = focusable[0]!;
  const last = focusable[focusable.length - 1]!;
  const active = document.activeElement;
  const activeIsInsideContainer = active instanceof Node && container.contains(active);

  if (event.shiftKey) {
    if (!activeIsInsideContainer || active === first) {
      event.preventDefault();
      last.focus();
    }
    return;
  }

  if (!activeIsInsideContainer || active === last) {
    event.preventDefault();
    first.focus();
  }
}
