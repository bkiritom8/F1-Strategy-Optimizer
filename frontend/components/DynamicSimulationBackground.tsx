/**
 * @file DynamicSimulationBackground.tsx
 * @description Immersive F1 racing simulation background.
 * Features: SVG oval circuit, multiple animated F1 cars with headlights,
 * exhaust trails, sector flashes, atmospheric glow layers, and a carbon
 * fibre texture — all theme-aware (dark / light mode).
 */

import React, { useMemo } from 'react';
import { motion } from 'framer-motion';

// ─────────────────────────────────────────────────────────────────────────────
// CONSTANTS
// ─────────────────────────────────────────────────────────────────────────────

/** A Silverstone-inspired looping SVG path that fills the viewport. */
const TRACK_PATH =
  'M 50,200 C 50,120 120,80 200,60 C 300,35 450,30 600,50 C 750,68 850,80 920,120 C 980,155 1000,200 990,270 C 975,330 920,360 860,380 C 780,405 680,400 580,390 C 460,378 360,365 270,390 C 190,412 130,440 90,400 C 55,365 50,290 50,200 Z';

/** Team colour / identity for each animated car. */
const CARS: {
  color: string;
  glow: string;
  delay: number;
  duration: number;
  lane: number; // slight path offset
}[] = [
  { color: '#E10600', glow: '#FF4433', delay: 0,    duration: 9,  lane: 0 },
  { color: '#00D2BE', glow: '#00FFEE', delay: 3.5,  duration: 10, lane: 1 },
  { color: '#0067FF', glow: '#4499FF', delay: 6,    duration: 11, lane: -1 },
  { color: '#FFF200', glow: '#FFEE00', delay: 2,    duration: 12, lane: 2 },
  { color: '#FF8700', glow: '#FFAA33', delay: 8,    duration: 9.5,lane: -2 },
];

// Pre-computed random tire-mark positions so renders are stable.
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
 * Renders a tiny top-down F1 car SVG centred at (0,0).
 * The car always faces right; framer-motion rotates via offsetRotate.
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
 * One F1 car animated along the master TRACK_PATH via CSS offset-path.
 * An exhausts blobs trail behind it for motion blur effect.
 */
const AnimatedCar: React.FC<{
  color: string;
  glow: string;
  delay: number;
  duration: number;
  lane: number;
}> = ({ color, glow, delay, duration, lane }) => {
  const glowId = `car-glow-${color.replace('#', '')}`;

  return (
    <svg
      className="absolute inset-0 w-full h-full pointer-events-none"
      viewBox="0 0 1050 480"
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

      {/* Exhaust heat haze / trail dots */}
      {[-8, -16, -26].map((offset, i) => (
        <motion.circle
          key={i}
          r={3 - i * 0.7}
          fill={color}
          opacity={0.25 - i * 0.06}
          style={{
            filter: 'blur(2px)',
            offsetPath: `path('${TRACK_PATH}')`,
            offsetRotate: 'auto',
          } as React.CSSProperties}
          initial={{ offsetDistance: `${offset < 0 ? 100 + offset / 2 : 0}%` }}
          animate={{ offsetDistance: `${offset < 0 ? 100 + offset / 2 + 100 : 100}%` }}
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
          offsetPath: `path('${TRACK_PATH}')`,
          offsetRotate: 'auto',
        } as React.CSSProperties}
        initial={{ offsetDistance: `${(lane * 5)}%` }}
        animate={{ offsetDistance: `${(lane * 5) + 100}%` }}
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

export const DynamicSimulationBackground: React.FC = () => {
  const sectors = useMemo(() =>
    [
      { d: 'M 50,200 C 50,120 120,80 200,60 C 300,35 450,30 600,50',      color: '#E10600' },
      { d: 'M 600,50 C 750,68 850,80 920,120 C 980,155 1000,200 990,270', color: '#FFF200' },
      { d: 'M 990,270 C 975,330 920,360 860,380 C 780,405 680,400 580,390 C 460,378 360,365 270,390 C 190,412 130,440 90,400 C 55,365 50,290 50,200', color: '#00D2BE' },
    ], []);

  return (
    <div className="fixed inset-0 z-0 overflow-hidden transition-colors duration-500 bg-gray-100 dark:bg-[#080808]">

      {/* ── Layer 1: Atmospheric glows ───────────────────────────── */}
      <div className="absolute top-[-15%] left-[-10%] w-[45%] h-[50%] bg-red-500/5 dark:bg-red-900/25 blur-[140px] rounded-full pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[45%] h-[50%] bg-blue-500/5 dark:bg-blue-900/20 blur-[140px] rounded-full pointer-events-none" />
      <div className="absolute top-[30%] left-[40%] w-[30%] h-[30%] bg-yellow-500/3 dark:bg-yellow-900/10 blur-[100px] rounded-full pointer-events-none" />

      {/* ── Layer 2: Circuit SVG (background track ghost + sectors) ─ */}
      <svg
        className="absolute inset-0 w-full h-full pointer-events-none"
        viewBox="0 0 1050 480"
        preserveAspectRatio="xMidYMid slice"
      >
        <defs>
          <filter id="track-glow">
            <feGaussianBlur stdDeviation="2.5" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        {/* Tire marks */}
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

        {/* Track ghost outline */}
        <path
          d={TRACK_PATH}
          fill="none"
          className="stroke-gray-300/40 dark:stroke-white/5"
          strokeWidth="38"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {/* Track tarmac */}
        <path
          d={TRACK_PATH}
          fill="none"
          className="stroke-gray-200/60 dark:stroke-white/[0.03]"
          strokeWidth="34"
          strokeLinecap="round"
        />
        {/* Track kerb lines (dashed) */}
        <path
          d={TRACK_PATH}
          fill="none"
          stroke="#E10600"
          strokeWidth="36"
          strokeOpacity="0.06"
          strokeLinecap="round"
          strokeDasharray="12 24"
        />

        {/* Sector colouring */}
        {sectors.map((s, i) => (
          <motion.path
            key={i}
            d={s.d}
            fill="none"
            stroke={s.color}
            strokeWidth="2"
            strokeLinecap="round"
            strokeOpacity={0}
            animate={{ strokeOpacity: [0, 0.6, 0] }}
            transition={{ duration: 6, repeat: Infinity, delay: i * 2, ease: 'easeInOut' }}
            filter="url(#track-glow)"
          />
        ))}

        {/* DRS Detection Line markers */}
        {[
          { x1: 600, y1: 42, x2: 600, y2: 62 },
          { x1: 990, y1: 262, x2: 1010, y2: 282 },
          { x1: 50, y1: 192, x2: 70, y2: 212 },
        ].map((line, i) => (
          <line key={i} {...line} stroke="#00D2BE" strokeWidth="2" strokeOpacity="0.5" />
        ))}

        {/* Start / Finish line */}
        <rect x="46" y="192" width="8" height="28" fill="white" opacity="0.15" rx="1" />
        <text x="58" y="212" fill="#888" fontSize="8" fontFamily="monospace" opacity="0.5">S/F</text>
      </svg>

      {/* ── Layer 3: Animated F1 Cars ────────────────────────────── */}
      {CARS.map((car, i) => (
        <AnimatedCar key={i} {...car} />
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

      {/* ── Layer 5: Fine carbon fibre texture ──────────────────── */}
      <div className="absolute inset-0 opacity-[0.04] dark:opacity-[0.06] bg-[url('https://www.transparenttextures.com/patterns/carbon-fibre.png')] pointer-events-none" />

      {/* ── Layer 6: Vignette ────────────────────────────────────── */}
      <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(ellipse_at_center,transparent_50%,rgba(0,0,0,0.25)_100%)] dark:bg-[radial-gradient(ellipse_at_center,transparent_40%,rgba(0,0,0,0.6)_100%)]" />
    </div>
  );
};
