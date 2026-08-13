import { readFile } from 'node:fs/promises';
import path from 'node:path';

const appRoot = path.resolve(import.meta.dirname, '..');
const componentPath = path.join(appRoot, 'src/components/AIParticleCore.tsx');
const cssPath = path.join(appRoot, 'src/styles/global.css');

const expectedModes = ['idle', 'listening', 'transcribing', 'thinking', 'speaking'];

async function main() {
  const [component, css] = await Promise.all([
    readFile(componentPath, 'utf8'),
    readFile(cssPath, 'utf8'),
  ]);

  assertModeUnion(component);
  assertManualStateMachine(component);
  assertMotionProfiles(component);
  assertCanvasDensity(component);
  assertAnimationLoopAvoidsLayoutThrash(component);
  assertCssFrameIsStable(css);

  console.warn('ai core motion ok: five states, native frame cadence, smooth mode handoff, no surprise auto-mode');
}

function assertModeUnion(source) {
  const match = source.match(/type\s+AiMode\s*=\s*([^;]+);/);
  assert(match, 'AiMode union is missing');
  const modes = Array.from(match[1].matchAll(/'([^']+)'/g), ([, mode]) => mode);
  assert(
    JSON.stringify(modes) === JSON.stringify(expectedModes),
    `AiMode must stay exactly ${expectedModes.join(', ')}; got ${modes.join(', ')}`,
  );
}

function assertManualStateMachine(source) {
  assert(!source.includes("streamState === 'open'"), 'stream state must not auto-switch the AI core mode');
  assert(!source.includes('setMode(\'listening\')') || source.includes('function handleCoreClick()'), (
    'listening mode must be entered by operator action, not a background effect'
  ));

  const clickBody = bodyOfFunction(source, 'handleCoreClick');
  const clickOrder = expectedModes
    .map((mode) => clickBody.indexOf(`'${mode}'`))
    .filter((index) => index >= 0);
  assert(clickOrder.length >= expectedModes.length, 'click handler does not mention every AI mode');
  assert(isNondecreasing(clickOrder), 'click handler mode order drifted; expected idle -> listening -> transcribing -> thinking -> speaking');
  assert(clickBody.includes("mode === 'thinking'"), 'click handler must expose SPEAKING after THINKING');
  assert(clickBody.includes("if (nextMode === 'idle')"), 'click handler must reset transcript when returning to IDLE');
}

function assertMotionProfiles(source) {
  const motionBody = bodyOfFunction(source, 'motionForMode');
  const profiles = Object.fromEntries(expectedModes.map((mode) => [mode, profileForMode(motionBody, mode)]));

  assert(profiles.thinking.speed < profiles.transcribing.speed, 'THINKING must be slower than TRANSCRIBING');
  assert(profiles.thinking.rotation < profiles.transcribing.rotation, 'THINKING rotation must stay calmer than TRANSCRIBING');
  assert(profiles.thinking.surface < profiles.transcribing.surface, 'THINKING surface motion must stay calmer than TRANSCRIBING');
  assert(profiles.transcribing.energy > profiles.speaking.energy, 'TRANSCRIBING should remain the highest-energy text-capture state');
  assert(profiles.listening.energy > profiles.idle.energy, 'LISTENING should read as more alert than IDLE');
  assert(motionBody.includes('Math.sin(timeSeconds * 3.2)'), 'THINKING breath cadence must stay responsive and time-based');
  assert(profiles.thinking.scale.includes('thinkingBreath * 0.085'), 'THINKING must use the large-breath scale profile');
  assert(!profiles.transcribing.scale.includes('thinkingBreath'), 'TRANSCRIBING must not use the thinking breath profile');
  assert(profiles.idle.speed >= 1.5, 'IDLE should stay alive enough to avoid feeling stalled');
  assert(profiles.thinking.speed >= 3, 'THINKING should breathe at a modern responsive cadence');
  assert(profiles.transcribing.speed >= 6.8, 'TRANSCRIBING must stay fast enough to feel like live capture');
  assert(profiles.transcribing.speed <= 8.2, 'TRANSCRIBING must stay controlled instead of frantic');
}

function assertCanvasDensity(source) {
  const count = Number(source.match(/const\s+particleCount\s*=\s*(\d+);/)?.[1]);
  assert(Number.isInteger(count), 'particleCount constant is missing');
  assert(count >= 140 && count <= 220, `particleCount ${count} should stay light enough for the command room`);
  assert(!source.includes('calmFrameMs'), 'AI core must not reintroduce a choppy calm frame cap');
  assert(!source.includes('activeFrameMs'), 'AI core must not reintroduce a choppy active frame cap');
  assert(!source.includes('frameBudget'), 'AI core must run at native requestAnimationFrame cadence');
  assert(source.includes('drawTranscribingSignal'), 'TRANSCRIBING-specific signal renderer is missing');
  assert(!source.includes('drawTranscribingOrbit'), 'TRANSCRIBING must not return to abstract orbit motion');
  assert(source.includes('timeSeconds * 2.9'), 'TRANSCRIBING caption lanes must stay fast and time-based');
  assert(source.includes('timeSeconds * 8.4'), 'TRANSCRIBING waveform ticks must stay live and time-based');
  assert(source.includes('drawTacticalLattice'), 'shared tactical lattice renderer is missing');
  assert(source.includes('drawSpeakingWave'), 'SPEAKING-specific wave renderer is missing');
  assert(source.includes('drawParticleSphere'), 'single particle sphere renderer is missing');
  assert(!source.includes('drawHologramRings'), 'old hologram ring renderer should not return');
  assert(!source.includes('drawFilaments'), 'old filament renderer should not return');
  assert(!source.includes('projected = particles.map'), 'draw loop must not allocate projected particle arrays');
  assert(!source.includes('.sort('), 'draw loop must not sort particles every frame');
  assert(!source.includes('drawDataStreams'), 'old shared data-stream renderer should not return');
  assert(source.includes('modeRef.current'), 'draw loop must read mode from a ref instead of restarting on every click');
  assert(source.includes('interpolateMotion(displayedMotion, targetMotion, 0.22)'), 'mode changes must ease inside the canvas animation loop');
}

function assertAnimationLoopAvoidsLayoutThrash(source) {
  assert(source.includes('ResizeObserver'), 'AI core canvas layout must be refreshed by ResizeObserver');
  assert(
    occurrences(source, 'getBoundingClientRect(') === 1,
    'getBoundingClientRect must stay out of the per-frame draw loop',
  );
  assert(
    occurrences(source, 'getComputedStyle(') === 1,
    'getComputedStyle must stay out of the per-frame draw loop',
  );
  const drawStart = source.search(/const\s+draw\s*=\s*\([^)]*\)\s*=>\s*\{/);
  assert(drawStart >= 0, 'AI core draw loop is missing');
  const drawEnd = source.indexOf('animation = requestAnimationFrame(draw);', drawStart);
  assert(drawEnd > drawStart, 'AI core draw loop end marker is missing');
  const drawBody = source.slice(drawStart, drawEnd);
  assert(!drawBody.includes('getBoundingClientRect('), 'draw loop must not force layout reads');
  assert(!drawBody.includes('getComputedStyle('), 'draw loop must not read computed styles');
}

function assertCssFrameIsStable(css) {
  const baseButton = cssBlock(css, '.ai-core-button');
  assert(baseButton.includes('aspect-ratio: 1'), 'AI core button must keep a square aspect ratio');
  assert(baseButton.includes('transition: filter 120ms ease'), 'AI core button should only transition fast non-layout visual properties');
  assert(!baseButton.includes('transform 260ms'), 'AI core button must not carry slow transform transitions');

  const responsiveButton = lastCssBlock(css, '.ai-core-button');
  assert(responsiveButton.includes('inline-size: clamp('), 'responsive AI core size clamp is missing');

  const thinkingBlock = cssBlock(css, '.ai-core-button--thinking');
  assert(!thinkingBlock.includes('transform'), 'THINKING must not use CSS transform; it changes the measured box');
  assert(!thinkingBlock.includes('animation'), 'THINKING must not add a CSS animation competing with canvas motion');

  for (const blockName of ['.ai-core-button', '.ai-core-button::before', '.ai-core-button::after']) {
    const block = cssBlock(css, blockName);
    assert(!block.includes('animation:'), `${blockName} must not add independent CSS animation`);
  }
}

function bodyOfFunction(source, name) {
  const start = source.indexOf(`function ${name}`);
  assert(start >= 0, `${name} is missing`);
  const firstBrace = source.indexOf('{', start);
  assert(firstBrace >= 0, `${name} has no body`);
  let depth = 0;
  for (let index = firstBrace; index < source.length; index += 1) {
    const char = source[index];
    if (char === '{') {
      depth += 1;
    }
    if (char === '}') {
      depth -= 1;
      if (depth === 0) {
        return source.slice(firstBrace + 1, index);
      }
    }
  }
  throw new Error(`${name} body was not closed`);
}

function profileForMode(motionBody, mode) {
  const modeCheck = mode === 'idle' ? 'return {' : `mode === '${mode}'`;
  const start = mode === 'idle' ? motionBody.lastIndexOf(modeCheck) : motionBody.indexOf(modeCheck);
  assert(start >= 0, `motion profile missing for ${mode}`);
  const returnStart = motionBody.indexOf('return {', start);
  assert(returnStart >= 0, `motion profile return missing for ${mode}`);
  const profileText = motionBody.slice(returnStart, motionBody.indexOf('};', returnStart) + 2);
  return {
    energy: numberProperty(profileText, 'energy'),
    rotation: numberProperty(profileText, 'rotation'),
    scale: stringProperty(profileText, 'scale'),
    speed: numberProperty(profileText, 'speed'),
    surface: numberProperty(profileText, 'surface'),
  };
}

function numberProperty(source, key) {
  const match = source.match(new RegExp(`${key}:\\s*([0-9.]+)`));
  assert(match, `${key} is missing from motion profile`);
  return Number(match[1]);
}

function stringProperty(source, key) {
  const match = source.match(new RegExp(`${key}:\\s*([^,\\n]+)`));
  assert(match, `${key} is missing from motion profile`);
  return match[1].trim();
}

function cssBlock(css, selector) {
  const escaped = selector.replaceAll('.', '\\.');
  const match = css.match(new RegExp(`${escaped}\\s*\\{([\\s\\S]*?)\\}`));
  return match?.[1] ?? '';
}

function lastCssBlock(css, selector) {
  const escaped = selector.replaceAll('.', '\\.');
  const matches = Array.from(css.matchAll(new RegExp(`${escaped}\\s*\\{([\\s\\S]*?)\\}`, 'g')));
  return matches.at(-1)?.[1] ?? '';
}

function isNondecreasing(values) {
  return values.every((value, index) => index === 0 || value >= values[index - 1]);
}

function occurrences(source, needle) {
  return source.split(needle).length - 1;
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
