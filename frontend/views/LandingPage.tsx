/**
 * @file views/LandingPage.tsx
 * @description Platform landing page with an integrated authentication modal.
 *
 * Auth modal has three tabs:
 *   1. Sign In (password)  → signIn() → JWT stored → redirect to /dashboard
 *   2. Sign In (OTP)       → requestOtp() then signInWithOtp() → same
 *   3. Sign Up             → signUp() → "check your email" state
 *
 * After a successful admin login the user is redirected to /admin.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useAppStore } from '../store/useAppStore';
import {
  requestOtp,
  resendVerification,
} from '../services/authService';

// ─── Types ───────────────────────────────────────────────────────────────────

type ModalTab   = 'password' | 'otp' | 'signup';
type ModalState = 'idle' | 'otp_sent' | 'verify_prompt' | 'success';

interface Props {
  onLoginSuccess: () => void;
  onAdminLogin:   () => void;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Robust password-strength rating (0-4). */
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

// ─── Component ───────────────────────────────────────────────────────────────

const LandingPage: React.FC<Props> = ({ onLoginSuccess, onAdminLogin }) => {
  const { loginAsync, loginWithOtpAsync, authLoading } = useAppStore();

  // Tab & workflow state
  const [tab,       setTab]       = useState<ModalTab>('password');
  const [modalState, setModalState] = useState<ModalState>('idle');

  // Shared
  const [error,       setError]       = useState('');
  const [successMsg,  setSuccessMsg]  = useState('');
  const [submitting,  setSubmitting]  = useState(false);

  // Password tab
  const [pwUsername, setPwUsername] = useState('');
  const [pwPassword, setPwPassword] = useState('');
  const [showPw,     setShowPw]     = useState(false);

  // OTP tab
  const [otpEmail,   setOtpEmail]   = useState('');
  const [otpCode,    setOtpCode]    = useState('');
  const [otpCountdown, setOtpCountdown] = useState(0);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Sign-up tab
  const [suUsername, setSuUsername] = useState('');
  const [suEmail,    setSuEmail]    = useState('');
  const [suName,     setSuName]     = useState('');
  const [suPassword, setSuPassword] = useState('');
  const [suConfirm,  setSuConfirm]  = useState('');
  const [suGdpr,     setSuGdpr]     = useState(false);
  const [suResendEmail, setSuResendEmail] = useState('');

  const strength     = passwordStrength(suPassword);
  const strengthLabel = STRENGTH_LABEL[strength];
  const strengthColor = STRENGTH_COLOR[strength];

  // ── Countdown timer for OTP expiry ─────────────────────────────────────────
  const startCountdown = useCallback(() => {
    setOtpCountdown(600); // 10 min
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

  // ── Reset state when tab changes ───────────────────────────────────────────
  const resetFormState = () => {
    setError(''); setSuccessMsg(''); setModalState('idle');
    setOtpCode(''); setOtpCountdown(0);
  };
  const switchTab = (t: ModalTab) => { setTab(t); resetFormState(); };

  // ── Password sign-in ───────────────────────────────────────────────────────
  const handlePasswordLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(''); setSubmitting(true);
    const result = await loginAsync(pwUsername, pwPassword);
    setSubmitting(false);

    if (result.needsVerification) {
      setError('Your email is not verified. Click "Resend verification email" below.');
      return;
    }
    if (!result.ok) {
      setError(result.errorMsg ?? 'Invalid credentials.');
      return;
    }
    if (useAppStore.getState().isAdmin) onAdminLogin();
    else onLoginSuccess();
  };

  // ── OTP: request code ──────────────────────────────────────────────────────
  const handleRequestOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!otpEmail) { setError('Enter your email address.'); return; }
    setError(''); setSubmitting(true);
    await requestOtp(otpEmail);   // always returns ok=true
    setSubmitting(false);
    setModalState('otp_sent');
    setSuccessMsg('A 6-digit code has been sent. Check your inbox (and spam folder).');
    startCountdown();
  };

  // ── OTP: verify code ───────────────────────────────────────────────────────
  const handleOtpLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (otpCode.length !== 6) { setError('Enter the 6-digit code.'); return; }
    setError(''); setSubmitting(true);
    const result = await loginWithOtpAsync(otpEmail, otpCode);
    setSubmitting(false);

    if (!result.ok) {
      setError(result.errorMsg ?? 'Invalid or expired code.');
      return;
    }
    
    if (useAppStore.getState().isAdmin) onAdminLogin();
    else onLoginSuccess();
  };

  // ── Sign up ────────────────────────────────────────────────────────────────
  const handleSignUp = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (suPassword !== suConfirm) { setError('Passwords do not match.'); return; }
    if (!suGdpr) { setError('Please accept the privacy policy to continue.'); return; }
    if (strength < 3) { setError('Choose a stronger password (aim for 8+ chars with mixed case, numbers & symbols).'); return; }

    setSubmitting(true);
    const { signUp } = await import('../services/authService');
    const result = await signUp(suUsername, suEmail, suName, suPassword);
    setSubmitting(false);

    if (!result.ok) { setError(result.errorMsg ?? 'Registration failed.'); return; }
    setSuResendEmail(suEmail);
    setModalState('verify_prompt');
  };

  const handleResendVerification = async () => {
    await resendVerification(suResendEmail);
    setSuccessMsg('Verification email resent! Check your inbox.');
  };

  // ─── JSX ──────────────────────────────────────────────────────────────────
  return (
    <div style={styles.page}>
      
      {/* ── Left Pane (Hero & Branding) ──────────────────────────────────── */}
      <div style={styles.leftPane}>
        <div style={styles.heroContent}>
          <div style={styles.badgeWrap}>
            <div style={styles.badgeGlow} />
            <div style={styles.badge}>2026 SEASON ENGINE</div>
          </div>
          <h1 style={styles.title}>
            APEX<br />
            <span style={styles.titleAccent}>INTELLIGENCE</span>
          </h1>
          <p style={styles.subtitle}>
            AI-powered Formula 1 race strategy, telemetry analysis,<br />
            and real-time pit-stop optimization. Built for the pit wall.
          </p>
        </div>
        
        {/* Dynamic Abstract Background Lines */}
        <div style={styles.heroBg} aria-hidden="true">
          {[...Array(15)].map((_, i) => (
            <div 
              key={i} 
              style={{ 
                ...styles.heroBgLine, 
                left: `${i * 7}%`, 
                animationDelay: `${i * 0.3}s`,
                height: `${80 + Math.random() * 40}%`,
                opacity: 0.1 + Math.random() * 0.3
              }} 
            />
          ))}
          <div style={styles.radialGlow} />
        </div>
      </div>

      {/* ── Right Pane (Auth Wizard) ─────────────────────────────────────── */}
      <div style={styles.rightPane}>
        <div style={styles.authCard}>
          <div style={styles.modalHeader}>
            <span style={styles.modalLogo}>
              <span style={{color: '#e10600'}}>🏎</span> Apex Intelligence
            </span>
          </div>

          <p style={styles.authSubtitle}>
            Authenticate to access live telemetry and modeling controls.
          </p>

          {/* Tabs */}
          <div style={styles.tabs} role="tablist">
            {(['password', 'otp', 'signup'] as ModalTab[]).map((t) => (
              <button
                key={t}
                role="tab"
                aria-selected={tab === t}
                id={`tab-${t}`}
                style={{ ...styles.tab, ...(tab === t ? styles.tabActive : {}) }}
                onClick={() => switchTab(t)}
              >
                {t === 'password' ? 'Sign In' : t === 'otp' ? 'Magic Code' : 'Register'}
              </button>
            ))}
          </div>

          <div style={styles.formContainer}>
            {/* ── Tab: Password ────────────────────────────────────────────── */}
            {tab === 'password' && (
              <form onSubmit={handlePasswordLogin} style={styles.form} noValidate>
                <div style={styles.inputGroup}>
                  <label style={styles.label}>Username or Email</label>
                  <input
                    id="pw-username"
                    style={styles.input}
                    type="text" autoComplete="username" required
                    placeholder="race_engineer"
                    value={pwUsername} onChange={(e) => setPwUsername(e.target.value)}
                  />
                </div>
                
                <div style={styles.inputGroup}>
                  <label style={styles.label}>Password</label>
                  <div style={styles.pwWrap}>
                    <input
                      id="pw-password"
                      style={styles.input}
                      type={showPw ? 'text' : 'password'}
                      autoComplete="current-password" required
                      placeholder="••••••••"
                      value={pwPassword} onChange={(e) => setPwPassword(e.target.value)}
                    />
                    <button type="button" style={styles.pwToggle} onClick={() => setShowPw(!showPw)}>
                      {showPw ? '🙈' : '👁'}
                    </button>
                  </div>
                </div>

                {error && <p style={styles.errorMsg}>{error}</p>}
                
                <button id="pw-submit" type="submit" style={styles.submitBtn} disabled={submitting || authLoading}>
                  <span style={styles.btnText}>{(submitting || authLoading) ? 'Authenticating…' : 'Secure Login'}</span>
                  <span style={styles.btnGlow} />
                </button>
                
                {error.includes('not verified') && (
                  <button type="button" style={styles.linkBtn}
                    onClick={() => resendVerification(pwUsername).then(() => setSuccessMsg('Verification email sent!'))}>
                    Resend verification email
                  </button>
                )}
                {successMsg && <p style={styles.successMsg}>{successMsg}</p>}
                
              </form>
            )}

            {/* ── Tab: OTP ────────────────────────────────────────────────── */}
            {tab === 'otp' && (
              <div style={styles.form}>
                {modalState !== 'otp_sent' ? (
                  <form onSubmit={handleRequestOtp} noValidate>
                    <p style={styles.hint}>Passwordless login. Enter your email to receive a secure one-time passcode.</p>
                    <div style={styles.inputGroup}>
                      <label style={styles.label}>Email Address</label>
                      <input
                        id="otp-email"
                        style={styles.input}
                        type="email" required autoComplete="email"
                        placeholder="you@team.com"
                        value={otpEmail} onChange={(e) => setOtpEmail(e.target.value)}
                      />
                    </div>
                    {error && <p style={styles.errorMsg}>{error}</p>}
                    <button id="otp-request-btn" type="submit" style={styles.submitBtn} disabled={submitting}>
                      <span style={styles.btnText}>{submitting ? 'Transmitting…' : 'Send Magic Code'}</span>
                      <span style={styles.btnGlow} />
                    </button>
                  </form>
                ) : (
                  <form onSubmit={handleOtpLogin} noValidate>
                    <p style={styles.successMsg}>{successMsg}</p>
                    <div style={styles.inputGroup}>
                      <label style={styles.label}>6-Digit Security Code</label>
                      <input
                        id="otp-code"
                        style={{ ...styles.input, ...styles.otpInput }}
                        type="text" inputMode="numeric" pattern="\d{6}" maxLength={6} required
                        placeholder="000000"
                        value={otpCode} onChange={(e) => setOtpCode(e.target.value.replace(/\D/, ''))}
                      />
                    </div>
                    {otpCountdown > 0 && (
                      <p style={styles.countdown}>
                        Code expires in {Math.floor(otpCountdown / 60)}:{String(otpCountdown % 60).padStart(2, '0')}
                      </p>
                    )}
                    {otpCountdown === 0 && <p style={styles.errorMsg}>Code expired. Request a new one.</p>}
                    {error && <p style={styles.errorMsg}>{error}</p>}
                    
                    <button id="otp-verify-btn" type="submit" style={styles.submitBtn} disabled={submitting || otpCountdown === 0}>
                      <span style={styles.btnText}>{submitting ? 'Verifying…' : 'Verify & Enter'}</span>
                      <span style={styles.btnGlow} />
                    </button>
                    <button type="button" style={{...styles.linkBtn, marginTop: '16px', display: 'block', textAlign: 'center', width: '100%'}}
                      onClick={() => { setModalState('idle'); setOtpCode(''); setError(''); }}>
                      ← Use a different email
                    </button>
                  </form>
                )}
              </div>
            )}

            {/* ── Tab: Sign Up ─────────────────────────────────────────────── */}
            {tab === 'signup' && (
              <div style={styles.form}>
                {modalState !== 'verify_prompt' ? (
                  <form onSubmit={handleSignUp} noValidate style={styles.compactForm}>
                    <div style={styles.row}>
                      <div style={styles.inputGroup}>
                        <label style={styles.label}>Username</label>
                        <input id="su-username" style={styles.input} type="text" autoComplete="username" required
                          placeholder="jdoe99" value={suUsername} onChange={(e) => setSuUsername(e.target.value)} />
                      </div>
                      <div style={styles.inputGroup}>
                        <label style={styles.label}>Full Name</label>
                        <input id="su-name" style={styles.input} type="text" autoComplete="name" required
                          placeholder="John Doe" value={suName} onChange={(e) => setSuName(e.target.value)} />
                      </div>
                    </div>
                    
                    <div style={styles.inputGroup}>
                      <label style={styles.label}>Email Address</label>
                      <input id="su-email" style={styles.input} type="email" autoComplete="email" required
                        placeholder="you@team.com" value={suEmail} onChange={(e) => setSuEmail(e.target.value)} />
                    </div>

                    <div style={styles.row}>
                      <div style={styles.inputGroup}>
                        <label style={styles.label}>Password</label>
                        <input id="su-password" style={styles.input} type="password" autoComplete="new-password" required
                          placeholder="min 8 chars" value={suPassword} onChange={(e) => setSuPassword(e.target.value)} />
                        {suPassword && (
                          <div style={styles.strengthBar}>
                            {[1,2,3,4].map((n) => (
                              <div key={n} style={{ ...styles.strengthSegment, background: n <= strength ? strengthColor : 'rgba(255,255,255,0.1)' }} />
                            ))}
                            <span style={{ color: strengthColor, fontSize: 10, marginLeft: 6, fontWeight: 600 }}>{strengthLabel}</span>
                          </div>
                        )}
                      </div>
                      <div style={styles.inputGroup}>
                        <label style={styles.label}>Confirm</label>
                        <input id="su-confirm" style={styles.input} type="password" autoComplete="new-password" required
                          placeholder="repeat" value={suConfirm} onChange={(e) => setSuConfirm(e.target.value)} />
                      </div>
                    </div>

                    <label style={styles.gdprLabel}>
                      <div style={styles.checkboxWrapper}>
                        <input id="su-gdpr" type="checkbox" style={styles.checkbox} checked={suGdpr} onChange={(e) => setSuGdpr(e.target.checked)} />
                      </div>
                      <span style={{lineHeight: 1.4}}>I agree to the <a href="#" style={styles.gdprLink}>Privacy Policy</a> and data processing terms for telemetry analysis.</span>
                    </label>

                    {error && <p style={styles.errorMsg}>{error}</p>}
                    <button id="su-submit" type="submit" style={styles.submitBtn} disabled={submitting}>
                      <span style={styles.btnText}>{submitting ? 'Initializing Node…' : 'Deploy Identity'}</span>
                      <span style={styles.btnGlow} />
                    </button>
                  </form>
                ) : (
                  <div style={styles.verifyPrompt}>
                    <div style={styles.verifyIcon}>
                      <div style={styles.verifyRing}/>
                      ✉️
                    </div>
                    <h3 style={styles.verifyTitle}>Awaiting Clearance</h3>
                    <p style={styles.verifyText}>
                      We transmitted a secure link to <strong style={{color: '#fff'}}>{suResendEmail}</strong>.
                      Validate your channel to access the grid.
                    </p>
                    {successMsg && <p style={styles.successMsg}>{successMsg}</p>}
                    <button type="button" style={{...styles.linkBtn, marginTop: 16}} onClick={handleResendVerification}>
                      Retransmit verification signal
                    </button>
                    <button type="button" style={{ ...styles.submitBtn, marginTop: 32 }} onClick={() => switchTab('password')}>
                      <span style={styles.btnText}>Return to Sign In</span>
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default LandingPage;

// ─── Styles ──────────────────────────────────────────────────────────────────

// Added custom css keyframes safely into a globally appended style block if needed, but going with standard inline layout.
// For advanced CSS effects that inline styles can't do (like ::before or complex animations), we use robust inline tricks or rely on index.css.

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight:       '100vh',
    display:         'flex',
    fontFamily:      "'Inter', 'Outfit', sans-serif",
    overflow:        'hidden',
    position:        'relative',
    background:      '#050505',
    color:           '#fff',
  },
  
  // Left side - Branding
  leftPane: {
    flex:            1.2,
    position:        'relative',
    display:         'flex',
    alignItems:      'center',
    justifyContent:  'flex-start',
    padding:         '8%',
    background:      'radial-gradient(ellipse at 30% 50%, #150606 0%, #050505 80%)',
    borderRight:     '1px solid rgba(225,6,0,0.1)',
  },
  heroContent: { 
    position: 'relative', 
    zIndex: 2,
    maxWidth: 600,
  },
  heroBg: { 
    position: 'absolute', 
    inset: 0, 
    overflow: 'hidden', 
    zIndex: 0 
  },
  heroBgLine: {
    position:        'absolute',
    top:             '-10%',
    width:           1,
    background:      'linear-gradient(to bottom, transparent, rgba(225,6,0,0.4), transparent)',
    animation:       'pulse 4s ease-in-out infinite alternate',
    boxShadow:       '0 0 15px rgba(225,6,0,0.5)',
  },
  radialGlow: {
    position: 'absolute',
    width: '600px',
    height: '600px',
    background: 'radial-gradient(circle, rgba(225,6,0,0.08) 0%, transparent 70%)',
    top: '30%',
    left: '10%',
    pointerEvents: 'none',
  },
  badgeWrap: {
    position: 'relative',
    display: 'inline-block',
    marginBottom: 32,
  },
  badgeGlow: {
    position: 'absolute',
    inset: 0,
    background: '#e10600',
    filter: 'blur(10px)',
    opacity: 0.3,
  },
  badge: {
    position:        'relative',
    display:         'inline-block',
    background:      'rgba(225,6,0,0.1)',
    border:          '1px solid rgba(225,6,0,0.3)',
    color:           '#ff4d4d',
    padding:         '6px 16px',
    borderRadius:    100,
    fontSize:        11,
    fontWeight:      700,
    letterSpacing:   '0.2em',
    backdropFilter:  'blur(4px)',
  },
  title: {
    fontSize:        'clamp(48px, 6vw, 96px)',
    fontWeight:      900,
    color:           '#ffffff',
    lineHeight:      0.95,
    margin:          '0 0 24px',
    letterSpacing:   '-0.03em',
  },
  titleAccent: { 
    color: '#e10600',
    textShadow: '0 0 40px rgba(225,6,0,0.3)',
  },
  subtitle: {
    color:    'rgba(255,255,255,0.5)',
    fontSize: 'clamp(16px, 1.2vw, 20px)',
    margin:   '0',
    lineHeight: 1.6,
    maxWidth: 500,
  },

  // Right side - Auth
  rightPane: {
    flex:            0.8,
    minWidth:        450,
    maxWidth:        650,
    position:        'relative',
    display:         'flex',
    alignItems:      'center',
    justifyContent:  'center',
    background:      'rgba(10, 10, 12, 0.8)',
    backdropFilter:  'blur(20px)',
    WebkitBackdropFilter: 'blur(20px)',
    padding:         '48px',
  },
  authCard: {
    width:        '100%',
    maxWidth:     420,
    display:      'flex',
    flexDirection: 'column',
  },
  modalHeader: {
    marginBottom:   12,
  },
  modalLogo: { 
    color: '#fff', 
    fontWeight: 800, 
    fontSize: 22,
    letterSpacing: '-0.5px'
  },
  authSubtitle: {
    color: 'rgba(255,255,255,0.4)',
    fontSize: 14,
    marginBottom: 40,
    lineHeight: 1.5,
  },
  tabs: {
    display:       'flex',
    gap:           4,
    marginBottom:  32,
    background:    'rgba(255,255,255,0.03)',
    borderRadius:  12,
    padding:       4,
    border:        '1px solid rgba(255,255,255,0.05)',
  },
  tab: {
    flex:         1,
    background:   'transparent',
    border:       'none',
    color:        'rgba(255,255,255,0.4)',
    fontFamily:   'inherit',
    fontSize:     13,
    fontWeight:   600,
    padding:      '10px 4px',
    borderRadius: 8,
    cursor:       'pointer',
    transition:   'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
  },
  tabActive: { 
    background: 'linear-gradient(180deg, rgba(225,6,0,0.15) 0%, rgba(225,6,0,0.05) 100%)', 
    color: '#fff',
    border: '1px solid rgba(225,6,0,0.3)',
    boxShadow: '0 4px 12px rgba(225,6,0,0.1)'
  },
  formContainer: {
    position: 'relative',
  },
  form: { 
    display: 'flex', 
    flexDirection: 'column', 
    gap: 20 
  },
  compactForm: {
    display: 'flex', 
    flexDirection: 'column', 
    gap: 16
  },
  row: {
    display: 'flex',
    gap: 12,
  },
  inputGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    flex: 1,
  },
  label: { 
    color: 'rgba(255,255,255,0.6)', 
    fontSize: 12, 
    fontWeight: 600, 
    letterSpacing: '0.05em',
  },
  input: {
    background:   'rgba(0,0,0,0.4)',
    border:       '1px solid rgba(255,255,255,0.1)',
    borderRadius: 10,
    color:        '#fff',
    fontFamily:   'inherit',
    fontSize:     15,
    padding:      '12px 16px',
    outline:      'none',
    width:        '100%',
    boxSizing:    'border-box',
    transition:   'all 0.2s',
    boxShadow:    'inset 0 2px 4px rgba(0,0,0,0.2)',
  },
  // We'll rely on normal css :focus state for outline if possible, but standard is fine.
  pwWrap: { position: 'relative' },
  pwToggle: { 
    position: 'absolute', 
    right: 12, 
    top: '50%', 
    transform: 'translateY(-50%)', 
    background: 'none', 
    border: 'none', 
    cursor: 'pointer', 
    fontSize: 16,
    opacity: 0.5,
    transition: 'opacity 0.2s'
  },
  otpInput: { 
    textAlign: 'center', 
    fontSize: 32, 
    letterSpacing: '14px', 
    fontWeight: 700,
    padding: '16px',
    background: 'rgba(225,6,0,0.03)',
    border: '1px solid rgba(225,6,0,0.2)',
    color: '#ff4d4d',
  },
  strengthBar: { display: 'flex', alignItems: 'center', gap: 4, marginTop: 8 },
  strengthSegment: { flex: 1, height: 4, borderRadius: 2, transition: 'background 0.3s' },
  submitBtn: {
    position:     'relative',
    marginTop:    12,
    background:   'linear-gradient(135deg, #e10600, #b30000)',
    color:        '#fff',
    border:       '1px solid rgba(255,255,255,0.1)',
    padding:      '14px 0',
    borderRadius: 10,
    fontFamily:   'inherit',
    fontSize:     15,
    fontWeight:   700,
    cursor:       'pointer',
    width:        '100%',
    overflow:     'hidden',
    transition:   'transform 0.2s, box-shadow 0.2s',
  },
  btnText: {
    position: 'relative',
    zIndex: 2,
    letterSpacing: '0.02em',
  },
  btnGlow: {
    position: 'absolute',
    top: 0, left: 0, right: 0, bottom: 0,
    background: 'linear-gradient(rgba(255,255,255,0.2), transparent)',
    zIndex: 1,
  },
  errorMsg:   { 
    color: '#ff4d4d', 
    fontSize: 13, 
    marginTop: 4,
    background: 'rgba(255,77,77,0.1)',
    padding: '8px 12px',
    borderRadius: 6,
    border: '1px solid rgba(255,77,77,0.2)'
  },
  successMsg: { 
    color: '#00e676', 
    fontSize: 13, 
    marginTop: 4,
    background: 'rgba(0,230,118,0.1)',
    padding: '8px 12px',
    borderRadius: 6,
    border: '1px solid rgba(0,230,118,0.2)'
  },
  hint:       { color: 'rgba(255,255,255,0.4)', fontSize: 14, marginBottom: 16, lineHeight: 1.5 },
  countdown:  { color: '#ffa64d', fontSize: 13, marginTop: 12, textAlign: 'center', fontWeight: 600 },
  linkBtn: {
    background: 'none', border: 'none', color: 'rgba(255,255,255,0.5)',
    cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, padding: 0, textDecoration: 'underline',
    transition: 'color 0.2s'
  },
  gdprLabel: {
    display:    'flex',
    gap:        12,
    alignItems: 'flex-start',
    color:      'rgba(255,255,255,0.4)',
    fontSize:   12,
    marginTop:  8,
    cursor:     'pointer',
  },
  checkboxWrapper: {
    paddingTop: 2,
  },
  checkbox: {
    accentColor: '#e10600',
    width: 16,
    height: 16,
    cursor: 'pointer',
  },
  gdprLink: { color: '#e10600', textDecoration: 'none' },
  verifyPrompt: { 
    textAlign: 'center', 
    padding: '32px 0 16px',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center'
  },
  verifyIcon:  { 
    fontSize: 40, 
    marginBottom: 24,
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 80,
    height: 80,
    background: 'rgba(225,6,0,0.1)',
    borderRadius: '50%',
    border: '1px solid rgba(225,6,0,0.2)'
  },
  verifyRing: {
    position: 'absolute',
    inset: -10,
    border: '1px dashed rgba(225,6,0,0.3)',
    borderRadius: '50%',
    animation: 'spin 10s linear infinite',
  },
  verifyTitle: { color: '#fff', fontWeight: 700, fontSize: 24, margin: '0 0 12px' },
  verifyText:  { color: 'rgba(255,255,255,0.5)', fontSize: 15, lineHeight: 1.6, marginBottom: 16 },
};

// Global animations appended dynamically
if (typeof document !== 'undefined') {
  const styleEl = document.createElement('style');
  styleEl.innerHTML = `
    @keyframes pulse {
      0% { opacity: 0.1; transform: scaleY(0.9); }
      100% { opacity: 0.5; transform: scaleY(1.1); }
    }
    @keyframes spin {
      100% { transform: rotate(360deg); }
    }
    input:focus {
      border-color: rgba(225,6,0,0.5) !important;
      box-shadow: 0 0 0 3px rgba(225,6,0,0.15) !important;
    }
    button[type="submit"]:hover {
      transform: translateY(-1px);
      box-shadow: 0 8px 24px rgba(225,6,0,0.4);
    }
    @media (max-width: 900px) {
      .landing-page-left-pane { display: none !important; }
      .landing-page-right-pane { flex: 1 !important; min-width: 100% !important; padding: 24px !important; }
    }
  `;
  document.head.appendChild(styleEl);
}
