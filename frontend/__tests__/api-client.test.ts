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

  it('should cache token in sessionStorage after authentication', async () => {
    const mockResponse = { access_token: 'test-jwt-token', token_type: 'bearer' };

    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockResponse),
    });

    const { getToken } = await import('../services/client');
    const token = await getToken();

    expect(token).toBe('test-jwt-token');
    expect(sessionStorage.getItem('f1_api_token')).toBe('test-jwt-token');
  });

  it('should return cached token on subsequent calls', async () => {
    sessionStorage.setItem('f1_api_token', 'cached-token');
    sessionStorage.setItem('f1_api_token_expiry', String(Date.now() + 60_000));

    // Re-import to get fresh module
    vi.resetModules();
    const { getToken } = await import('../services/client');
    const token = await getToken();

    expect(token).toBe('cached-token');
  });

  it('should re-authenticate when token is expired', async () => {
    sessionStorage.setItem('f1_api_token', 'expired-token');
    sessionStorage.setItem('f1_api_token_expiry', String(Date.now() - 1000));

    const mockResponse = { access_token: 'fresh-token', token_type: 'bearer' };
    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockResponse),
    });

    vi.resetModules();
    const { getToken } = await import('../services/client');
    const token = await getToken();

    expect(token).toBe('fresh-token');
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
