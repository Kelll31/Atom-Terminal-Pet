import React, { useEffect, useRef, useState } from 'react';

// ── Emotion config ────────────────────────────────────────────────────────────
interface EmotionConfig {
  label: string;
  primaryColor: string;
  secondaryColor: string;
  glowColor: string;
  bgGradient: string;
  particleColor: string;
  eyeShape: 'normal' | 'happy' | 'angry' | 'sleepy' | 'wide' | 'heart' | 'dizzy' | 'sad' | 'dot' | 'spiral';
  mouthShape: 'smile' | 'frown' | 'open' | 'line' | 'wide-smile' | 'zig-zag' | 'small' | 'talking';
  animation: 'idle' | 'bounce' | 'shake' | 'spin' | 'pulse-fast' | 'float' | 'glitch' | 'wobble';
  particleEffect: 'none' | 'hearts' | 'sparks' | 'tears' | 'stars' | 'spiral' | 'explode' | 'music';
  auraEffect: 'none' | 'cyan' | 'red' | 'yellow' | 'pink' | 'blue' | 'purple' | 'rainbow';
  scanlines: boolean;
  glitch: boolean;
}

const EMOTIONS: Record<string, EmotionConfig> = {
  idle: {
    label: 'IDLE',
    primaryColor: '#00f0ff',
    secondaryColor: '#0a2030',
    glowColor: 'rgba(0,240,255,0.4)',
    bgGradient: 'radial-gradient(ellipse at 50% 60%, rgba(0,240,255,0.08) 0%, transparent 70%)',
    particleColor: '#00f0ff',
    eyeShape: 'normal', mouthShape: 'line',
    animation: 'idle', particleEffect: 'none',
    auraEffect: 'cyan', scanlines: true, glitch: false,
  },
  happy: {
    label: 'HAPPY',
    primaryColor: '#00ff9d',
    secondaryColor: '#001a0d',
    glowColor: 'rgba(0,255,157,0.5)',
    bgGradient: 'radial-gradient(ellipse at 50% 60%, rgba(0,255,157,0.12) 0%, transparent 70%)',
    particleColor: '#00ff9d',
    eyeShape: 'happy', mouthShape: 'wide-smile',
    animation: 'bounce', particleEffect: 'stars',
    auraEffect: 'cyan', scanlines: false, glitch: false,
  },
  angry: {
    label: 'ANGRY',
    primaryColor: '#ff2244',
    secondaryColor: '#1a0005',
    glowColor: 'rgba(255,34,68,0.6)',
    bgGradient: 'radial-gradient(ellipse at 50% 60%, rgba(255,34,68,0.15) 0%, transparent 70%)',
    particleColor: '#ff4400',
    eyeShape: 'angry', mouthShape: 'frown',
    animation: 'shake', particleEffect: 'sparks',
    auraEffect: 'red', scanlines: true, glitch: true,
  },
  sleepy: {
    label: 'SLEEPY',
    primaryColor: '#8866ff',
    secondaryColor: '#0d0018',
    glowColor: 'rgba(136,102,255,0.4)',
    bgGradient: 'radial-gradient(ellipse at 50% 60%, rgba(136,102,255,0.10) 0%, transparent 70%)',
    particleColor: '#8866ff',
    eyeShape: 'sleepy', mouthShape: 'small',
    animation: 'float', particleEffect: 'spiral',
    auraEffect: 'purple', scanlines: true, glitch: false,
  },
  panic: {
    label: 'PANIC',
    primaryColor: '#ffcc00',
    secondaryColor: '#1a1000',
    glowColor: 'rgba(255,204,0,0.6)',
    bgGradient: 'radial-gradient(ellipse at 50% 60%, rgba(255,204,0,0.15) 0%, transparent 70%)',
    particleColor: '#ffcc00',
    eyeShape: 'wide', mouthShape: 'open',
    animation: 'pulse-fast', particleEffect: 'explode',
    auraEffect: 'yellow', scanlines: true, glitch: true,
  },
  love: {
    label: 'LOVE',
    primaryColor: '#ff66aa',
    secondaryColor: '#1a000f',
    glowColor: 'rgba(255,102,170,0.5)',
    bgGradient: 'radial-gradient(ellipse at 50% 60%, rgba(255,102,170,0.12) 0%, transparent 70%)',
    particleColor: '#ff66aa',
    eyeShape: 'heart', mouthShape: 'smile',
    animation: 'float', particleEffect: 'hearts',
    auraEffect: 'pink', scanlines: false, glitch: false,
  },
  dizzy: {
    label: 'DIZZY',
    primaryColor: '#aa44ff',
    secondaryColor: '#0d0015',
    glowColor: 'rgba(170,68,255,0.5)',
    bgGradient: 'radial-gradient(ellipse at 50% 60%, rgba(170,68,255,0.12) 0%, transparent 70%)',
    particleColor: '#aa44ff',
    eyeShape: 'dizzy', mouthShape: 'zig-zag',
    animation: 'spin', particleEffect: 'spiral',
    auraEffect: 'rainbow', scanlines: false, glitch: true,
  },
  sad: {
    label: 'SAD',
    primaryColor: '#4488ff',
    secondaryColor: '#00020e',
    glowColor: 'rgba(68,136,255,0.4)',
    bgGradient: 'radial-gradient(ellipse at 50% 60%, rgba(68,136,255,0.10) 0%, transparent 70%)',
    particleColor: '#4488ff',
    eyeShape: 'sad', mouthShape: 'frown',
    animation: 'idle', particleEffect: 'tears',
    auraEffect: 'blue', scanlines: true, glitch: false,
  },
  talking: {
    label: 'TALKING',
    primaryColor: '#00f0ff',
    secondaryColor: '#001520',
    glowColor: 'rgba(0,240,255,0.5)',
    bgGradient: 'radial-gradient(ellipse at 50% 60%, rgba(0,240,255,0.12) 0%, transparent 70%)',
    particleColor: '#00f0ff',
    eyeShape: 'normal', mouthShape: 'talking',
    animation: 'wobble', particleEffect: 'music',
    auraEffect: 'cyan', scanlines: true, glitch: false,
  },
  listening: {
    label: 'LISTENING',
    primaryColor: '#00ffcc',
    secondaryColor: '#00150e',
    glowColor: 'rgba(0,255,204,0.4)',
    bgGradient: 'radial-gradient(ellipse at 50% 60%, rgba(0,255,204,0.10) 0%, transparent 70%)',
    particleColor: '#00ffcc',
    eyeShape: 'dot', mouthShape: 'small',
    animation: 'idle', particleEffect: 'music',
    auraEffect: 'cyan', scanlines: true, glitch: false,
  },
  thinking: {
    label: 'THINKING',
    primaryColor: '#ffaa00',
    secondaryColor: '#150a00',
    glowColor: 'rgba(255,170,0,0.4)',
    bgGradient: 'radial-gradient(ellipse at 50% 60%, rgba(255,170,0,0.10) 0%, transparent 70%)',
    particleColor: '#ffaa00',
    eyeShape: 'normal', mouthShape: 'small',
    animation: 'float', particleEffect: 'stars',
    auraEffect: 'yellow', scanlines: false, glitch: false,
  },
};

// ── Particle system ───────────────────────────────────────────────────────────
interface Particle {
  id: number;
  x: number; y: number;
  vx: number; vy: number;
  life: number; maxLife: number;
  size: number;
  symbol?: string;
  angle?: number;
  spin?: number;
}

function useParticles(effect: EmotionConfig['particleEffect'], color: string) {
  const [particles, setParticles] = useState<Particle[]>([]);
  const counterRef = useRef(0);
  const frameRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (effect === 'none') { setParticles([]); return; }

    const symbols: Record<string, string[]> = {
      hearts: ['♥', '❤', '♡'],
      sparks: ['✦', '✸', '✺', '⚡'],
      tears: ['💧', '·', '˙'],
      stars: ['★', '✦', '✧', '⋆', '°'],
      spiral: ['◉', '○', '●', '◎'],
      explode: ['✸', '✦', '✺', '◈'],
      music: ['♪', '♫', '♩', '♬'],
    };

    const spawnRate: Record<string, number> = {
      hearts: 25, sparks: 10, tears: 30, stars: 20,
      spiral: 15, explode: 5, music: 20,
    };

    let lastSpawn = 0;

    const tick = (time: number) => {
      if (time - lastSpawn > (spawnRate[effect] ?? 20)) {
        lastSpawn = time;
        const syms = symbols[effect] ?? ['·'];
        const id = counterRef.current++;

        let p: Particle;
        if (effect === 'tears') {
          p = { id, x: 28 + Math.random() * 44, y: 50, vx: (Math.random() - 0.5) * 0.3, vy: 1.5 + Math.random(), life: 1, maxLife: 1, size: 10 + Math.random() * 6, symbol: syms[Math.floor(Math.random() * syms.length)] };
        } else if (effect === 'spiral') {
          const angle = Math.random() * Math.PI * 2;
          p = { id, x: 50 + Math.cos(angle) * 20, y: 50 + Math.sin(angle) * 20, vx: Math.cos(angle) * 0.4, vy: Math.sin(angle) * 0.4 - 0.6, life: 1, maxLife: 1, size: 8 + Math.random() * 6, symbol: syms[Math.floor(Math.random() * syms.length)], angle, spin: (Math.random() - 0.5) * 5 };
        } else if (effect === 'explode') {
          const angle = Math.random() * Math.PI * 2;
          const speed = 1.5 + Math.random() * 2;
          p = { id, x: 50, y: 50, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed, life: 1, maxLife: 1, size: 10 + Math.random() * 8, symbol: syms[Math.floor(Math.random() * syms.length)], spin: (Math.random() - 0.5) * 8 };
        } else {
          p = { id, x: 10 + Math.random() * 80, y: 85 + Math.random() * 10, vx: (Math.random() - 0.5) * 0.8, vy: -(0.8 + Math.random() * 1.2), life: 1, maxLife: 1, size: 10 + Math.random() * 8, symbol: syms[Math.floor(Math.random() * syms.length)], spin: (Math.random() - 0.5) * 4 };
        }

        setParticles(prev => [...prev.slice(-25), p]);
      }

      setParticles(prev =>
        prev
          .map(p => ({ ...p, x: p.x + p.vx, y: p.y + p.vy, vy: p.vy + 0.04, life: p.life - 0.018, angle: (p.angle ?? 0) + (p.spin ?? 0) * 0.02 }))
          .filter(p => p.life > 0)
      );

      frameRef.current = requestAnimationFrame(tick);
    };

    frameRef.current = requestAnimationFrame(tick);
    return () => { if (frameRef.current) cancelAnimationFrame(frameRef.current); };
  }, [effect, color]);

  return particles;
}

// ── Blink animation hook ──────────────────────────────────────────────────────
function useBlinkState(emotion: string) {
  const [blinkProgress, setBlinkProgress] = useState(0);
  const frameRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    let phase: 'open' | 'closing' | 'closed' | 'opening' = 'open';
    let progress = 0;
    let waitFrames = 0;
    const waitDuration = () => 80 + Math.random() * 200;

    if (emotion === 'sleepy') {
      setBlinkProgress(0.65);
      return;
    }

    const tick = () => {
      if (phase === 'open') {
        waitFrames++;
        if (waitFrames > waitDuration()) { phase = 'closing'; waitFrames = 0; }
      } else if (phase === 'closing') {
        progress = Math.min(1, progress + 0.12);
        setBlinkProgress(progress);
        if (progress >= 1) { phase = 'closed'; waitFrames = 0; }
      } else if (phase === 'closed') {
        waitFrames++;
        if (waitFrames > 5) { phase = 'opening'; }
      } else {
        progress = Math.max(0, progress - 0.12);
        setBlinkProgress(progress);
        if (progress <= 0) { phase = 'open'; waitFrames = 0; }
      }
      frameRef.current = requestAnimationFrame(tick);
    };

    frameRef.current = requestAnimationFrame(tick);
    return () => { if (frameRef.current) cancelAnimationFrame(frameRef.current); };
  }, [emotion]);

  return blinkProgress;
}

// ── Mouth animation hook ──────────────────────────────────────────────────────
function useMouthState(mouthShape: EmotionConfig['mouthShape']) {
  const [phase, setPhase] = useState(0);
  useEffect(() => {
    if (mouthShape !== 'talking') return;
    const id = setInterval(() => setPhase(p => (p + 1) % 4), 150);
    return () => clearInterval(id);
  }, [mouthShape]);
  return phase;
}

// ── SVG Face ─────────────────────────────────────────────────────────────────
function FaceSVG({ config, blinkProgress, mouthPhase }: {
  config: EmotionConfig;
  blinkProgress: number;
  mouthPhase: number;
}) {
  const c = config;
  const eyeY = 40;
  const eyeLX = 33, eyeRX = 67;
  const eyeW = 12, eyeH = 10;
  const blinkH = eyeH * (1 - blinkProgress);

  const renderEye = (cx: number, isLeft: boolean) => {
    const ey = eyeY;
    switch (c.eyeShape) {
      case 'happy':
        return (
          <g key={isLeft ? 'el' : 'er'}>
            <clipPath id={`happy-clip-${isLeft ? 'l' : 'r'}`}>
              <rect x={cx - eyeW} y={ey - eyeH} width={eyeW * 2} height={eyeH} />
            </clipPath>
            <ellipse cx={cx} cy={ey} rx={eyeW} ry={eyeH * (1 - blinkProgress * 0.5)} fill="none" stroke={c.primaryColor} strokeWidth="2.5" clipPath={`url(#happy-clip-${isLeft ? 'l' : 'r'})`} />
            <ellipse cx={cx} cy={ey} rx={eyeW * 0.5} ry={eyeH * 0.4 * (1 - blinkProgress * 0.7)} fill={c.primaryColor} opacity="0.7" />
          </g>
        );
      case 'angry':
        return (
          <g key={isLeft ? 'el' : 'er'}>
            <line x1={cx - eyeW} y1={ey - eyeH * 0.8} x2={cx + eyeW} y2={ey - eyeH * 0.2 * (isLeft ? 1 : -1)} stroke={c.primaryColor} strokeWidth="2.5" strokeLinecap="round" />
            <ellipse cx={cx} cy={ey + 2} rx={eyeW * 0.85} ry={Math.max(1, eyeH * 0.65 * (1 - blinkProgress))} fill={c.primaryColor} opacity="0.85" />
          </g>
        );
      case 'sleepy':
        return (
          <g key={isLeft ? 'el' : 'er'}>
            <ellipse cx={cx} cy={ey} rx={eyeW} ry={Math.max(0.5, eyeH * (1 - 0.65))} fill="none" stroke={c.primaryColor} strokeWidth="2.5" />
            <line x1={cx - eyeW * 0.8} y1={ey - eyeH * 0.65} x2={cx + eyeW * 0.8} y2={ey - eyeH * 0.65} stroke={c.primaryColor} strokeWidth="2.5" strokeLinecap="round" />
          </g>
        );
      case 'wide':
        return (
          <g key={isLeft ? 'el' : 'er'}>
            <ellipse cx={cx} cy={ey} rx={eyeW * 1.2} ry={Math.max(0.5, eyeH * 1.3 * (1 - blinkProgress))} fill="none" stroke={c.primaryColor} strokeWidth="2.5" />
            <ellipse cx={cx} cy={ey} rx={eyeW * 0.5} ry={Math.max(0.5, eyeH * 0.5 * (1 - blinkProgress))} fill={c.primaryColor} />
            <ellipse cx={cx + 3} cy={ey - 3} rx={2} ry={2} fill="white" opacity="0.8" />
          </g>
        );
      case 'heart': {
        const hx = cx, hy = ey;
        return (
          <g key={isLeft ? 'el' : 'er'} opacity={1 - blinkProgress * 0.9}>
            <path d={`M${hx},${hy+3} C${hx-6},${hy-3} ${hx-10},${hy-7} ${hx-6},${hy-10} C${hx-2},${hy-13} ${hx},${hy-9} ${hx},${hy-9} C${hx},${hy-9} ${hx+2},${hy-13} ${hx+6},${hy-10} C${hx+10},${hy-7} ${hx+6},${hy-3} ${hx},${hy+3} Z`} fill={c.primaryColor} opacity="0.9" />
          </g>
        );
      }
      case 'dizzy':
        return (
          <g key={isLeft ? 'el' : 'er'} opacity={1 - blinkProgress * 0.5}>
            <ellipse cx={cx} cy={ey} rx={eyeW} ry={eyeH * 0.9} fill="none" stroke={c.primaryColor} strokeWidth="1.5" opacity="0.4" />
            <line x1={cx - eyeW * 0.7} y1={ey - eyeH * 0.6} x2={cx + eyeW * 0.7} y2={ey + eyeH * 0.6} stroke={c.primaryColor} strokeWidth="2.5" strokeLinecap="round" />
            <line x1={cx + eyeW * 0.7} y1={ey - eyeH * 0.6} x2={cx - eyeW * 0.7} y2={ey + eyeH * 0.6} stroke={c.primaryColor} strokeWidth="2.5" strokeLinecap="round" />
          </g>
        );
      case 'sad':
        return (
          <g key={isLeft ? 'el' : 'er'}>
            <line x1={cx - eyeW} y1={ey - eyeH * 0.2 * (isLeft ? 1 : -1)} x2={cx + eyeW} y2={ey - eyeH * 0.8} stroke={c.primaryColor} strokeWidth="2.5" strokeLinecap="round" />
            <ellipse cx={cx} cy={ey + 2} rx={eyeW * 0.8} ry={Math.max(0.5, eyeH * 0.55 * (1 - blinkProgress))} fill={c.primaryColor} opacity="0.75" />
          </g>
        );
      case 'dot':
        return (
          <g key={isLeft ? 'el' : 'er'}>
            <ellipse cx={cx} cy={ey} rx={eyeW} ry={Math.max(0.5, eyeH * (1 - blinkProgress * 0.9))} fill="none" stroke={c.primaryColor} strokeWidth="1.5" opacity="0.4" />
            <circle cx={cx} cy={ey} r={Math.max(0.5, 4 * (1 - blinkProgress * 0.8))} fill={c.primaryColor} />
          </g>
        );
      default:
        return (
          <g key={isLeft ? 'el' : 'er'}>
            <ellipse cx={cx} cy={ey} rx={eyeW} ry={Math.max(0.5, blinkH)} fill="none" stroke={c.primaryColor} strokeWidth="2.5" />
            <ellipse cx={cx} cy={ey} rx={eyeW * 0.45} ry={Math.max(0.5, blinkH * 0.6)} fill={c.primaryColor} opacity="0.9" />
            <ellipse cx={cx + 3} cy={ey - 2} rx={2} ry={Math.max(0.5, blinkH * 0.3)} fill="white" opacity="0.7" />
          </g>
        );
    }
  };

  const getMouthPath = () => {
    switch (c.mouthShape) {
      case 'wide-smile': return `M 28,65 Q 50,82 72,65`;
      case 'smile':      return `M 35,65 Q 50,75 65,65`;
      case 'frown':      return `M 30,70 Q 50,58 70,70`;
      case 'open':       return `M 36,63 Q 50,80 64,63`;
      case 'zig-zag':    return `M 32,64 L 40,70 L 50,62 L 60,70 L 68,64`;
      case 'small':      return `M 42,66 Q 50,70 58,66`;
      case 'talking': {
        const opens = ['M 36,63 Q 50,63 64,63', 'M 36,63 Q 50,74 64,63', 'M 36,63 Q 50,80 64,63', 'M 36,63 Q 50,74 64,63'];
        return opens[mouthPhase] ?? opens[0];
      }
      default:           return `M 38,66 L 62,66`;
    }
  };

  const mouthIsFill = c.mouthShape === 'open' || c.mouthShape === 'talking';
  const mouthPath = getMouthPath();

  return (
    <svg viewBox="0 0 100 100" className="w-full h-full" style={{ overflow: 'visible' }}>
      <defs>
        <filter id="glow" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="2.5" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        <filter id="glow-strong" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="4" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        <radialGradient id="face-grad" cx="50%" cy="45%" r="55%">
          <stop offset="0%" stopColor={c.primaryColor} stopOpacity="0.15" />
          <stop offset="100%" stopColor={c.primaryColor} stopOpacity="0.03" />
        </radialGradient>
      </defs>

      <circle cx="50" cy="50" r="46" fill="url(#face-grad)" stroke={c.primaryColor} strokeWidth="1.5" strokeOpacity="0.5" filter="url(#glow)" />
      <circle cx="50" cy="50" r="42" fill="none" stroke={c.primaryColor} strokeWidth="0.5" strokeOpacity="0.2" strokeDasharray="4 4" />

      <g filter="url(#glow-strong)">
        {renderEye(eyeLX, true)}
        {renderEye(eyeRX, false)}
      </g>

      <g filter="url(#glow)">
        {mouthIsFill ? (
          <>
            <path d={mouthPath} fill={c.primaryColor} opacity="0.25" />
            <path d={mouthPath} fill="none" stroke={c.primaryColor} strokeWidth="2.5" strokeLinecap="round" />
          </>
        ) : (
          <path d={mouthPath} fill="none" stroke={c.primaryColor} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        )}
      </g>

      {(c.eyeShape === 'happy' || c.eyeShape === 'heart') && (
        <g opacity="0.6">
          <ellipse cx="22" cy="60" rx="8" ry="5" fill={c.primaryColor} opacity="0.25" />
          <ellipse cx="78" cy="60" rx="8" ry="5" fill={c.primaryColor} opacity="0.25" />
        </g>
      )}
    </svg>
  );
}

// ── Aura rings ────────────────────────────────────────────────────────────────
function AuraRings({ config }: { config: EmotionConfig }) {
  const auraColors: Record<string, string[]> = {
    cyan:    ['rgba(0,240,255,0.25)', 'rgba(0,240,255,0.12)', 'rgba(0,240,255,0.05)'],
    red:     ['rgba(255,34,68,0.30)', 'rgba(255,34,68,0.15)', 'rgba(255,34,68,0.06)'],
    yellow:  ['rgba(255,204,0,0.28)', 'rgba(255,204,0,0.13)', 'rgba(255,204,0,0.05)'],
    pink:    ['rgba(255,102,170,0.28)', 'rgba(255,102,170,0.13)', 'rgba(255,102,170,0.05)'],
    blue:    ['rgba(68,136,255,0.25)', 'rgba(68,136,255,0.12)', 'rgba(68,136,255,0.05)'],
    purple:  ['rgba(136,102,255,0.25)', 'rgba(136,102,255,0.12)', 'rgba(136,102,255,0.05)'],
    rainbow: ['rgba(255,0,200,0.2)', 'rgba(0,200,255,0.2)', 'rgba(255,200,0,0.15)'],
    none:    [],
  };

  const colors = auraColors[config.auraEffect] ?? [];
  if (!colors.length) return null;

  return (
    <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
      {colors.map((color, i) => (
        <div
          key={i}
          className="absolute rounded-full emotion-aura-ring"
          style={{
            width: `${110 + i * 30}%`,
            height: `${110 + i * 30}%`,
            border: `1.5px solid ${color}`,
            boxShadow: `0 0 ${12 + i * 8}px ${color}`,
            animationDelay: `${i * 0.4}s`,
            animationDuration: `${2.5 + i * 0.8}s`,
          }}
        />
      ))}
    </div>
  );
}

// ── Main EmotionPet component ─────────────────────────────────────────────────
interface EmotionPetProps {
  emotion: string;
  size?: 'sm' | 'md' | 'lg';
}

export const EmotionPet: React.FC<EmotionPetProps> = ({ emotion, size = 'md' }) => {
  const config = EMOTIONS[emotion] ?? EMOTIONS['idle'];
  const particles = useParticles(config.particleEffect, config.particleColor);
  const blinkProgress = useBlinkState(emotion);
  const mouthPhase = useMouthState(config.mouthShape);
  const [glitchActive, setGlitchActive] = useState(false);
  const [prevEmotion, setPrevEmotion] = useState(emotion);
  const [transitioning, setTransitioning] = useState(false);

  useEffect(() => {
    if (!config.glitch) return;
    const interval = setInterval(() => {
      setGlitchActive(true);
      setTimeout(() => setGlitchActive(false), 150 + Math.random() * 200);
    }, 1500 + Math.random() * 2000);
    return () => clearInterval(interval);
  }, [config.glitch, emotion]);

  useEffect(() => {
    if (emotion !== prevEmotion) {
      setTransitioning(true);
      setTimeout(() => { setTransitioning(false); setPrevEmotion(emotion); }, 400);
    }
  }, [emotion, prevEmotion]);

  const sizeClass = { sm: 'w-28 h-28', md: 'w-44 h-44', lg: 'w-56 h-56' }[size];

  const animClass: Record<EmotionConfig['animation'], string> = {
    idle:         'emotion-anim-idle',
    bounce:       'emotion-anim-bounce',
    shake:        'emotion-anim-shake',
    spin:         'emotion-anim-spin',
    'pulse-fast': 'emotion-anim-pulse-fast',
    float:        'emotion-anim-float',
    glitch:       'emotion-anim-glitch',
    wobble:       'emotion-anim-wobble',
  };

  return (
    <div className="relative flex flex-col items-center justify-center select-none">
      <div
        className={`relative ${sizeClass} flex items-center justify-center`}
        style={{ filter: `drop-shadow(0 0 18px ${config.glowColor}) drop-shadow(0 0 6px ${config.primaryColor})` }}
      >
        <AuraRings config={config} />

        <div
          className={`relative w-full h-full flex items-center justify-center ${animClass[config.animation]}`}
          style={{
            opacity: transitioning ? 0 : 1,
            transform: transitioning ? 'scale(0.9)' : 'scale(1)',
            transition: 'opacity 0.25s ease, transform 0.25s ease',
          }}
        >
          {config.scanlines && (
            <div
              className="absolute inset-0 rounded-full overflow-hidden pointer-events-none z-10"
              style={{ background: 'repeating-linear-gradient(0deg, transparent, transparent 3px, rgba(0,0,0,0.08) 3px, rgba(0,0,0,0.08) 4px)' }}
            />
          )}

          {glitchActive && (
            <>
              <div className="absolute inset-0 rounded-full z-20 pointer-events-none" style={{ background: `${config.primaryColor}22`, mixBlendMode: 'screen', transform: 'translate(3px, 0)', filter: 'blur(1px)' }} />
              <div className="absolute inset-0 rounded-full z-20 pointer-events-none" style={{ background: 'rgba(255,0,80,0.1)', mixBlendMode: 'screen', transform: 'translate(-2px, 0)' }} />
            </>
          )}

          <FaceSVG config={config} blinkProgress={blinkProgress} mouthPhase={mouthPhase} />
        </div>

        <div className="absolute inset-0 pointer-events-none overflow-visible" style={{ zIndex: 30 }}>
          {particles.map(p => (
            <div
              key={p.id}
              className="absolute"
              style={{
                left: `${p.x}%`,
                top: `${p.y}%`,
                fontSize: `${p.size}px`,
                color: config.particleColor,
                opacity: p.life,
                transform: `rotate(${p.angle ?? 0}rad)`,
                textShadow: `0 0 8px ${config.particleColor}`,
                pointerEvents: 'none',
                lineHeight: 1,
                willChange: 'transform, opacity',
              }}
            >
              {p.symbol}
            </div>
          ))}
        </div>
      </div>

      <div
        className="mt-3 px-4 py-1 rounded-full text-xs font-bold tracking-widest uppercase"
        style={{
          background: `linear-gradient(90deg, ${config.primaryColor}22, ${config.primaryColor}44, ${config.primaryColor}22)`,
          border: `1px solid ${config.primaryColor}66`,
          color: config.primaryColor,
          boxShadow: `0 0 10px ${config.glowColor}, inset 0 0 8px ${config.primaryColor}11`,
          letterSpacing: '0.2em',
        }}
      >
        <span className="inline-block animate-pulse mr-1.5" style={{ color: config.primaryColor }}>◈</span>
        {config.label}
      </div>
    </div>
  );
};

export default EmotionPet;
