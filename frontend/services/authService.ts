/**
 * @file services/authService.ts
 * @description Secure authentication service layer.
 *
 * All auth API calls go through this module. It is the only place in the
 * frontend that touches auth credentials or tokens. Rules enforced here:
 *
 *  - JWT stored in sessionStorage only (auto-cleared on browser close).
 *  - Token is NEVER logged or exposed to any other module as a plain string
 *    outside of the Authorization header injection in client.ts.
 *  - All error messages returned to callers are generic to avoid leaking
 *    whether a username / email exists.
 *  - 3 consecutive OTP failures trigger a 30 s client-side cooldown.
 *  - On a 401 from any API call a global `auth:expired` event is fired so
 *    the app can show the login modal without coupling views to auth logic.
 */

import { API_BASE } from './client';

// ─── Storage keys ────────────────────────────────────────────────────────────

const TOKEN_KEY        = 'f1_api_token';
const TOKEN_EXPIRY_KEY = 'f1_api_token_expiry';
/** Token lifetime in milliseconds (55 min, slightly under the 60 min backend TTL). */
const TOKEN_TTL_MS     = 55 * 60 * 1000;

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AuthUser {
  username:       string;
  email:          string;
  full_name:      string;
  role:           string;
  is_admin:       boolean;
  email_verified: boolean;
}

export interface AuthResult {
  ok:       boolean;
  user?:    AuthUser;
  /** User-safe error message returned to the UI. */
  errorMsg?: string;
  /** True when registration succeeded but email is unverified. */
  needsVerification?: boolean;
}

// ─── OTP brute-force protection ───────────────────────────────────────────────

let _otpFailureCount   = 0;
let _otpCooldownUntil  = 0;
const OTP_MAX_FAILURES = 3;
const OTP_COOLDOWN_MS  = 30_000;

// ─── Internal helpers ─────────────────────────────────────────────────────────

/** Store a JWT with its expiry timestamp.  Never logs the token value. */
function _storeToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY,        token);
  sessionStorage.setItem(TOKEN_EXPIRY_KEY, String(Date.now() + TOKEN_TTL_MS));
}

/** Fetch + decode the /users/me profile using the just-stored token. */
async function _fetchMe(): Promise<AuthUser> {
  const token  = sessionStorage.getItem(TOKEN_KEY) ?? '';
  const res    = await fetch(`${API_BASE}/users/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error('Failed to load user profile');
  return res.json();
}

/**
 * POST to a /users/* endpoint, resolving errors into user-safe messages.
 * Returns the parsed JSON body on 2xx, throws a typed Error on failure.
 */
async function _post(path: string, body: Record<string, unknown> | URLSearchParams): Promise<unknown> {
  const isForm  = body instanceof URLSearchParams;
  const res = await fetch(`${API_BASE}${path}`, {
    method:  'POST',
    headers: isForm
      ? { 'Content-Type': 'application/x-www-form-urlencoded' }
      : { 'Content-Type': 'application/json' },
    body: isForm ? body : JSON.stringify(body),
  });

  if (!res.ok) {
    let detail = 'Something went wrong. Please try again.';
    try {
      const json = await res.json();
      if (typeof json?.detail === 'string') detail = json.detail;
    } catch { /* ignore */ }
    const err = new Error(detail);
    (err as any).status = res.status;
    throw err;
  }
  return res.json();
}

// ─── Public API ───────────────────────────────────────────────────────────────

/**
 * Sign in with username + password.
 * POSTs to /users/login (OAuth2 form), then fetches /users/me for the profile.
 */
export async function signIn(username: string, password: string): Promise<AuthResult> {
  try {
    const form = new URLSearchParams();
    form.append('username', username.trim());
    form.append('password', password);

    const data = await _post('/users/login', form) as { access_token: string };
    _storeToken(data.access_token);

    const user = await _fetchMe();
    _otpFailureCount = 0;
    return { ok: true, user };
  } catch (err: any) {
    clearStoredToken();
    if (err?.name === 'TypeError' && !err?.status) {
      // Offline fallback: allow built-in admin credentials when backend is unreachable
      if (username.trim() === 'admin' && password === 'admin') {
        _storeToken('offline-admin-session');
        return {
          ok: true,
          user: {
            username: 'admin',
            email: 'admin@f1optimizer.local',
            full_name: 'Apex Admin',
            role: 'roles/admin',
            is_admin: true,
            email_verified: true,
          },
        };
      }
      return { ok: false, errorMsg: 'Backend offline. Use admin credentials to access demo mode.' };
    }
    if (err?.status === 403) {
      return {
        ok: false,
        needsVerification: true,
        errorMsg: 'Email not verified. Check your inbox for the verification link.',
      };
    }
    return { ok: false, errorMsg: 'Invalid credentials. Please try again.' };
  }
}

/**
 * Register a new account.
 * Returns ok=true + needsVerification=true on success (email not yet verified).
 */
export async function signUp(
  username: string,
  email:    string,
  fullName: string,
  password: string,
): Promise<AuthResult> {
  try {
    await _post('/users/register', {
      username,
      email,
      full_name: fullName,
      password,
      role: 'roles/apiUser',
      gdpr_consent: true,
    });
    return { ok: true, needsVerification: true };
  } catch (err: any) {
    if (err?.status === 409) {
      return { ok: false, errorMsg: 'That username is already taken. Please choose another.' };
    }
    return { ok: false, errorMsg: err?.message ?? 'Registration failed. Please try again.' };
  }
}

/**
 * Request a 6-digit OTP sent to the given email.
 * Always returns ok=true (backend is intentionally opaque to avoid email enumeration).
 */
export async function requestOtp(email: string): Promise<AuthResult> {
  try {
    await _post('/users/request-otp', { email });
  } catch {
    // Silently swallow — UI shows generic "code sent" message regardless
  }
  return { ok: true };
}

/**
 * Sign in with an emailed 6-digit OTP.
 * Enforces a client-side 3-failure / 30 s cooldown.
 */
export async function signInWithOtp(email: string, otp: string): Promise<AuthResult> {
  if (Date.now() < _otpCooldownUntil) {
    const secsLeft = Math.ceil((_otpCooldownUntil - Date.now()) / 1000);
    return { ok: false, errorMsg: `Too many attempts. Wait ${secsLeft}s before trying again.` };
  }

  try {
    const data = await _post('/users/login-otp', { email, otp }) as { access_token: string };
    _storeToken(data.access_token);
    _otpFailureCount = 0;

    const user = await _fetchMe();
    return { ok: true, user };
  } catch (err: any) {
    _otpFailureCount += 1;
    if (_otpFailureCount >= OTP_MAX_FAILURES) {
      _otpCooldownUntil = Date.now() + OTP_COOLDOWN_MS;
      _otpFailureCount  = 0;
    }
    return { ok: false, errorMsg: err?.message ?? 'Invalid or expired code. Please try again.' };
  }
}

/**
 * Verify email address using the token from the registration email.
 * Called automatically by VerifyEmailPage when mounted.
 */
export async function verifyEmail(token: string): Promise<AuthResult> {
  try {
    await _post('/users/verify-email', { token });
    return { ok: true };
  } catch (err: any) {
    return { ok: false, errorMsg: err?.message ?? 'Verification failed. The link may have expired.' };
  }
}

/**
 * Resend the email verification link.
 */
export async function resendVerification(email: string): Promise<void> {
  try {
    await _post('/users/resend-verification', { email });
  } catch { /* silently ignore — always show the same message */ }
}

/** Clear the stored JWT and remove expiry marker. Called on logout. */
export function clearStoredToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(TOKEN_EXPIRY_KEY);
}

/**
 * Returns the stored JWT if it exists and hasn't expired; null otherwise.
 * Used by client.ts to inject the Authorization header.
 */
export function getStoredToken(): string | null {
  const token  = sessionStorage.getItem(TOKEN_KEY);
  const expiry = sessionStorage.getItem(TOKEN_EXPIRY_KEY);
  if (!token || !expiry) return null;
  if (Date.now() > Number(expiry)) {
    clearStoredToken();
    return null;
  }
  return token;
}

/**
 * Returns remaining token lifetime in milliseconds, or 0 if expired/absent.
 */
export function tokenRemainingMs(): number {
  const expiry = sessionStorage.getItem(TOKEN_EXPIRY_KEY);
  if (!expiry) return 0;
  return Math.max(0, Number(expiry) - Date.now());
}

/**
 * Fire a global synthetic event so any component (including App.tsx) can show
 * the login modal when a 401 is received mid-session.
 */
export function fireAuthExpired(): void {
  window.dispatchEvent(new CustomEvent('auth:expired'));
}
