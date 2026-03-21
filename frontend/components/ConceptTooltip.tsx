import React, { useState } from 'react';
import { F1_GLOSSARY } from '../constants';

interface ConceptTooltipProps {
  term: string;
  children: React.ReactNode;
}

/**
 * ConceptTooltip Component
 * Wraps technical terms and displays a beginner-friendly definition on hover.
 * Features a subtle "intelligence" pulse and premium glassmorphism.
 */
const ConceptTooltip: React.FC<ConceptTooltipProps> = ({ term, children }) => {
  const [isVisible, setIsVisible] = useState(false);
  const definition = F1_GLOSSARY[term];

  if (!definition) return <>{children}</>;

  return (
    <div 
      className="relative inline-block group cursor-help"
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
    >
      <span className="border-b border-dashed border-accent-blue/40 hover:border-accent-blue transition-colors">
        {children}
      </span>
      
      {isVisible && (
        <div className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-3 rounded-lg 
                        bg-[#1A1A1A]/95 backdrop-blur-md border border-white/10 shadow-2xl
                        animate-in fade-in zoom-in duration-200 origin-bottom">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-2 h-2 rounded-full bg-accent-blue animate-pulse" />
            <span className="text-[10px] font-bold uppercase tracking-wider text-accent-blue">Concept Insight</span>
          </div>
          <p className="text-xs text-white/90 leading-relaxed font-medium">
            {definition}
          </p>
          {/* Tooltip Arrow */}
          <div className="absolute top-full left-1/2 -translate-x-1/2 border-8 border-transparent border-t-[#1A1A1A]/95" />
        </div>
      )}
    </div>
  );
};

export default ConceptTooltip;
