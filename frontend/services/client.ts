/**
 * @file services/client.ts
 * @description Authenticated HTTP client for the F1 Strategy backend.
 *
 * Every API request passes through `apiFetch`.  It:
 *  1. Injects `Authorization: Bearer <user JWT>` from sessionStorage.
 *  2. If no token is present or it's expired → fires `auth:expired` event
 *     so the login modal appears, then throws (request is not sent).
 *  3. On 401/403 response → same `auth:expired` event + throws.
 *
 * No service-account credentials are stored here.  Users must sign in via
 * the LoginModal → authService → JWT stored in sessionStorage.
 */

import { getStoredToken, fireAuthExpired } from './authService';

// ─── API base URL ─────────────────────────────────────────────────────────────

/**
 * Resolves the backend base URL:
 *  1. VITE_CLOUD_RUN_URL (set in .env.local for local→Cloud Run testing)
 *  2. VITE_API_URL (legacy env var)
 *  3. Falls back to the Vite proxy path (/api) for local dev via vite.config.ts
 */
export const API_BASE: string =
  (import.meta.env.VITE_CLOUD_RUN_URL as string) ||
  (import.meta.env.VITE_API_URL      as string) ||
  '/api';

// ─── Core fetch wrapper ───────────────────────────────────────────────────────

interface FetchOptions extends RequestInit {
  /** Skip the auth header injection (used for public endpoints like /health). */
  skipAuth?: boolean;
}

/**
 * Authenticated fetch wrapper.
 *
 * @param path   - API path, relative to API_BASE (e.g. '/strategy/predict')
 * @param options - Standard fetch options + optional `skipAuth` flag
 * @returns Parsed JSON response
 * @throws  On missing token, expired token, or non-OK HTTP response
 */
export async function apiFetch<T = unknown>(
  path:     string,
  options?: FetchOptions,
): Promise<T> {
  const { skipAuth = false, ...fetchOptions } = options ?? {};

  const headers = new Headers(fetchOptions.headers);
  headers.set('Content-Type', headers.get('Content-Type') ?? 'application/json');

  if (!skipAuth) {
    const token = getStoredToken();
    if (!token) {
      fireAuthExpired();
      throw new Error('Not authenticated. Please sign in.');
    }
    headers.set('Authorization', `Bearer ${token}`);
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...fetchOptions,
    headers,
  });

  if (res.status === 401 || res.status === 403) {
    fireAuthExpired();
    throw new Error('Session expired. Please sign in again.');
  }

  if (!res.ok) {
    let detail = `API error: ${res.status}`;
    try {
      const json = await res.json();
      if (typeof json?.detail === 'string') detail = json.detail;
    } catch { /* non-JSON body */ }
    throw new Error(detail);
  }

  // Handle 204 No Content
  if (res.status === 204) return undefined as T;

  return res.json() as Promise<T>;
}

/**
 * Convenience: POST JSON body, expecting a JSON response.
 */
export function apiPost<T = unknown>(
  path: string,
  body: unknown,
  options?: FetchOptions,
): Promise<T> {
  return apiFetch<T>(path, {
    ...options,
    method: 'POST',
    body:   JSON.stringify(body),
  });
}

/**
 * Convenience: GET, expecting a JSON response.
 */
export function apiGet<T = unknown>(
  path:     string,
  options?: FetchOptions,
): Promise<T> {
  return apiFetch<T>(path, { ...options, method: 'GET' });
}

// ─── Health check (public, no auth) ──────────────────────────────────────────

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/health`, { method: 'GET' });
    return res.ok;
  } catch {
    return false;
  }
}
