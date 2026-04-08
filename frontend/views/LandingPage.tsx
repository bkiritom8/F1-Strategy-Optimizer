/**
 * @file views/LandingPage.tsx
 * @description Modern, premium landing page for Apex Intelligence.
 * 
 * Features:
 * - Smooth scroll-driven animations with Framer Motion.
 * - Informative sections highlighting platform capabilities.
 * - High-quality animated SVGs.
 * - Glassmorphism UI for authentication.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { motion, useScroll, useTransform, AnimatePresence, useSpring } from 'framer-motion';
import { 
  ChevronDown, 
  Cpu, 
  Zap, 
  Activity, 
  ShieldCheck, 
  Layers, 
  Mail, 
  Lock, 
  User, 
  CheckCircle2,
  AlertCircle,
  Eye,
  EyeOff,
  ArrowRight,
  Database,
  BarChart3,
  X
} from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import { requestOtp, resendVerification } from '../services/authService';
import Footer from '../components/Footer';

// ─── Types ───────────────────────────────────────────────────────────────────

type ModalTab   = 'password' | 'otp' | 'signup';
type ModalState = 'idle' | 'otp_sent' | 'verify_prompt' | 'success';

interface Props {
  onLoginSuccess: () => void;
  onAdminLogin:   () => void;
}

// ─── SVG Components ──────────────────────────────────────────────────────────

const F1CarSVG = () => (
  <motion.svg
    width="100%"
    height="100%"
    viewBox="0 0 800 300"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className="f1-red-glow"
    initial={{ opacity: 0, scale: 0.9 }}
    animate={{ opacity: 1, scale: 1 }}
    transition={{ duration: 1.5, ease: "easeOut" }}
  >
    <motion.path
      d="M50 250 L150 250 L170 230 L300 230 L350 200 L600 200 L650 230 L750 230 L750 250 M150 250 Q160 210 200 210 Q240 210 250 250 M600 250 Q610 210 650 210 Q690 210 700 250"
      stroke="#E10600"
      strokeWidth="2"
      strokeLinecap="round"
      initial={{ pathLength: 0 }}
      animate={{ pathLength: 1 }}
      transition={{ duration: 3, ease: "easeInOut" }}
    />
    <motion.path
      d="M360 190 Q480 180 600 190"
      stroke="#00D2BE"
      strokeWidth="1"
      strokeDasharray="5 5"
      initial={{ pathLength: 0 }}
      animate={{ pathLength: 1 }}
      transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
    />
  </motion.svg>
);

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

// ─── Helper: Password Strength ───────────────────────────────────────────

function passwordStrength(pwd: string): number {
  let score = 0;
  if (pwd.length >= 8)  score++;
  if (pwd.length >= 12) score++;
  if (/[A-Z]/.test(pwd)) score++;
  if (/[0-9]/.test(pwd)) score++;
  if (/[^a-zA-Z0-9]/.test(pwd)) score++;
  return Math.min(4, score);
}

const STRENGTH_LABEL = ['', 'Weak', 'Fair', 'Good', 'Strong'];
const STRENGTH_COLOR = ['', '#ff4d4d', '#ffa64d', '#f1c40f', '#00e676'];

// ─── Main Component ───────────────────────────────────────────────────────────

const LandingPage: React.FC<Props> = ({ onLoginSuccess, onAdminLogin }) => {
  const { loginAsync, loginWithOtpAsync, authLoading, isReturningUser, setHasVisited, isAdmin } = useAppStore();
  const containerRef = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: containerRef });
  const smoothProgress = useSpring(scrollYProgress, { stiffness: 100, damping: 30, restDelta: 0.001 });
  
  // Parallax transforms for background elements
  const glowY = useTransform(smoothProgress, [0, 1], [-100, 200]);
  const carParallax = useTransform(smoothProgress, [0, 0.4], [0, 150]);
  const sectionOpacity = useTransform(smoothProgress, [0, 0.1], [1, 0]);

  // Auth States
  const [tab, setTab] = useState<ModalTab>('password');
  const [modalState, setModalState] = useState<ModalState>('idle');
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [showPw, setShowPw] = useState(false);
  // isReturning is now derived directly from store in the component body
  // or we can just use isReturningUser from the hook destructuring.

  // Form States
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [otpCode, setOtpCode] = useState('');
  const [fullName, setFullName] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [gdpr, setGdpr] = useState(false);
  const [resendEmail, setResendEmail] = useState('');
  const [showDataSpecs, setShowDataSpecs] = useState(false);

  const strength = passwordStrength(password);
  const [otpCountdown, setOtpCountdown] = useState(0);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const startCountdown = useCallback(() => {
    setOtpCountdown(600);
    if (countdownRef.current) clearInterval(countdownRef.current);
    countdownRef.current = setInterval(() => {
      setOtpCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(countdownRef.current!);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }, []);

  useEffect(() => () => { if (countdownRef.current) clearInterval(countdownRef.current); }, []);

  const resetFormState = () => {
    setError(''); setSuccessMsg(''); setModalState('idle');
    setOtpCode(''); setOtpCountdown(0);
  };
  const switchTab = (t: ModalTab) => { setTab(t); resetFormState(); };

  // ── Auth Handlers ─────────────────────────────────────────────────────────

  const handlePasswordLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(''); setSubmitting(true);
    const result = await loginAsync(username, password);
    setSubmitting(false);

    if (result.needsVerification) {
      setError('Email not verified. Please check your inbox.');
      setModalState('verify_prompt');
      setResendEmail(username);
      return;
    }
    if (result.ok) {
      if (!isReturningUser) setHasVisited();
      if (useAppStore.getState().isAdmin) onAdminLogin();
      else onLoginSuccess();
    }
  };

  const handleRequestOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) { setError('Enter your email.'); return; }
    setError(''); setSubmitting(true);
    await requestOtp(email);
    setSubmitting(false);
    setModalState('otp_sent');
    setSuccessMsg('A security code has been transmitted.');
    startCountdown();
  };

  const handleOtpLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (otpCode.length !== 6) { setError('Invalid code length.'); return; }
    setError(''); setSubmitting(true);
    const result = await loginWithOtpAsync(email, otpCode);
    setSubmitting(false);
    if (result.ok) {
      if (!isReturningUser) setHasVisited();
      if (useAppStore.getState().isAdmin) onAdminLogin();
      else onLoginSuccess();
    }
  };

  const handleSignUp = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (password !== confirmPassword) { setError('Passwords mismatch.'); return; }
    if (!gdpr) { setError('Privacy policy agreement required.'); return; }
    if (strength < 3) { setError('Password too weak.'); return; }

    setSubmitting(true);
    const { signUp } = await import('../services/authService');
    const result = await signUp(username, email, fullName, password);
    setSubmitting(false);

    if (!result.ok) { setError(result.errorMsg ?? 'Registration failed.'); return; }
    setResendEmail(email);
    setModalState('verify_prompt');
  };

  const scrollToAuth = () => {
    const el = document.getElementById('auth-section');
    el?.scrollIntoView({ behavior: 'smooth' });
  };

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div ref={containerRef} className="bg-black text-white min-h-screen font-sans selection:bg-red-600/30 overflow-x-hidden">
      
      {/* ── Floating Header ── */}
      <nav className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 lg:px-12 h-20 backdrop-blur-md border-b border-white/5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-red-600 flex items-center justify-center shadow-lg shadow-red-900/20">
            <Cpu className="w-6 h-6 text-white" />
          </div>
          <span className="font-display font-black text-xl italic tracking-tighter uppercase">Apex Intelligence</span>
        </div>
        <button 
          onClick={scrollToAuth}
          className="hidden md:flex items-center gap-2 px-6 py-2 rounded-full border border-white/10 hover:bg-white/5 transition-all text-sm font-bold uppercase tracking-widest text-white/70 hover:text-white"
        >
          Access Portal <ArrowRight className="w-4 h-4" />
        </button>
      </nav>

      {/* ── Progress Bar ── */}
      <motion.div 
        className="fixed top-0 left-0 right-0 h-1 bg-gradient-to-r from-red-600 to-red-400 z-[60] origin-left"
        style={{ scaleX: scrollYProgress }}
      />

      {/* ── SECTION 1: HERO ── */}
      <section className="relative min-h-screen flex flex-col items-center justify-center pt-20 px-6 overflow-hidden">
        <motion.div 
          style={{ y: glowY }}
          className="absolute inset-0 z-0 pointer-events-none opacity-20"
        >
          <div className="absolute top-1/4 left-1/4 w-[600px] h-[600px] bg-red-600/10 rounded-full blur-[120px]" />
          <div className="absolute top-3/4 right-1/4 w-[400px] h-[400px] bg-blue-600/5 rounded-full blur-[100px]" />
        </motion.div>

        <motion.div 
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
          className="relative z-10 text-center max-w-4xl"
        >
          <motion.div 
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full glass-morphism mb-8 border-red-900/30"
          >
            <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
            <span className="text-[10px] font-black uppercase tracking-[0.2em] text-red-500 mt-0.5">2026 Season Engine Active</span>
          </motion.div>
          
          <h1 className="font-display font-black text-6xl md:text-8xl italic tracking-tighter uppercase leading-[0.9] mb-8 hero-gradient-text">
            Outthink.<br />Outpace.<br />Optimize.
          </h1>
          
          <p className="text-lg md:text-xl text-white/50 max-w-2xl mx-auto leading-relaxed mb-12">
            The next generation of Formula 1 strategy. Real-time telemetry, predictive AI simulations, and adaptive modeling for the hybrid era.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <button 
              onClick={scrollToAuth}
              className="w-full sm:w-auto px-10 py-4 rounded-2xl bg-red-600 text-white font-bold hover:bg-red-700 transition-all shadow-xl shadow-red-900/30 active:scale-95"
            >
              Sign In to Command Center
            </button>
            <button 
              onClick={() => setShowDataSpecs(true)}
              className="w-full sm:w-auto px-10 py-4 rounded-2xl glass-morphism text-white/80 font-bold hover:bg-white/5 transition-all"
            >
              View Data Specs
            </button>
          </div>
        </motion.div>

        <motion.div 
          style={{ y: carParallax }}
          className="mt-20 w-full max-w-4xl opacity-50 relative"
        >
          <div className="absolute inset-0 bg-red-600/5 blur-3xl rounded-full" />
          <F1CarSVG />
        </motion.div>

        <motion.div 
          animate={{ y: [0, 10, 0] }}
          transition={{ duration: 2, repeat: Infinity }}
          className="absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 text-white/30"
        >
          <span className="text-[10px] uppercase font-bold tracking-widest">Explore Intelligence</span>
          <ChevronDown className="w-5 h-5" />
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
              Our proprietary Monte Carlo simulator runs 50,000+ race scenarios per second, accounting for tire degradation, rain probability, and safety car windows.
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

      {/* ── SECTION 2.5: REAL-TIME TELEMETRY (NEW) ── */}
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
            <p className="text-white/40 max-w-2xl mx-auto">Instantaneous processing of 200+ sensor data points from the power unit to the aero-surfaces.</p>
          </div>

          <div className="grid lg:grid-cols-3 gap-8">
            {[
              { label: 'Power Unit', value: '11,400 RPM', status: 'Optimal', color: 'red' },
              { label: 'ERS Deployment', value: '4.2 MJ', status: 'Charging', color: 'blue' },
              { label: 'Tire Carcass', value: '98°C', status: 'Nominal', color: 'red' }
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

      {/* ── SECTION 4: AUTH ── */}
      <section id="auth-section" className="relative min-h-screen flex items-center justify-center py-20 px-6">
        <div className="absolute inset-0 pointer-events-none opacity-30 overflow-hidden">
          <div className="absolute bottom-0 left-0 w-full h-[50vh] bg-gradient-to-t from-red-600/20 to-transparent" />
        </div>

        <motion.div 
          whileInView={{ opacity: 1, y: 0 }}
          initial={{ opacity: 0, y: 100 }}
          viewport={{ once: true }}
          className="w-full max-w-xl glass-morphism-dark p-8 md:p-12 rounded-[2.5rem] shadow-2xl relative z-20"
        >
          <div className="text-center mb-10">
            <h2 className="text-2xl font-display font-black italic tracking-tighter uppercase mb-2">
              {isReturningUser ? 'Welcome Back, Strategist' : 'Login for the 1st time'}
            </h2>
            <p className="text-white/40 text-sm">
              {isReturningUser 
                ? 'Your session intelligence is ready for re-initialization.' 
                : 'Initialize your connection for the 1st time to authorize your terminal.'}
            </p>
          </div>

          <div className="flex p-1 bg-white/5 rounded-2xl mb-8 border border-white/5">
            {(['password', 'otp', 'signup'] as ModalTab[]).map(t => (
              <button
                key={t}
                onClick={() => switchTab(t)}
                className={`flex-1 py-3 text-xs font-black uppercase tracking-widest rounded-xl transition-all ${
                  tab === t ? 'bg-red-600 text-white shadow-lg' : 'text-white/30 hover:text-white/50'
                }`}
              >
                {t === 'password' ? 'Sign In' : t === 'otp' ? 'OTP' : 'Register'}
              </button>
            ))}
          </div>

          <div className="min-h-[300px]">
            <AnimatePresence mode="wait">
              {tab === 'password' && (
                <motion.form 
                  key="password"
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  onSubmit={handlePasswordLogin}
                  className="space-y-6"
                >
                  <div className="space-y-4">
                    <div className="relative">
                      <User className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30" />
                      <input 
                        type="text" placeholder="Username / Email"
                        className="w-full pl-12 pr-4 py-4 rounded-2xl bg-white/5 border border-white/10 focus:border-red-600/50 outline-none transition-all text-sm"
                        value={username} onChange={e => setUsername(e.target.value)}
                      />
                    </div>
                    <div className="relative">
                      <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30" />
                      <input 
                        type={showPw ? "text" : "password"} placeholder="Secure Password"
                        className="w-full pl-12 pr-12 py-4 rounded-2xl bg-white/5 border border-white/10 focus:border-red-600/50 outline-none transition-all text-sm"
                        value={password} onChange={e => setPassword(e.target.value)}
                      />
                      <button 
                        type="button" onClick={() => setShowPw(!showPw)}
                        className="absolute right-4 top-1/2 -translate-y-1/2 text-white/30 hover:text-white transition-all"
                      >
                        {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>

                  {error && <div className="flex gap-2 p-3 rounded-xl bg-red-600/10 border border-red-600/20 text-red-500 text-xs font-bold leading-relaxed">
                    <AlertCircle className="w-4 h-4 shrink-0" /> {error}
                  </div>}

                  <button 
                    disabled={submitting || authLoading}
                    className="w-full py-4 rounded-2xl bg-red-600 text-white font-bold text-sm uppercase tracking-widest hover:bg-red-700 transition-all shadow-lg shadow-red-900/40"
                  >
                    {submitting ? "Establishing Connection..." : "Initialize Session"}
                  </button>
                </motion.form>
              )}

              {tab === 'otp' && (
                <motion.div 
                  key="otp"
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                >
                  {modalState !== 'otp_sent' ? (
                    <form onSubmit={handleRequestOtp} className="space-y-6">
                      <div className="relative">
                        <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30" />
                        <input 
                          type="email" placeholder="Verification Email"
                          className="w-full pl-12 pr-4 py-4 rounded-2xl bg-white/5 border border-white/10 focus:border-red-600/50 outline-none transition-all text-sm"
                          value={email} onChange={e => setEmail(e.target.value)}
                        />
                      </div>
                      <button className="w-full py-4 rounded-2xl border border-red-600/50 text-red-500 font-bold text-sm uppercase tracking-widest hover:bg-red-600/5 transition-all">
                        Transmit Magic Code
                      </button>
                    </form>
                  ) : (
                    <form onSubmit={handleOtpLogin} className="space-y-6">
                      <input 
                        type="text" maxLength={6} placeholder="000000"
                        className="w-full py-6 rounded-2xl bg-white/5 border border-red-600/30 text-center text-4xl font-bold tracking-[0.5em] text-red-500 outline-none"
                        value={otpCode} onChange={e => setOtpCode(e.target.value.replace(/\D/g, ''))}
                      />
                      <p className="text-center text-[10px] uppercase font-bold text-white/40 tracking-widest">
                        Expiring in {Math.floor(otpCountdown / 60)}:{String(otpCountdown % 60).padStart(2, '0')}
                      </p>
                      <button className="w-full py-4 rounded-2xl bg-red-600 text-white font-bold text-sm uppercase tracking-widest">
                        Authorize Terminal
                      </button>
                    </form>
                  )}
                </motion.div>
              )}

              {tab === 'signup' && (
                <motion.form 
                  key="signup"
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  onSubmit={handleSignUp}
                  className="space-y-4"
                >
                  <div className="grid grid-cols-2 gap-3">
                    <input 
                      type="text" placeholder="Username"
                      className="w-full px-4 py-4 rounded-2xl bg-white/5 border border-white/10 outline-none text-sm"
                      value={username} onChange={e => setUsername(e.target.value)}
                    />
                    <input 
                      type="text" placeholder="Full Name"
                      className="w-full px-4 py-4 rounded-2xl bg-white/5 border border-white/10 outline-none text-sm"
                      value={fullName} onChange={e => setFullName(e.target.value)}
                    />
                  </div>
                  <input 
                    type="email" placeholder="Strategic Email Address"
                    className="w-full px-4 py-4 rounded-2xl bg-white/5 border border-white/10 outline-none text-sm"
                    value={email} onChange={e => setEmail(e.target.value)}
                  />
                  <div className="grid grid-cols-2 gap-3">
                    <input 
                      type="password" placeholder="Password"
                      className="w-full px-4 py-4 rounded-2xl bg-white/5 border border-white/10 outline-none text-sm"
                      value={password} onChange={e => setPassword(e.target.value)}
                    />
                    <input 
                      type="password" placeholder="Confirm"
                      className="w-full px-4 py-4 rounded-2xl bg-white/5 border border-white/10 outline-none text-sm"
                      value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)}
                    />
                  </div>
                  
                  <label className="flex gap-3 text-[10px] text-white/40 items-start cursor-pointer select-none px-2 py-2">
                    <input 
                      type="checkbox" className="mt-0.5 accent-red-600"
                      checked={gdpr} onChange={e => setGdpr(e.target.checked)}
                    />
                    <span>I agree to the <a href="/privacy-policy.html" target="_blank" className="text-red-500 hover:underline">Privacy Policy</a> and <a href="/terms.html" target="_blank" className="text-red-500 hover:underline">Terms of Service</a>.</span>
                  </label>

                  <button className="w-full py-4 rounded-2xl bg-red-600 text-white font-bold text-sm uppercase tracking-widest">
                    Create Identity
                  </button>
                </motion.form>
              )}
            </AnimatePresence>
          </div>
        </motion.div>
      </section>

      <Footer />
      {/* ── DATA SPECS MODAL ── */}
      <AnimatePresence>
        {showDataSpecs && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-black/80 backdrop-blur-xl"
            onClick={() => setShowDataSpecs(false)}
          >
            <motion.div 
              initial={{ scale: 0.9, y: 20 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.9, y: 20 }}
              onClick={e => e.stopPropagation()}
              className="w-full max-w-2xl glass-morphism-dark p-8 md:p-12 rounded-[2.5rem] border border-white/10 shadow-2xl relative"
            >
              <button 
                onClick={() => setShowDataSpecs(false)}
                className="absolute top-6 right-6 p-2 rounded-full hover:bg-white/5 transition-colors"
              >
                <X className="w-6 h-6 text-white/40" />
              </button>
              
              <div className="space-y-8">
                <div className="flex items-center gap-4">
                  <div className="p-3 rounded-2xl bg-red-600/10 border border-red-500/20">
                    <Database className="w-8 h-8 text-red-500" />
                  </div>
                  <div>
                    <h2 className="text-2xl font-display font-black italic tracking-tighter uppercase">Technical Architecture</h2>
                    <p className="text-white/40 text-xs font-mono uppercase tracking-widest mt-1">Apex Engine v4.2.0-Pro</p>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {[
                    { label: 'Compute Engine', value: 'Google Cloud Vertex AI', desc: 'Predictive modeling via 512-core TPU clusters.' },
                    { label: 'Data Frequency', value: '100Hz Refresh Rate', desc: 'Real-time telemetry ingestion from trackside nodes.' },
                    { label: 'Network Latency', value: '< 15ms Global Orbit', desc: 'Distributed edge points for race-critical reactivity.' },
                    { label: 'Security Protocols', value: 'AES-256 Multi-layer', desc: 'Bank-grade encryption for proprietary strategies.' }
                  ].map(spec => (
                    <div key={spec.label} className="p-4 rounded-2xl bg-white/5 border border-white/5">
                      <p className="text-[10px] font-black uppercase tracking-widest text-red-500 mb-1">{spec.label}</p>
                      <p className="text-sm font-bold text-white mb-2">{spec.value}</p>
                      <p className="text-[10px] text-white/40 leading-tight">{spec.desc}</p>
                    </div>
                  ))}
                </div>

                <div className="pt-6 border-t border-white/5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                       <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                       <span className="text-[10px] font-black uppercase tracking-[0.2em] text-emerald-500">All Systems Operational</span>
                    </div>
                    <button 
                      onClick={() => setShowDataSpecs(false)}
                      className="px-8 py-3 rounded-xl bg-white text-black font-bold text-xs uppercase tracking-widest hover:bg-white/90 transition-all"
                    >
                      Acknowledge
                    </button>
                  </div>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default LandingPage;
