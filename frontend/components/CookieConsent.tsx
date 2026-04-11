/**
 * @file components/CookieConsent.tsx
 * @description Premium GDPR-compliant cookie consent banner for Apex Intelligence.
 * 
 * Features:
 * - Glassmorphism UI (backdrop-blur).
 * - Animated entrance/exit with Framer Motion.
 * - LocalStorage persistence.
 * - Harmonious red/black/white theme.
 */

import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ShieldCheck, Info, X, ChevronRight } from 'lucide-react';

const CookieConsent: React.FC = () => {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    // Check if user has already consented
    const consent = localStorage.getItem('apex-cookie-consent');
    if (!consent) {
      // Delay entrance for better UX focus
      const timer = setTimeout(() => setIsVisible(true), 2000);
      return () => clearTimeout(timer);
    }
  }, []);

  const handleAccept = () => {
    localStorage.setItem('apex-cookie-consent', 'accepted');
    setIsVisible(false);
  };

  const handleDecline = () => {
    localStorage.setItem('apex-cookie-consent', 'declined');
    setIsVisible(false);
  };

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          initial={{ y: 100, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 100, opacity: 0 }}
          transition={{ type: 'spring', damping: 25, stiffness: 200 }}
          className="fixed bottom-6 left-6 right-6 md:left-auto md:right-8 md:max-w-md z-[100]"
        >
          <div className="glass-morphism-dark p-6 rounded-[2rem] border border-white/10 shadow-2xl relative overflow-hidden group">
            {/* Animated accent glow */}
            <div className="absolute -top-24 -right-24 w-48 h-48 bg-red-600/10 rounded-full blur-[80px] group-hover:bg-red-600/20 transition-all duration-700" />
            
            <div className="flex items-start gap-4 relative z-10">
              <div className="w-12 h-12 rounded-2xl bg-red-600/10 flex items-center justify-center shrink-0 border border-red-500/20">
                <ShieldCheck className="w-6 h-6 text-red-500" />
              </div>
              
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-black uppercase tracking-widest text-white">Strategy Intelligence Cookies</h3>
                  <button 
                    onClick={() => setIsVisible(false)}
                    className="text-white/20 hover:text-white transition-colors"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
                <p className="text-xs text-white/40 leading-relaxed font-medium">
                  Apex Intelligence uses essential and analytical cookies to optimize your strategic engine and race telemetry experience.
                </p>
              </div>
            </div>

            <div className="mt-8 flex items-center gap-3 relative z-10">
              <button
                onClick={handleAccept}
                className="flex-1 px-4 py-3 rounded-xl bg-red-600 text-white text-[10px] font-black uppercase tracking-widest hover:bg-red-700 transition-all shadow-lg shadow-red-900/20 flex items-center justify-center gap-2 group/btn"
              >
                Accept All <ChevronRight className="w-3 h-3 group-hover/btn:translate-x-1 transition-transform" />
              </button>
              <button
                onClick={handleDecline}
                className="px-6 py-3 rounded-xl border border-white/10 text-white/60 text-[10px] font-black uppercase tracking-widest hover:bg-white/5 transition-all"
              >
                Settings
              </button>
            </div>

            <div className="mt-4 flex justify-center">
              <a 
                href="/privacy-policy.html" 
                target="_blank" 
                className="flex items-center gap-1.5 text-[8px] uppercase font-bold text-white/20 hover:text-red-500 transition-colors tracking-[0.1em]"
              >
                <Info className="w-2.5 h-2.5" /> Core Privacy Directives
              </a>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default CookieConsent;
