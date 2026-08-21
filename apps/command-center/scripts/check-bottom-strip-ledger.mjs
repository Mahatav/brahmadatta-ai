import { readFile } from 'node:fs/promises';
import path from 'node:path';

// Regression test for the bottom strip's resource ledger and four controls
// (docs/09-company/04-design-system.md §6.6, DS-04, §3). Guards that EXPORT EVIDENCE is a real,
// newly-wired control against the already-typed client function (it did not exist as a UI
// control anywhere before this change), that PAUSE/CANCEL call the same tested client functions
// D-100 wired rather than a reimplementation, and that the ledger's roll-up never rounds up.

const appRoot = path.resolve(import.meta.dirname, '..');
const stripPath = path.join(appRoot, 'src/components/BottomStrip.tsx');
const ledgerPath = path.join(appRoot, 'src/components/ResourceLedger.tsx');
const cssPath = path.join(appRoot, 'src/styles/command-center-frame.css');

async function main() {
  const [strip, ledger, css] = await Promise.all([
    readFile(stripPath, 'utf8'),
    readFile(ledgerPath, 'utf8'),
    readFile(cssPath, 'utf8'),
  ]);

  assertFourControls(strip);
  assertExportEvidenceIsReal(strip);
  assertPauseCancelReuseTestedClient(strip);
  assertDestructiveConfirmation(strip);
  assertRollupNeverRoundsUp(ledger);
  assertReceiptNotIntention(ledger);
  assertControlHitTarget(css);

  console.warn('bottom strip + ledger ok: four real controls, export evidence wired, receipt-not-intention, 44px hit targets');
}

function assertFourControls(strip) {
  for (const label of ['[ OPEN COMPARE ]', '[ PAUSE ]', '[ CANCEL MISSION ]', '[ EXPORT EVIDENCE ]']) {
    assert(strip.includes(label), `bottom strip missing control: ${label}`);
  }
}

function assertExportEvidenceIsReal(strip) {
  assert(strip.includes('exportEvidence(activeMissionId'), 'EXPORT EVIDENCE must call the real POST /missions/{id}/export client function');
  assert(strip.includes('[ ● EXPORTING ]'), 'export must show the in-flight state (§4.1 row 11)');
  assert(strip.includes('[ + EXPORTED'), 'export success must name the produced artifacts');
  assert(strip.includes('[ × EXPORT FAILED ]'), 'export failure must surface the real error verbatim, control re-enabled');
  assert(strip.includes('receipt.artifacts'), 'the success state must read real artifact paths from the ExportReceipt, not a fabricated message');
}

function assertPauseCancelReuseTestedClient(strip) {
  assert(strip.includes("import { ApiError, cancelMission, exportEvidence, pauseMission"), (
    'PAUSE and CANCEL must call the same pauseMission/cancelMission client functions MissionControlPanel.tsx (D-100) already uses and tests cover — not a reimplementation'
  ));
}

function assertDestructiveConfirmation(strip) {
  assert(strip.includes('ConfirmDialog'), 'CANCEL MISSION must go through the shared ConfirmDialog primitive (§2.7)');
  assert(strip.includes('destructive'), 'CANCEL MISSION\'s dialog must render in the destructive/critical style');
  assert(strip.includes('cannot be undone'), 'the cancel confirmation must name the consequence in a full sentence (§2.7)');
}

function assertRollupNeverRoundsUp(ledger) {
  const body = bodyOfFunction(ledger, 'rollupText');
  assert(body.includes('released === known'), 'the roll-up must read N of N only when N real receipts exist, never assumed');
  assert(body.includes("'[ RESOURCES · — ]'"), 'nothing leased yet must render the not-measured state, never a fabricated zero');
}

function assertReceiptNotIntention(ledger) {
  assert(ledger.includes('resource.released'), 'a chip must read RELEASED only from a real receipt (`released: true`), never an intention');
  assert(ledger.includes('RELEASE FAILED'), 'a failed release must be a distinct, named, critical state');
}

function assertControlHitTarget(css) {
  const block = css.match(/\.bd-bottom-strip__controls\s*\{([\s\S]*?)\}/)?.[1] ?? '';
  assert(block.includes('var(--bd-control-h)'), 'the control row must use the 44px hit-target token (§2.7)');
}

// Finds a function's real body, correctly skipping over TypeScript destructured-parameter type
// annotations like `({ a }: { a: T })`, which contain `{`/`}` pairs that a naive
// first-brace-after-name search would mistake for the body itself.
function bodyOfFunction(source, name) {
  const start = source.indexOf(`function ${name}`);
  assert(start >= 0, `${name} is missing`);
  const parenStart = source.indexOf('(', start);
  assert(parenStart >= 0, `${name} has no parameter list`);
  let parenDepth = 0;
  let parenEnd = -1;
  for (let index = parenStart; index < source.length; index += 1) {
    const char = source[index];
    if (char === '(') parenDepth += 1;
    if (char === ')') {
      parenDepth -= 1;
      if (parenDepth === 0) {
        parenEnd = index;
        break;
      }
    }
  }
  assert(parenEnd >= 0, `${name} parameter list was not closed`);
  const firstBrace = source.indexOf('{', parenEnd);
  assert(firstBrace >= 0, `${name} has no body`);
  let depth = 0;
  for (let index = firstBrace; index < source.length; index += 1) {
    const char = source[index];
    if (char === '{') depth += 1;
    if (char === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(firstBrace + 1, index);
    }
  }
  throw new Error(`${name} body was not closed`);
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
