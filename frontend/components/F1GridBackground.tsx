import React from 'react';
import { motion } from 'framer-motion';

export const F1GridBackground: React.FC = () => {
  const reduceMotion = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  return (
    <div className="fixed inset-0 pointer-events-none z-0 bg-[#020202] overflow-hidden">
      <div 
        className="absolute inset-0 opacity-10"
        style={{
          backgroundImage: `
            linear-gradient(to right, rgba(255, 255, 255, 0.06) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(255, 255, 255, 0.06) 1px, transparent 1px)
          `,
          backgroundSize: '40px 40px'
        }}
      />
      <div className="absolute inset-0 bg-gradient-to-b from-black via-transparent to-black" />
      <motion.div 
        className="absolute inset-0 opacity-[0.015]"
        style={{
          backgroundImage: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0, 210, 190, 0.35) 2px, rgba(0, 210, 190, 0.35) 4px)',
          backgroundSize: '100% 4px'
        }}
        animate={reduceMotion ? undefined : { backgroundPosition: ['0px 0px', '0px -40px'] }}
        transition={{
          duration: 6,
          ease: "linear",
          repeat: Infinity
        }}
      />
    </div>
  );
};
