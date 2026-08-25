// #56 — real, keyboard-driven verification against real Chromium (Playwright), not the
// sandboxed MCP browser tool (documented in this session as unable to reach localhost here).
// Standalone node script, matching this codebase's established pattern for anything that needs
// a real browser rather than the check-*.mjs static-source-assertion style.
//
// Two real dev servers are started (never `npm run build`'s finale artifact — this drives real
// interactive state, not a static export):
//   1. The plain app (no flags) on PORT_MAIN — idle/no-mission state. Every P0 control that is
//      reachable without a live backend (the whole pre-mission setup drawer) is walked with
//      real Tab/Shift+Tab keypresses, confirming DOM order matches visual order and that
//      `:focus-visible` renders a real, non-`none` outline at every stop.
//   2. The #56 keyboard-operability harness (`BD_KEYBOARD_HARNESS_BUILD=true`) on
//      PORT_HARNESS — mounts the real `ConfirmDialog`/`CandidateCompareOverlay` components with
//      deterministic mock data (two verified/rejected candidates) so the focus trap can be
//      driven for real: opened via keyboard, `Tab`/`Shift+Tab` confirmed to wrap only at the
//      dialog's own boundaries (never escaping into the harness page behind it), `Escape`
//      confirmed to close and return focus to the exact control that opened it.
//
// Screenshots are written to `scripts/.keyboard-verification/` as evidence.

import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';

const PORT_MAIN = 4331;
const PORT_HARNESS = 4332;
const SCREENSHOT_DIR = path.resolve(import.meta.dirname, '.keyboard-verification');

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

async function main() {
  await mkdir(SCREENSHOT_DIR, { recursive: true });

  // Astro 7 refuses a second concurrent `astro dev` against the same project directory (a
  // project-level lock file, independent of port) — so the two servers this script needs run
  // sequentially, one stopped before the next starts, rather than side by side.
  const browser = await chromium.launch();
  try {
    const mainServer = await startDevServer(PORT_MAIN, {});
    try {
      await verifyIdleStateTabOrder(browser, PORT_MAIN);
    } finally {
      await stopDevServer(mainServer);
    }

    const harnessServer = await startDevServer(PORT_HARNESS, { BD_KEYBOARD_HARNESS_BUILD: 'true' });
    try {
      await verifyConfirmDialogFocusTrap(browser, PORT_HARNESS);
      await verifyCandidateCompareFocusTrap(browser, PORT_HARNESS);
    } finally {
      await stopDevServer(harnessServer);
    }
  } finally {
    await browser.close();
  }

  console.warn('\nverify-keyboard-operability: ALL PASS');
}

// ---------------------------------------------------------------------------
// Section A — idle-state tab order + visible focus, real dev server, no backend needed.
// ---------------------------------------------------------------------------

async function verifyIdleStateTabOrder(browser, port) {
  console.warn('\n== idle-state tab order (no active mission) ==');
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: 'networkidle' });

  // §3.1's real, current tab order for the idle/no-mission state: the setup drawer's own
  // <summary>, then LocalRepositoryIntake's controls, then MissionControlPanel's form fields.
  // Nothing in the frozen frame (TopStrip, StageTimeline, Core, VerdictPanel, FindingsRail,
  // BottomStrip) is focusable with no active mission — every BottomStrip control is `disabled`,
  // which real browsers correctly skip.
  //
  // `[ CHOOSE BROWSER FOLDER ]`'s real `<input type="file">` is itself `disabled` until the
  // operator has both typed a name AND checked the authorization box (`canPick`,
  // `LocalRepositoryIntake.tsx`) — correctly and deliberately absent from the pristine tab
  // order below, not a bug. It is exercised right after, exactly where the design intends: only
  // reachable once those two keyboard actions actually unlock it.
  const pristineSequence = [
    { tag: 'SUMMARY', text: 'MISSION SETUP' },
    { tag: 'INPUT' }, // HUMAN
    { tag: 'INPUT' }, // LOCAL PATH
    { tag: 'INPUT', type: 'checkbox' },
  ];

  const actual = [];
  for (let index = 0; index < pristineSequence.length; index += 1) {
    await page.keyboard.press('Tab');
    const stop = await describeActiveElement(page);
    actual.push(stop);
    assert(stop.tag !== 'BODY', `Tab stop ${index + 1} landed on <body> — focus was lost, not advanced (expected ${JSON.stringify(pristineSequence[index])})`);
    assert(stop.outlineVisible, `Tab stop ${index + 1} (${stop.tag} "${stop.text}") has no visible :focus-visible outline — got outline "${stop.outline}"`);
    if (index === 1) {
      // On the HUMAN field — type a real name via the keyboard, exactly as an operator would,
      // so the file-picker's disabled gate lifts for the section below.
      await page.keyboard.type('QA Operator');
    }
  }
  assertSequenceMatches(pristineSequence, actual, 'pristine setup drawer');
  console.warn(`PASS: ${pristineSequence.length} tab stops matched real DOM/visual order, every stop had a visible focus outline`);
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '01-idle-checkbox-focus-before-check.png') });

  // Check the box with Space — native semantics, no click, no synthetic handler — which is the
  // second half of `canPick` and unlocks the file input tested next.
  const checkboxStop = await describeActiveElement(page);
  assert(checkboxStop.type === 'checkbox', `expected to still be on the checkbox, got ${checkboxStop.tag} type=${checkboxStop.type}`);
  await page.keyboard.press('Space');
  const checked = await page.evaluate(() => document.activeElement instanceof HTMLInputElement && document.activeElement.checked);
  assert(checked, 'Space on a focused checkbox must toggle it — native semantics, no synthetic handler needed');
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '02-idle-checkbox-checked.png') });
  console.warn('PASS: Space toggles the authorization checkbox via native semantics');

  // Continue forward: DEV PATH SCAN -> CHOOSE BROWSER FOLDER (now enabled) -> the six
  // MissionControlPanel fields -> the submit button.
  const restOfSequence = [
    { tag: 'BUTTON', text: 'DEV PATH SCAN' },
    { tag: 'INPUT', type: 'file' }, // CHOOSE BROWSER FOLDER — now enabled
    { tag: 'INPUT' }, // MISSION NAME
    { tag: 'INPUT' }, // REPOSITORY REF
    { tag: 'SELECT' }, // ADAPTER
    { tag: 'INPUT' }, // GRANTED BY
    { tag: 'INPUT', type: 'number' }, // VALID FOR MINUTES
    { tag: 'TEXTAREA' }, // AUTHORIZATION STATEMENT
    { tag: 'BUTTON', text: 'CREATE + AUTHORIZE + SNAPSHOT' },
  ];
  const actualRest = [];
  for (let index = 0; index < restOfSequence.length; index += 1) {
    await page.keyboard.press('Tab');
    const stop = await describeActiveElement(page);
    actualRest.push(stop);
    assert(stop.tag !== 'BODY', `Tab stop ${index + 1} (post-checkbox) landed on <body> — focus was lost (expected ${JSON.stringify(restOfSequence[index])})`);
    assert(stop.outlineVisible, `Tab stop ${index + 1} (post-checkbox, ${stop.tag} "${stop.text}") has no visible :focus-visible outline — got outline "${stop.outline}"`);
    if (index === 1) {
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, '03-idle-file-picker-now-enabled-focus.png') });
    }
    if (index === 2) {
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, '04-idle-mission-name-focus.png') });
    }
  }
  assertSequenceMatches(restOfSequence, actualRest, 'mission control form, once unlocked');
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '05-idle-submit-focus.png') });
  console.warn(`PASS: ${restOfSequence.length} further tab stops matched real DOM/visual order, including the now-unlocked file picker, every stop had a visible focus outline`);
  console.warn(`Screenshots written to ${SCREENSHOT_DIR}`);

  await page.close();
}

/** Asserts tag/type/text against a captured stop sequence — real DOM-order/visual-order
 * regression coverage (§3.1, §9): a field reordered, or a button relabelled without updating
 * this test, fails loudly rather than silently passing. */
function assertSequenceMatches(expectedSequence, actualSequence, label) {
  for (let index = 0; index < expectedSequence.length; index += 1) {
    const expected = expectedSequence[index];
    const got = actualSequence[index];
    assert(got.tag === expected.tag, `${label}, stop ${index + 1}: expected <${expected.tag}>, got <${got.tag}> ("${got.text}")`);
    if (expected.type) {
      assert(got.type === expected.type, `${label}, stop ${index + 1}: expected type="${expected.type}", got "${got.type}"`);
    }
    if (expected.text) {
      assert(got.text.includes(expected.text), `${label}, stop ${index + 1}: expected text containing "${expected.text}", got "${got.text}"`);
    }
  }
}

// ---------------------------------------------------------------------------
// Section B — ConfirmDialog: deliberate, escapable focus trap.
// ---------------------------------------------------------------------------

async function verifyConfirmDialogFocusTrap(browser, port) {
  console.warn('\n== ConfirmDialog focus trap (#56 keyboard harness) ==');
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(`http://127.0.0.1:${port}/__dev/keyboard-harness`, { waitUntil: 'networkidle' });

  const openButton = page.getByRole('button', { name: '[ OPEN CONFIRM DIALOG ]' });
  await openButton.focus();
  await assertVisibleOutline(page, 'the [ OPEN CONFIRM DIALOG ] trigger');
  await page.keyboard.press('Enter');

  const dialog = page.locator('.bd-confirm-dialog');
  await dialog.waitFor({ state: 'visible' });

  let active = await describeActiveElement(page);
  assert(active.text.includes('CANCEL'), `default focus on open must be the safe [ CANCEL ] button, got "${active.text}"`);
  await assertVisibleOutline(page, 'the dialog’s default-focused [ CANCEL ] button');
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '06-confirm-dialog-open-focus.png') });

  // Forward wrap: Tab from CANCEL -> destructive CONFIRM button (2 controls total) -> Tab again
  // must wrap back to CANCEL, never escape to the harness page's own buttons behind the scrim.
  await page.keyboard.press('Tab');
  active = await describeActiveElement(page);
  assert(active.text.includes('CANCEL MISSION'), `Tab from CANCEL must reach the destructive confirm button, got "${active.text}"`);
  assert(active.insideDialog, 'focus left the dialog on a plain Tab press — that is a background focus leak');

  await page.keyboard.press('Tab');
  active = await describeActiveElement(page);
  assert(active.text.includes('CANCEL') && !active.text.includes('CANCEL MISSION'), `Tab from the last control must WRAP to [ CANCEL ], got "${active.text}" — the trap boundary is missing`);
  assert(active.insideDialog, 'wrapped focus landed outside the dialog');

  // Backward wrap: Shift+Tab from CANCEL (first) -> destructive button (last).
  await page.keyboard.press('Shift+Tab');
  active = await describeActiveElement(page);
  assert(active.text.includes('CANCEL MISSION'), `Shift+Tab from the first control must WRAP to the last (destructive) control, got "${active.text}"`);
  console.warn('PASS: Tab/Shift+Tab cycle strictly between the dialog’s own two controls, wrapping at both boundaries');

  // Escape releases the trap and returns focus to the exact control that opened it — the
  // deliberate, escapable trap #56’s acceptance criteria require, not a keyboard trap.
  await page.keyboard.press('Escape');
  await dialog.waitFor({ state: 'hidden' });
  active = await describeActiveElement(page);
  assert(active.text.includes('OPEN CONFIRM DIALOG'), `Escape must return focus to the [ OPEN CONFIRM DIALOG ] opener, got "${active.text}"`);
  await assertVisibleOutline(page, 'the opener, after Escape released the trap');
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '07-confirm-dialog-closed-focus-returned.png') });
  console.warn('PASS: Escape closes the dialog without confirming the destructive action, and returns focus to the opener');

  await page.close();
}

// ---------------------------------------------------------------------------
// Section C — CandidateCompareOverlay: deliberate, escapable focus trap.
// ---------------------------------------------------------------------------

async function verifyCandidateCompareFocusTrap(browser, port) {
  console.warn('\n== CandidateCompareOverlay focus trap (#56 keyboard harness) ==');
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(`http://127.0.0.1:${port}/__dev/keyboard-harness`, { waitUntil: 'networkidle' });

  const openButton = page.getByRole('button', { name: '[ OPEN CANDIDATE COMPARE ]' });
  await openButton.focus();
  await page.keyboard.press('Enter');

  const overlay = page.locator('.bd-overlay[role="dialog"]');
  await overlay.waitFor({ state: 'visible' });

  let active = await describeActiveElement(page);
  assert(active.text.includes('ESC CLOSE'), `default focus on open must be [ ESC CLOSE ], got "${active.text}"`);
  await assertVisibleOutline(page, 'the overlay’s default-focused [ ESC CLOSE ] button');
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '08-candidate-compare-open-focus.png') });

  // Ground truth: every focusable element actually inside the overlay, in real DOM order —
  // this is what the trap is supposed to cycle through, computed the same way `focusTrap.ts`
  // computes it, so this test does not hardcode a brittle count that silently stops meaning
  // anything the next time the overlay's content changes.
  const focusableInOverlay = await page.evaluate((selector) => {
    const overlayEl = document.querySelector('.bd-overlay[role="dialog"]');
    return Array.from(overlayEl.querySelectorAll(selector)).map((el) => el.textContent?.trim().slice(0, 40) ?? el.tagName);
  }, FOCUSABLE_SELECTOR);
  assert(focusableInOverlay.length >= 2, `expected multiple focusable elements inside the compare overlay (diff scroll regions + disclosure buttons), got ${focusableInOverlay.length}: ${JSON.stringify(focusableInOverlay)}`);
  console.warn(`overlay focusable elements in DOM order: ${JSON.stringify(focusableInOverlay)}`);

  // Walk forward via real Tab presses through the whole set, confirming (a) every stop stays
  // inside the overlay — no background focus leak into the harness page behind the scrim — and
  // (b) the final Tab press wraps back to the first element rather than escaping.
  for (let i = 1; i < focusableInOverlay.length; i += 1) {
    await page.keyboard.press('Tab');
    active = await describeActiveElement(page);
    assert(active.insideOverlay, `Tab stop ${i + 1} inside Candidate Compare left the overlay (background focus leak) — landed on "${active.text}"`);
    assert(active.outlineVisible, `Tab stop ${i + 1} inside Candidate Compare has no visible focus outline`);
  }
  await page.keyboard.press('Tab'); // one more than the element count -> must wrap
  active = await describeActiveElement(page);
  assert(active.text.includes('ESC CLOSE'), `Tab past the last focusable element must WRAP to [ ESC CLOSE ], got "${active.text}" — the trap boundary is missing`);
  console.warn(`PASS: Tab cycles through all ${focusableInOverlay.length} of the overlay's own focusable elements and wraps back to [ ESC CLOSE ] without ever leaking focus into the page behind it`);

  // Backward wrap: Shift+Tab from [ ESC CLOSE ] (first) -> the last focusable element.
  await page.keyboard.press('Shift+Tab');
  active = await describeActiveElement(page);
  assert(!active.text.includes('ESC CLOSE'), 'Shift+Tab from the first control must WRAP to the last, not stay put');
  assert(active.insideOverlay, 'Shift+Tab wrap landed outside the overlay');
  console.warn('PASS: Shift+Tab from the first control wraps to the last');

  // Escape releases the trap and returns focus to the [ OPEN CANDIDATE COMPARE ] opener.
  await page.keyboard.press('Escape');
  await overlay.waitFor({ state: 'hidden' });
  active = await describeActiveElement(page);
  assert(active.text.includes('OPEN CANDIDATE COMPARE'), `Escape must return focus to the [ OPEN CANDIDATE COMPARE ] opener, got "${active.text}"`);
  await assertVisibleOutline(page, 'the opener, after Escape released the compare-overlay trap');
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '09-candidate-compare-closed-focus-returned.png') });
  console.warn('PASS: Escape closes the overlay and returns focus to the exact control that opened it');

  await page.close();
}

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

async function describeActiveElement(page) {
  return page.evaluate(() => {
    const el = document.activeElement;
    if (!el || el === document.body) {
      return { tag: 'BODY', text: '', type: null, outline: 'none', outlineVisible: false, insideDialog: false, insideOverlay: false };
    }
    const style = window.getComputedStyle(el);
    const outline = `${style.outlineStyle} ${style.outlineWidth} ${style.outlineColor}`;
    const outlineVisible = style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) > 0;
    const boxShadowVisible = style.boxShadow !== 'none' && style.boxShadow.length > 0;
    return {
      tag: el.tagName,
      text: (el.textContent || el.getAttribute('aria-label') || el.getAttribute('placeholder') || '').trim(),
      type: el.getAttribute('type'),
      outline,
      // A visible ring is either a real outline OR an equivalent box-shadow ring — this
      // codebase's base rule uses `outline`, so `outlineVisible` alone is expected true, but
      // both are computed so the check reflects what the task asked for ("outline/box-shadow").
      outlineVisible: outlineVisible || boxShadowVisible,
      insideDialog: Boolean(el.closest('.bd-confirm-dialog')),
      insideOverlay: Boolean(el.closest('.bd-overlay[role="dialog"]')),
    };
  });
}

async function assertVisibleOutline(page, description) {
  const active = await describeActiveElement(page);
  assert(active.outlineVisible, `${description}: expected a visible :focus-visible outline, computed outline was "${active.outline}"`);
}

async function startDevServer(port, extraEnv) {
  const appDir = path.resolve(import.meta.dirname, '..');
  const child = spawn('npx', ['astro', 'dev', '--port', String(port), '--host', '127.0.0.1', '--force'], {
    cwd: appDir,
    env: { ...process.env, ...extraEnv, ASTRO_TELEMETRY_DISABLED: '1' },
    stdio: 'pipe',
  });
  let output = '';
  child.stdout.on('data', (chunk) => { output += chunk; });
  child.stderr.on('data', (chunk) => { output += chunk; });
  child.on('exit', (code) => {
    if (code !== null && code !== 0) {
      console.error(`dev server on port ${port} exited early (code ${code}):\n${output}`);
    }
  });

  await waitForServer(`http://127.0.0.1:${port}/`, 60_000);
  return child;
}

async function stopDevServer(child) {
  child.kill();
  // Astro 7's own lock file is only reliably cleared by `astro dev stop`; a bare SIGTERM to the
  // child process can leave a stale lock behind that then blocks the next `astro dev` call in
  // this same script from starting at all.
  await new Promise((resolve) => {
    const stopper = spawn('npx', ['astro', 'dev', 'stop'], {
      cwd: path.resolve(import.meta.dirname, '..'),
      env: process.env,
      stdio: 'ignore',
    });
    stopper.on('exit', resolve);
    stopper.on('error', resolve);
  });
}

async function waitForServer(url, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok || response.status === 404) {
        return;
      }
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error(`server at ${url} did not become ready: ${lastError?.message ?? 'timeout'}`);
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

main().catch((error) => {
  console.error('\nverify-keyboard-operability: FAIL');
  console.error(error instanceof Error ? error.stack : error);
  process.exitCode = 1;
});
