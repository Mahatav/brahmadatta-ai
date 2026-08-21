import { readFile, access } from 'node:fs/promises';
import path from 'node:path';

// Regression test for the Brahmadatta Core rebuild (docs/09-company/04-design-system.md §6.1,
// §7). Guards two things a visual reviewer cannot always catch by eye: (1) the forbidden
// glowing-particle-sphere aesthetic genuinely does not exist anywhere in the shipped bundle any
// more, and (2) the six arcs are driven from real mission telemetry, never a decorative timer.

const appRoot = path.resolve(import.meta.dirname, '..');
const corePath = path.join(appRoot, 'src/components/BrahmadattaCore.tsx');
const phasesPath = path.join(appRoot, 'src/lib/design/phases.ts');
const cssPath = path.join(appRoot, 'src/styles/command-center-frame.css');
const oldCorePath = path.join(appRoot, 'src/components/AIParticleCore.tsx');

async function main() {
  const [core, phases, css] = await Promise.all([
    readFile(corePath, 'utf8'),
    readFile(phasesPath, 'utf8'),
    readFile(cssPath, 'utf8'),
  ]);

  await assertOldCoreRemoved();
  assertNoGlowOrParticles(core, css);
  assertPhaseOrder(phases);
  assertSixArcsFromRealData(core);
  assertNoTimerDrivenProgress(core);
  assertChakraGeometryPresent(core);
  assertGreyscaleSafeStates(core);

  console.warn('brahmadatta core ok: no glow/particles, six-arc geometry from PHASE_ORDER, driven by real telemetry only');
}

async function assertOldCoreRemoved() {
  const exists = await access(oldCorePath).then(() => true, () => false);
  assert(!exists, 'AIParticleCore.tsx (the forbidden glowing-particle-sphere) must be removed, not left dead');
}

function assertNoGlowOrParticles(core, css) {
  for (const forbidden of ['radial-gradient', 'box-shadow', 'filter: blur', 'text-shadow', 'requestAnimationFrame', 'canvas', 'interface Particle']) {
    assert(!core.includes(forbidden), `BrahmadattaCore.tsx must not use ${forbidden} — §1's "not a glowing progress ring"`);
  }
  for (const selector of ['.bd-core__ray', '.bd-core__rim-circle', '.bd-core__plate']) {
    const block = cssBlock(css, selector);
    assert(block, `${selector} is missing from command-center-frame.css`);
    assert(!block.includes('box-shadow') && !block.includes('filter'), `${selector} must stay a flat hairline stroke, no glow`);
  }
}

function assertPhaseOrder(phases) {
  const match = phases.match(/export const PHASE_ORDER: CorePhase\[\] = \[([\s\S]*?)\];/);
  assert(match, 'PHASE_ORDER array is missing');
  const phaseList = Array.from(match[1].matchAll(/'([A-Z_]+)'/g), ([, phase]) => phase);
  assert(phaseList.length === 6, `PHASE_ORDER must have exactly six phases; got ${phaseList.length}`);
  const expected = ['INGEST', 'ANALYZE', 'STRESS_TEST', 'CORRELATE', 'REMEDIATE', 'VERIFY'];
  assert(JSON.stringify(phaseList) === JSON.stringify(expected), (
    `PHASE_ORDER must match D-038's resolution ${expected.join(',')}; got ${phaseList.join(',')}`
  ));
}

function assertSixArcsFromRealData(core) {
  assert(core.includes('PHASE_ORDER.map'), 'the six arcs must be derived from the single PHASE_ORDER array (§12 build note 8), not six hardcoded paths');
  assert(core.includes('RAY_STROKE_COUNT = 48'), '48 ray strokes (§7) are required');
  assert(core.includes('ARC_SPAN_DEG = 60'), 'each arc must span 60 degrees (§7.1)');
  assert(core.includes('snapshot.completedStages.includes'), 'arc completion must be derived from real completed-stage telemetry');
  assert(core.includes('snapshot.stageProgress'), 'the running arc fraction must come from real stageProgress, not a guess');
}

function assertNoTimerDrivenProgress(core) {
  assert(!core.includes('setInterval'), 'the Core itself must not run its own timer — §2.6 rule 2, "nothing advances on a timer"');
  assert(!core.includes('Math.random'), 'the Core must never fabricate a value');
  assert(core.includes('percent == null'), 'a null percent_complete must render as sparse running density, never a guessed fraction (§13 open question 1)');
}

function assertChakraGeometryPresent(core) {
  for (const marker of ['bd-core__rays', 'bd-core__rim', 'bd-core__kavacha', 'bd-core__yantra', 'KAVACHA_PLATE_COUNT = 12', 'RAMP_COMPLETE', 'RAMP_FAILED']) {
    assert(core.includes(marker), `chakra geometry element missing: ${marker}`);
  }
}

function assertGreyscaleSafeStates(core) {
  // §5, §9 — colour is never the only channel. Every visual state must carry a distinct word.
  for (const word of ['Standby', 'Verified', 'Rejected', 'Held', 'Failed', 'Cancelled']) {
    assert(core.includes(`'${word}'`) || core.includes(`"${word}"`), `centre word vocabulary missing: ${word}`);
  }
}

function cssBlock(css, selector) {
  const escaped = selector.replaceAll('.', '\\.');
  const match = css.match(new RegExp(`${escaped}\\s*\\{([\\s\\S]*?)\\}`));
  return match?.[1] ?? '';
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
