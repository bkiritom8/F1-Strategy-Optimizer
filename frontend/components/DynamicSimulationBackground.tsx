/**
 * @file DynamicSimulationBackground.tsx
 * @description Immersive F1 racing simulation background that dynamically
 * renders the actual SVG circuit layout of the selected track.
 *
 * Props:
 *  - circuitId: string — the circuit ID used to look up the real track path.
 *    Falls back to a generic oval if the circuit is not in trackPaths.ts.
 *
 * Architecture:
 *  - Layer 1: Atmospheric glow blobs (CSS blur divs).
 *  - Layer 2: The circuit outline scaled to fill the viewport (SVG).
 *  - Layer 3: Five animated F1 cars moving along the circuit via CSS
 *             offset-path / framer-motion.
 *  - Layer 4: Horizontal speed-streak lines for kinetic energy.
 *  - Layer 5: Carbon-fibre texture overlay.
 *  - Layer 6: Vignette darkening at edges.
 *
 * @remarks
 *  The track paths are defined in a small coordinate space (approx 300×200).
 *  They are scaled via an SVG <g transform="scale(…)"> to fill the 1050×480
 *  master viewBox — the same transform string is embeds into the CSS
 *  offset-path for the car animations, so the cars correctly follow the
 *  displayed circuit shape.
 */

import React, { useMemo } from 'react';
import { motion } from 'framer-motion';
import { getTrackPath } from './tracks/trackPaths';

// ─────────────────────────────────────────────────────────────────────────────
// CONSTANTS
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Master SVG viewport dimensions. All paths (after scaling) live in this space.
 * The car offset-path must reference the SCALED path, not the raw track data.
 */
const VW = 1050;
const VH = 480;

/**
 * The raw track paths from trackPaths.ts were drawn in an approx 300×200 box.
 * We translate and scale them so they fill most of the VW×VH viewport.
 */
const TRACK_NATURAL_W = 300;
const TRACK_NATURAL_H = 200;

/** Scale factor to fit the track into the viewport with padding. */
const SCALE_X = (VW * 1.0) / TRACK_NATURAL_W;
const SCALE_Y = (VH * 1.0) / TRACK_NATURAL_H;
const SCALE = Math.min(SCALE_X, SCALE_Y);

/** Translate so the scaled track is centred in the viewport. */
const TX = (VW - TRACK_NATURAL_W * SCALE) / 2;
const TY = (VH - TRACK_NATURAL_H * SCALE) / 2;

/** CSS transform applied to the SVG group AND embedded in the car offset-path. */
const SVG_TRANSFORM = `translate(${TX}, ${TY}) scale(${SCALE})`;

/** Team colour identities for the five animated cars. */
const CARS: {
  color: string;
  glow: string;
  delay: number;
  duration: number;
  startPct: number; // initial offsetDistance %
}[] = [
  { color: '#E10600', glow: '#FF4433', delay: 0,   duration: 9.5,  startPct: 0  },
  { color: '#00D2BE', glow: '#00FFEE', delay: 2,   duration: 10,   startPct: 20 },
  { color: '#0067FF', glow: '#4499FF', delay: 4,   duration: 10.5, startPct: 40 },
  { color: '#FFF200', glow: '#FFEE00', delay: 1.5, duration: 11,   startPct: 60 },
  { color: '#FF8700', glow: '#FFAA33', delay: 5.5, duration: 9.8,  startPct: 80 },
];

// Pre-computed stable tire-mark positions.
const TIRE_MARKS = Array.from({ length: 14 }, (_, i) => ({
  x: 80  + (i * 79)  % 900,
  y: 80  + (i * 53)  % 380,
  w: 30  + (i * 17)  % 60,
  r: (i * 37) % 180,
}));

// ─────────────────────────────────────────────────────────────────────────────
// SUB-COMPONENTS
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Tiny top-down F1 car SVG centred at (0,0).
 * framer-motion rotates the car to follow the offset-path automatically.
 */
const F1CarSvg: React.FC<{ color: string; glow: string }> = ({ color, glow }) => (
  <g filter={`url(#car-glow-${color.replace('#', '')})`}>
    {/* Rear wing */}
    <rect x="-13" y="-5" width="3" height="10" fill="#111" rx="0.8" />
    {/* Rear tyres */}
    <rect x="-10" y="-7" width="5" height="4" fill="#222" rx="1" />
    <rect x="-10" y="3"  width="5" height="4" fill="#222" rx="1" />
    {/* Sidepods / body */}
    <path d="M-8,-4 L8,-3 L9,0 L8,3 L-8,4 Z" fill={color} />
    {/* Cockpit canopy */}
    <ellipse cx="1" cy="0" rx="5" ry="2.5" fill="#1a1a2e" />
    {/* Driver helmet */}
    <circle cx="1" cy="0" r="2" fill="#FFE500" />
    {/* Front tyres */}
    <rect x="5"  y="-7" width="5" height="4" fill="#222" rx="1" />
    <rect x="5"  y="3"  width="5" height="4" fill="#222" rx="1" />
    {/* Nose cone */}
    <path d="M9,-2 L15,0 L9,2 Z" fill={color} />
    {/* Front wing */}
    <rect x="14" y="-5" width="2" height="10" fill="#111" rx="0.5" />
    {/* Headlights */}
    <circle cx="14" cy="-2" r="1.2" fill={glow} opacity="0.9" />
    <circle cx="14" cy="2"  r="1.2" fill={glow} opacity="0.9" />
    {/* Tail lights */}
    <rect x="-12" y="-1.5" width="2.5" height="3" fill="#FF0000" rx="0.5" opacity="0.9" />
  </g>
);

/**
 * One F1 car animated along the circuit path via CSS offset-path.
 * The path string is the raw track path PREFIXED with the transform applied
 * via a matrix() function so the browser places the car on the displayed route.
 *
 * @param trackPath - Raw (un-scaled) SVG path string from trackPaths.ts.
 * @param scaledOffsetPath - The path string to use for CSS offset-path,
 *   already baked with translate+scale so it matches screen coordinates.
 */
const AnimatedCar: React.FC<{
  color: string;
  glow: string;
  delay: number;
  duration: number;
  startPct: number;
  scaledOffsetPath: string;
}> = ({ color, glow, delay, duration, startPct, scaledOffsetPath }) => {
  const glowId = `car-glow-${color.replace('#', '')}`;

  return (
    <svg
      className="absolute inset-0 w-full h-full pointer-events-none"
      viewBox={`0 0 ${VW} ${VH}`}
      preserveAspectRatio="xMidYMid slice"
      style={{ overflow: 'visible' }}
    >
      <defs>
        <filter id={glowId} x="-80%" y="-80%" width="250%" height="250%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* Exhaust trail dots */}
      {[-6, -12, -20].map((pctOffset, i) => (
        <motion.circle
          key={i}
          r={3 - i * 0.7}
          fill={color}
          opacity={0.25 - i * 0.06}
          style={{
            filter: 'blur(2px)',
            offsetPath: `path('${scaledOffsetPath}')`,
            offsetRotate: 'auto',
          } as React.CSSProperties}
          initial={{ offsetDistance: `${(startPct + pctOffset + 100) % 100}%` }}
          animate={{ offsetDistance: `${(startPct + pctOffset + 200) % 100}%` }}
          transition={{
            duration,
            ease: 'linear',
            repeat: Infinity,
            delay,
          }}
        />
      ))}

      {/* Car body */}
      <motion.g
        style={{
          offsetPath: `path('${scaledOffsetPath}')`,
          offsetRotate: 'auto',
        } as React.CSSProperties}
        initial={{ offsetDistance: `${startPct}%` }}
        animate={{ offsetDistance: `${startPct + 100}%` }}
        transition={{
          duration,
          ease: 'linear',
          repeat: Infinity,
          delay,
        }}
      >
        <F1CarSvg color={color} glow={glow} />
      </motion.g>
    </svg>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// MAIN COMPONENT
// ─────────────────────────────────────────────────────────────────────────────

interface DynamicSimulationBackgroundProps {
  /** Circuit ID from useAppStore / TrackMaps registry. e.g. 'bahrain', 'monaco'. */
  circuitId?: string;
}

export const DynamicSimulationBackground: React.FC<DynamicSimulationBackgroundProps> = ({
  circuitId = 'bahrain',
}) => {
  /**
   * Raw (un-scaled) path string for the selected circuit.
   * Falls back to the generic oval if circuitId is unknown.
   */
  const rawPath = useMemo(() => getTrackPath(circuitId), [circuitId]);

  /**
   * Scaled path string for CSS offset-path.
   * We achieve scaling by encoding the transform directly into the path
   * co-ordinates via SVG's path transform — CSS offset-path does NOT
   * support SVG transform attributes, but we can wrap the path in an SVG
   * <g transform> for rendering and derive the equivalent coordinate-space path
   * for offset-path by applying the matrix manually.
   *
   * SIMPLIFICATION: We pass the raw path to `path()` inside the SVG <g>
   * that ALREADY has the transform applied (for rendering). For the CSS
   * offset-path we cannot reuse the same path, so we instead use a separate
   * transform approach:
   *
   *  We embed the full transform string into the path() using a matrix()
   *  CSS transform on the element, setting `transform-origin: 0 0`.
   *  This way the browser applies the scale+translate to the car's element.
   *
   * The cars therefore travel on `path('${rawPath}')` and are visually
   * scaled+translated by a CSS transform matrix on their <svg> container.
   */

  /**
   * Sector highlight arcs derived from the raw path.
   * We split the path into three visual segments by taking substrings of the
   * control points — a rough but visually effective approach for the sector
   * flash animation.
   */
  const sectors = useMemo(() => {
    // Very simple heuristic: split the path string into three equal-length
    // sub-paths for the three sector colours. A closed circuit's sector
    // points are already ordered, so this produces a visually reasonable result.
    const commands = rawPath.match(/[MLCQAZTS][^MLCQAZTS]*/g) ?? [];
    const third = Math.floor(commands.length / 3);
    return [
      { d: commands.slice(0, third + 1).join(' '),        color: '#E10600' },
      { d: commands.slice(third, third * 2 + 1).join(' '), color: '#FFF200' },
      { d: commands.slice(third * 2).join(' '),            color: '#00D2BE' },
    ];
  }, [rawPath]);

  return (
    <div className="fixed inset-0 z-0 overflow-hidden transition-colors duration-500 bg-gray-100 dark:bg-[#080808]">

      {/* ── Layer 1: Atmospheric glows ───────────────────────────── */}
      <div className="absolute top-[-15%] left-[-10%] w-[45%] h-[50%] bg-red-500/5 dark:bg-red-900/25 blur-[140px] rounded-full pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[45%] h-[50%] bg-blue-500/5 dark:bg-blue-900/20 blur-[140px] rounded-full pointer-events-none" />
      <div className="absolute top-[30%] left-[40%] w-[30%] h-[30%] bg-yellow-500/3 dark:bg-yellow-900/10 blur-[100px] rounded-full pointer-events-none" />

      {/* ── Layer 2: Circuit SVG (track ghost outline + sector flashes) ─ */}
      <svg
        className="absolute inset-0 w-full h-full pointer-events-none"
        viewBox={`0 0 ${VW} ${VH}`}
        preserveAspectRatio="xMidYMid slice"
      >
        <defs>
          <filter id="track-glow">
            <feGaussianBlur stdDeviation="2.5" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        {/* Tire marks (absolute coords — decorative, not circuit-relative) */}
        {TIRE_MARKS.map((m, i) => (
          <rect
            key={i}
            x={m.x} y={m.y}
            width={m.w} height={3}
            fill="currentColor"
            className="text-gray-400/20 dark:text-white/5"
            rx="1"
            transform={`rotate(${m.r} ${m.x + m.w / 2} ${m.y + 1.5})`}
          />
        ))}

        {/* All track paths live inside this scaled group */}
        <g transform={SVG_TRANSFORM}>
          {/* Track ghost outline */}
          <path
            d={rawPath}
            fill="none"
            className="stroke-gray-300/20 dark:stroke-white/5"
            strokeWidth="14"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {/* Track tarmac */}
          <path
            d={rawPath}
            fill="none"
            className="stroke-gray-200/30 dark:stroke-white/[0.02]"
            strokeWidth="11"
            strokeLinecap="round"
          />
          {/* Kerb dashes */}
          <path
            d={rawPath}
            fill="none"
            stroke="#E10600"
            strokeWidth="13"
            strokeOpacity="0.06"
            strokeLinecap="round"
            strokeDasharray="5 10"
          />

          {/* Sector colouring (inside the scaled group) */}
          {sectors.map((s, i) => (
            <motion.path
              key={`${circuitId}-sector-${i}`}
              d={s.d}
              fill="none"
              stroke={s.color}
              strokeWidth="1"
              strokeLinecap="round"
              strokeOpacity={0}
              animate={{ strokeOpacity: [0, 0.7, 0] }}
              transition={{ duration: 6, repeat: Infinity, delay: i * 2, ease: 'easeInOut' }}
              filter="url(#track-glow)"
            />
          ))}
        </g>
      </svg>

      {/* ── Layer 3: Animated F1 Cars ────────────────────────────── */}
      {/*
        The cars use CSS offset-path with the raw (un-scaled) path, but their
        <svg> container is visually scaled+positioned by a CSS transform that
        mirrors the SVG_TRANSFORM. This decouples the path coordinate system
        from the screen coordinate system.
      */}
      {CARS.map((car, i) => (
        <div
          key={i}
          className="absolute inset-0 pointer-events-none"
          style={{
            transformOrigin: '0 0',
            transform: `translate(${TX}px, ${TY}px) scale(${SCALE})`,
          }}
        >
          <svg
            className="absolute pointer-events-none"
            style={{
              // The raw path lives in TRACK_NATURAL_W × TRACK_NATURAL_H space.
              // We expand the SVG to cover the full scaled area.
              width: VW / SCALE,
              height: VH / SCALE,
              top: 0,
              left: 0,
              overflow: 'visible',
            }}
            viewBox={`0 0 ${VW / SCALE} ${VH / SCALE}`}
          >
            <defs>
              <filter id={`car-glow-${car.color.replace('#', '')}`} x="-80%" y="-80%" width="250%" height="250%">
                <feGaussianBlur stdDeviation="3" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            {/* Exhaust trail dots */}
            {[-6, -12, -20].map((pctOffset, j) => (
              <motion.circle
                key={j}
                r={3 - j * 0.7}
                fill={car.color}
                opacity={0.30 - j * 0.07}
                style={{
                  filter: 'blur(2px)',
                  offsetPath: `path('${rawPath}')`,
                  offsetRotate: 'auto',
                } as React.CSSProperties}
                initial={{ offsetDistance: `${(car.startPct + pctOffset + 100) % 100}%` }}
                animate={{ offsetDistance: `${(car.startPct + pctOffset + 200) % 100}%` }}
                transition={{ duration: car.duration, ease: 'linear', repeat: Infinity, delay: car.delay }}
              />
            ))}

            {/* Car body */}
            <motion.g
              style={{
                offsetPath: `path('${rawPath}')`,
                offsetRotate: 'auto',
              } as React.CSSProperties}
              initial={{ offsetDistance: `${car.startPct}%` }}
              animate={{ offsetDistance: `${car.startPct + 100}%` }}
              transition={{ duration: car.duration, ease: 'linear', repeat: Infinity, delay: car.delay }}
            >
              <F1CarSvg color={car.color} glow={car.glow} />
            </motion.g>
          </svg>
        </div>
      ))}

      {/* ── Layer 4: Speed lines (perspective streaks) ───────────── */}
      {[...Array(8)].map((_, i) => (
        <motion.div
          key={`streak-${i}`}
          className="absolute pointer-events-none"
          style={{
            top: `${12 + i * 10}%`,
            left: 0,
            width: `${60 + (i * 17) % 80}px`,
            height: '1.5px',
            background: `linear-gradient(to right, transparent, ${
              ['#E10600','#00D2BE','#0067FF','#FFF200','#FF8700'][i % 5]
            }44, transparent)`,
            filter: 'blur(0.5px)',
          }}
          initial={{ x: '-20vw' }}
          animate={{ x: '110vw' }}
          transition={{
            duration: 2.5 + (i * 0.4),
            repeat: Infinity,
            delay: i * 0.8,
            ease: 'linear',
          }}
        />
      ))}

      {/* ── Layer 5: Fine carbon fibre texture overlay ──────────────────── */}
      <div className="absolute inset-0 opacity-[0.04] dark:opacity-[0.06] bg-[url('https://www.transparenttextures.com/patterns/carbon-fibre.png')] pointer-events-none" />

      {/* ── Layer 6: Vignette ────────────────────────────────────── */}
      <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(ellipse_at_center,transparent_50%,rgba(0,0,0,0.25)_100%)] dark:bg-[radial-gradient(ellipse_at_center,transparent_40%,rgba(0,0,0,0.6)_100%)]" />
    </div>
  );
};
