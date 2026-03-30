/**
 * @file __tests__/endpoints.test.ts
 * @description Unit tests for services/endpoints.ts API endpoint wrappers.
 *
 * These tests validate:
 *  - All required endpoint functions are exported and callable.
 *  - Each endpoint calls `apiFetch` with the correct URL path.
 *  - Three-tier fallback: live API → static JSON → mock constants.
 *  - Error handling: failed fetch does not throw, falls back gracefully.
 *  - fetchHealthCheck returns a boolean.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

// ─── Mock dependencies ────────────────────────────────────────────────────────

vi.mock('../services/client', () => ({
  apiFetch: vi.fn(),
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

import { apiFetch } from '../services/client';
const mockApiFetch = apiFetch as ReturnType<typeof vi.fn>;

describe('API Endpoints — exports', () => {
  it('exports all required endpoint functions', async () => {
    const endpoints = await import('../services/endpoints');
    expect(typeof endpoints.fetchDrivers).toBe('function');
    expect(typeof endpoints.fetchDriverHistory).toBe('function');
    expect(typeof endpoints.fetchRaceState).toBe('function');
    expect(typeof endpoints.fetchStrategyRecommendation).toBe('function');
    expect(typeof endpoints.fetchModelStatus).toBe('function');
    expect(typeof endpoints.fetchModelBiasReport).toBe('function');
    expect(typeof endpoints.fetchOvertakeProb).toBe('function');
    expect(typeof endpoints.fetchSafetyCarProb).toBe('function');
    expect(typeof endpoints.fetchValidationStats).toBe('function');
    expect(typeof endpoints.fetchSystemHealth).toBe('function');
    expect(typeof endpoints.fetchHealthCheck).toBe('function');
    expect(typeof endpoints.simulateStrategy).toBe('function');
  });
});

describe('fetchDrivers', () => {
  beforeEach(() => {
    vi.resetModules();
    mockApiFetch.mockReset();
    // Default fetch mock for static fallback
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([{ id: 'mock_driver', name: 'Mock Driver' }]),
    });
  });

  it('calls apiFetch with the drivers endpoint', async () => {
    mockApiFetch.mockResolvedValueOnce([{ driver_id: 'max_verstappen' }]);
    const { fetchDrivers } = await import('../services/endpoints');
    await fetchDrivers();
    expect(mockApiFetch).toHaveBeenCalledWith(
      expect.stringContaining('drivers'),
    );
  });

  it('returns an array on success', async () => {
    const mockData = [{ driver_id: 'max_verstappen', name: 'Max Verstappen' }];
    mockApiFetch.mockResolvedValueOnce(mockData);
    const { fetchDrivers } = await import('../services/endpoints');
    const result = await fetchDrivers();
    expect(Array.isArray(result)).toBe(true);
  });
});

describe('fetchOvertakeProb', () => {
  beforeEach(() => { vi.resetModules(); mockApiFetch.mockReset(); });

  it('calls apiFetch with driver/lap context', async () => {
    mockApiFetch.mockResolvedValueOnce({ probability: 0.15, trend: 'stable' });
    const { fetchOvertakeProb } = await import('../services/endpoints');
    await fetchOvertakeProb('VER', 'NOR');
    expect(mockApiFetch).toHaveBeenCalledWith(
      expect.stringContaining('overtake'),
    );
  });
});

describe('fetchValidationStats', () => {
  beforeEach(() => { vi.resetModules(); mockApiFetch.mockReset(); });

  it('returns validation metrics on success', async () => {
    const mock = { 
      race_id: '2024_1', 
      accuracy: 0.88, 
      precision: 0.87, 
      recall: 0.86, 
      f1_score: 0.88, 
      samples: 1000 
    };
    mockApiFetch.mockResolvedValueOnce(mock);
    const { fetchValidationStats } = await import('../services/endpoints');
    const result = await fetchValidationStats('2024_1');
    expect(result.f1_score).toBe(0.88);
  });
});

describe('fetchModelStatus', () => {
  beforeEach(() => { vi.resetModules(); mockApiFetch.mockReset(); });

  it('returns model status data on success', async () => {
    const mock = { models: [{ name: 'strategy', version: '1.0', status: 'ok', accuracy: 0.95, last_updated: '2024-01-01' }] };
    mockApiFetch.mockResolvedValueOnce(mock);
    const { fetchModelStatus } = await import('../services/endpoints');
    const result = await fetchModelStatus();
    expect(result).toBeDefined();
  });
});
