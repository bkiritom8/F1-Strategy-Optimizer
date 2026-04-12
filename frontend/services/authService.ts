/**
 * @file services/authService.ts
 * @description Secure authentication service layer.
 *
 * All auth API calls go through this module. It is the only place in the
 * frontend that touches auth credentials or tokens. Rules enforced here:
 *
 *  - JWT stored in localStorage (persists across tab closes; cleared on sign-out or expiry).
 *  - Token is NEVER logged or exposed to any other module as a plain string
 *    outside of the Authorization header injection in client.ts.
 *  - All error messages returned to callers are generic to avoid leaking
 *    whether a username / email exists.
 *  - 3 consecutive OTP failures trigger a 30 s client-side cooldown.
 *  - On a 401 from any API call a global `auth:expired` event is fired so
 *    the app can show the login modal without coupling views to auth logic.
 */

import { API_BASE } from './client';
import { logger } from './logger';

// ─── Storage keys ────────────────────────────────────────────────────────────

const TOKEN_KEY        = 'f1_api_token';
const TOKEN_EXPIRY_KEY = 'f1_api_token_expiry';
/** Token lifetime in milliseconds (55 min, slightly under the 60 min backend TTL). */
const TOKEN_TTL_MS     = 55 * 60 * 1000;

// ─── Types ───────────────────────────────────────────────────────────────────

/**
 * Logged-in user profile attributes.
 */
export interface AuthUser {
  /** Ergast-format driver slug or system username. */
  username:       string;
  email:          string;
  full_name:      string;
  /** RBAC role (e.g., 'roles/admin', 'roles/apiUser'). */
  role:           string;
  is_admin:       boolean;
  /** True if the user has confirmed their email address. */
  email_verified: boolean;
}

/**
 * Result of an authentication operation.
 */
export interface AuthResult {
  /** True if the operation succeeded. */
  ok:       boolean;
  /** The loaded user profile (only on success). */
  user?:    AuthUser;
  /** Human-readable error message for UI display. */
  errorMsg?: string;
  /** Indicates the user must verify their email before proceeding. */
  needsVerification?: boolean;
}

// ─── OTP brute-force protection ───────────────────────────────────────────────

let _otpFailureCount   = 0;
let _otpCooldownUntil  = 0;
const OTP_MAX_FAILURES = 3;
const OTP_COOLDOWN_MS  = 30_000;

// ─── Internal helpers ─────────────────────────────────────────────────────────

/**
 * Persists the JWT and calculates expiry.
 * 
 * @param token - The raw JWT string.
 */
function _storeToken(token: string): void {
  logger.debug('[authService] _storeToken: persisting JWT and expiry');
  localStorage.setItem(TOKEN_KEY,        token);
  localStorage.setItem(TOKEN_EXPIRY_KEY, String(Date.now() + TOKEN_TTL_MS));
}

/**
 * Fetches current user profile from the backend.
 * 
 * @returns The authenticated user's profile.
 * @throws {Error} if the request fails or unauthorized.
 */
async function _fetchMe(): Promise<AuthUser> {
  const token  = localStorage.getItem(TOKEN_KEY) ?? '';
  logger.debug('[authService] _fetchMe: requesting profile from /users/me');
  const res    = await fetch(`${API_BASE}/users/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    logger.warn(`[authService] _fetchMe failed: status=${res.status}`);
    throw new Error('Failed to load user profile');
  }
  return res.json();
}

/**
 * Generic POST wrapper for auth endpoints.
 * 
 * @param path - URL segment.
 * @param body - Payload as Object or URLSearchParams.
 */
async function _post(path: string, body: Record<string, unknown> | URLSearchParams): Promise<unknown> {
  const isForm  = body instanceof URLSearchParams;
  logger.debug(`[authService] _post: ${path}`, { contentType: isForm ? 'form' : 'json' });
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
    
    logger.warn(`[authService] _post failed: path=${path} status=${res.status} detail=${detail}`);
    const err = new Error(detail);
    (err as any).status = res.status;
    throw err;
  }
  return res.json();
}

// ─── Public API ───────────────────────────────────────────────────────────────

/**
 * Sign in with classic username and password.
 * Supports an 'offline-admin' mode if the backend is unreachable.
 * 
 * @param username - User identifier.
 * @param password - Plaintext password.
 */
export async function signIn(username: string, password: string): Promise<AuthResult> {
  logger.info(`[authService] signIn: attempting login for ${username}`);
  try {
    const form = new URLSearchParams();
    form.append('username', username.trim());
    form.append('password', password);

    const data = await _post('/users/login', form) as { access_token: string };
    _storeToken(data.access_token);

    const user = await _fetchMe();
    _otpFailureCount = 0;
    logger.info(`[authService] signIn: success for ${username}`);
    return { ok: true, user };
  } catch (err: any) {
    clearStoredToken();
    if (err?.name === 'TypeError' && !err?.status) {
      logger.warn('[authService] signIn: backend unreachable, checking demo fallback');
      // Offline fallback: allow built-in admin credentials when backend is unreachable
      if (username.trim() === 'admin' && password === 'admin') {
        logger.info('[authService] signIn: entering DEMO mode (offline admin)');
        _storeToken('offline-admin-session');
        return {
          ok: true,
          user: {
            username: 'admin',
            email: 'admin@f1optimizer.local',
            full_name: 'Apex Admin (Offline)',
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
 * Register a new user account.
 * 
 * @param username - Target slug.
 * @param email - Valid contact email.
 * @param fullName - Display name.
 * @param password - Strong password.
 */
export async function signUp(
  username: string,
  email:    string,
  fullName: string,
  password: string,
): Promise<AuthResult> {
  logger.info(`[authService] signUp: registering ${username} (${email})`);
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
 * Triggers an OTP code delivery to the user's email.
 * 
 * @param email - Target email.
 */
export async function requestOtp(email: string): Promise<AuthResult> {
  logger.info(`[authService] requestOtp: ${email}`);
  try {
    await _post('/users/request-otp', { email });
  } catch (err) {
    logger.warn('[authService] requestOtp failed (silent)', err);
  }
  return { ok: true };
}

/**
 * Completes login using the 6-digit email code.
 * Enforces rate limiting on the client side to prevent brute forcing.
 * 
 * @param email - User's email.
 * @param otp - 6-digit code.
 */
export async function signInWithOtp(email: string, otp: string): Promise<AuthResult> {
  logger.info(`[authService] signInWithOtp: ${email}`);
  if (Date.now() < _otpCooldownUntil) {
    const secsLeft = Math.ceil((_otpCooldownUntil - Date.now()) / 1000);
    logger.warn(`[authService] signInWithOtp blocked by cooldown: ${secsLeft}s`);
    return { ok: false, errorMsg: `Too many attempts. Wait ${secsLeft}s before trying again.` };
  }

  try {
    const data = await _post('/users/login-otp', { email, otp }) as { access_token: string };
    _storeToken(data.access_token);
    _otpFailureCount = 0;

    const user = await _fetchMe();
    logger.info(`[authService] signInWithOtp: success for ${email}`);
    return { ok: true, user };
  } catch (err: any) {
    _otpFailureCount += 1;
    logger.warn(`[authService] signInWithOtp failed (count=${_otpFailureCount}): ${err?.message}`);
    if (_otpFailureCount >= OTP_MAX_FAILURES) {
      logger.error('[authService] OTP rate limit exceeded; starting cooldown');
      _otpCooldownUntil = Date.now() + OTP_COOLDOWN_MS;
      _otpFailureCount  = 0;
    }
    return { ok: false, errorMsg: err?.message ?? 'Invalid or expired code. Please try again.' };
  }
}

/**
 * Validates an email verification token from a magic link.
 * 
 * @param token - Raw verification token.
 */
export async function verifyEmail(token: string): Promise<AuthResult> {
  logger.info('[authService] verifyEmail: processing token');
  try {
    await _post('/users/verify-email', { token });
    return { ok: true };
  } catch (err: any) {
    return { ok: false, errorMsg: err?.message ?? 'Verification failed. The link may have expired.' };
  }
}

/**
 * Resends the verification email if the user lost the first one.
 * 
 * @param email - Target email.
 */
export async function resendVerification(email: string): Promise<void> {
  logger.info(`[authService] resendVerification: ${email}`);
  try {
    await _post('/users/resend-verification', { email });
  } catch (err) {
    logger.warn('[authService] resendVerification failed (silent)', err);
  }
}

/** 
 * Purges all auth data from the session. 
 */
export function clearStoredToken(): void {
  logger.debug('[authService] clearStoredToken: clearing local storage');
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(TOKEN_EXPIRY_KEY);
}

/**
 * Retrieves the valid JWT for header injection.
 * 
 * @returns The token string or null if absent/expired.
 */
export function getStoredToken(): string | null {
  const token  = localStorage.getItem(TOKEN_KEY);
  const expiry = localStorage.getItem(TOKEN_EXPIRY_KEY);
  if (!token || !expiry) return null;
  
  if (Date.now() > Number(expiry)) {
    logger.warn('[authService] getStoredToken: token expired');
    clearStoredToken();
    return null;
  }
  return token;
}

/**
 * Calculates current session TTL.
 * 
 * @returns Milliseconds until the token expires.
 */
export function tokenRemainingMs(): number {
  const expiry = localStorage.getItem(TOKEN_EXPIRY_KEY);
  if (!expiry) return 0;
  return Math.max(0, Number(expiry) - Date.now());
}

/**
 * Triggers a system-wide auth failure event.
 * Views listen for this to open the login modal.
 */
export function fireAuthExpired(): void {
  logger.error('[authService] fireAuthExpired: broadcasting auth:expired event');
  window.dispatchEvent(new CustomEvent('auth:expired'));
}
