import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Shield, X, Settings, Info, Check } from 'lucide-react';

/**
 * @file CookieConsent.tsx
 * @description Premium, GDPR-compliant in-memory cookie consent banner.
 */

interface ConsentState {
  necessary: boolean;
  analytics: boolean;
  marketing: boolean;
}

const CookieConsent: React.FC = () => {
  const [isVisible, setIsVisible] = useState(false);
  const [showPreferences, setShowPreferences] = useState(false);
  const [consent, setConsent] = useState<ConsentState>({
    necessary: true,
    analytics: false,
    marketing: false,
  });

  // Check if consent has already been given in this session (in-memory)
  useEffect(() => {
    const sessionConsent = (window as any)._apex_consent_given;
    if (!sessionConsent) {
      const timer = setTimeout(() => setIsVisible(true), 1500);
      return () => clearTimeout(timer);
    }
  }, []);

  const handleAcceptAll = () => {
    const allOn = { necessary: true, analytics: true, marketing: true };
    applyConsent(allOn);
  };

  const handleRejectNonEssential = () => {
    const onlyNecessary = { necessary: true, analytics: false, marketing: false };
    applyConsent(onlyNecessary);
  };

  const handleSavePreferences = () => {
    applyConsent(consent);
  };

  const applyConsent = (newState: ConsentState) => {
    setConsent(newState);
    (window as any)._apex_consent_state = newState;
    (window as any)._apex_consent_given = true;
    setIsVisible(false);
    
    // Fire analytics if allowed
    if (newState.analytics) {
      console.log('[Consent] Analytics enabled');
      // window.gtag?.('consent', 'update', { 'analytics_storage': 'granted' });
    }
    
    // Dispatch custom event for app-wide awareness
    window.dispatchEvent(new CustomEvent('apex:consent_updated', { detail: newState }));
  };

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          initial={{ y: 100, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 100, opacity: 0 }}
          className="fixed bottom-6 left-6 right-6 md:left-auto md:max-w-md z-[100]"
        >
          <div className="glass-morphism-dark p-6 rounded-3xl border border-white/10 shadow-2xl overflow-hidden relative">
            <div className="absolute top-0 left-0 w-1 h-full bg-red-600" />
            
            {!showPreferences ? (
              <div className="space-y-4">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-xl bg-red-600/10 border border-red-500/20">
                    <Shield className="w-5 h-5 text-red-500" />
                  </div>
                  <h3 className="font-bold text-lg uppercase tracking-tight italic">Privacy Protocols</h3>
                </div>
                
                <p className="text-sm text-white/60 leading-relaxed">
                  We use cookies to analyze telemetry and enhance your strategic interface. Some are mission-critical, while others help us optimize performance.
                </p>

                <div className="flex flex-col gap-2 pt-2">
                  <button
                    onClick={handleAcceptAll}
                    className="w-full py-3 rounded-xl bg-red-600 text-white font-bold text-xs uppercase tracking-widest hover:bg-red-700 transition-all shadow-lg shadow-red-900/20"
                  >
                    Accept All Protocols
                  </button>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      onClick={handleRejectNonEssential}
                      className="py-3 rounded-xl bg-white/5 border border-white/10 text-white/70 font-bold text-[10px] uppercase tracking-widest hover:bg-white/10 transition-all"
                    >
                      Strictly Necessary
                    </button>
                    <button
                      onClick={() => setShowPreferences(true)}
                      className="py-3 rounded-xl bg-white/5 border border-white/10 text-white/70 font-bold text-[10px] uppercase tracking-widest hover:bg-white/10 transition-all flex items-center justify-center gap-1.5"
                    >
                      <Settings className="w-3.5 h-3.5" /> Configure
                    </button>
                  </div>
                </div>
                
                <p className="text-[10px] text-white/30 text-center italic">
                  Read our <a href="/privacy-policy.html" target="_blank" className="text-red-500/80 hover:underline">Privacy Policy</a>
                </p>
              </div>
            ) : (
              <div className="space-y-5">
                <div className="flex items-center justify-between">
                  <h3 className="font-bold text-lg uppercase tracking-tight italic">Mission Config</h3>
                  <button onClick={() => setShowPreferences(false)} className="text-white/40 hover:text-white">
                    <X className="w-5 h-5" />
                  </button>
                </div>

                <div className="space-y-4">
                  <PreferenceToggle
                    title="Strictly Necessary"
                    desc="Required for authentication and core simulation engine."
                    enabled={true}
                    locked={true}
                  />
                  <PreferenceToggle
                    title="Analytics Telemetry"
                    desc="Helps us optimize the platform based on performance data."
                    enabled={consent.analytics}
                    onChange={(v) => setConsent(prev => ({ ...prev, analytics: v }))}
                  />
                  <PreferenceToggle
                    title="Marketing & Research"
                    desc="Allows us to share technical updates and relevant insights."
                    enabled={consent.marketing}
                    onChange={(v) => setConsent(prev => ({ ...prev, marketing: v }))}
                  />
                </div>

                <button
                  onClick={handleSavePreferences}
                  className="w-full py-3 mt-2 rounded-xl bg-white text-black font-bold text-xs uppercase tracking-widest hover:bg-white/90 transition-all"
                >
                  Apply Settings
                </button>
              </div>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

interface ToggleProps {
  title: string;
  desc: string;
  enabled: boolean;
  locked?: boolean;
  onChange?: (v: boolean) => void;
}

const PreferenceToggle: React.FC<ToggleProps> = ({ title, desc, enabled, locked, onChange }) => (
  <div className="flex items-start justify-between gap-4 group">
    <div className="space-y-0.5">
      <div className="flex items-center gap-2">
        <span className="text-xs font-bold text-white uppercase tracking-wide">{title}</span>
        {locked && <span className="text-[8px] font-black bg-white/10 px-1.5 py-0.5 rounded uppercase text-white/40 tracking-tighter">System Lock</span>}
      </div>
      <p className="text-[10px] text-white/40 leading-tight pr-4">{desc}</p>
    </div>
    <button
      disabled={locked}
      onClick={() => onChange?.(!enabled)}
      className={`relative w-8 h-5 rounded-full shrink-0 transition-colors ${enabled ? 'bg-red-600' : 'bg-white/10'} ${locked ? 'opacity-50 cursor-not-allowed' : ''}`}
    >
      <motion.div
        animate={{ x: enabled ? 14 : 2 }}
        className="absolute top-1 w-3 h-3 rounded-full bg-white shadow-sm flex items-center justify-center"
      >
        {locked && <Check className="w-2 h-2 text-red-600" />}
      </motion.div>
    </button>
  </div>
);

export default CookieConsent;
