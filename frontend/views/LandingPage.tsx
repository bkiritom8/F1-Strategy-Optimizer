// frontend/views/LandingPage.tsx
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { SpeedLines } from '../components/SpeedLines';

const css = `
  @keyframes lp-fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }
  @keyframes lp-riseIn {
    from { opacity: 0; transform: translateY(32px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  @keyframes lp-glare {
    0% { transform: translateX(-100%); }
    100% { transform: translateX(200%); }
  }
  @keyframes lp-pulse-glow {
    0%, 100% { box-shadow: 0 0 10px var(--accent-f1-glow); }
    50%       { box-shadow: 0 0 25px var(--accent-f1); }
  }

  .lp-nav      { opacity: 0; animation: lp-fadeIn  1.2s ease 0.1s  forwards; }
  .lp-eyebrow  { opacity: 0; animation: lp-riseIn  1.0s cubic-bezier(0.16, 1, 0.3, 1) 0.3s forwards; }
  .lp-headline { opacity: 0; animation: lp-riseIn  1.2s cubic-bezier(0.16, 1, 0.3, 1) 0.5s forwards; }
  .lp-sub      { opacity: 0; animation: lp-riseIn  1.2s cubic-bezier(0.16, 1, 0.3, 1) 0.7s  forwards; }
  .lp-ctas     { opacity: 0; animation: lp-riseIn  1.2s cubic-bezier(0.16, 1, 0.3, 1) 0.9s forwards; }
  .lp-stats    { opacity: 0; animation: lp-fadeIn  1.5s ease 1.2s  forwards; }

  .lp-btn-p {
    position: relative;
    overflow: hidden;
    transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  }
  .lp-btn-p:hover { 
    transform: translateY(-2px);
    box-shadow: 0 12px 30px var(--accent-f1-glow);
  }
  .lp-btn-p::after {
    content: "";
    position: absolute;
    top: 0; left: 0; width: 50%; height: 100%;
    background: linear-gradient(to right, transparent, rgba(255,255,255,0.2), transparent);
    transform: skewX(-25deg);
    animation: lp-glare 3s infinite;
  }

  .lp-btn-s:hover { 
    background: rgba(255,255,255,0.1) !important;
    border-color: rgba(255,255,255,0.3) !important;
    transform: translateY(-2px);
  }

  .lp-glass-card {
    background: var(--glass-bg);
    backdrop-filter: blur(var(--glass-blur));
    border: 1px solid var(--glass-border);
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  }

  .font-outfit { font-family: 'Outfit', sans-serif; }
  .font-inter { font-family: 'Inter', sans-serif; }
`;

const NAV_LINKS = [
  { label: 'Race Center', path: '/race'     },
  { label: 'Strategy',    path: '/strategy' },
  { label: 'Circuits',    path: '/circuits' },
  { label: 'Drivers',     path: '/drivers'  },
  { label: 'Analysis',    path: '/analysis' },
];

export default function LandingPage() {
  const navigate = useNavigate();

  return (
    <div className="font-inter" style={{ minHeight: '100vh', backgroundColor: '#000', color: '#fff', overflow: 'hidden' }}>
      <style>{css}</style>

      {/* Background Gradient */}
      <div style={{
        position: 'fixed', inset: 0, zIndex: 0,
        background: 'radial-gradient(circle at 50% -20%, rgba(225,6,0,0.15) 0%, transparent 70%), #000',
      }} />

      <SpeedLines />

      {/* Navigation */}
      <nav className="lp-nav lp-glass-card" style={{
        position: 'fixed', top: 20, left: '50%', transform: 'translateX(-50%)',
        zIndex: 50, width: '90%', maxWidth: 1200, height: 64,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 32px', borderRadius: 20,
      }}>
        {/* Brand */}
        <div
          onClick={() => navigate('/')}
          style={{ display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer' }}
        >
          <div style={{
            width: 38, height: 38, borderRadius: 12,
            background: 'linear-gradient(135deg, var(--accent-f1), #9b0400)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 4px 15px var(--accent-f1-glow)',
          }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <rect x="9" y="9" width="6" height="6" />
              <rect x="2" y="2" width="20" height="20" rx="2" />
              <path d="M9 2V9M15 2V9M9 15v7M15 15v7M2 9h7M2 15h7M15 9h7M15 15h7" />
            </svg>
          </div>
          <div>
            <div className="font-outfit" style={{ fontSize: 16, fontWeight: 900, letterSpacing: '-0.5px', fontStyle: 'italic', lineHeight: 1 }}>
              APEX F1
            </div>
            <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: 2, textTransform: 'uppercase', color: 'var(--accent-f1)', marginTop: 2 }}>
              Race Intelligence
            </div>
          </div>
        </div>

        {/* Links */}
        <ul style={{ display: 'flex', gap: 32, listStyle: 'none', margin: 0, padding: 0 }}>
          {NAV_LINKS.map(({ label, path }) => (
            <li key={label}>
              <button
                onClick={() => navigate(path)}
                style={{
                  fontSize: 14, fontWeight: 500, color: 'rgba(255,255,255,0.6)',
                  background: 'none', border: 'none', cursor: 'pointer',
                  transition: 'color 0.2s',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.color = '#fff')}
                onMouseLeave={(e) => (e.currentTarget.style.color = 'rgba(255,255,255,0.6)')}
              >
                {label}
              </button>
            </li>
          ))}
        </ul>

        {/* Action */}
        <button 
          onClick={() => navigate('/race')}
          className="lp-nav-btn" 
          style={{
            fontSize: 14, fontWeight: 600, color: '#fff',
            background: 'rgba(225,6,0,0.1)', border: '1px solid rgba(225,6,0,0.3)',
            padding: '8px 24px', borderRadius: 12, cursor: 'pointer',
            transition: 'all 0.2s',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'var(--accent-f1)';
            e.currentTarget.style.borderColor = 'var(--accent-f1)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'rgba(225,6,0,0.1)';
            e.currentTarget.style.borderColor = 'rgba(225,6,0,0.3)';
          }}
        >
          Get Started
        </button>
      </nav>

      {/* Main Hero Section */}
      <main style={{
        position: 'relative', zIndex: 10, height: '100vh',
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        textAlign: 'center', padding: '0 24px',
      }}>
        {/* Eyebrow */}
        <div className="lp-eyebrow" style={{ 
          display: 'flex', alignItems: 'center', gap: 10, marginBottom: 24,
          background: 'rgba(255,255,255,0.05)', padding: '6px 16px', borderRadius: 100,
          border: '1px solid rgba(255,255,255,0.1)',
        }}>
          <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent-f1)', boxShadow: '0 0 8px var(--accent-f1)' }} />
          <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: 2, color: 'rgba(255,255,255,0.5)', textTransform: 'uppercase' }}>
            Next-Gen Strategy Platform
          </span>
        </div>

        {/* Headline */}
        <div className="lp-headline">
          <h1 className="font-outfit" style={{ 
            fontSize: 'clamp(48px, 8vw, 110px)', fontWeight: 800, 
            lineHeight: 0.95, letterSpacing: '-0.04em', margin: 0,
            textShadow: '0 20px 50px rgba(0,0,0,0.5)',
          }}>
            Master the <br />
            <span style={{ color: 'var(--accent-f1)', position: 'relative' }}>
              Apex Point
              <span style={{ 
                position: 'absolute', bottom: '15%', left: 0, width: '100%', height: '8%',
                background: 'var(--accent-f1-glow)', zIndex: -1, filter: 'blur(10px)'
              }} />
            </span>
          </h1>
        </div>

        {/* Subcopy */}
        <p className="lp-sub" style={{
          fontSize: 'clamp(16px, 1.2vw, 20px)', fontWeight: 400,
          color: 'rgba(255,255,255,0.6)', lineHeight: 1.6,
          maxWidth: 600, margin: '32px auto 48px',
        }}>
          Enterprise-grade race intelligence. Predict tire life, optimize pit stops, 
          and simulate thousands of scenarios in milliseconds.
        </p>

        {/* CTAs */}
        <div className="lp-ctas" style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
          <button className="lp-btn-p" onClick={() => navigate('/race')} style={{
            background: 'var(--accent-f1)', color: '#fff', border: 'none',
            padding: '16px 40px', fontSize: 16, fontWeight: 700,
            borderRadius: 14, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 10,
          }}>
            Launch Strategy Hub
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </button>
          <button className="lp-btn-s" onClick={() => navigate('/race')} style={{
            background: 'rgba(255,255,255,0.05)', color: '#fff',
            border: '1px solid rgba(255,255,255,0.1)',
            padding: '16px 40px', fontSize: 16, fontWeight: 600,
            borderRadius: 14, cursor: 'pointer', backdropFilter: 'blur(10px)',
            transition: 'all 0.2s',
          }}>
            Technical Specs
          </button>
        </div>
      </main>

      {/* Stats Section */}
      <div className="lp-stats lp-glass-card" style={{
        position: 'fixed', bottom: 40, left: '50%', transform: 'translateX(-50%)',
        display: 'flex', gap: 60, alignItems: 'center', zIndex: 10,
        padding: '20px 60px', borderRadius: 24,
      }}>
        {[
          { n: '76', unit: 'yrs', label: 'Race Data' },
          { n: '6',  unit: '+',   label: 'AI Models' },
          { n: '<500', unit: 'ms', label: 'Inference' },
          { n: '20', unit: 'idx',  label: 'Circuits' },
        ].map((s, i) => (
          <div key={s.label} style={{ textAlign: 'center' }}>
            <div className="font-outfit" style={{ fontSize: 24, fontWeight: 800, color: '#fff', lineHeight: 1 }}>
              {s.n}<span style={{ color: 'var(--accent-f1)' }}>{s.unit}</span>
            </div>
            <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)', letterSpacing: 1.5, textTransform: 'uppercase', marginTop: 6, fontWeight: 700 }}>
              {s.label}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
