import { readFile } from 'node:fs/promises';
import path from 'node:path';

// Regression test for the Findings rail and its evidence block (docs/09-company/04-design-system.md
// §6.3, §6.3a — the review's C2). Guards that the sanitizer trace and reproducer replay record
// are fetched from the real `FindingDetail` endpoint (never fabricated from the SSE summary
// alone), that a zero-finding state is only ever shown after the stress test actually completed,
// and that the determinism chip is computed from `successes === attempts`, never inferred.

const appRoot = path.resolve(import.meta.dirname, '..');
const railPath = path.join(appRoot, 'src/components/FindingsRail.tsx');
const cssPath = path.join(appRoot, 'src/styles/command-center-frame.css');

async function main() {
  const [rail, css] = await Promise.all([
    readFile(railPath, 'utf8'),
    readFile(cssPath, 'utf8'),
  ]);

  assertRealDetailFetch(rail);
  assertNotMeasuredVsZero(rail);
  assertEvidenceNeverFabricated(rail);
  assertDeterminismFromRatioOnly(rail);
  assertFrameDisclosureNeverSilent(rail);
  assertSanitized(rail);
  assertCssStates(css);

  console.warn('findings evidence ok: real FindingDetail fetch, honest — vs 0, determinism from ratio only, frame disclosure never silent');
}

function assertRealDetailFetch(rail) {
  assert(rail.includes("getFinding(snapshot.missionId, findingId"), 'evidence must be fetched from the real GET /findings/{id} endpoint');
  assert(rail.includes('ApiError'), 'a failed fetch must be handled as a real API error, not swallowed');
  assert(rail.includes('[ RETRY ]'), 'a failed evidence fetch must offer a real retry control (§6.3 Failed state)');
}

function assertNotMeasuredVsZero(rail) {
  assert(rail.includes("'[ FINDINGS · — ]'"), 'header must render the not-measured em dash before analysis has run');
  assert(rail.includes("'[ FINDINGS · 0 ]'"), 'header must render a real zero only after the stress test completed');
  assert(rail.includes('crashes_found === 0'), 'the zero state must be derived from a real completed fuzzing report, never assumed');
}

function assertEvidenceNeverFabricated(rail) {
  assert(!rail.includes('Math.random'), 'evidence must never fabricate a value');
  assert(rail.includes('detail.sanitizer_report'), 'the sanitizer block must read the real FindingDetail.sanitizer_report field');
  assert(rail.includes('NOT YET CAPTURED'), 'a finding with no sanitizer artifact yet must say so, not render as confirmed');
}

function assertDeterminismFromRatioOnly(rail) {
  const body = bodyOfFunction(rail, 'DeterminismChip');
  assert(body.includes('successes === attempts'), 'determinism must be successes === attempts, never inferred (architecture spec §5.1)');
  assert(body.includes('successes === 0'), 'the not-reproducible case (0 successes) must be distinguished from partial non-determinism');
}

function assertFrameDisclosureNeverSilent(rail) {
  assert(rail.includes('FRAME_PREVIEW_COUNT'), 'the frame preview count must be a named constant, not a magic number');
  assert(rail.includes('[ FRAMES'), 'eliding frames must always disclose the count elided — never a silent truncation (§6.3a)');
  assert(rail.includes('[ FULL TRACE ]'), 'a full-trace disclosure control must exist');
}

function assertSanitized(rail) {
  assert(rail.includes('sanitizeDisplayText'), 'finding/evidence strings must go through sanitizeDisplayText before reaching the DOM');
}

function assertCssStates(css) {
  for (const selector of ['.bd-evidence__pending', '.bd-evidence__error', '.bd-findings__row--selected']) {
    assert(css.includes(selector), `CSS missing ${selector}`);
  }
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
