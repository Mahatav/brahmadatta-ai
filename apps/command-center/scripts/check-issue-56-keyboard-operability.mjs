import { readFile, readdir } from 'node:fs/promises';
import path from 'node:path';

// Regression test for #56 (keyboard operability of the Command Center, D-059
// `docs/09-company/13-cut-pullback-design-spec.md` §3). Guards:
//   1. The shared focus-trap primitive exists and both modal-shaped overlays (`ConfirmDialog`,
//      `CandidateCompareOverlay`) actually use it, and both restore focus to whichever control
//      opened them on close — a deliberate, escapable trap, not the "no keyboard trap in any
//      panel" violation the acceptance criteria forbid.
//   2. The one genuinely CSS-scrollable region with no focusable child of its own
//      (`.bd-diff__body`, §3.2) is a real tab stop.
//   3. Focus is always visible — the base `:focus-visible` rule in tokens.css is intact.
//   4. The keyboard-operability test harness stays behind its own build-time flag, off by
//      default, the same mechanism #52's presentation mode already established and is verified
//      the same way (`check-keyboard-harness-exclusion.sh` runs the real build; this only checks
//      the source-level wiring, cheaply, on every `npm run check`).
//   5. No component under `src/components/` attaches a click handler to a bare, non-interactive
//      `<div>`/`<span>` without a `role` — the acceptance criterion's own wording ("real
//      `<button>`/`<a>` elements ... not synthetic click-handlers on `<div>`s").

const appRoot = path.resolve(import.meta.dirname, '..');
const componentsDir = path.join(appRoot, 'src/components');
const focusTrapPath = path.join(appRoot, 'src/lib/a11y/focusTrap.ts');
const confirmDialogPath = path.join(componentsDir, 'ConfirmDialog.tsx');
const compareOverlayPath = path.join(componentsDir, 'CandidateCompareOverlay.tsx');
const tokensPath = path.resolve(appRoot, '../../packages/ui-components/tokens.css');
const astroConfigPath = path.join(appRoot, 'astro.config.mjs');

async function main() {
  const [focusTrap, confirmDialog, compareOverlay, tokens, astroConfig] = await Promise.all([
    readFile(focusTrapPath, 'utf8'),
    readFile(confirmDialogPath, 'utf8'),
    readFile(compareOverlayPath, 'utf8'),
    readFile(tokensPath, 'utf8'),
    readFile(astroConfigPath, 'utf8'),
  ]);

  assertFocusTrapPrimitive(focusTrap);
  assertConfirmDialogTrapsAndRestoresFocus(confirmDialog);
  assertCompareOverlayTrapsAndRestoresFocus(compareOverlay);
  assertDiffBodyIsATabStop(compareOverlay);
  assertFocusRingTokenIntact(tokens);
  assertKeyboardHarnessOffByDefault(astroConfig);
  await assertNoDivClickHandlersWithoutRole();

  console.warn(
    'keyboard operability (#56) ok: shared focus trap used by both overlays, focus restored to ' +
      'opener on close, the diff scroll region is a real tab stop, the base focus ring is ' +
      'intact, the keyboard harness stays behind its own off-by-default build flag, and no ' +
      'component attaches a click handler to a bare div/span',
  );
}

function assertFocusTrapPrimitive(focusTrap) {
  assert(focusTrap.includes('export function trapTabKey'), 'trapTabKey must be exported for both overlays to share');
  assert(focusTrap.includes('export function getFocusableElements'), 'getFocusableElements must be exported');
  assert(focusTrap.includes("event.key !== 'Tab'"), 'trapTabKey must no-op for every key other than Tab');
  assert(focusTrap.includes('event.shiftKey'), 'trapTabKey must distinguish Tab from Shift+Tab to wrap at the correct boundary');
}

function assertConfirmDialogTrapsAndRestoresFocus(confirmDialog) {
  assert(confirmDialog.includes("import { trapTabKey } from '../lib/a11y/focusTrap'"), 'ConfirmDialog must use the shared focus trap, not a bespoke one');
  assert(confirmDialog.includes('trapTabKey(dialogRef.current, event)'), 'ConfirmDialog must call trapTabKey on its own dialog element while open');
  assert(confirmDialog.includes('openerRef.current = document.activeElement'), 'ConfirmDialog must capture the control that opened it');
  assert(confirmDialog.includes('openerRef.current?.focus()'), 'ConfirmDialog must restore focus to the opener when it closes (D-059 §3.3)');
  assert(confirmDialog.includes("event.key === 'Escape'"), 'Escape must still dismiss the dialog without performing the destructive action');
  assert(confirmDialog.includes('cancelRef.current?.focus()'), 'the safe Cancel button, never the destructive one, must be the default focus target (§2.7)');
}

function assertCompareOverlayTrapsAndRestoresFocus(compareOverlay) {
  assert(compareOverlay.includes("import { trapTabKey } from '../lib/a11y/focusTrap'"), 'CandidateCompareOverlay must use the shared focus trap, not a bespoke one');
  assert(compareOverlay.includes('trapTabKey(dialogRef.current, event)'), 'CandidateCompareOverlay must call trapTabKey on its own dialog element while open');
  assert(compareOverlay.includes('returnFocusRef.current?.focus()'), 'CandidateCompareOverlay must restore focus to whatever opened it when it closes (D-059 §3.4)');
  assert(compareOverlay.includes("event.key === 'Escape'"), 'Escape must still close the overlay');
  assert(compareOverlay.includes('closeRef.current?.focus()'), '[ ESC CLOSE ] must be the default focus target on open, per the design spec’s own layout');
  assert((compareOverlay.match(/ref={dialogRef}/g) ?? []).length === 1, 'exactly one element wired as the trap boundary — the overlay’s own root, not a nested one');
}

function assertDiffBodyIsATabStop(compareOverlay) {
  const match = compareOverlay.match(/<ol\s+className="bd-diff__body"[\s\S]*?>/);
  assert(match, 'the diff body <ol> is missing or was restructured — update this check');
  assert(match[0].includes('tabIndex={0}'), '.bd-diff__body is CSS-scrollable (max-height + overflow-y: auto) with no focusable child of its own; it must be a real tab stop (D-059 §3.2)');
  assert(match[0].includes('role="region"'), '.bd-diff__body must carry role="region" alongside its existing aria-label, per D-059 §3.2');
}

function assertFocusRingTokenIntact(tokens) {
  assert(tokens.includes('--bd-focus-ring:'), 'the --bd-focus-ring token must still exist');
  assert(/:focus-visible\s*\{[^}]*outline:\s*var\(--bd-rule-heavy\)\s*solid\s*var\(--bd-focus-ring\)/.test(tokens), 'the base :focus-visible rule must still apply the focus-ring token as a visible outline, not just a colour change');
}

function assertKeyboardHarnessOffByDefault(astroConfig) {
  assert(astroConfig.includes("process.env.BD_KEYBOARD_HARNESS_BUILD === 'true'"), 'the keyboard harness must be gated behind an explicit, off-by-default env flag, mirroring #52’s presentation-mode exclusion');
  assert(astroConfig.includes('keyboardHarnessBuild ? keyboardHarnessIntegration() : undefined'), 'the harness route must only be injected when the flag is true');
}

async function assertNoDivClickHandlersWithoutRole() {
  const files = await readdir(componentsDir);
  for (const file of files) {
    if (!file.endsWith('.tsx')) {
      continue;
    }
    const filePath = path.join(componentsDir, file);
    const source = await readFile(filePath, 'utf8');
    // The overlay/dialog scrims are the one legitimate exception: a `role="presentation"`
    // click-to-dismiss backdrop, which is explicitly not part of the tab order (it has no
    // interactive semantics of its own — dismissal is also always reachable via a real button
    // and Escape). Everything else must be a real interactive element.
    const withoutScrims = source.replace(/<div className="bd-(?:overlay-scrim|confirm-scrim)"[^]*?onClick={onC(?:lose|ancel)}/g, '');
    const match = withoutScrims.match(/<(div|span)\b(?![^>]*role=)[^>]*onClick=/i);
    assert(!match, `${file} attaches an onClick to a <div>/<span> with no role — must be a real <button>/<a>, or carry an explicit role: ${match?.[0]}`);
  }
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
