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
import { logger } from './logger';

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
  '';

// ─── Core fetch wrapper ───────────────────────────────────────────────────────

/**
 * Extended fetch options for the F1 Strategy client.
 */
interface FetchOptions extends RequestInit {
  /** Skip the auth header injection (used for public endpoints like /health). */
  skipAuth?: boolean;
}

/**
 * Authenticated fetch wrapper. Automatically injects Bearer token and
 * handles 401/403 session expiration by firing global events.
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
  const method = fetchOptions.method ?? 'GET';

  logger.debug(`[apiFetch] ${method} ${path} (skipAuth=${skipAuth})`);

  const headers = new Headers(fetchOptions.headers);
  headers.set('Content-Type', headers.get('Content-Type') ?? 'application/json');

  if (!skipAuth) {
    const token = getStoredToken();
    if (!token) {
      logger.warn(`[apiFetch] Missing token for protected route: ${path}`);
      fireAuthExpired();
      throw new Error('Not authenticated. Please sign in.');
    }
    headers.set('Authorization', `Bearer ${token}`);
  }

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...fetchOptions,
      headers,
    });

    logger.debug(`[apiFetch] Response ${res.status} for ${path}`);

    if (res.status === 401 || res.status === 403) {
      logger.error(`[apiFetch] Auth failure (${res.status}) on ${path}`);
      fireAuthExpired();
      throw new Error('Session expired. Please sign in again.');
    }

    if (!res.ok) {
      let detail = `API error: ${res.status}`;
      try {
        const json = await res.json();
        if (typeof json?.detail === 'string') detail = json.detail;
      } catch { /* non-JSON body */ }
      
      logger.warn(`[apiFetch] API logical error: ${detail}`);
      throw new Error(detail);
    }

    // Handle 204 No Content
    if (res.status === 204) {
      logger.debug(`[apiFetch] 204 No Content for ${path}`);
      return undefined as T;
    }

    return res.json() as Promise<T>;
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') {
      logger.debug(`[apiFetch] Request aborted: ${path}`);
    } else {
      logger.error(`[apiFetch] Network/Request error on ${path}:`, err);
    }
    throw err;
  }
}

/**
 * Convenience: POST JSON body, expecting a JSON response.
 * 
 * @param path - API path.
 * @param body - JSON-serializable object.
 * @param options - Fetch options.
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
 * 
 * @param path - API path.
 * @param options - Fetch options.
 */
export function apiGet<T = unknown>(
  path:     string,
  options?: FetchOptions,
): Promise<T> {
  return apiFetch<T>(path, { ...options, method: 'GET' });
}

/**
 * Probes the backend health endpoint (public).
 * 
 * @returns true if the backend is reachable and healthy.
 */
export async function checkHealth(): Promise<boolean> {
  logger.debug('[client] checkHealth: probing backend /health');
  try {
    const res = await fetch(`${API_BASE}/health`, { method: 'GET' });
    return res.ok;
  } catch (err) {
    logger.warn('[client] checkHealth: backend unreachable', err);
    return false;
  }
}
