import React, { useEffect, useMemo, useRef, useState } from 'react';

/**
 * Патрик — мордочка питомца в web-панели.
 * Рисуется тем же «языком», что и прошивка на M5: розовая голова-конус,
 * огромные глаза с чёрными зрачками, открытый рот со слюнкой и зелёные шорты.
 * Все состояния совпадают с эмоциями прошивки, поэтому экран устройства
 * и панель показывают одно и то же.
 */

export type PetEmotion =
  | 'idle' | 'happy' | 'angry' | 'sad' | 'love' | 'dizzy' | 'sleepy'
  | 'working' | 'listening' | 'talking' | 'thinking' | 'panic' | 'sweat' | 'party';

type EyeShape = 'normal' | 'squint' | 'angry' | 'sad' | 'wide' | 'heart' | 'spiral' | 'closed' | 'focus';
type MouthShape = 'open' | 'smile' | 'grin' | 'frown' | 'small' | 'talk' | 'wave' | 'o';
type BodyAnim = 'breathe' | 'bounce' | 'shake' | 'sway' | 'float' | 'jitter' | 'nod' | 'spin-wobble';
type Particles = 'none' | 'hearts' | 'stars' | 'sparks' | 'tears' | 'notes' | 'zzz' | 'code' | 'waves' | 'sweat';

interface EmotionConfig {
  label: string;
  accent: string;
  glow: string;
  eyes: EyeShape;
  mouth: MouthShape;
  brows: 'neutral' | 'angry' | 'sad' | 'up' | 'wiggle';
  body: BodyAnim;
  particles: Particles;
  drool: boolean;
  blush: boolean;
  blink: boolean;
}

export const EMOTIONS: Record<PetEmotion, EmotionConfig> = {
  idle:      { label: 'Отдыхает',   accent: '#ff9bb0', glow: 'rgba(255,155,176,0.35)', eyes: 'normal', mouth: 'open',  brows: 'neutral', body: 'breathe', particles: 'none',   drool: true,  blush: false, blink: true },
  happy:     { label: 'Радуется',   accent: '#ffd166', glow: 'rgba(255,209,102,0.45)', eyes: 'squint', mouth: 'grin',  brows: 'up',      body: 'bounce',  particles: 'stars',  drool: false, blush: true,  blink: false },
  angry:     { label: 'Злится',     accent: '#ff4d5e', glow: 'rgba(255,77,94,0.45)',   eyes: 'angry',  mouth: 'frown', brows: 'angry',   body: 'shake',   particles: 'sparks', drool: false, blush: false, blink: true },
  sad:       { label: 'Грустит',    accent: '#5aa9ff', glow: 'rgba(90,169,255,0.4)',   eyes: 'sad',    mouth: 'frown', brows: 'sad',     body: 'sway',    particles: 'tears',  drool: false, blush: false, blink: true },
  love:      { label: 'Влюблён',    accent: '#ff5fa2', glow: 'rgba(255,95,162,0.5)',   eyes: 'heart',  mouth: 'smile', brows: 'up',      body: 'float',   particles: 'hearts', drool: false, blush: true,  blink: false },
  dizzy:     { label: 'Кружится',   accent: '#c084fc', glow: 'rgba(192,132,252,0.45)', eyes: 'spiral', mouth: 'wave',  brows: 'wiggle',  body: 'spin-wobble', particles: 'stars', drool: true, blush: false, blink: false },
  sleepy:    { label: 'Спит',       accent: '#8b8bff', glow: 'rgba(139,139,255,0.35)', eyes: 'closed', mouth: 'o',     brows: 'neutral', body: 'float',   particles: 'zzz',    drool: true,  blush: false, blink: false },
  working:   { label: 'Работает',   accent: '#33d69f', glow: 'rgba(51,214,159,0.4)',   eyes: 'focus',  mouth: 'small', brows: 'neutral', body: 'nod',     particles: 'code',   drool: false, blush: false, blink: true },
  listening: { label: 'Слушает',    accent: '#22d3ee', glow: 'rgba(34,211,238,0.45)',  eyes: 'wide',   mouth: 'small', brows: 'up',      body: 'breathe', particles: 'waves',  drool: true,  blush: false, blink: true },
  talking:   { label: 'Говорит',    accent: '#38bdf8', glow: 'rgba(56,189,248,0.45)',  eyes: 'normal', mouth: 'talk',  brows: 'neutral', body: 'nod',     particles: 'none',   drool: true,  blush: false, blink: true },
  thinking:  { label: 'Думает',     accent: '#a78bfa', glow: 'rgba(167,139,250,0.4)',  eyes: 'focus',  mouth: 'small', brows: 'up',      body: 'sway',    particles: 'code',   drool: false, blush: false, blink: true },
  panic:     { label: 'Паникует',   accent: '#ff6b35', glow: 'rgba(255,107,53,0.5)',   eyes: 'wide',   mouth: 'o',     brows: 'sad',     body: 'jitter',  particles: 'sweat',  drool: false, blush: false, blink: false },
  sweat:     { label: 'Перегрев',   accent: '#ffb703', glow: 'rgba(255,183,3,0.45)',   eyes: 'squint', mouth: 'frown', brows: 'sad',     body: 'sway',    particles: 'sweat',  drool: false, blush: true,  blink: true },
  party:     { label: 'Пати',       accent: '#f472b6', glow: 'rgba(244,114,182,0.5)',  eyes: 'squint', mouth: 'grin',  brows: 'wiggle',  body: 'bounce',  particles: 'notes',  drool: false, blush: true,  blink: false },
};

const SKIN = '#ff9bb0';
const SKIN_DARK = '#e87d95';
const SKIN_LIGHT = '#ffb7c6';
const MOUTH_BG = '#5d1a1f';
const TONGUE = '#ff7d96';
const PANTS = '#7ac943';
const FLOWER = '#9b30d9';

/** Один rAF-цикл на компонент: моргание, «болтовня» рта и фаза дыхания. */
function usePetTicker(emotion: PetEmotion) {
  const config = EMOTIONS[emotion] ?? EMOTIONS.idle;
  const [frame, setFrame] = useState({ blink: 0, mouth: 0, phase: 0 });
  const raf = useRef<number>(0);

  useEffect(() => {
    let blink = 0;
    let nextBlink = performance.now() + 1500 + Math.random() * 3500;
    let blinkStart = 0;
    let lastRender = 0;

    const tick = (now: number) => {
      if (config.blink) {
        if (!blinkStart && now > nextBlink) blinkStart = now;
        if (blinkStart) {
          const t = (now - blinkStart) / 140;
          blink = t < 0.5 ? t * 2 : Math.max(0, 2 - t * 2);
          if (t >= 1) {
            blink = 0;
            blinkStart = 0;
            nextBlink = now + 1800 + Math.random() * 4000;
          }
        }
      } else {
        blink = 0;
      }

      if (now - lastRender > 33) {
        lastRender = now;
        setFrame({
          blink,
          mouth: config.mouth === 'talk' ? Math.abs(Math.sin(now / 90)) : 0,
          phase: now / 1000,
        });
      }
      raf.current = requestAnimationFrame(tick);
    };

    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [emotion, config.blink, config.mouth]);

  return frame;
}

/** Зрачки следят за курсором — питомец «замечает» пользователя. */
function usePupilTracking(ref: React.RefObject<HTMLDivElement | null>, active: boolean) {
  const [offset, setOffset] = useState({ x: 0, y: 0 });

  useEffect(() => {
    if (!active) {
      setOffset({ x: 0, y: 0 });
      return;
    }
    let scheduled = false;
    const onMove = (event: PointerEvent) => {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(() => {
        scheduled = false;
        const box = ref.current?.getBoundingClientRect();
        if (!box) return;
        const dx = (event.clientX - (box.left + box.width / 2)) / (box.width / 2);
        const dy = (event.clientY - (box.top + box.height / 2)) / (box.height / 2);
        setOffset({
          x: Math.max(-1, Math.min(1, dx)) * 4.5,
          y: Math.max(-1, Math.min(1, dy)) * 3.5,
        });
      });
    };
    window.addEventListener('pointermove', onMove);
    return () => window.removeEventListener('pointermove', onMove);
  }, [ref, active]);

  return offset;
}

interface ParticleProps {
  kind: Particles;
  accent: string;
}

const PARTICLE_SYMBOLS: Record<Particles, string[]> = {
  none: [],
  hearts: ['♥', '❤', '♡'],
  stars: ['★', '✦', '✧', '⋆'],
  sparks: ['✦', '⚡', '✸'],
  tears: ['💧'],
  notes: ['♪', '♫', '♬'],
  zzz: ['z', 'Z'],
  code: ['{ }', '</>', '01', 'λ'],
  waves: ['◟', '◞', '≈'],
  sweat: ['💦'],
};

const ParticleLayer: React.FC<ParticleProps> = ({ kind, accent }) => {
  const symbols = PARTICLE_SYMBOLS[kind];
  const items = useMemo(
    () =>
      symbols.length === 0
        ? []
        : Array.from({ length: 6 }, (_, i) => ({
            id: i,
            symbol: symbols[i % symbols.length],
            left: 8 + ((i * 37) % 84),
            delay: (i * 0.55) % 3.2,
            duration: 2.8 + ((i * 0.37) % 1.8),
            size: 11 + ((i * 5) % 9),
          })),
    [symbols],
  );

  if (items.length === 0) return null;

  const falling = kind === 'tears' || kind === 'sweat';

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
      {items.map(item => (
        <span
          key={item.id}
          className={falling ? 'pet-particle-fall' : 'pet-particle-rise'}
          style={{
            left: `${item.left}%`,
            fontSize: `${item.size}px`,
            color: accent,
            animationDelay: `${item.delay}s`,
            animationDuration: `${item.duration}s`,
            textShadow: `0 0 10px ${accent}`,
          }}
        >
          {item.symbol}
        </span>
      ))}
    </div>
  );
};

interface PatrickPetProps {
  emotion: string;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  caption?: string;
  onPat?: () => void;
  showLabel?: boolean;
}

const SIZES = { sm: 96, md: 160, lg: 240, xl: 320 };

export const PatrickPet: React.FC<PatrickPetProps> = ({
  emotion,
  size = 'lg',
  caption,
  onPat,
  showLabel = true,
}) => {
  const key = (emotion in EMOTIONS ? emotion : 'idle') as PetEmotion;
  const config = EMOTIONS[key];
  const containerRef = useRef<HTMLDivElement>(null);
  const { blink, mouth, phase } = usePetTicker(key);
  const tracking = usePupilTracking(containerRef, config.eyes === 'normal' || config.eyes === 'wide');
  const [patted, setPatted] = useState(false);

  const px = SIZES[size];
  const breathe = Math.sin(phase * 1.6) * 1.6;

  const eyeOpen = (base: number) => Math.max(0.6, base * (1 - blink));

  const handlePat = () => {
    if (!onPat) return;
    onPat();
    setPatted(true);
    setTimeout(() => setPatted(false), 600);
  };

  return (
    <div className="flex flex-col items-center gap-3 select-none">
      <div
        ref={containerRef}
        className={`relative ${onPat ? 'cursor-pointer' : ''}`}
        style={{ width: px, height: px }}
        onClick={handlePat}
        role={onPat ? 'button' : undefined}
        aria-label={onPat ? 'Погладить питомца' : undefined}
        title={onPat ? 'Погладить' : undefined}
      >
        {/* Ореол настроения */}
        <div
          className="absolute inset-0 rounded-full pet-aura"
          style={{ background: `radial-gradient(circle at 50% 55%, ${config.glow} 0%, transparent 68%)` }}
        />

        <ParticleLayer kind={config.particles} accent={config.accent} />

        <svg
          viewBox="0 0 200 200"
          className={`relative h-full w-full pet-body pet-anim-${config.body} ${patted ? 'pet-patted' : ''}`}
          style={{ overflow: 'visible' }}
        >
          <defs>
            <radialGradient id="skinGrad" cx="42%" cy="28%" r="78%">
              <stop offset="0%" stopColor={SKIN_LIGHT} />
              <stop offset="70%" stopColor={SKIN} />
              <stop offset="100%" stopColor={SKIN_DARK} />
            </radialGradient>
            <radialGradient id="mouthGrad" cx="50%" cy="30%" r="70%">
              <stop offset="0%" stopColor="#7a2027" />
              <stop offset="100%" stopColor={MOUTH_BG} />
            </radialGradient>
            <linearGradient id="droolGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#dff3ff" stopOpacity="0.95" />
              <stop offset="100%" stopColor="#9fd8ff" stopOpacity="0.75" />
            </linearGradient>
            <filter id="softShadow" x="-30%" y="-30%" width="160%" height="160%">
              <feDropShadow dx="0" dy="4" stdDeviation="5" floodColor="#000" floodOpacity="0.35" />
            </filter>
          </defs>

          <g filter="url(#softShadow)" transform={`translate(0 ${breathe})`}>
            {/* Руки-обрубки */}
            <g className="pet-arm pet-arm-left">
              <ellipse cx="34" cy="140" rx="15" ry="12" fill={SKIN_DARK} />
            </g>
            <g className="pet-arm pet-arm-right">
              <ellipse cx="166" cy="140" rx="15" ry="12" fill={SKIN_DARK} />
            </g>

            {/* Тело-конус (голова морской звезды) */}
            <path
              d="M100 10
                 C112 10 120 20 124 34
                 L158 150
                 C162 166 150 178 132 178
                 L68 178
                 C50 178 38 166 42 150
                 L76 34
                 C80 20 88 10 100 10 Z"
              fill="url(#skinGrad)"
            />

            {/* Пятнышки как у морской звезды */}
            <g opacity="0.35" fill={SKIN_DARK}>
              <ellipse cx="72" cy="52" rx="4" ry="3" />
              <ellipse cx="128" cy="44" rx="3" ry="2.4" />
              <ellipse cx="60" cy="120" rx="5" ry="3.4" />
              <ellipse cx="142" cy="112" rx="4" ry="2.8" />
            </g>

            {/* Шорты */}
            <path d="M44 158 L156 158 L158 174 C158 180 152 184 146 184 L54 184 C48 184 42 180 42 174 Z" fill={PANTS} />
            <g fill={FLOWER} opacity="0.9">
              <circle cx="66" cy="170" r="5" />
              <circle cx="100" cy="174" r="6" />
              <circle cx="134" cy="168" r="5" />
            </g>
            <path d="M44 158 L156 158 L157 163 L43 163 Z" fill="#5aa32c" opacity="0.6" />

            {/* Брови */}
            <Brows shape={config.brows} phase={phase} />

            {/* Глаза */}
            <Eyes
              shape={config.eyes}
              open={eyeOpen(1)}
              look={tracking}
              phase={phase}
              accent={config.accent}
            />

            {/* Румянец */}
            {config.blush && (
              <g opacity="0.55">
                <ellipse cx="62" cy="108" rx="13" ry="7" fill="#ff5f8f" />
                <ellipse cx="138" cy="108" rx="13" ry="7" fill="#ff5f8f" />
              </g>
            )}

            {/* Рот */}
            <Mouth shape={config.mouth} openness={mouth} phase={phase} />

            {/* Слюнка */}
            {config.drool && <Drool phase={phase} />}
          </g>
        </svg>
      </div>

      {showLabel && (
        <div
          className="rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em]"
          style={{
            color: config.accent,
            borderColor: `${config.accent}66`,
            background: `${config.accent}14`,
            boxShadow: `0 0 14px ${config.glow}`,
          }}
        >
          {config.label}
        </div>
      )}

      {caption && (
        <p className="max-w-xs text-center text-sm leading-snug text-slate-300">{caption}</p>
      )}
    </div>
  );
};

// ── Части лица ────────────────────────────────────────────────────────────

const Brows: React.FC<{ shape: EmotionConfig['brows']; phase: number }> = ({ shape, phase }) => {
  const wiggle = Math.sin(phase * 6) * 3;
  const paths: Record<EmotionConfig['brows'], [string, string]> = {
    neutral: ['M60 62 Q74 54 88 60', 'M112 60 Q126 54 140 62'],
    angry:   ['M58 54 L90 66', 'M110 66 L142 54'],
    sad:     ['M58 66 L90 54', 'M110 54 L142 66'],
    up:      ['M58 56 Q74 44 90 54', 'M110 54 Q126 44 142 56'],
    wiggle:  [`M58 ${60 + wiggle} Q74 ${50 - wiggle} 90 ${58 + wiggle}`, `M110 ${58 - wiggle} Q126 ${50 + wiggle} 142 ${60 - wiggle}`],
  };
  const [left, right] = paths[shape];
  return (
    <g stroke="#3b1f24" strokeWidth="5" strokeLinecap="round" fill="none">
      <path d={left} />
      <path d={right} />
    </g>
  );
};

interface EyesProps {
  shape: EyeShape;
  open: number;
  look: { x: number; y: number };
  phase: number;
  accent: string;
}

const Eyes: React.FC<EyesProps> = ({ shape, open, look, phase, accent }) => {
  const eyes = [
    { cx: 76, cy: 84 },
    { cx: 124, cy: 84 },
  ];

  if (shape === 'closed') {
    return (
      <g stroke="#3b1f24" strokeWidth="4" strokeLinecap="round" fill="none">
        <path d="M62 86 Q76 96 90 86" />
        <path d="M110 86 Q124 96 138 86" />
      </g>
    );
  }

  if (shape === 'squint') {
    return (
      <g stroke="#3b1f24" strokeWidth="5" strokeLinecap="round" fill="none">
        <path d="M60 90 Q76 74 92 90" />
        <path d="M108 90 Q124 74 140 90" />
      </g>
    );
  }

  if (shape === 'heart') {
    const pulse = 1 + Math.sin(phase * 5) * 0.08;
    return (
      <g fill="#ff2d6f">
        {eyes.map(eye => (
          <path
            key={eye.cx}
            transform={`translate(${eye.cx} ${eye.cy}) scale(${pulse})`}
            d="M0 12 C-14 0 -18 -10 -10 -15 C-4 -19 0 -13 0 -10 C0 -13 4 -19 10 -15 C18 -10 14 0 0 12 Z"
          />
        ))}
      </g>
    );
  }

  if (shape === 'spiral') {
    const rotate = (phase * 220) % 360;
    return (
      <g fill="#fff" stroke="#3b1f24" strokeWidth="3">
        {eyes.map(eye => (
          <g key={eye.cx}>
            <ellipse cx={eye.cx} cy={eye.cy} rx="20" ry="22" />
            <g transform={`rotate(${rotate} ${eye.cx} ${eye.cy})`} stroke="#3b1f24" strokeWidth="4" fill="none">
              <path d={`M${eye.cx - 11} ${eye.cy - 11} L${eye.cx + 11} ${eye.cy + 11}`} />
              <path d={`M${eye.cx + 11} ${eye.cy - 11} L${eye.cx - 11} ${eye.cy + 11}`} />
            </g>
          </g>
        ))}
      </g>
    );
  }

  const geometry: Record<string, { rx: number; ry: number; pupil: number; lid: number }> = {
    normal: { rx: 21, ry: 24, pupil: 11, lid: 0 },
    wide:   { rx: 24, ry: 28, pupil: 9,  lid: 0 },
    angry:  { rx: 21, ry: 22, pupil: 11, lid: 0.42 },
    sad:    { rx: 20, ry: 23, pupil: 10, lid: 0.3 },
    focus:  { rx: 19, ry: 18, pupil: 12, lid: 0.18 },
  };
  const g = geometry[shape] ?? geometry.normal;
  const ry = Math.max(1.5, g.ry * open);

  return (
    <g>
      {eyes.map((eye, index) => {
        const inward = index === 0 ? 2 : -2;
        return (
          <g key={eye.cx}>
            <ellipse cx={eye.cx} cy={eye.cy} rx={g.rx} ry={ry} fill="#fffdfa" stroke="#3b1f24" strokeWidth="3" />
            {open > 0.25 && (
              <>
                <circle
                  cx={eye.cx + inward + look.x}
                  cy={eye.cy + look.y}
                  r={g.pupil}
                  fill="#241417"
                />
                <circle
                  cx={eye.cx + inward + look.x + 3.5}
                  cy={eye.cy + look.y - 4}
                  r={3.2}
                  fill="#fff"
                  opacity="0.95"
                />
                {shape === 'focus' && (
                  <circle
                    cx={eye.cx + inward + look.x}
                    cy={eye.cy + look.y}
                    r={g.pupil + 4}
                    fill="none"
                    stroke={accent}
                    strokeWidth="1.5"
                    opacity="0.7"
                  />
                )}
              </>
            )}
            {/* Веко для злого/грустного взгляда */}
            {g.lid > 0 && (
              <path
                d={
                  shape === 'sad'
                    ? `M${eye.cx - g.rx - 1} ${eye.cy - ry * (1 - g.lid)} L${eye.cx + g.rx + 1} ${eye.cy - ry}
                       L${eye.cx + g.rx + 1} ${eye.cy - ry - 6} L${eye.cx - g.rx - 1} ${eye.cy - ry - 6} Z`
                    : `M${eye.cx - g.rx - 1} ${eye.cy - ry} L${eye.cx + g.rx + 1} ${eye.cy - ry * (1 - g.lid)}
                       L${eye.cx + g.rx + 1} ${eye.cy - ry - 8} L${eye.cx - g.rx - 1} ${eye.cy - ry - 8} Z`
                }
                fill={SKIN}
                transform={index === 1 ? `scale(-1 1) translate(${-2 * eye.cx} 0)` : undefined}
              />
            )}
          </g>
        );
      })}
    </g>
  );
};

const Mouth: React.FC<{ shape: MouthShape; openness: number; phase: number }> = ({ shape, openness, phase }) => {
  if (shape === 'smile') {
    return <path d="M74 128 Q100 146 126 128" stroke="#3b1f24" strokeWidth="5" fill="none" strokeLinecap="round" />;
  }
  if (shape === 'frown') {
    return <path d="M76 142 Q100 124 124 142" stroke="#3b1f24" strokeWidth="5" fill="none" strokeLinecap="round" />;
  }
  if (shape === 'small') {
    return (
      <g>
        <ellipse cx="100" cy="134" rx="11" ry="8" fill="url(#mouthGrad)" />
        <ellipse cx="100" cy="137" rx="7" ry="3" fill={TONGUE} />
      </g>
    );
  }
  if (shape === 'wave') {
    return (
      <path
        d="M74 134 Q84 126 94 134 Q104 142 114 134 Q124 126 130 134"
        stroke="#3b1f24"
        strokeWidth="5"
        fill="none"
        strokeLinecap="round"
      />
    );
  }
  if (shape === 'o') {
    const r = 14 + Math.sin(phase * 4) * 2;
    return (
      <g>
        <ellipse cx="100" cy="136" rx={r} ry={r * 1.15} fill="url(#mouthGrad)" />
        <ellipse cx="100" cy={136 + r * 0.5} rx={r * 0.6} ry={r * 0.3} fill={TONGUE} />
      </g>
    );
  }
  if (shape === 'grin') {
    return (
      <g>
        <path d="M66 122 Q100 168 134 122 Q100 134 66 122 Z" fill="url(#mouthGrad)" />
        <path d="M74 132 Q100 152 126 132 Q100 142 74 132 Z" fill={TONGUE} opacity="0.9" />
      </g>
    );
  }

  // open / talk — фирменный «отвисший» рот Патрика
  const stretch = shape === 'talk' ? 1 + openness * 0.55 : 1;
  const height = 30 * stretch;
  return (
    <g>
      <ellipse cx="100" cy={128 + height / 3} rx={26} ry={height} fill="url(#mouthGrad)" />
      <ellipse cx="100" cy={128 + height * 0.85} rx={16} ry={height * 0.35} fill={TONGUE} opacity="0.95" />
      <ellipse cx="90" cy={128 - height * 0.4} rx={7} ry={4} fill="#fff" opacity="0.12" />
    </g>
  );
};

const Drool: React.FC<{ phase: number }> = ({ phase }) => {
  const length = 12 + (Math.sin(phase * 1.1) + 1) * 7;
  return (
    <g>
      <path
        d={`M120 142 q4 ${length / 2} 0 ${length}`}
        stroke="url(#droolGrad)"
        strokeWidth="5"
        strokeLinecap="round"
        fill="none"
      />
      <circle cx="120" cy={142 + length} r="4.5" fill="url(#droolGrad)" />
    </g>
  );
};

export default PatrickPet;
