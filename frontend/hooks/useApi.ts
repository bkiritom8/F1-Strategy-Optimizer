/**
 * @file hooks/useApi.ts
 * @description React hooks that fetch data from the F1 backend API.
 * Each hook returns { data, loading, error } and falls back to mock
 * data when the backend is unreachable, so the UI always renders.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  fetchDrivers,
  fetchDriverHistory,
  fetchRaceState,
  fetchRaceStandings,
  fetchLapTelemetry,
  fetchStrategyRecommendation,
  fetchModelStatus,
  fetchSystemHealth,
  fetchHealthCheck,
} from '../api/endpoints';
import type { DriverProfile, RaceState, StrategyRecommendation } from '../types';
import {
  MOCK_DRIVERS,
  MOCK_RACE_STATE,
  getMockTelemetry,
  getMockStrategy,
} from '../constants';

// ─── Generic async hook ─────────────────────────────────────────────────────

interface UseApiResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
  isLive: boolean; // true if data came from the real API
}

function useApiCall<T>(
  fetcher: () => Promise<T>,
  fallback: T | null = null,
  deps: any[] = []
): UseApiResult<T> {
  const [data, setData] = useState<T | null>(fallback);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isLive, setIsLive] = useState(false);
  const mountedRef = useRef(true);

  const execute = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetcher();
      if (mountedRef.current) {
        setData(result);
        setIsLive(true);
      }
    } catch (err: any) {
      if (mountedRef.current) {
        const msg = err?.message || 'API call failed';
        setError(msg);
        setIsLive(false);
        // Keep fallback data if available
        if (fallback && !data) {
          setData(fallback);
        }
        console.warn(`[useApi] Falling back to mock data: ${msg}`);
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, deps);

  useEffect(() => {
    mountedRef.current = true;
    execute();
    return () => { mountedRef.current = false; };
  }, [execute]);

  return { data, loading, error, refetch: execute, isLive };
}

// ─── Specific hooks ─────────────────────────────────────────────────────────

/**
 * Fetch all driver profiles from the backend.
 * Falls back to MOCK_DRIVERS if the backend is down.
 */
export function useDrivers(): UseApiResult<DriverProfile[]> {
  return useApiCall<DriverProfile[]>(
    () => fetchDrivers(),
    MOCK_DRIVERS
  );
}

/**
 * Fetch career history for a single driver.
 */
export function useDriverHistory(driverId: string) {
  return useApiCall(
    () => fetchDriverHistory(driverId),
    null,
    [driverId]
  );
}

/**
 * Fetch race state at a given lap.
 * Falls back to MOCK_RACE_STATE.
 */
export function useRaceState(raceId: string, lap: number) {
  return useApiCall(
    () => fetchRaceState(raceId, lap),
    {
      raceState: MOCK_RACE_STATE,
      driverStates: MOCK_DRIVERS.map((d, i) => ({
        driver_id: d.driver_id,
        position: i + 1,
        gap_to_leader: i * 2.5,
        gap_to_ahead: 1.2,
        lap_time_ms: 74500 + Math.random() * 500,
        tire_compound: 'MEDIUM',
        tire_age_laps: 12,
        pit_stops_count: 0,
        fuel_remaining_kg: 42.5,
      })),
    },
    [raceId, lap]
  );
}

/**
 * Fetch race standings at a given lap.
 */
export function useRaceStandings(raceId: string, lap: number) {
  return useApiCall(
    () => fetchRaceStandings(raceId, lap),
    null,
    [raceId, lap]
  );
}

/**
 * Fetch telemetry for a specific driver/lap.
 */
export function useLapTelemetry(driverId: string, lap: number, raceId: string) {
  return useApiCall(
    () => fetchLapTelemetry(driverId, lap, raceId),
    null,
    [driverId, lap, raceId]
  );
}

/**
 * Fetch strategy recommendation.
 * Falls back to getMockStrategy.
 */
export function useStrategyRecommendation(params: {
  race_id: string;
  driver_id: string;
  current_lap: number;
  current_compound: string;
  fuel_level: number;
  track_temp: number;
  air_temp: number;
} | null) {
  const fallbackStrategy = params
    ? getMockStrategy(params.driver_id)
    : null;

  return useApiCall<StrategyRecommendation>(
    async () => {
      if (!params) throw new Error('No params');
      return fetchStrategyRecommendation(params);
    },
    fallbackStrategy,
    [params?.driver_id, params?.current_lap]
  );
}

/**
 * Fetch ML model status.
 */
export function useModelStatus() {
  return useApiCall(
    () => fetchModelStatus(),
    {
      models: [
        { name: 'tire_degradation', version: '1.2.0', status: 'active', accuracy: 0.92, last_updated: '2024-01-15T10:30:00Z' },
        { name: 'fuel_consumption', version: '1.1.0', status: 'active', accuracy: 0.89, last_updated: '2024-01-10T14:20:00Z' },
      ],
    }
  );
}

/**
 * Fetch system health.
 */
export function useSystemHealth() {
  return useApiCall(
    () => fetchSystemHealth(),
    {
      timestamp: new Date().toISOString(),
      status: 'healthy',
      feature_pipeline: 'not_loaded',
      simulators_cached: 0,
      ml_model: 'fallback',
    }
  );
}

/**
 * Simple connectivity check. Polls /health every 10s.
 */
export function useBackendStatus() {
  const [online, setOnline] = useState(false);
  const [latency, setLatency] = useState<number | null>(null);

  useEffect(() => {
    let mounted = true;
    const check = async () => {
      const start = performance.now();
      try {
        await fetchHealthCheck();
        if (mounted) {
          setOnline(true);
          setLatency(Math.round(performance.now() - start));
        }
      } catch {
        if (mounted) {
          setOnline(false);
          setLatency(null);
        }
      }
    };

    check();
    const interval = setInterval(check, 10_000);
    return () => { mounted = false; clearInterval(interval); };
  }, []);

  return { online, latency };
}
