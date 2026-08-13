import { useEffect, useMemo, useRef, useState } from 'react';

import type { LocalRepositoryContext, MissionSnapshot, StreamState } from '../lib/events/store';
import { sanitizeDisplayText } from '../lib/security/renderSafety.mjs';
import type { FormEvent } from 'react';

type AiMode = 'idle' | 'listening' | 'transcribing' | 'thinking' | 'speaking';

interface Particle {
  x: number;
  y: number;
  z: number;
  drift: number;
  lane: number;
  size: number;
}

interface CoreMotion {
  energy: number;
  rotation: number;
  scale: number;
  speed: number;
  surface: number;
  tilt: number;
}

interface CoreLayout {
  centerX: number;
  centerY: number;
  height: number;
  particleColor: string;
  radius: number;
  ratio: number;
  veilColor: string;
  width: number;
}

interface AIParticleCoreProps {
  snapshot: MissionSnapshot;
  localRepository: LocalRepositoryContext | null;
  streamState: StreamState;
}

const particleCount = 180;
const goldenAngle = Math.PI * (3 - Math.sqrt(5));

function motionForMode(mode: AiMode, timeSeconds: number): CoreMotion {
  const calmBreath = Math.sin(timeSeconds * 1.65);
  const thinkingBreath = Math.sin(timeSeconds * 3.2);
  if (mode === 'thinking') {
    return {
      energy: 0.55,
      rotation: 0.58,
      scale: 1.06 + thinkingBreath * 0.085,
      speed: 3.4,
      surface: 0.018,
      tilt: 0.12,
    };
  }
  if (mode === 'listening') {
    return {
      energy: 0.66,
      rotation: 0.72,
      scale: 1.03 + Math.sin(timeSeconds * 2.8) * 0.035,
      speed: 3.8,
      surface: 0.022,
      tilt: 0.14,
    };
  }
  if (mode === 'transcribing') {
    return {
      energy: 0.78,
      rotation: 0.68,
      scale: 1.025,
      speed: 7.2,
      surface: 0.02,
      tilt: 0.11,
    };
  }
  if (mode === 'speaking') {
    return {
      energy: 0.76,
      rotation: 0.92,
      scale: 1.025 + Math.sin(timeSeconds * 4.8) * 0.024,
      speed: 6.4,
      surface: 0.026,
      tilt: 0.16,
    };
  }
  return {
    energy: 0.36,
    rotation: 0.46,
    scale: 1 + calmBreath * 0.03,
    speed: 1.75,
    surface: 0.012,
    tilt: 0.09,
  };
}

function readCoreLayout(canvas: HTMLCanvasElement): CoreLayout {
  const box = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.floor(box.width * ratio));
  const height = Math.max(1, Math.floor(box.height * ratio));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }

  const styles = getComputedStyle(canvas);
  const field = Math.min(width, height);
  return {
    centerX: width / 2,
    centerY: height / 2,
    height,
    particleColor: styles.getPropertyValue('--bd-text').trim() || '#F4F3EE',
    radius: field * 0.27,
    ratio,
    veilColor: styles.getPropertyValue('--bd-text-secondary').trim() || '#9FA1C9',
    width,
  };
}

export function AIParticleCore({ snapshot, localRepository, streamState }: AIParticleCoreProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const modeRef = useRef<AiMode>('idle');
  const [mode, setMode] = useState<AiMode>('idle');
  const [prompt, setPrompt] = useState('');
  const [transcript, setTranscript] = useState('Core idle. Scan a local repo, then ask a question.');
  const selectedRepository = sanitizeDisplayText(localRepository?.name ?? 'no repo selected', {
    fallback: 'no repo selected',
    maxLength: 120,
  });
  const hasContext = Boolean(localRepository || snapshot.missionId);

  const particles = useMemo(() => makeParticles(), []);

  useEffect(() => {
    modeRef.current = mode;
  }, [mode]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return undefined;
    }

    let drawCount = 0;
    let animation = 0;
    let layout: CoreLayout = readCoreLayout(canvas);
    let displayedMotion = motionForMode(modeRef.current, 0);
    const context = canvas.getContext('2d');
    if (!context) {
      return undefined;
    }

    const refreshLayout = () => {
      layout = readCoreLayout(canvas);
    };
    const resizeObserver = typeof ResizeObserver === 'undefined'
      ? null
      : new ResizeObserver(refreshLayout);
    resizeObserver?.observe(canvas);
    window.addEventListener('resize', refreshLayout);

    const draw = (timestamp = 0) => {
      if (drawCount % 240 === 0) {
        refreshLayout();
      }
      if (!layout.width || !layout.height) {
        animation = requestAnimationFrame(draw);
        return;
      }
      const {
        centerX,
        centerY,
        height,
        particleColor,
        radius,
        ratio,
        veilColor,
        width,
      } = layout;
      const timeSeconds = timestamp / 1000;
      const activeMode = modeRef.current;
      const targetMotion = motionForMode(activeMode, timeSeconds);
      displayedMotion = interpolateMotion(displayedMotion, targetMotion, 0.22);
      const motion = displayedMotion;

      context.clearRect(0, 0, width, height);
      context.save();
      context.lineCap = 'round';
      context.globalCompositeOperation = 'lighter';

      const halo = context.createRadialGradient(centerX, centerY, 0, centerX, centerY, radius * 1.7);
      halo.addColorStop(0, withAlpha(particleColor, 0.16 + motion.energy * 0.08));
      halo.addColorStop(0.24, withAlpha(particleColor, 0.055));
      halo.addColorStop(1, withAlpha(particleColor, 0));
      context.fillStyle = halo;
      context.beginPath();
      context.arc(centerX, centerY, radius * 1.42, 0, Math.PI * 2);
      context.fill();

      drawParticleSphere(context, particles, layout, motion, timeSeconds);
      drawTacticalLattice(context, centerX, centerY, radius, ratio, timeSeconds, motion, particleColor, veilColor);
      if (activeMode === 'listening') {
        drawListeningSweep(context, centerX, centerY, radius, ratio, timeSeconds, particleColor, veilColor);
      }
      if (activeMode === 'transcribing') {
        drawTranscribingSignal(context, centerX, centerY, radius, ratio, timeSeconds, particleColor, veilColor);
      }
      if (activeMode === 'speaking') {
        drawSpeakingWave(context, centerX, centerY, radius, ratio, timeSeconds, particleColor, veilColor);
      }

      const nucleus = context.createRadialGradient(centerX, centerY, 0, centerX, centerY, radius * 0.24);
      nucleus.addColorStop(0, withAlpha(particleColor, 0.92));
      nucleus.addColorStop(0.36, withAlpha(particleColor, 0.22 + motion.energy * 0.16));
      nucleus.addColorStop(1, withAlpha(particleColor, 0));
      context.fillStyle = nucleus;
      context.beginPath();
      context.arc(centerX, centerY, radius * (0.17 + motion.energy * 0.06), 0, Math.PI * 2);
      context.fill();

      context.globalCompositeOperation = 'source-over';
      context.strokeStyle = withAlpha(particleColor, 0.2 + motion.energy * 0.24);
      context.lineWidth = ratio;
      context.setLineDash([3 * ratio, 9 * ratio]);
      context.beginPath();
      context.arc(centerX, centerY, radius * 1.17, timeSeconds * motion.rotation, Math.PI * 2 + timeSeconds * motion.rotation);
      context.stroke();
      context.setLineDash([]);

      context.restore();
      drawCount += 1;
      animation = requestAnimationFrame(draw);
    };

    animation = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(animation);
      resizeObserver?.disconnect();
      window.removeEventListener('resize', refreshLayout);
    };
  }, [particles]);

  function handleCoreClick() {
    const nextMode: AiMode = mode === 'idle'
      ? 'listening'
      : mode === 'listening'
        ? 'transcribing'
        : mode === 'transcribing'
          ? 'thinking'
          : mode === 'thinking'
            ? 'speaking'
            : 'idle';
    setMode(nextMode);
    if (nextMode === 'listening') {
      setTranscript(sanitizeDisplayText(`Listening for input. Context: ${selectedRepository}.`, { maxLength: 220 }));
    }
    if (nextMode === 'transcribing') {
      setTranscript(sanitizeDisplayText(`Transcribing locally. Context: ${selectedRepository}.`, { maxLength: 220 }));
    }
    if (nextMode === 'thinking') {
      setTranscript(hasContext ? 'Thinking over the local code map.' : 'Scan a local repo so the core has code to reason about.');
    }
    if (nextMode === 'speaking') {
      setTranscript(sanitizeDisplayText(`Speaking from local context: ${selectedRepository}.`, { maxLength: 220 }));
    }
    if (nextMode === 'idle') {
      setTranscript(hasContext ? 'Core idle. Local context is loaded.' : 'Core idle. Scan a local repo, then ask a question.');
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!prompt.trim()) {
      return;
    }
    setMode('thinking');
    const request = sanitizeDisplayText(prompt.trim(), { fallback: 'empty request', maxLength: 220 });
    setPrompt('');
    window.setTimeout(() => {
      setMode('speaking');
      setTranscript(
        sanitizeDisplayText(hasContext
          ? `Local draft captured for ${selectedRepository}: ${request}`
          : `I need a scanned local repo before I can answer: ${request}`, { maxLength: 280 }),
      );
    }, 700);
  }

  return (
    <div className="ai-core" data-stream-state={streamState}>
      <button
        type="button"
        className={`ai-core-button ai-core-button--${mode}`}
        onClick={handleCoreClick}
        aria-label="Activate local AI core"
      >
        <canvas ref={canvasRef} className="ai-core-canvas" />
        <span>{mode.toUpperCase()}</span>
      </button>
      <form className="ai-console" onSubmit={handleSubmit}>
        <label className="text-field">
          <span>LOCAL AI CHANNEL</span>
          <input
            type="text"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder={hasContext ? 'what should I inspect first?' : 'scan a local repo first'}
          />
        </label>
        <button type="submit">
          [ ASK ]
        </button>
      </form>
      <p className="ai-transcript">{transcript}</p>
    </div>
  );
}

function drawParticleSphere(
  context: CanvasRenderingContext2D,
  particles: Particle[],
  layout: CoreLayout,
  motion: CoreMotion,
  timeSeconds: number,
): void {
  const rotationY = timeSeconds * motion.rotation;
  const rotationX = Math.sin(timeSeconds * motion.rotation * 0.7) * motion.tilt;
  const cosY = Math.cos(rotationY);
  const sinY = Math.sin(rotationY);
  const cosX = Math.cos(rotationX);
  const sinX = Math.sin(rotationX);

  for (const particle of particles) {
    const phase = timeSeconds * motion.speed + particle.drift;
    const surface = motion.scale + Math.sin(phase * 1.35 + particle.lane) * motion.surface;
    const rawX = particle.x * surface;
    const rawY = particle.y * surface;
    const rawZ = particle.z * surface;
    const x = rawX * cosY - rawZ * sinY;
    const z = rawX * sinY + rawZ * cosY;
    const y = rawY * cosX - z * sinX;
    const finalZ = rawY * sinX + z * cosX;
    const perspective = 1.36 / (1.9 - finalZ);
    const alpha = Math.max(0.09, Math.min(0.78, 0.2 + finalZ * 0.28 + motion.energy * 0.12));
    const dotX = layout.centerX + x * layout.radius * perspective;
    const dotY = layout.centerY + y * layout.radius * perspective;
    const dotSize = Math.max(0.6 * layout.ratio, (particle.size + perspective * 0.72) * layout.ratio);
    context.fillStyle = withAlpha(particle.lane % 8 === 0 ? layout.veilColor : layout.particleColor, alpha);
    context.beginPath();
    context.arc(dotX, dotY, dotSize, 0, Math.PI * 2);
    context.fill();
  }
}

function drawTacticalLattice(
  context: CanvasRenderingContext2D,
  centerX: number,
  centerY: number,
  radius: number,
  ratio: number,
  timeSeconds: number,
  motion: CoreMotion,
  particleColor: string,
  veilColor: string,
): void {
  const pulse = 0.5 + Math.sin(timeSeconds * (2.8 + motion.energy * 3.4)) * 0.5;
  context.lineWidth = Math.max(0.6, ratio * 0.72);

  for (let lane = 0; lane < 8; lane += 1) {
    const angle = timeSeconds * (0.34 + motion.rotation * 0.38) + lane * Math.PI * 0.25;
    const longRadius = radius * (0.74 + (lane % 3) * 0.07 + motion.energy * 0.05);
    const shortRadius = longRadius * (0.34 + (lane % 2) * 0.05);
    context.strokeStyle = withAlpha(lane % 2 === 0 ? particleColor : veilColor, 0.11 + pulse * 0.1 + motion.energy * 0.08);
    context.beginPath();
    context.ellipse(
      centerX,
      centerY,
      longRadius,
      shortRadius,
      angle,
      angle + Math.PI * 0.08,
      angle + Math.PI * (0.68 + motion.energy * 0.2),
    );
    context.stroke();
  }
}

function drawTranscribingSignal(
  context: CanvasRenderingContext2D,
  centerX: number,
  centerY: number,
  radius: number,
  ratio: number,
  timeSeconds: number,
  particleColor: string,
  veilColor: string,
): void {
  context.lineWidth = Math.max(0.85, ratio);

  for (let tick = 0; tick < 25; tick += 1) {
    const t = tick / 24;
    const x = centerX - radius * 0.68 + t * radius * 1.36;
    const pulse = Math.abs(Math.sin(timeSeconds * 8.4 + tick * 0.72));
    const tickHeight = radius * (0.035 + pulse * 0.15);
    context.strokeStyle = withAlpha(tick % 4 === 0 ? particleColor : veilColor, 0.13 + pulse * 0.22);
    context.beginPath();
    context.moveTo(x, centerY - tickHeight);
    context.lineTo(x, centerY + tickHeight);
    context.stroke();
  }

  for (let lane = 0; lane < 3; lane += 1) {
    const y = centerY + (lane - 1) * radius * 0.18;
    context.strokeStyle = withAlpha(veilColor, 0.16);
    context.beginPath();
    context.moveTo(centerX - radius * 0.78, y);
    context.lineTo(centerX + radius * 0.78, y);
    context.stroke();

    for (let segment = 0; segment < 7; segment += 1) {
      const progress = (timeSeconds * 2.9 + lane * 0.13 + segment * 0.19) % 1;
      const fade = 1 - Math.abs(progress - 0.5) * 1.8;
      const x = centerX - radius * 0.76 + progress * radius * 1.52;
      const length = radius * (0.07 + ((segment + lane) % 3) * 0.035);
      context.strokeStyle = withAlpha(particleColor, Math.max(0.08, 0.15 + fade * 0.28));
      context.beginPath();
      context.moveTo(x, y);
      context.lineTo(Math.min(centerX + radius * 0.78, x + length), y);
      context.stroke();
    }
  }

  const scan = (timeSeconds * 3.35) % 1;
  const scanX = centerX - radius * 0.82 + scan * radius * 1.64;
  const beam = context.createLinearGradient(scanX, centerY - radius * 0.38, scanX, centerY + radius * 0.38);
  beam.addColorStop(0, withAlpha(particleColor, 0));
  beam.addColorStop(0.5, withAlpha(particleColor, 0.38));
  beam.addColorStop(1, withAlpha(particleColor, 0));
  context.strokeStyle = beam;
  context.lineWidth = ratio * 1.4;
  context.beginPath();
  context.moveTo(scanX, centerY - radius * 0.38);
  context.lineTo(scanX, centerY + radius * 0.38);
  context.stroke();
}

function drawSpeakingWave(
  context: CanvasRenderingContext2D,
  centerX: number,
  centerY: number,
  radius: number,
  ratio: number,
  timeSeconds: number,
  particleColor: string,
  veilColor: string,
): void {
  context.lineWidth = ratio;
  for (let band = -2; band <= 2; band += 1) {
    const y = centerY + band * radius * 0.14;
    const amplitude = radius * (0.018 + Math.abs(band) * 0.006);
    context.strokeStyle = withAlpha(band === 0 ? particleColor : veilColor, band === 0 ? 0.5 : 0.26);
    context.beginPath();
    for (let step = 0; step <= 48; step += 1) {
      const t = step / 48;
      const x = centerX - radius * 0.82 + t * radius * 1.64;
      const wave = Math.sin(t * Math.PI * 7 + timeSeconds * 9.2 + band) * amplitude;
      if (step === 0) {
        context.moveTo(x, y + wave);
      } else {
        context.lineTo(x, y + wave);
      }
    }
    context.stroke();
  }
}

function drawListeningSweep(
  context: CanvasRenderingContext2D,
  centerX: number,
  centerY: number,
  radius: number,
  ratio: number,
  timeSeconds: number,
  particleColor: string,
  veilColor: string,
): void {
  const sweep = timeSeconds * 4.8;
  context.lineWidth = ratio;
  context.strokeStyle = withAlpha(particleColor, 0.34);
  for (let ring = 0; ring < 3; ring += 1) {
    const size = radius * (0.78 + ring * 0.17);
    const start = sweep + ring * 1.85;
    context.beginPath();
    context.ellipse(
      centerX,
      centerY,
      size,
      size * (0.34 + ring * 0.03),
      ring % 2 === 0 ? 0.18 : -0.42,
      start,
      start + Math.PI * 0.34,
    );
    context.stroke();
  }

  context.fillStyle = withAlpha(veilColor, 0.42);
  for (let ping = 0; ping < 5; ping += 1) {
    const angle = sweep * 0.7 + ping * Math.PI * 0.4;
    const distance = radius * (0.84 + Math.sin(sweep + ping) * 0.08);
    context.beginPath();
    context.arc(
      centerX + Math.cos(angle) * distance,
      centerY + Math.sin(angle) * distance * 0.46,
      ratio * (1.8 + ping % 2),
      0,
      Math.PI * 2,
    );
    context.fill();
  }
}

function interpolateMotion(current: CoreMotion, target: CoreMotion, amount: number): CoreMotion {
  return {
    energy: lerp(current.energy, target.energy, amount),
    rotation: lerp(current.rotation, target.rotation, amount),
    scale: lerp(current.scale, target.scale, amount),
    speed: lerp(current.speed, target.speed, amount),
    surface: lerp(current.surface, target.surface, amount),
    tilt: lerp(current.tilt, target.tilt, amount),
  };
}

function lerp(current: number, target: number, amount: number): number {
  return current + (target - current) * amount;
}

function makeParticles(): Particle[] {
  return Array.from({ length: particleCount }, (_, index) => {
    const y = 1 - (index / (particleCount - 1)) * 2;
    const radius = Math.sqrt(1 - y * y);
    const theta = goldenAngle * index;
    const lane = index % 17;
    return {
      x: Math.cos(theta) * radius,
      y,
      z: Math.sin(theta) * radius,
      drift: index * 0.037,
      lane,
      size: lane % 9 === 0 ? 1.45 : 0.85,
    };
  });
}

function withAlpha(color: string, alpha: number): string {
  if (color.startsWith('#')) {
    const hex = color.length === 4
      ? color.slice(1).split('').map((part) => `${part}${part}`).join('')
      : color.slice(1, 7);
    return `#${hex}${Math.round(alpha * 255).toString(16).padStart(2, '0')}`;
  }
  return color;
}
