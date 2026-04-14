import React from 'react';
import { motion } from 'framer-motion';

export const F1GridBackground: React.FC = () => {
  return (
    <div className="fixed inset-0 pointer-events-none z-0 bg-[#020202] overflow-hidden">
      <div 
        className="absolute inset-0 opacity-20"
        style={{
          backgroundImage: `
            linear-gradient(to right, rgba(225, 6, 0, 0.1) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(225, 6, 0, 0.1) 1px, transparent 1px)
          `,
          backgroundSize: '40px 40px'
        }}
      />
      <div className="absolute inset-0 bg-gradient-to-b from-black via-transparent to-black" />
      <motion.div 
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage: 'repeating-linear-gradient(0deg, transparent, transparent 2px, #E10600 2px, #E10600 4px)',
          backgroundSize: '100% 4px'
        }}
        animate={{
          backgroundPosition: ['0px 0px', '0px -40px']
        }}
        transition={{
          duration: 2,
          ease: "linear",
          repeat: Infinity
        }}
      />
    </div>
  );
};
