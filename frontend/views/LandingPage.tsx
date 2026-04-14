/**
 * @file views/LandingPage.tsx
 * @description Modern, premium landing page for DivergeX.
 *
 * Features:
 * - Smooth scroll-driven animations with Framer Motion.
 * - Informative sections highlighting platform capabilities.
 * - High-quality animated SVGs.
 * - Glassmorphism UI for authentication (admin-only via showAuth prop).
 */

import {
  Database,
  X,
  Lock,
  ShieldCheck,
  ChevronDown,
  Zap,
  CheckCircle2,
  Layers,
  Activity
} from 'lucide-react';
import React, { useState, useRef } from 'react';
import { motion, useScroll, useSpring, useTransform, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { useAppStore } from '../store/useAppStore';
import Footer from '../components/Footer';


// ─── Types ───────────────────────────────────────────────────────────────────

/**
 * @interface LandingPageProps
 * @description Props for the highly animated LandingPage component.
 */
interface Props {}

// ─── SVG Components ──────────────────────────────────────────────────────────

const StrategyGraphSVG = () => (
  <svg width="100%" height="200" viewBox="0 0 400 200" className="opacity-80">
    <motion.path
      d="M0 180 Q100 170 200 100 T400 20"
      stroke="#E10600"
      strokeWidth="3"
      fill="none"
      initial={{ pathLength: 0 }}
      whileInView={{ pathLength: 1 }}
      transition={{ duration: 2 }}
    />
    <motion.path
      d="M0 180 Q100 175 200 140 T400 100"
      stroke="#00D2BE"
      strokeWidth="3"
      fill="none"
      initial={{ pathLength: 0 }}
      whileInView={{ pathLength: 1 }}
      transition={{ duration: 2, delay: 0.5 }}
    />
    <circle cx="200" cy="100" r="4" fill="#E10600" />
    <text x="210" y="105" fill="white" fontSize="10" className="font-mono">PIT WINDOW OPEN</text>
  </svg>
);

const TelemetryBackground = () => (
  <div className="absolute inset-0 overflow-hidden pointer-events-none z-0 bg-black">
    <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgba(225,6,0,0.08)_0%,transparent_70%)]" />
    <svg className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[120%] h-[120%] opacity-20" viewBox="0 0 1000 1000">
      <circle cx="500" cy="500" r="450" stroke="#E10600" strokeWidth="0.5" fill="none" strokeDasharray="100 200" />
      <path d="M500 50 L950 500 L500 950 L50 500 Z" stroke="#E10600" strokeWidth="0.2" fill="none" strokeDasharray="50 150" />
    </svg>
    <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,black_90%)]" />
  </div>
);

// ─── Main Component ───────────────────────────────────────────────────────────

const LandingPage: React.FC<Props> = () => {
  const navigate = useNavigate();
  const { isAdmin, setAdminModalOpen, logout } = useAppStore();
  const containerRef = useRef<HTMLDivElement>(null);
  
  const { scrollYProgress } = useScroll({ target: containerRef });
  const smoothProgress = useSpring(scrollYProgress, { stiffness: 100, damping: 30, restDelta: 0.001 });

  // Parallax transforms for background elements
  
  // Hero Section transitions
  const heroScale = useTransform(smoothProgress, [0, 0.2], [1, 0.8]);
  const heroOpacity = useTransform(smoothProgress, [0, 0.15], [1, 0]);

  const [showDataSpecs, setShowDataSpecs] = useState(false);

  return (
    <div ref={containerRef} className="bg-black text-white min-h-screen font-sans selection:bg-red-600/30 overflow-x-hidden">

      {/* ── Floating Header ── */}
      <nav className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 lg:px-12 h-20 backdrop-blur-md border-b border-white/5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl overflow-hidden flex items-center justify-center">
            <img src="/divergex-logo.svg" alt="DivergeX" className="w-10 h-10 object-contain" />
          </div>
          <span className="font-display font-black text-xl italic tracking-tighter uppercase">Diverge<span className="text-red-600">X</span></span>
        </div>
        
        <div className="flex items-center gap-4 md:gap-10">
          {!isAdmin ? (
             <button
              onClick={() => setAdminModalOpen(true)}
              className="hidden sm:flex items-center gap-2 text-white/40 hover:text-red-500 transition-all group"
            >
              <Lock className="w-4 h-4" />
              <span className="text-[10px] font-black uppercase tracking-widest">Admin Control</span>
            </button>
          ) : (
            <button
              onClick={() => logout()}
              className="hidden sm:flex items-center gap-2 text-red-500/60 hover:text-red-500 transition-all group"
            >
              <span className="text-[10px] font-black uppercase tracking-widest">Exit Admin</span>
            </button>
          )}

        </div>
      </nav>

      {/* ── Progress Bar ── */}
      <motion.div
        className="fixed top-0 left-0 right-0 h-1 bg-gradient-to-r from-red-600 to-red-400 z-[60] origin-left"
        style={{ scaleX: scrollYProgress }}
      />

      {/* ── SECTION 1: HERO ── */}
      <section className="relative min-h-screen flex flex-col items-center justify-center pt-20 px-6 overflow-hidden">
        <div className="absolute inset-0 z-0 pointer-events-none overflow-hidden">
          <TelemetryBackground />
        </div>

        {/* Translucent logo watermark */}
        <motion.div
          className="absolute inset-0 flex items-center justify-center pointer-events-none"
          initial={{ opacity: 0, scale: 0.85 }}
          animate={{ opacity: 0.04, scale: 1 }}
          transition={{ duration: 4, ease: "easeOut" }}
        >
          <img src="/divergex-logo.svg" alt="" aria-hidden="true" className="w-[60vw] max-w-[700px] object-contain" />
        </motion.div>

        <motion.div
          style={{ scale: heroScale, opacity: heroOpacity }}
          className="relative z-10 text-center max-w-3xl"
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full glass-morphism mb-6 border-red-900/30"
          >
            <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
            <span className="text-[10px] font-black uppercase tracking-[0.2em] text-red-500 mt-0.5">Season Engine Active</span>
          </motion.div>

          <h1 className="font-display font-black text-5xl md:text-7xl italic tracking-tighter uppercase leading-[0.9] mb-6 hero-gradient-text">
            Outthink.<br />Outpace.<br />Outsmart.<br />Optimize.
          </h1>

          <p className="text-base md:text-lg text-white/50 max-w-2xl mx-auto leading-relaxed mb-8">
            Unleash the full potential of elite motorsport intelligence. Experience hyper-accurate telemetry, advanced predictive modeling, and AI-driven race strategy engineered for the absolute leading edge.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <button
              onClick={() => navigate('/race')}
              className="w-full sm:w-auto px-10 py-4 rounded-2xl bg-red-600 text-white font-bold hover:bg-red-700 transition-all shadow-xl shadow-red-900/30 active:scale-95"
            >
              Launch Command Center
            </button>
            <button
              onClick={() => setShowDataSpecs(true)}
              className="w-full sm:w-auto px-10 py-4 rounded-2xl glass-morphism text-white/80 font-bold hover:bg-white/5 transition-all"
            >
              View Data Specs
            </button>
          </div>
        </motion.div>

        {/* Car parallax removed in favor of lightweight branding and layout */}

        <motion.div
          animate={{ opacity: [0.4, 1, 0.4] }}
          transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
          className="absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-4 cursor-pointer group"
          onClick={() => window.scrollTo({ top: window.innerHeight, behavior: 'smooth' })}
        >
          <div className="relative w-32 h-16 flex items-center justify-center overflow-hidden">
            {/* Arched lines from screenshot */}
            {[...Array(3)].map((_, i) => (
              <motion.div
                key={i}
                className="absolute border-t-2 border-red-600/40 rounded-[100%]"
                style={{
                  width: `${60 + i * 30}%`,
                  height: `${100 + i * 40}%`,
                  top: '100%',
                }}
                animate={{ 
                  opacity: [0.2, 0.5, 0.2],
                  scale: [1, 1.05, 1],
                  y: [-2, 2, -2]
                }}
                transition={{ 
                  duration: 2, 
                  repeat: Infinity, 
                  delay: i * 0.3,
                  ease: "easeInOut"
                }}
              />
            ))}
            <div className="absolute top-0 w-full h-full bg-gradient-to-t from-black to-transparent z-10" />
            <motion.div 
              className="z-20 flex flex-col items-center"
              whileHover={{ y: 5 }}
            >
              <span className="text-[10px] uppercase font-black tracking-[0.3em] text-white/60 group-hover:text-red-500 transition-colors">Explore Intelligence</span>
              <ChevronDown className="w-5 h-5 text-white/20 group-hover:text-red-500 transition-colors mt-1" />
            </motion.div>
          </div>
        </motion.div>
      </section>

      {/* ── SECTION 2: STRATEGY ENGINE ── */}
      <section className="relative py-32 px-6 lg:px-24">
        <div className="max-w-7xl mx-auto grid lg:grid-cols-2 gap-16 items-center">
          <motion.div
            whileInView={{ opacity: 1, x: 0 }}
            initial={{ opacity: 0, x: -50 }}
            viewport={{ once: true }}
            className="space-y-8"
          >
            <div className="p-3 w-fit rounded-2xl bg-red-600/10 border border-red-500/20">
              <Zap className="w-8 h-8 text-red-500" />
            </div>
            <h2 className="font-display font-black text-4xl md:text-6xl italic uppercase tracking-tight leading-none text-white">
              Adaptive Race<br /><span className="text-red-600">Strategy</span>
            </h2>
            <p className="text-white/60 text-lg leading-relaxed">
              Dominate the pit wall with our proprietary Monte Carlo engine. Simulating 50,000+ race outcomes every second to solve for tire degradation, weather shifts, and high-stakes safety car windows in real-time.
            </p>
            <ul className="space-y-4">
              {[
                "Instant undercut/overcut analysis",
                "Dynamic tire compounding modeling",
                "Multi-driver gap synchronization"
              ].map((item, i) => (
                <li key={i} className="flex items-center gap-3 text-white/80 font-medium">
                  <CheckCircle2 className="w-5 h-5 text-accent-green" /> {item}
                </li>
              ))}
            </ul>
          </motion.div>

          <motion.div
            whileInView={{ opacity: 1, scale: 1 }}
            initial={{ opacity: 0, scale: 0.9 }}
            viewport={{ once: true }}
            className="glass-morphism p-8 rounded-[32px] border-white/5 relative overflow-hidden group"
          >
            <div className="absolute inset-0 bg-gradient-to-tr from-red-600/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
            <h3 className="text-xs font-black uppercase tracking-widest text-white/40 mb-12">LIVE SIMULATION STREAM</h3>
            <StrategyGraphSVG />
            <div className="mt-8 flex justify-between items-end">
              <div>
                <p className="text-xs text-white/30 uppercase font-bold">Accuracy</p>
                <p className="text-2xl font-display font-bold text-white">99.8%</p>
              </div>
              <div className="h-10 w-24 bg-red-600/20 rounded-lg flex items-center justify-center">
                <div className="flex gap-1">
                  {[1,2,3,4,5].map(i => <div key={i} className="w-1.5 h-4 bg-red-500 rounded-full animate-pulse" style={{ animationDelay: `${i*0.2}s` }} />)}
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* ── SECTION 2.5: REAL-TIME TELEMETRY ── */}
      <section className="relative py-32 px-6 lg:px-24 overflow-hidden">
        <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-white/10 to-transparent" />
        <div className="max-w-7xl mx-auto space-y-20">
          <div className="text-center space-y-4">
            <motion.h2
              whileInView={{ opacity: 1, y: 0 }}
              initial={{ opacity: 0, y: 30 }}
              viewport={{ once: true }}
              className="font-display font-black text-4xl md:text-6xl italic uppercase tracking-tighter"
            >
              Real-Time <span className="text-red-600">Telemetry</span> Streaming
            </motion.h2>
            <p className="text-white/40 max-w-2xl mx-auto">Absolute data transparency. We process over 200 mission-critical sensor nodes per millisecond: from thermal kinetics in the power unit to the micro-aero surfaces of the front wing.</p>
          </div>

          <div className="grid lg:grid-cols-3 gap-8">
            {[
              { label: 'Thermal Internal Combustion', value: '11,400 RPM', status: 'Optimal', color: 'red' },
              { label: 'Kinetic Recovery Matrix', value: '4.2 MJ', status: 'Charging', color: 'blue' },
              { label: 'Compound Thermal State', value: '98°C', status: 'Nominal', color: 'red' }
            ].map((stat, i) => (
              <motion.div
                key={i}
                whileInView={{ opacity: 1, x: 0 }}
                initial={{ opacity: 0, x: i % 2 === 0 ? -30 : 30 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1, duration: 0.8 }}
                className="glass-morphism-dark p-6 rounded-3xl border border-white/5 flex flex-col gap-4 relative overflow-hidden group"
              >
                <motion.div
                  className="absolute inset-0 bg-gradient-to-br from-red-600/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity"
                />
                <div className={`absolute top-4 right-4 w-1.5 h-1.5 rounded-full ${stat.color === 'red' ? 'bg-red-500' : 'bg-blue-500'} animate-pulse`} />
                <span className="text-[10px] font-black uppercase tracking-widest text-white/30">{stat.label}</span>
                <div className="flex items-end justify-between relative z-10">
                  <span className="text-3xl font-display font-bold italic">{stat.value}</span>
                  <span className="text-[10px] font-mono text-emerald-400">{stat.status}</span>
                </div>
                <div className="h-1 w-full bg-white/5 rounded-full overflow-hidden relative z-10">
                  <motion.div
                    initial={{ width: 0 }}
                    whileInView={{ width: '85%' }}
                    transition={{ duration: 2, delay: 0.5, ease: "circOut" }}
                    className={`h-full ${stat.color === 'red' ? 'bg-red-600' : 'bg-blue-600'}`}
                  />
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── SECTION 3: INFRASTRUCTURE ── */}
      <section className="relative py-32 px-6 lg:px-24 bg-gradient-to-b from-transparent to-[#050505]">
        <div className="max-w-7xl mx-auto flex flex-col items-center text-center space-y-12">
          <motion.div
             whileInView={{ opacity: 1, y: 0 }}
             initial={{ opacity: 0, y: 50 }}
             viewport={{ once: true }}
             className="space-y-6 max-w-3xl"
          >
            <div className="mx-auto p-3 w-fit rounded-2xl bg-accent-green/10 border border-accent-green/20">
              <Database className="w-8 h-8 text-accent-green" />
            </div>
            <h2 className="font-display font-black text-4xl md:text-6xl italic uppercase tracking-tight text-white">
              Global <span className="text-accent-green">Infrastructure</span>
            </h2>
            <p className="text-white/60 text-lg">
              High-performance computing on Google Cloud. Sub-millisecond latency for race-critical telemetry processing.
            </p>
          </motion.div>

          <div className="grid md:grid-cols-3 gap-6 w-full mt-12">
            {[
              { icon: Layers, title: "Distributed Compute", desc: "Powered by GCP high-performance clusters for zero-lag calculations." },
              { icon: ShieldCheck, title: "Secure Enclaves", desc: "Industry-leading encryption for team-sensitive strategic intellectual property." },
              { icon: Activity, title: "Live Vitals", desc: "Monitor car health and driver performance metrics with microsecond precision." }
            ].map((feature, i) => (
              <motion.div
                key={i}
                whileInView={{ opacity: 1, y: 0 }}
                initial={{ opacity: 0, y: 50 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.15, duration: 0.6 }}
                whileHover={{ y: -10, scale: 1.02 }}
                className="glass-morphism p-8 rounded-3xl text-left border border-white/5 bg-gradient-to-b from-white/[0.03] to-transparent"
              >
                <div className="w-12 h-12 rounded-2xl bg-red-600/10 flex items-center justify-center mb-6 border border-red-500/10">
                  <feature.icon className="w-6 h-6 text-red-500" />
                </div>
                <h4 className="text-lg font-bold text-white mb-3 tracking-tight">{feature.title}</h4>
                <p className="text-sm text-white/40 leading-relaxed font-medium">{feature.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Section 3.5 removed to optimize landing page weight. */}

      {/* ── SECTION 4: FINAL CTA ── */}
      <section className="relative min-h-[60vh] flex items-center justify-center py-20 px-6">
        <div className="absolute inset-0 pointer-events-none opacity-30 overflow-hidden">
          <div className="absolute bottom-0 left-0 w-full h-[50vh] bg-gradient-to-t from-red-600/20 to-transparent" />
        </div>

        <motion.div
           whileInView={{ opacity: 1, scale: 1 }}
           initial={{ opacity: 0, scale: 0.95 }}
           viewport={{ once: true }}
           className="relative z-10 text-center space-y-10"
        >
          <h2 className="font-display font-black text-5xl md:text-8xl italic uppercase tracking-tighter leading-none">
            READY TO <span className="text-red-600">DOMINATE?</span>
          </h2>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-6">
            <button
               onClick={() => navigate('/race')}
               className="w-full sm:w-auto px-12 py-5 rounded-full bg-red-600 text-white font-black uppercase tracking-widest text-sm hover:bg-red-700 transition-all shadow-2xl shadow-red-900/40"
            >
              Enter Command Center
            </button>
          </div>
        </motion.div>
      </section>

      <Footer onAdminClick={() => setAdminModalOpen(true)} />

      {/* ── DATA SPECS MODAL ── */}
      <AnimatePresence>
        {showDataSpecs && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-6">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setShowDataSpecs(false)}
              className="absolute inset-0 bg-black/80 backdrop-blur-xl"
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.9, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.9, y: 20 }}
              className="relative w-full max-w-2xl glass-morphism p-8 md:p-12 rounded-[40px] border-white/10 shadow-2xl"
            >
              <button
                onClick={() => setShowDataSpecs(false)}
                className="absolute top-6 right-6 p-2 rounded-full hover:bg-white/10 transition-colors"
              >
                <X className="w-6 h-6" />
              </button>
              
              <div className="space-y-8">
                <div>
                  <h3 className="text-2xl font-display font-bold italic uppercase tracking-tight text-red-500 mb-4">Technical Specifications</h3>
                  <div className="h-1 w-20 bg-red-600 rounded-full" />
                </div>
                
                <div className="grid md:grid-cols-2 gap-8">
                  <div className="space-y-4">
                    <h4 className="text-xs font-black uppercase tracking-widest text-white/30">Backend Architecture</h4>
                    <p className="text-sm text-white/70 leading-relaxed font-medium">
                      Powered by <strong className="text-white">Python/FastAPI</strong> and <strong className="text-white">Redis</strong> for sub-millisecond data distribution. Predictive modeling via <strong className="text-white">Monte Carlo simulations</strong>.
                    </p>
                  </div>
                  <div className="space-y-4">
                    <h4 className="text-xs font-black uppercase tracking-widest text-white/30">Frontend Core</h4>
                    <p className="text-sm text-white/70 leading-relaxed font-medium">
                      Built with <strong className="text-white">React 18</strong>, <strong className="text-white">TypeScript</strong>, and <strong className="text-white">Framer Motion</strong> for a high-fidelity, interactive telemetry experience.
                    </p>
                  </div>
                  <div className="space-y-4">
                    <h4 className="text-xs font-black uppercase tracking-widest text-white/30">Data Integration</h4>
                    <p className="text-sm text-white/70 leading-relaxed font-medium">
                      Dynamic ingestion of <strong className="text-white">Formula 1 Historical Data</strong> (2024-2026 Season Mapping) and real-time tire degradation sensors.
                    </p>
                  </div>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* No local Admin Modal anymore - now handled by App.tsx */}
    </div>
  );
};

export default LandingPage;
