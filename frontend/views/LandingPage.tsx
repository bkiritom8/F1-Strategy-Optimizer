// frontend/views/LandingPage.tsx
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { SpeedLines } from '../components/SpeedLines';

const css = `
  @keyframes lp-fadeIn {
    to { opacity: 1; }
  }
  @keyframes lp-riseIn {
    from { opacity: 0; transform: translateY(28px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  @keyframes lp-pulse {
    0%, 100% { box-shadow: 0 0 6px rgba(225,6,0,0.8); }
    50%       { box-shadow: 0 0 18px rgba(225,6,0,1); }
  }

  .lp-nav      { opacity: 0; animation: lp-fadeIn  0.8s ease 0.1s  forwards; }
  .lp-line     { opacity: 0; animation: lp-fadeIn  1.5s ease 0.9s  forwards; }
  .lp-eyebrow  { opacity: 0; animation: lp-riseIn  0.9s cubic-bezier(0.22,1,0.36,1) 0.35s forwards; }
  .lp-sub      { opacity: 0; animation: lp-riseIn  1.0s cubic-bezier(0.22,1,0.36,1) 1.6s  forwards; }
  .lp-ctas     { opacity: 0; animation: lp-riseIn  1.0s cubic-bezier(0.22,1,0.36,1) 1.85s forwards; }
  .lp-stats    { opacity: 0; animation: lp-riseIn  1.0s cubic-bezier(0.22,1,0.36,1) 2.3s  forwards; }

  .lp-w1 { opacity: 0; animation: lp-riseIn 1.0s cubic-bezier(0.22,1,0.36,1) 0.55s forwards; }
  .lp-w2 { opacity: 0; animation: lp-riseIn 1.0s cubic-bezier(0.22,1,0.36,1) 0.72s forwards; }
  .lp-w3 { opacity: 0; animation: lp-riseIn 1.0s cubic-bezier(0.22,1,0.36,1) 0.88s forwards; }
  .lp-w4 { opacity: 0; animation: lp-riseIn 1.0s cubic-bezier(0.22,1,0.36,1) 1.03s forwards; }
  .lp-w5 { opacity: 0; animation: lp-riseIn 1.0s cubic-bezier(0.22,1,0.36,1) 1.16s forwards; }
  .lp-w6 { opacity: 0; animation: lp-riseIn 1.0s cubic-bezier(0.22,1,0.36,1) 1.29s forwards; }

  .lp-dot { animation: lp-pulse 2.5s ease-in-out 1.5s infinite; }

  .lp-btn-p:hover { background: #c50500 !important; transform: scale(1.03); box-shadow: 0 8px 28px rgba(225,6,0,0.45); }
  .lp-btn-s:hover { background: rgba(255,255,255,0.13) !important; transform: scale(1.03); }
  .lp-nav-btn:hover { background: rgba(225,6,0,0.3) !important; }
  .lp-nav-link:hover { color: #fff !important; }
`;

export default function LandingPage() {
  const navigate = useNavigate();

  return (
    <>
      <style>{css}</style>

      {/* Background */}
      <div style={{
        position: 'fixed', inset: 0, zIndex: 0,
        background: 'radial-gradient(ellipse 80% 50% at 50% 0%, rgba(225,6,0,0.12) 0%, transparent 55%), #000',
      }} />

      <SpeedLines />

      {/* Nav */}
      <nav className="lp-nav" style={{
        position: 'fixed', top: 0, left: 0, right: 0, zIndex: 20, height: 54,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 52px',
        background: 'rgba(0,0,0,0.55)',
        backdropFilter: 'blur(20px) saturate(180%)',
        borderBottom: '1px solid rgba(255,255,255,0.07)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 700, letterSpacing: 2, textTransform: 'uppercase', color: '#fff' }}>
          <div className="lp-dot" style={{ width: 7, height: 7, borderRadius: '50%', background: '#e10600', boxShadow: '0 0 8px rgba(225,6,0,0.9)' }} />
          Apex Intelligence
        </div>
        <ul style={{ display: 'flex', gap: 32, listStyle: 'none', margin: 0, padding: 0 }}>
          {['Race Center','Strategy','Circuits','Drivers','Analysis'].map(label => (
            <li key={label}>
              <button className="lp-nav-link" onClick={() => navigate('/race')}
                style={{ fontSize: 13, color: 'rgba(255,255,255,0.5)', background: 'none', border: 'none', cursor: 'pointer', transition: 'color 0.2s' }}>
                {label}
              </button>
            </li>
          ))}
        </ul>
        <button className="lp-nav-btn" onClick={() => navigate('/race')} style={{
          fontSize: 13, fontWeight: 500, color: '#fff',
          background: 'rgba(225,6,0,0.15)', border: '1px solid rgba(225,6,0,0.3)',
          padding: '7px 18px', borderRadius: 980, cursor: 'pointer', transition: 'background 0.2s',
        }}>
          Sign In
        </button>
      </nav>

      {/* Ambient line below nav */}
      <div className="lp-line" style={{
        position: 'fixed', top: 54, left: '50%', transform: 'translateX(-50%)',
        width: '55vw', height: 1, zIndex: 19,
        background: 'linear-gradient(to right, transparent, rgba(225,6,0,0.4), transparent)',
      }} />

      {/* Hero */}
      <main style={{
        position: 'relative', zIndex: 10, height: '100vh',
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        textAlign: 'center', padding: '0 24px',
        fontFamily: "'Inter', -apple-system, 'SF Pro Display', sans-serif",
        color: '#fff',
      }}>
        {/* Eyebrow */}
        <div className="lp-eyebrow" style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 26 }}>
          <div style={{ width: 5, height: 5, borderRadius: '50%', background: '#e10600' }} />
          <span style={{ fontSize: 12, fontWeight: 500, letterSpacing: 4, color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase' }}>
            F1 Strategy Intelligence Platform
          </span>
        </div>

        {/* Headline */}
        <h1 style={{ fontSize: 'clamp(48px, 9vw, 118px)', fontWeight: 800, lineHeight: 1.0, letterSpacing: '-2.5px', margin: 0 }}>
          <span className="lp-w1" style={{ display: 'inline-block' }}>Race</span>
          {' '}
          <span className="lp-w2" style={{ display: 'inline-block' }}>at</span>
          {' '}
          <span className="lp-w3" style={{ display: 'inline-block' }}>the</span>
          <span style={{ display: 'block', color: '#e10600' }}>
            <span className="lp-w4" style={{ display: 'inline-block' }}>speed</span>
            {' '}
            <span className="lp-w5" style={{ display: 'inline-block' }}>of</span>
            {' '}
            <span className="lp-w6" style={{ display: 'inline-block' }}>data.</span>
          </span>
        </h1>

        {/* Sub */}
        <p className="lp-sub" style={{
          fontSize: 'clamp(14px, 1.7vw, 19px)', fontWeight: 400,
          color: 'rgba(255,255,255,0.38)', lineHeight: 1.6,
          maxWidth: 480, margin: '20px auto 42px',
        }}>
          Real-time F1 strategy intelligence powered by machine learning.<br />
          Pit windows, tire degradation, race outcomes — all in one platform.
        </p>

        {/* CTAs */}
        <div className="lp-ctas" style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <button className="lp-btn-p" onClick={() => navigate('/race')} style={{
            display: 'inline-flex', alignItems: 'center', gap: 8,
            background: '#e10600', color: '#fff', border: 'none',
            padding: '14px 32px', fontSize: 15, fontWeight: 600,
            borderRadius: 980, cursor: 'pointer', transition: 'background 0.2s, transform 0.15s, box-shadow 0.2s',
          }}>
            Enter App
            <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2.2">
              <path d="M3 8h10M9 4l4 4-4 4" />
            </svg>
          </button>
          <button className="lp-btn-s" onClick={() => navigate('/race')} style={{
            display: 'inline-flex', alignItems: 'center', gap: 8,
            background: 'rgba(255,255,255,0.08)', color: 'rgba(255,255,255,0.82)',
            border: '1px solid rgba(255,255,255,0.12)',
            padding: '14px 32px', fontSize: 15, fontWeight: 500,
            borderRadius: 980, cursor: 'pointer',
            backdropFilter: 'blur(12px)', transition: 'background 0.2s, transform 0.15s',
          }}>
            Watch Demo
          </button>
        </div>
      </main>

      {/* Stats */}
      <div className="lp-stats" style={{
        position: 'fixed', bottom: 40, left: '50%', transform: 'translateX(-50%)',
        display: 'flex', gap: 44, alignItems: 'center', zIndex: 10,
      }}>
        {[
          { n: '76', unit: 'yrs', label: 'Race Data' },
          { n: '6',  unit: '+',   label: 'ML Models' },
          { n: '<500', unit: 'ms', label: 'P99 Latency' },
          { n: '860', unit: '+',  label: 'Drivers' },
        ].map((s, i) => (
          <React.Fragment key={s.label}>
            {i > 0 && <div style={{ width: 1, height: 32, background: 'rgba(255,255,255,0.1)' }} />}
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 20, fontWeight: 700, letterSpacing: -0.5, color: '#fff' }}>
                {s.n}<span style={{ color: '#e10600' }}>{s.unit}</span>
              </div>
              <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.32)', letterSpacing: 1.5, textTransform: 'uppercase', marginTop: 2 }}>
                {s.label}
              </div>
            </div>
          </React.Fragment>
        ))}
      </div>
    </>
  );
}
