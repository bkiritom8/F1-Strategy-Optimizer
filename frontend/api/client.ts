/**
 * @file api/client.ts
 * @description Authenticated HTTP client for the F1 Strategy Optimizer FastAPI backend.
 * Handles JWT token lifecycle (auto-login, refresh, caching) so that
 * every downstream fetch is pre-authorized.
 *
 * The Vite dev server proxies /api requests to http://localhost:8000.
 */

const TOKEN_KEY = 'f1_api_token';
const TOKEN_EXPIRY_KEY = 'f1_api_token_expiry';

// Default credentials for the IAM simulator (local dev)
const DEFAULT_USER = 'admin';
const DEFAULT_PASS = 'admin';

/** Base URL is empty because Vite proxies /api to the backend */
export const API_BASE = '';

interface TokenResponse {
  access_token: string;
  token_type: string;
}

/**
 * Authenticate against POST /token and cache the JWT.
 */
async function authenticate(
  username: string = DEFAULT_USER,
  password: string = DEFAULT_PASS
): Promise<string> {
  const form = new URLSearchParams();
  form.append('username', username);
  form.append('password', password);

  const res = await fetch(`${API_BASE}/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: form,
  });

  if (!res.ok) {
    throw new Error(`Authentication failed: ${res.status} ${res.statusText}`);
  }

  const data: TokenResponse = await res.json();
  const token = data.access_token;

  // Cache token with 25 min expiry (token lasts 30 min, we refresh early)
  sessionStorage.setItem(TOKEN_KEY, token);
  sessionStorage.setItem(
    TOKEN_EXPIRY_KEY,
    String(Date.now() + 25 * 60 * 1000)
  );

  return token;
}

/**
 * Return a valid JWT, re-authenticating if the cached one is expired or missing.
 */
export async function getToken(): Promise<string> {
  const cached = sessionStorage.getItem(TOKEN_KEY);
  const expiry = sessionStorage.getItem(TOKEN_EXPIRY_KEY);

  if (cached && expiry && Date.now() < Number(expiry)) {
    return cached;
  }

  return authenticate();
}

/**
 * Wrapper around fetch that injects the Authorization header automatically.
 * Returns parsed JSON on success, throws on HTTP errors.
 */
export async function apiFetch<T = any>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = await getToken();

  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  };

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    // Token may have been revoked; force re-auth and retry once
    sessionStorage.removeItem(TOKEN_KEY);
    const freshToken = await getToken();
    const retry = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: { ...headers, Authorization: `Bearer ${freshToken}` },
    });
    if (!retry.ok) throw new Error(`API ${path}: ${retry.status}`);
    return retry.json();
  }

  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`API ${path}: ${res.status} ${body}`);
  }

  return res.json();
}
