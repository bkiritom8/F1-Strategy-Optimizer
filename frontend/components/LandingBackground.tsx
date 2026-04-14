/**
 * @file components/LandingBackground.tsx
 * @description A high-performance, cinematic background for the Apex Intelligence landing page.
 * Features scroll-driven parallax, SVG track sketching, and kinetic speed lines.
 */

import React, { useMemo } from 'react';
import { motion, useScroll, useTransform } from 'framer-motion';
import { TRACK_PATHS } from './tracks/trackPaths';

interface Props {
  circuitId?: string;
  intensity?: number;
}

export const LandingBackground: React.FC<Props> = ({ 
  circuitId = 'silverstone', 
  intensity = 1 
}) => {
  const { scrollYProgress } = useScroll();
  
  // Parallax effects
  const y1 = useTransform(scrollYProgress, [0, 1], [0, -200 * intensity]);
  const y2 = useTransform(scrollYProgress, [0, 1], [0, -100 * intensity]);
  const rotate = useTransform(scrollYProgress, [0, 1], [0, 5]);
  const opacity = useTransform(scrollYProgress, [0, 0.2], [0.6, 0.1]);

  const rawPath = useMemo(() => TRACK_PATHS[circuitId] || TRACK_PATHS['_fallback'], [circuitId]);

  return (
    <div className="fixed inset-0 z-0 overflow-hidden bg-[#000] pointer-events-none">
      {/* ── Atmospheric Glows ── */}
      <motion.div 
        style={{ y: y1 }}
        className="absolute -top-[10%] -left-[10%] w-[60%] h-[60%] bg-red-600/10 rounded-full blur-[120px] opacity-40"
      />
      <motion.div 
        style={{ y: y2 }}
        className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] bg-red-900/10 rounded-full blur-[100px] opacity-30"
      />

      {/* ── The Track ── */}
      <motion.div 
        style={{ rotate, opacity }}
        className="absolute inset-0 flex items-center justify-center p-20 scale-110 lg:scale-125 transition-transform duration-1000"
      >
        <svg
          viewBox="0 0 300 200"
          className="w-full h-full max-w-5xl opacity-20 lg:opacity-30"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            <filter id="glow">
              <feGaussianBlur stdDeviation="2" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
          </defs>
          
          {/* Main Track Path */}
          <motion.path
            d={rawPath}
            stroke="white"
            strokeWidth="0.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: 1 }}
            transition={{ duration: 4, ease: "easeInOut" }}
            filter="url(#glow)"
          />

          {/* Tracer Dots (Kinetic energy) */}
          {[0, 0.2, 0.4, 0.7].map((offset, i) => (
            <motion.circle
              key={i}
              r="1"
              fill="#e10600"
              initial={{ offsetDistance: "0%" }}
              animate={{ offsetDistance: "100%" }}
              transition={{
                duration: 10 + i * 2,
                repeat: Infinity,
                ease: "linear",
                delay: i * 2,
              }}
              style={{
                offsetPath: `path('${rawPath}')`,
                filter: 'drop-shadow(0 0 4px #e10600)',
              } as any}
            />
          ))}
        </svg>
      </motion.div>

      {/* ── Speed Lines ── */}
      <div className="absolute inset-0 overflow-hidden">
        {Array.from({ length: 12 }).map((_, i) => (
          <motion.div
            key={i}
            className="absolute h-[1px] bg-gradient-to-r from-transparent via-white/5 to-transparent"
            style={{
              top: `${Math.random() * 100}%`,
              left: '-20%',
              width: `${20 + Math.random() * 40}%`,
            }}
            animate={{
              x: ['0%', '200%'],
              opacity: [0, 0.5, 0],
            }}
            transition={{
              duration: 2 + Math.random() * 3,
              repeat: Infinity,
              delay: Math.random() * 5,
              ease: "linear",
            }}
          />
        ))}
      </div>

      {/* ── Scanning Line ── */}
      <div className="absolute inset-0 z-10 pointer-events-none overflow-hidden opacity-10">
        <div className="w-full h-[2px] bg-red-600 animate-scan blur-[2px]" />
      </div>

      {/* ── Vignette ── */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,rgba(0,0,0,0.8)_100%)]" />
    </div>
  );
};
