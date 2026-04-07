/**
 * @file views/VerifyEmailPage.tsx
 * @description Handles the /verify-email?token=... route.
 *
 * When the user clicks the link in their registration email they land here.
 * The component auto-calls POST /users/verify-email on mount using the token
 * in the URL query string, then displays a success or failure message.
 */

import React, { useEffect, useState } from 'react';
import { verifyEmail } from '../services/authService';

interface Props {
  /** Called when user clicks "Go to Sign In" after a successful verification. */
  onGoToLogin: () => void;
}

type State = 'loading' | 'success' | 'error';

const VerifyEmailPage: React.FC<Props> = ({ onGoToLogin }) => {
  const [state,   setState]   = useState<State>('loading');
  const [message, setMessage] = useState('');

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token  = params.get('token') ?? '';

    if (!token) {
      setState('error');
      setMessage('No verification token found in the URL. Please check the link in your email.');
      return;
    }

    verifyEmail(token).then((result) => {
      if (result.ok) {
        setState('success');
      } else {
        setState('error');
        setMessage(result.errorMsg ?? 'Verification failed. The link may have expired.');
      }
    });
  }, []);

  const icon = state === 'loading' ? '⏳' : state === 'success' ? '✅' : '❌';
  const title =
    state === 'loading' ? 'Verifying your email…'
    : state === 'success' ? 'Email Verified!'
    : 'Verification Failed';

  return (
    <div style={styles.page}>
      <div style={styles.card}>
        <div style={styles.icon}>{icon}</div>
        <h1 style={styles.title}>{title}</h1>
        {state === 'loading' && (
          <p style={styles.text}>Please wait while we verify your email address.</p>
        )}
        {state === 'success' && (
          <>
            <p style={styles.text}>
              Your email has been verified. You can now sign in to Apex Intelligence.
            </p>
            <button id="verify-go-signin" style={styles.btn} onClick={onGoToLogin}>
              Go to Sign In
            </button>
          </>
        )}
        {state === 'error' && (
          <>
            <p style={styles.errorText}>{message}</p>
            <p style={styles.text}>
              Request a new verification link by signing in and choosing
              "Resend verification email."
            </p>
            <button id="verify-go-signin-err" style={styles.btn} onClick={onGoToLogin}>
              Go to Sign In
            </button>
          </>
        )}
      </div>
    </div>
  );
};

export default VerifyEmailPage;

// ─── Styles ──────────────────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight:      '100vh',
    background:     'radial-gradient(ellipse at 20% 50%, #1a0a00 0%, #0a0a0a 60%)',
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'center',
    fontFamily:     "'Inter', 'Outfit', sans-serif",
    padding:        24,
  },
  card: {
    background:   '#111',
    border:       '1px solid rgba(255,255,255,0.1)',
    borderRadius: 16,
    padding:      48,
    maxWidth:     480,
    width:        '100%',
    textAlign:    'center',
    boxShadow:    '0 32px 80px rgba(0,0,0,0.6)',
  },
  icon:      { fontSize: 56, marginBottom: 20 },
  title:     { color: '#fff', fontSize: 24, fontWeight: 800, margin: '0 0 16px' },
  text:      { color: 'rgba(255,255,255,0.5)', fontSize: 14, lineHeight: 1.7, margin: '0 0 24px' },
  errorText: { color: '#e74c3c', fontSize: 14, lineHeight: 1.6, margin: '0 0 16px' },
  btn: {
    background:   'linear-gradient(135deg, #e10600, #c00)',
    color:        '#fff',
    border:       'none',
    padding:      '12px 32px',
    borderRadius: 8,
    fontFamily:   'inherit',
    fontSize:     14,
    fontWeight:   700,
    cursor:       'pointer',
    display:      'inline-block',
  },
};
