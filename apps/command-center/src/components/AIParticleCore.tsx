import { useEffect, useMemo, useRef, useState } from 'react';

import type { LocalRepositoryContext, MissionSnapshot, StreamState } from '../lib/events/store';
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

interface AIParticleCoreProps {
  snapshot: MissionSnapshot;
  localRepository: LocalRepositoryContext | null;
  streamState: StreamState;
}

const particleCount = 720;
const goldenAngle = Math.PI * (3 - Math.sqrt(5));

export function AIParticleCore({ snapshot, localRepository, streamState }: AIParticleCoreProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [mode, setMode] = useState<AiMode>('idle');
  const [prompt, setPrompt] = useState('');
  const [transcript, setTranscript] = useState('Core idle. Scan a local repo, then ask a question.');
  const selectedRepository = localRepository?.name ?? 'no repo selected';
  const hasContext = Boolean(localRepository || snapshot.missionId);

  const particles = useMemo(() => makeParticles(), []);

  useEffect(() => {
    if (streamState === 'open' && mode === 'idle') {
      setMode('listening');
    }
  }, [mode, streamState]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return undefined;
    }

    let frame = 0;
    let animation = 0;
    const context = canvas.getContext('2d');
    if (!context) {
      return undefined;
    }

    const draw = () => {
      const box = canvas.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      const width = Math.max(1, Math.floor(box.width * ratio));
      const height = Math.max(1, Math.floor(box.height * ratio));
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }

      const styles = getComputedStyle(canvas);
      const particleColor = styles.getPropertyValue('--bd-text').trim() || '#F4F3EE';
      const ruleColor = styles.getPropertyValue('--bd-rule-active').trim() || '#F4F3EE';
      const veilColor = styles.getPropertyValue('--bd-text-secondary').trim() || '#9FA1C9';
      const field = Math.min(width, height);
      const centerX = width / 2;
      const centerY = height / 2;
      const radius = field * 0.29;
      const breath = 1 + Math.sin(frame * 0.018) * 0.045;
      const pulse = mode === 'thinking' ? breath : mode === 'transcribing' ? 1.1 : mode === 'speaking' ? 1.05 : mode === 'listening' ? 1.02 : 1;
      const speed = mode === 'transcribing' ? 0.024 : mode === 'speaking' ? 0.014 : mode === 'listening' ? 0.009 : mode === 'thinking' ? 0.005 : 0.005;
      const energy = mode === 'transcribing' ? 1 : mode === 'speaking' ? 0.7 : mode === 'listening' ? 0.52 : mode === 'thinking' ? 0.32 : 0.32;

      context.clearRect(0, 0, width, height);
      context.save();
      context.lineCap = 'round';
      context.globalCompositeOperation = 'lighter';

      const projected = particles.map((particle, index) => {
        const phase = frame * speed + particle.drift;
        const surface = 1 + Math.sin(phase * 2.4 + particle.lane) * 0.035 * energy;
        const wobble = Math.sin(phase * 1.7) * 0.05;
        const rotationY = frame * speed * 0.72;
        const rotationX = Math.sin(frame * speed * 0.23) * 0.32;
        const rawX = particle.x * surface;
        const rawY = particle.y * surface;
        const rawZ = particle.z * surface;
        const x = rawX * Math.cos(rotationY) - rawZ * Math.sin(rotationY);
        const z = rawX * Math.sin(rotationY) + rawZ * Math.cos(rotationY);
        const y = rawY * Math.cos(rotationX) - z * Math.sin(rotationX);
        const finalZ = rawY * Math.sin(rotationX) + z * Math.cos(rotationX);
        const perspective = 1.45 / (1.85 - finalZ);
        return {
          index,
          x: centerX + x * radius * perspective * pulse,
          y: centerY + y * radius * perspective * pulse,
          z: finalZ,
          lane: particle.lane,
          size: Math.max(0.65 * ratio, (particle.size + perspective * 0.9 + wobble) * ratio),
          alpha: Math.max(0.08, Math.min(0.86, 0.28 + finalZ * 0.34 + energy * 0.18)),
        };
      });

      const halo = context.createRadialGradient(centerX, centerY, 0, centerX, centerY, radius * 1.7);
      halo.addColorStop(0, withAlpha(particleColor, 0.24 + energy * 0.1));
      halo.addColorStop(0.22, withAlpha(particleColor, 0.08));
      halo.addColorStop(1, withAlpha(particleColor, 0));
      context.fillStyle = halo;
      context.beginPath();
      context.arc(centerX, centerY, radius * 1.55, 0, Math.PI * 2);
      context.fill();

      drawHologramRings(context, centerX, centerY, radius, ratio, frame, speed, energy, particleColor, veilColor);
      drawFilaments(context, projected, centerX, centerY, ratio, energy, ruleColor, particleColor);
      if (mode === 'listening') {
        drawListeningSweep(context, centerX, centerY, radius, ratio, frame, particleColor, veilColor);
      }
      if (mode === 'transcribing' || mode === 'speaking') {
        drawDataStreams(context, centerX, centerY, radius, ratio, frame, speed, energy, particleColor);
      }

      const nucleus = context.createRadialGradient(centerX, centerY, 0, centerX, centerY, radius * 0.24);
      nucleus.addColorStop(0, withAlpha(particleColor, 0.92));
      nucleus.addColorStop(0.36, withAlpha(particleColor, 0.24 + energy * 0.18));
      nucleus.addColorStop(1, withAlpha(particleColor, 0));
      context.fillStyle = nucleus;
      context.beginPath();
      context.arc(centerX, centerY, radius * (0.2 + energy * 0.06), 0, Math.PI * 2);
      context.fill();

      projected
        .sort((a, b) => a.z - b.z)
        .forEach((particle) => {
          const tone = particle.lane % 5 === 0 ? veilColor : particleColor;
          context.fillStyle = withAlpha(tone, particle.alpha);
          context.beginPath();
          context.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
          context.fill();
        });

      context.globalCompositeOperation = 'source-over';
      context.strokeStyle = withAlpha(particleColor, 0.22 + energy * 0.28);
      context.lineWidth = ratio;
      context.setLineDash([3 * ratio, 9 * ratio]);
      context.beginPath();
      context.arc(centerX, centerY, radius * pulse * 1.17, frame * speed, Math.PI * 2 + frame * speed);
      context.stroke();
      context.setLineDash([]);

      context.restore();
      frame += 1;
      animation = requestAnimationFrame(draw);
    };

    animation = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(animation);
  }, [mode, particles]);

  function handleCoreClick() {
    const nextMode: AiMode = mode === 'idle'
      ? 'listening'
      : mode === 'listening'
        ? 'transcribing'
        : mode === 'transcribing'
          ? 'thinking'
          : 'idle';
    setMode(nextMode);
    if (nextMode === 'listening') {
      setTranscript(`Listening for input. Context: ${selectedRepository}.`);
    }
    if (nextMode === 'transcribing') {
      setTranscript(`Transcribing locally. Context: ${selectedRepository}.`);
    }
    if (nextMode === 'thinking') {
      setTranscript(hasContext ? 'Thinking over the local code map.' : 'Scan a local repo so the core has code to reason about.');
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!prompt.trim()) {
      return;
    }
    setMode('thinking');
    const request = prompt.trim();
    setPrompt('');
    window.setTimeout(() => {
      setMode('speaking');
      setTranscript(
        hasContext
          ? `Local draft captured for ${selectedRepository}: ${request}`
          : `I need a scanned local repo before I can answer: ${request}`,
      );
    }, 700);
  }

  return (
    <div className="ai-core">
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

function drawHologramRings(
  context: CanvasRenderingContext2D,
  centerX: number,
  centerY: number,
  radius: number,
  ratio: number,
  frame: number,
  speed: number,
  energy: number,
  particleColor: string,
  veilColor: string,
): void {
  for (let arc = 0; arc < 7; arc += 1) {
    const sweep = frame * speed * (arc % 2 === 0 ? 1 : -1) + arc * 0.72;
    context.strokeStyle = withAlpha(arc % 2 === 0 ? particleColor : veilColor, 0.12 + energy * 0.16);
    context.lineWidth = (arc === 2 ? 1.8 : 1) * ratio;
    context.beginPath();
    context.ellipse(
      centerX,
      centerY,
      radius * (0.56 + arc * 0.105),
      radius * (0.13 + arc * 0.038),
      sweep,
      0,
      Math.PI * 2,
    );
    context.stroke();
  }
}

function drawFilaments(
  context: CanvasRenderingContext2D,
  projected: Array<{ index: number; x: number; y: number; z: number; lane: number; size: number; alpha: number }>,
  centerX: number,
  centerY: number,
  ratio: number,
  energy: number,
  ruleColor: string,
  particleColor: string,
): void {
  context.lineWidth = ratio;
  for (let index = 0; index < projected.length; index += 11) {
    const current = projected[index];
    if (!current) {
      continue;
    }
    const next = projected[(index + 34 + current.lane * 5) % projected.length];
    if (!next || current.z < -0.45 || next.z < -0.55) {
      continue;
    }
    const alpha = Math.min(0.28, 0.05 + (current.z + 1) * 0.08 + energy * 0.08);
    context.strokeStyle = withAlpha(current.lane % 3 === 0 ? particleColor : ruleColor, alpha);
    context.beginPath();
    context.moveTo(current.x, current.y);
    context.quadraticCurveTo(
      centerX + (current.x - centerX) * 0.2,
      centerY + (next.y - centerY) * 0.2,
      next.x,
      next.y,
    );
    context.stroke();
  }
}

function drawDataStreams(
  context: CanvasRenderingContext2D,
  centerX: number,
  centerY: number,
  radius: number,
  ratio: number,
  frame: number,
  speed: number,
  energy: number,
  particleColor: string,
): void {
  context.strokeStyle = withAlpha(particleColor, 0.1 + energy * 0.28);
  context.lineWidth = ratio * (1 + energy * 0.7);
  for (let stream = 0; stream < 4; stream += 1) {
    const phase = frame * speed * (1.4 + stream * 0.16) + stream * Math.PI * 0.5;
    const start = phase;
    const end = phase + Math.PI * (0.38 + energy * 0.22);
    const ring = radius * (0.94 + stream * 0.08);
    context.beginPath();
    context.ellipse(
      centerX,
      centerY,
      ring,
      ring * (0.24 + stream * 0.05),
      phase * 0.6,
      start,
      end,
    );
    context.stroke();
  }
}

function drawListeningSweep(
  context: CanvasRenderingContext2D,
  centerX: number,
  centerY: number,
  radius: number,
  ratio: number,
  frame: number,
  particleColor: string,
  veilColor: string,
): void {
  const sweep = frame * 0.018;
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
