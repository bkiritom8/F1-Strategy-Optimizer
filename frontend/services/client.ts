/**
 * @file services/client.ts
 * @description Authenticated HTTP client for the F1 Strategy Optimizer FastAPI backend.
 *
 * API base URL resolution (in priority order):
 *   1. Production build           → CLOUD_RUN_URL (hardcoded Cloud Run endpoint)
 *   2. Dev + VITE_API_URL env var → that URL (allows targeting Cloud Run from dev)
 *   3. Dev without VITE_API_URL   → '' (Vite reverse-proxy to localhost:8000)
 *
 * Auth flow:
 *   - Auto-authenticates with admin credentials on first request.
 *   - Caches the JWT token in sessionStorage for 25 minutes.
 *   - Retries once on 401 by refreshing the token.
 *   - Circuit breaker: after an auth failure, suppresses retries for 15 seconds
 *     to prevent request floods when the backend is offline.
 */

import { logger } from './logger';

// ─── Configuration constants ─────────────────────────────────────────────────

const TOKEN_KEY        = 'f1_api_token';
const TOKEN_EXPIRY_KEY = 'f1_api_token_expiry';
const DEFAULT_USER     = 'admin';
const DEFAULT_PASS     = 'admin';
const CLOUD_RUN_URL    = 'https://f1-strategy-api-dev-694267183904.us-central1.run.app';

// ─── Circuit breaker state ───────────────────────────────────────────────────

/** Timestamp (ms) of the last auth failure. 0 = no failure recorded. */
let authFailedAt      = 0;
/** Minimum time (ms) to wait before retrying authentication after a failure. */
const AUTH_COOLDOWN_MS = 15_000;

// ─── Public API base URL ─────────────────────────────────────────────────────

/**
 * Resolved base URL for all API requests.
 * `import.meta.env.PROD` is replaced at build time by Vite.
 */
export const API_BASE: string = import.meta.env.PROD
  ? CLOUD_RUN_URL
  : (import.meta.env.VITE_API_URL || '');

logger.info(`[client] API_BASE resolved to: "${API_BASE || '(Vite proxy → localhost:8000)'}"`);

// ─── Types ───────────────────────────────────────────────────────────────────

/** Shape of a successful OAuth2 password-grant response. */
interface TokenResponse {
  access_token: string;
  token_type:   string;
}

// ─── Auth helpers ────────────────────────────────────────────────────────────

/**
 * Authenticates against the backend `/token` endpoint using username/password
 * credentials (OAuth2 password grant).
 *
 * Stores the resulting JWT in sessionStorage alongside its expiry timestamp.
 * Activates the circuit breaker on failure so subsequent calls fail fast.
 *
 * @param username - Backend username (default: 'admin').
 * @param password - Backend password (default: 'admin').
 * @returns The raw JWT access token string.
 * @throws {Error} If the circuit breaker is active or the request fails.
 */
async function authenticate(
  username: string = DEFAULT_USER,
  password: string = DEFAULT_PASS,
): Promise<string> {
  if (Date.now() - authFailedAt < AUTH_COOLDOWN_MS) {
    const remainingMs = AUTH_COOLDOWN_MS - (Date.now() - authFailedAt);
    logger.warn(`[client] Auth cooldown active — ${Math.ceil(remainingMs / 1000)}s remaining`);
    throw new Error('Backend offline (auth cooldown active)');
  }

  logger.info('[client] Authenticating with backend…');
  const form = new URLSearchParams();
  form.append('username', username);
  form.append('password', password);

  try {
    const res = await fetch(`${API_BASE}/token`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body:    form,
    });
    logger.api('POST', '/token', res.status);

    if (!res.ok) {
      authFailedAt = Date.now();
      const msg = `Authentication failed: ${res.status} ${res.statusText}`;
      logger.error(`[client] ${msg}`);
      throw new Error(msg);
    }

    const data: TokenResponse = await res.json();
    const token = data.access_token;

    sessionStorage.setItem(TOKEN_KEY,        token);
    sessionStorage.setItem(TOKEN_EXPIRY_KEY, String(Date.now() + 25 * 60 * 1000));
    authFailedAt = 0;

    logger.info('[client] Auth successful — token cached for 25 min');
    return token;
  } catch (err) {
    authFailedAt = Date.now();
    throw err;
  }
}

/**
 * Returns a valid JWT, either from the sessionStorage cache or by triggering
 * a fresh authentication flow.
 *
 * @returns The JWT access token string.
 */
export async function getToken(): Promise<string> {
  const cached = sessionStorage.getItem(TOKEN_KEY);
  const expiry  = sessionStorage.getItem(TOKEN_EXPIRY_KEY);

  if (cached && expiry && Date.now() < Number(expiry)) {
    logger.debug('[client] Using cached token');
    return cached;
  }

  logger.info('[client] Token missing or expired — re-authenticating');
  return authenticate();
}

// ─── Fetch wrapper ───────────────────────────────────────────────────────────

/**
 * Authenticated fetch wrapper for all backend API calls.
 *
 * Injects the Bearer token into every request. On a 401 response it
 * invalidates the cached token and retries once with a fresh one.
 *
 * @template T    - Expected response body type.
 * @param path    - API path relative to API_BASE (e.g. '/api/v1/drivers').
 * @param options - Standard `RequestInit` options (method, body, headers…).
 * @returns Parsed JSON response typed as T.
 * @throws {Error} On non-OK status codes after the optional 401 retry.
 */
export async function apiFetch<T = any>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const start = performance.now();
  const token = await getToken();

  const headers: Record<string, string> = {
    Authorization:  `Bearer ${token}`,
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  };

  const method = (options.method || 'GET').toUpperCase();
  logger.api(method, path, '→ pending');

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  const ms  = Math.round(performance.now() - start);
  logger.api(method, path, res.status, ms);

  if (res.status === 401) {
    logger.warn(`[client] 401 on ${path} — refreshing token and retrying`);
    sessionStorage.removeItem(TOKEN_KEY);
    const freshToken = await getToken();
    const retry = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: { ...headers, Authorization: `Bearer ${freshToken}` },
    });
    logger.api(method, `${path} (retry)`, retry.status);
    if (!retry.ok) {
      const errMsg = `API ${path}: ${retry.status} (after token refresh)`;
      logger.error(`[client] ${errMsg}`);
      throw new Error(errMsg);
    }
    return retry.json();
  }

  if (!res.ok) {
    const body   = await res.text().catch(() => '');
    const errMsg = `API ${path}: ${res.status} ${body}`;
    logger.error(`[client] ${errMsg}`);
    throw new Error(errMsg);
  }

  return res.json();
}
