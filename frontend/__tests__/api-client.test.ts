/**
 * @file __tests__/api-client.test.ts
 * @description Unit tests for the API client layer.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

describe('API Client', () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it('should include Authorization header when token is in sessionStorage', async () => {
    sessionStorage.setItem('f1_api_token', 'test-jwt');
    sessionStorage.setItem('f1_api_token_expiry', String(Date.now() + 60000));
    
    let capturedHeaders: Headers | undefined;
    globalThis.fetch = vi.fn().mockImplementationOnce(async (url, options) => {
      capturedHeaders = options.headers;
      return { ok: true, json: () => Promise.resolve({ success: true }) };
    });

    const { apiFetch } = await import('../services/client');
    await apiFetch('/test-endpoint');

    expect(globalThis.fetch).toHaveBeenCalled();
    expect(capturedHeaders?.get('Authorization')).toBe('Bearer test-jwt');
  });

  it('should dispatch auth:expired event on 401 response', async () => {
    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: false,
      status: 401,
      text: () => Promise.resolve('Unauthorized'),
    });

    const dispatchEventSpy = vi.spyOn(window, 'dispatchEvent');
    const { apiFetch } = await import('../services/client');

    try {
      await apiFetch('/protected');
    } catch (e) {
      // Expected to throw
    }

    expect(dispatchEventSpy).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'auth:expired' })
    );
  });
});

describe('API Endpoints', () => {
  it('should export all required endpoint functions', async () => {
    const endpoints = await import('../services/endpoints');

    expect(typeof endpoints.fetchDrivers).toBe('function');
    expect(typeof endpoints.fetchDriverHistory).toBe('function');
    expect(typeof endpoints.fetchRaceState).toBe('function');
    expect(typeof endpoints.fetchStrategyRecommendation).toBe('function');
    expect(typeof endpoints.fetchModelStatus).toBe('function');
    expect(typeof endpoints.fetchSystemHealth).toBe('function');
    expect(typeof endpoints.fetchHealthCheck).toBe('function');
    expect(typeof endpoints.simulateStrategy).toBe('function');
  });
});
