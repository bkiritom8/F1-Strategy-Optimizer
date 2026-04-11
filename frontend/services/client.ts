/**
 * @file services/client.ts
 * @description Standardized HTTP client for the F1 Strategy backend.
 *
 * This client provides a unified wrapper around `fetch` for all backend
 * communications. It handles base URL resolution, JSON parsing, and 
 * consistent error reporting.
 *
 * Authentication:
 * - CORE platform features (Race Command, Strategy Hub) are public.
 * - Admin features are gated by the Admin Control password.
 */

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
  /** Skip the auth header injection (legacy support). */
  skipAuth?: boolean;
}

/**
 * Robust fetch wrapper. Handles base URL resolution and JSON parsing.
 * Authentication is now optional and managed via the Admin Control.
 *
 * @param path   - API path, relative to API_BASE (e.g. '/strategy/predict')
 * @param options - Standard fetch options
 * @returns Parsed JSON response
 * @throws  On non-OK HTTP response
 */
export async function apiFetch<T = unknown>(
  path:     string,
  options?: FetchOptions,
): Promise<T> {
  const { ...fetchOptions } = options ?? {};
  const method = fetchOptions.method ?? 'GET';

  logger.debug(`[apiFetch] ${method} ${path}`);

  const headers = new Headers(fetchOptions.headers);
  headers.set('Content-Type', headers.get('Content-Type') ?? 'application/json');

  // Optional: Inject legacy token if still present in storage for backend compatibility
  const legacyToken = sessionStorage.getItem('f1_api_token');
  if (legacyToken) {
    headers.set('Authorization', `Bearer ${legacyToken}`);
  }

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...fetchOptions,
      headers,
    });

    logger.debug(`[apiFetch] Response ${res.status} for ${path}`);

    if (!res.ok) {
      // 401/403 are no longer intercepted for redirection
      let detail = `API error: ${res.status}`;
      try {
        const json = await res.json();
        if (typeof json?.detail === 'string') detail = json.detail;
      } catch { /* non-JSON body */ }
      
      logger.warn(`[apiFetch] API error: ${detail}`);
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
