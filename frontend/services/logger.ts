/**
 * @file services/logger.ts
 * @description Lightweight structured logger for Apex Intelligence.
 *
 * Behaviour:
 *  - In DEVELOPMENT (`import.meta.env.DEV`):  all levels are printed with
 *    styled console output and a timestamp prefix.
 *  - In PRODUCTION:  only `logger.error` and `logger.warn` are emitted so
 *    the browser console stays clean for end-users.
 *
 * Usage:
 *   import { logger } from './logger';
 *   logger.api('GET', '/api/v1/drivers', 200);
 *   logger.warn('[useApi] Falling back to mock data', err.message);
 *   logger.error('[auth] Token refresh failed', err);
 */

/** Available log levels in priority order. */
type LogLevel = 'debug' | 'info' | 'warn' | 'error' | 'api';

const IS_DEV = import.meta.env.DEV;

/** Colour codes for styled console output (dev only). */
const STYLES: Record<LogLevel, string> = {
  debug: 'color:#888;font-weight:normal',
  info:  'color:#60A5FA;font-weight:bold',
  warn:  'color:#FBBF24;font-weight:bold',
  error: 'color:#F87171;font-weight:bold',
  api:   'color:#34D399;font-weight:bold',
};

/**
 * Returns an ISO-8601 timestamp string truncated to milliseconds.
 * Used as a prefix for every log line in development.
 */
function ts(): string {
  return new Date().toISOString().replace('T', ' ').slice(0, 23);
}

/**
 * Core log emitter.
 *
 * @param level  - Severity level.
 * @param args   - Arbitrary values forwarded to the underlying console method.
 */
function emit(level: LogLevel, ...args: unknown[]): void {
  if (!IS_DEV && level !== 'error' && level !== 'warn') return;

  const prefix = `%c[Apex ${level.toUpperCase()}] ${ts()}`;
  const style  = STYLES[level];

  switch (level) {
    case 'error':
      console.error(prefix, style, ...args);
      break;
    case 'warn':
      console.warn(prefix, style, ...args);
      break;
    default:
      console.log(prefix, style, ...args);
  }
}

/**
 * The global logger instance.
 *
 * Methods:
 *  - `debug`  — low-noise trace messages (dev only)
 *  - `info`   — normal operational messages (dev only)
 *  - `warn`   — recoverable issues / fallbacks (dev + prod)
 *  - `error`  — fatal / unexpected errors (dev + prod)
 *  - `api`    — HTTP request lifecycle events (dev only)
 */
export const logger = {
  /** Low-noise trace — only visible in development. */
  debug: (...args: unknown[]) => emit('debug', ...args),

  /** General informational message — only visible in development. */
  info: (...args: unknown[]) => emit('info', ...args),

  /** Recoverable condition (e.g. fallback activated) — visible in all envs. */
  warn: (...args: unknown[]) => emit('warn', ...args),

  /** Unexpected / fatal error — visible in all envs. */
  error: (...args: unknown[]) => emit('error', ...args),

  /**
   * HTTP request/response trace.
   *
   * @param method  - HTTP verb, e.g. 'GET'.
   * @param path    - Relative API path, e.g. '/api/v1/drivers'.
   * @param status  - HTTP status code or descriptive string.
   * @param ms      - Optional elapsed time in milliseconds.
   */
  api: (method: string, path: string, status: number | string, ms?: number) =>
    emit('api', `${method} ${path} → ${status}${ms !== undefined ? ` (${ms}ms)` : ''}`),
};
