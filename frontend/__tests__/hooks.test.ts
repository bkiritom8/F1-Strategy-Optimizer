/**
 * @file __tests__/hooks.test.ts
 * @description Unit tests for hooks/useApi.ts — the API data-fetching hook layer.
 *
 * Tests the named hooks exported from useApi.ts (useDrivers, useRaceState,
 * useModelStatus, useBackendStatus) which all wrap a shared internal generic
 * hook. Each test mocks the underlying apiFetch and verifies loading state,
 * data shape, and error handling / fallback behaviour.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

// Control API_BASE to prevent relative URL errors in tests
vi.mock('../services/client', () => ({
  apiFetch: vi.fn(),
  getToken: vi.fn().mockResolvedValue('test-token'),
  API_BASE: 'https://f1-strategy-api-dev-694267183904.us-central1.run.app',
}));

vi.mock('../services/logger', () => ({
  logger: {
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    debug: vi.fn(),
    api: vi.fn(),
  },
}));

// Mock AbortSignal.timeout if it doesn't exist in the test env
if (typeof AbortSignal.timeout !== 'function') {
  (AbortSignal as any).timeout = (ms: number) => {
    const controller = new AbortController();
    setTimeout(() => controller.abort(), ms);
    return controller.signal;
  };
}

import { apiFetch } from '../services/client';
const mockApiFetch = apiFetch as ReturnType<typeof vi.fn>;

// ─── useDrivers ───────────────────────────────────────────────────────────────

describe('useDrivers', () => {
  beforeEach(() => {
    vi.resetModules();
    mockApiFetch.mockReset();
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('no network'));
  });

  it('returns an object with data, loading, error, and refetch', async () => {
    mockApiFetch.mockResolvedValueOnce([]);
    const { useDrivers } = await import('../hooks/useApi');
    const { result } = renderHook(() => useDrivers());

    expect(result.current).toHaveProperty('loading');
    expect(result.current).toHaveProperty('data');
    expect(result.current).toHaveProperty('error');
    expect(result.current).toHaveProperty('refetch');
    expect(typeof result.current.refetch).toBe('function');
    
    // Ensure we wait for the initial fetch to complete to avoid act() warnings
    await waitFor(() => expect(result.current.loading).toBe(false));
  });

  it('resolves with an error when API and static fetch both fail', async () => {
    mockApiFetch.mockRejectedValueOnce(new Error('backend down'));
    globalThis.fetch = vi.fn().mockResolvedValueOnce({ ok: false });
    
    const { useDrivers } = await import('../hooks/useApi');
    const { result } = renderHook(() => useDrivers());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeDefined();
  });
});

// ─── useModelStatus ───────────────────────────────────────────────────────────

describe('useModelStatus', () => {
  beforeEach(() => {
    vi.resetModules();
    mockApiFetch.mockReset();
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false });
  });

  it('returns loading=true initially', async () => {
    // Hang the fetch promise so it stays in loading state
    mockApiFetch.mockReturnValueOnce(new Promise(() => {}));
    const { useModelStatus } = await import('../hooks/useApi');
    const { result } = renderHook(() => useModelStatus());
    expect(result.current.loading).toBe(true);
  });

  it('returns data on successful API call', async () => {
    const mock = {
      models: [{ name: 'strategy', version: '1.0', status: 'ok', accuracy: 0.95, last_updated: '2024-01-01' }],
    };
    mockApiFetch.mockResolvedValueOnce(mock);
    const { useModelStatus } = await import('../hooks/useApi');
    const { result } = renderHook(() => useModelStatus());

    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 2000 });
    expect(result.current.data).not.toBeNull();
  });
});

// ─── useBackendStatus ─────────────────────────────────────────────────────────

describe('useBackendStatus', () => {
  beforeEach(() => {
    vi.resetModules();
    mockApiFetch.mockReset();
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false });
  });

  it('returns online=true on success', async () => {
    // Mock for initial useEffect check
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ status: 'ok' }),
    });
    
    // We already mocked API_BASE at the top level, 
    // but we re-import to ensure we have the latest version of the hook
    const { useBackendStatus } = await import('../hooks/useApi');
    const { result } = renderHook(() => useBackendStatus());

    // Wait for the online state to flip to true
    await waitFor(() => {
      expect(result.current.online).toBe(true);
    }, { timeout: 3000 });
  });

  it('returns isOnline=false when backend is down', async () => {
    mockApiFetch.mockRejectedValueOnce(new Error('timeout'));
    const { useBackendStatus } = await import('../hooks/useApi');
    const { result } = renderHook(() => useBackendStatus());

    await waitFor(() => expect(result.current.online).toBe(false));
  });
});

// ─── useRaceState ─────────────────────────────────────────────────────────────

describe('useRaceState', () => {
  beforeEach(() => {
    vi.resetModules();
    mockApiFetch.mockReset();
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false });
  });

  it('resolves with data and handles error when API fails', async () => {
    mockApiFetch.mockRejectedValueOnce(new Error('backend down'));
    const { useRaceState } = await import('../hooks/useApi');
    const { result } = renderHook(() => useRaceState('2024_1', 23));

    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 2000 });
    expect(result.current.data).toBeDefined();
    expect(result.current.error).not.toBeNull();
  });
});
