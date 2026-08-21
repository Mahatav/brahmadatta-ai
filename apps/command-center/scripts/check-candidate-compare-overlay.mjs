import { readFile, access } from 'node:fs/promises';
import path from 'node:path';

// Regression test for the Candidate Compare overlay (docs/09-company/04-design-system.md §6.4,
// DS-02). Guards the review's blocking condition C4 (provenance is mandatory on both columns,
// above the verdict, with no default and no third value), the fixed five-row gate matrix order
// (§6.4.3), the policy-failure path's gate suppression, and that the old inline
// `VerdictComparePanel.tsx` (2 x 292, which could not fit a 72px verdict word) is gone.

const appRoot = path.resolve(import.meta.dirname, '..');
const overlayPath = path.join(appRoot, 'src/components/CandidateCompareOverlay.tsx');
const oldPanelPath = path.join(appRoot, 'src/components/VerdictComparePanel.tsx');
const cssPath = path.join(appRoot, 'src/styles/command-center-frame.css');

async function main() {
  const [overlay, css] = await Promise.all([
    readFile(overlayPath, 'utf8'),
    readFile(cssPath, 'utf8'),
  ]);

  await assertOldPanelRemoved();
  assertProvenanceMandatory(overlay);
  assertFixedGateOrder(overlay);
  assertColumnsOrderedByIndex(overlay);
  assertPolicyFailurePath(overlay);
  assertNeverSilentTruncation(overlay);
  assertModelSelfReportNeverAVerdict(overlay);
  assertOverlayIsOneModeNotTwo(overlay);
  assertOverlayWidthTokens(css);

  console.warn('candidate compare overlay ok: mandatory provenance, fixed gate order, policy-failure suppression, one overlay not two');
}

async function assertOldPanelRemoved() {
  const exists = await access(oldPanelPath).then(() => true, () => false);
  assert(!exists, 'VerdictComparePanel.tsx (the 2x292 layout that could not fit the verdict word or five gate rows, C3) must be removed');
}

function assertProvenanceMandatory(overlay) {
  assert(overlay.includes('[ × PROVENANCE MISSING ]'), 'a candidate with no provenance must render the missing-provenance state, never a default');
  assert(overlay.includes('provenance is not recorded'), 'the suppressed column must state the verdict is withheld, per §6.4.2');
  const fn = bodyOfFunction(overlay, 'provenanceValue');
  assert(fn.includes('MODEL-GENERATED') && fn.includes('OPERATOR-SUPPLIED'), 'provenance must be exactly one of the two named values, no third value, no abbreviation');
  assert(!fn.includes('??') && !fn.includes('default'), 'provenance must not fall back to a default value');
}

function assertFixedGateOrder(overlay) {
  const match = overlay.match(/const GATE_ORDER: Array<keyof GateMatrix> = \[([\s\S]*?)\];/);
  assert(match, 'GATE_ORDER is missing');
  const order = Array.from(match[1].matchAll(/'([a-z_]+)'/g), ([, gate]) => gate);
  const expected = ['compile', 'reproducer_eliminated', 'regression_preserved', 'static_delta', 'renewed_fuzzing'];
  assert(JSON.stringify(order) === JSON.stringify(expected), (
    `gate matrix order must be fixed per §6.4.3; got ${order.join(',')}`
  ));
}

function assertColumnsOrderedByIndex(overlay) {
  assert(overlay.includes('index: number'), 'candidate columns must carry their real index');
  assert(!overlay.includes('.sort('), 'columns must never be sorted by verdict — index order only (§6.4.2: "never arrangeable to flatter")');
}

function assertPolicyFailurePath(overlay) {
  assert(overlay.includes('refused by patch policy'), 'a policy-refused candidate must show all five gates as NOT RUN with this exact reason');
  assert(overlay.includes("'Not verified'"), 'a policy-refused candidate\'s verdict word must read "Not verified", never an optimistic guess');
  assert(overlay.includes('policyFailed'), 'the diff body must still render (greyed), never an empty column, on policy failure');
}

function assertNeverSilentTruncation(overlay) {
  assert(overlay.includes('DIFF_MAX_LINES = 200'), 'the 200-line truncation cap (reachable only via policy failure, §6.4.5) must be a named constant');
  assert(overlay.includes('[ ! TRUNCATED'), 'a truncated diff must disclose the truncation, never silently cut');
  assert(overlay.includes('[ … '), 'a collapsed diff must disclose how many lines are hidden');
}

function assertModelSelfReportNeverAVerdict(overlay) {
  const fn = bodyOfFunction(overlay, 'modelSelfReport');
  assert(fn.includes('not a verdict'), 'the model self-report must explicitly disclaim it is not a verdict (§6.4.6)');
  assert(fn.includes("'n/a · operator-supplied'"), 'an operator-supplied candidate must read n/a, never a confidence number');
}

function assertOverlayIsOneModeNotTwo(overlay) {
  assert(overlay.includes('fullDiffColumn'), 'OPEN FULL DIFF must be a mode of the same overlay, not a second overlay (§6.4.4)');
  assert(overlay.includes('BACK TO COMPARE'), 'full-diff mode must be reversible back to the compare view without closing the overlay');
  assert((overlay.match(/role="dialog"/g) ?? []).length === 1, 'exactly one overlay dialog element — nothing opens on top of an overlay');
}

function assertOverlayWidthTokens(css) {
  const overlayBlock = cssBlock(css, 'bd-overlay');
  assert(overlayBlock.includes('var(--bd-overlay-w)'), 'the overlay must size from the design-token width, not a hardcoded pixel value');
  const gridBlock = cssBlock(css, 'bd-overlay__grid');
  assert(gridBlock.includes('var(--bd-compare-col)'), 'compare columns must size from --bd-compare-col (652px)');
}

function cssBlock(css, className) {
  // Exact-selector match: `.className {` or `.className ` followed by another selector/brace,
  // never a BEM child like `.className__part`.
  const match = css.match(new RegExp(`\\.${className}(?![\\w-])[^{]*\\{([\\s\\S]*?)\\}`));
  return match?.[1] ?? '';
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
