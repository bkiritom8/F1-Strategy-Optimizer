/**
 * @file hooks/useApi.ts
 * @description React hooks for consuming backend and static pipeline data.
 *
 * Architecture (fallback chain per hook):
 *   1. Cloud Run FastAPI backend  →  live, authenticated data
 *   2. GET /data/*.json           →  real pipeline data bundled as static files
 *   3. Hardcoded constants        →  last-resort mock fallback
 *
 * Every hook returns { data, loading, error, refetch, isLive } so views can
 * render a consistent loading / error / live / mock experience.
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
  fetchModelBiasReport,
  fetchFeatureImportance,
  fetchOvertakeProb,
  fetchSafetyCarProb,
  fetchValidationStats,
  fetchSystemHealth,
  fetchStaticCircuits,
  fetchStaticRaces2024,
  fetchStaticSeasons,
  fetchPipelineReports,
  BackendModelStatus,
  ModelBiasReport,
  FeatureImportance,
  ValidationStats,
  BackendSystemHealth,
  PredictiveMetric,
  GcpMetrics,
  AdminLog,
  AdminQuotas,
  fetchAdminGcpMetrics,
  fetchAdminLogs,
  fetchAdminQuotas,
} from '../services/endpoints';
import { API_BASE } from '../services/client';
import { logger } from '../services/logger';
import type { DriverProfile, StrategyRecommendation } from '../types';

// ─── Shared result type ──────────────────────────────────────────────────────

/**
 * Uniform result shape returned by every hook in this module.
 *
 * @template T - The domain type the hook is fetching (e.g. DriverProfile[]).
 */
interface UseApiResult<T> {
  /** The fetched (or mock-fallback) data, or null while the first fetch is pending. */
  data: T | null;
  /** True while any fetch request is in-flight. */
  loading: boolean;
  /** Error message string if the last request failed; null otherwise. */
  error: string | null;
  /** Imperatively re-trigger the fetch. Useful for manual refresh buttons. */
  refetch: () => void;
  /** True if the data came from the live backend; false if from mock/static. */
  isLive: boolean;
}

// ─── Generic fetch hook ──────────────────────────────────────────────────────

/**
 * Generic hook that executes an async fetcher function, manages loading / error
 * state, and activates a fallback value when the request fails.
 *
 * @template T       - Shape of the data to fetch.
 * @param fetcher    - Async function that performs the actual data fetch.
 * @param fallback   - Value to use if the fetch fails (null by default).
 * @param deps       - Extra dependency array entries for `useCallback`.
 * @returns          - `UseApiResult<T>` with reactive data + control helpers.
 */
function useApiCall<T>(
  fetcher: () => Promise<T>,
  fallback: T | null = null,
  deps: any[] = [],
  label = 'fetch',
): UseApiResult<T> {
  const [data,    setData   ] = useState<T | null>(fallback);
  const [loading, setLoading] = useState(true);
  const [error,   setError  ] = useState<string | null>(null);
  const [isLive,  setIsLive ] = useState(false);
  const mountedRef = useRef(true);

  const execute = useCallback(async () => {
    setLoading(true);
    setError(null);

    logger.debug(`[useApi] Starting fetch: ${label}`);

    try {
      const result = await fetcher();
      if (mountedRef.current) {
        setData(result);
        setIsLive(true);
        logger.info(`[useApi] Live data received: ${label}`);
      }
    } catch (err: any) {
      const msg = err?.message || 'Unknown error';
      if (mountedRef.current) {
        setError(msg);
        setIsLive(false);
        if (fallback && !data) setData(fallback);
        logger.warn(`[useApi] Fallback activated for ${label} — ${msg}`);
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);


  useEffect(() => {
    mountedRef.current = true;
    execute();
    return () => { mountedRef.current = false; };
  }, [execute]);

  return { data, loading, error, refetch: execute, isLive };
}

// ─── Domain hooks ────────────────────────────────────────────────────────────

/**
 * Fetches all driver profiles.
 */
export function useDrivers(): UseApiResult<DriverProfile[]> {
  return useApiCall(() => fetchDrivers(), null, [], 'drivers');
}

/**
 * Fetches the career history for a specific driver.
 *
 * @param driverId - Ergast-format driver slug (e.g. 'max_verstappen').
 */
export function useDriverHistory(driverId: string) {
  return useApiCall(() => fetchDriverHistory(driverId), null, [driverId], `driverHistory(${driverId})`);
}

/**
 * Fetches the full race state (positions, compounds, gaps) for a given lap.
 *
 * @param raceId - Race identifier string (e.g. '2024_1').
 * @param lap    - Lap number to query.
 */
export function useRaceState(raceId: string, lap: number) {
  return useApiCall(
    () => fetchRaceState(raceId, lap),
    null,
    [raceId, lap],
    `raceState(${raceId}:L${lap})`,
  );
}

/**
 * Fetches race standings at a specific lap.
 *
 * @param raceId - Race identifier string.
 * @param lap    - Lap number.
 */
export function useRaceStandings(raceId: string, lap: number) {
  return useApiCall(() => fetchRaceStandings(raceId, lap), null, [raceId, lap], `raceStandings(${raceId}:L${lap})`);
}

/**
 * Fetches per-lap telemetry for a specific driver.
 *
 * @param driverId - Driver slug.
 * @param lap      - Lap number.
 * @param raceId   - Race identifier.
 */
export function useLapTelemetry(driverId: string, lap: number, raceId: string) {
  return useApiCall(
    () => fetchLapTelemetry(driverId, lap, raceId),
    null,
    [driverId, lap, raceId],
    `lapTelemetry(${driverId}:L${lap})`,
  );
}

/**
 * Fetches a real-time strategy recommendation from the ML backend.
 *
 * @param params - Input telemetry for the strategy model; pass null to skip
 *                 the fetch (hook returns null data without an error).
 */
export function useStrategyRecommendation(params: {
  race_id:          string;
  driver_id:        string;
  current_lap:      number;
  current_compound: string;
  fuel_level:       number;
  track_temp:       number;
  air_temp:         number;
} | null) {
  return useApiCall<StrategyRecommendation>(
    async () => {
      if (!params) throw new Error('No strategy params provided');
      return fetchStrategyRecommendation(params);
    },
    null,
    [params?.driver_id, params?.current_lap],
    `strategy(${params?.driver_id ?? 'none'})`,
  );
}

/**
 * Fetches the ML model registry status (version, accuracy, last update).
 * Returns the status of 6 supervised models and the RL strategy agent.
 */
export function useModelStatus() {
  return useApiCall(() => fetchModelStatus(), {
    models: [
      { name: 'tire_degradation', version: '2.1.4', status: 'active', accuracy: 0.94, last_updated: '2024-03-24T08:00:00Z', type: 'supervised' },
      { name: 'driving_style', version: '1.0.8', status: 'active', accuracy: 0.88, last_updated: '2024-03-22T14:20:00Z', type: 'supervised' },
      { name: 'safety_car', version: '1.2.0', status: 'active', accuracy: 0.91, last_updated: '2024-03-23T10:30:00Z', type: 'supervised' },
      { name: 'pit_window', version: '3.0.1', status: 'active', accuracy: 0.95, last_updated: '2024-03-24T09:00:00Z', type: 'supervised' },
      { name: 'overtake_prob', version: '1.1.0', status: 'active', accuracy: 0.84, last_updated: '2024-03-20T16:45:00Z', type: 'supervised' },
      { name: 'race_outcome', version: '2.0.0', status: 'active', accuracy: 0.89, last_updated: '2024-03-24T12:00:00Z', type: 'supervised' },
      { name: 'rl_strategy_agent', version: '1.0.0-rc', status: 'active', accuracy: 0.87, last_updated: '2024-03-24T15:30:00Z', type: 'rl' },
    ],
  }, [], 'modelStatus');
}

/**
 * Fetches bias slices for a model (e.g. Street vs Perm, Soft vs Hard).
 */
export function useModelBiasReport(modelName: string | null) {
  return useApiCall(
    () => {
      if (!modelName) throw new Error('Model name required');
      return fetchModelBiasReport(modelName);
    },
    null,
    [modelName],
    `bias(${modelName ?? 'none'})`,
  );
}

/**
 * Fetches feature importance / SHAP values for a model.
 */
export function useFeatureImportance(modelName: string | null) {
  return useApiCall(
    () => {
      if (!modelName) throw new Error('Model name required');
      return fetchFeatureImportance(modelName);
    },
    null,
    [modelName],
    `shap(${modelName ?? 'none'})`,
  );
}

/**
 * Hook for live overtake probability between two drivers.
 */
export function useOvertakeMetric(driverId: string | null, opponentId: string | null): UseApiResult<PredictiveMetric> {
  return useApiCall<PredictiveMetric>(
    () => {
      if (!driverId || !opponentId) throw new Error('Driver and Opponent IDs required');
      return fetchOvertakeProb(driverId, opponentId);
    },
    null,
    [driverId, opponentId],
    `overtake(${driverId ?? 'none'}-${opponentId ?? 'none'})`,
  );
}

/**
 * Hook for live Safety Car / VSC probability for a specific race.
 */
export function useSafetyCarProb(raceId: string | null): UseApiResult<PredictiveMetric> {
  return useApiCall<PredictiveMetric>(
    () => {
      if (!raceId) throw new Error('Race ID required');
      return fetchSafetyCarProb(raceId);
    },
    null,
    [raceId],
    `scProb(${raceId ?? 'none'})`,
  );
}

/**
 * Fetches validation metrics for a specific race from the MLOps pipeline.
 */
export function useValidationStats(raceId: string | null) {
  return useApiCall(
    () => {
      if (!raceId) throw new Error('Race ID required');
      return fetchValidationStats(raceId);
    },
    null,
    [raceId],
    `validation(${raceId ?? 'none'})`,
  );
}

/**
 * Fetches the system health report (pipeline status, simulator cache, model mode).
 */
export function useSystemHealth() {
  return useApiCall(() => fetchSystemHealth(), {
    timestamp:          new Date().toISOString(),
    status:             'healthy',
    feature_pipeline:   'not_loaded',
    simulators_cached:  0,
    ml_model:           'fallback',
  }, [], 'systemHealth');
}

/**
 * Fetches all F1 circuits from the static pipeline data file.
 * Returns 77+ circuits with GPS coordinates, locality, and country.
 */
export function useCircuits() {
  return useApiCall(() => fetchStaticCircuits(), [], [], 'circuits');
}

/**
 * Fetches 2024 season race results from the static pipeline data file.
 * Includes driver standings, constructor, fastest laps, and points.
 */
export function useRaces2024() {
  return useApiCall(() => fetchStaticRaces2024(), [], [], 'races2024');
}

/**
 * Fetches the list of all seasons present in the dataset (1950–2026).
 */
export function useSeasons() {
  return useApiCall(() => fetchStaticSeasons(), [], [], 'seasons');
}

/**
 * Fetches anomaly and bias pipeline quality reports.
 * Returns null when the report file has not been generated yet.
 */
export function usePipelineReports() {
  return useApiCall(() => fetchPipelineReports(), null, [], 'pipelineReports');
}

// ─── Admin Hooks ────────────────────────────────────────────────────────────

export function useAdminGcpMetrics() {
  return useApiCall<GcpMetrics>(() => fetchAdminGcpMetrics(), null, [], 'adminGcpMetrics');
}

export function useAdminLogs() {
  return useApiCall<{ logs: AdminLog[] }>(() => fetchAdminLogs(), { logs: [] }, [], 'adminLogs');
}

export function useAdminQuotas() {
  return useApiCall<AdminQuotas>(() => fetchAdminQuotas(), null, [], 'adminQuotas');
}

// ─── Backend connectivity hook ───────────────────────────────────────────────

/**
 * Polls the backend `/health` endpoint every 30 seconds to determine
 * whether the API is reachable from the current browser environment.
 *
 * @returns `{ online: boolean, latency: number | null }`
 *   - `online`  — true if the last health check succeeded.
 *   - `latency` — round-trip time in ms for the last successful check, or null.
 */
export function useBackendStatus() {
  const [online,  setOnline ] = useState(false);
  const [latency, setLatency] = useState<number | null>(null);

  useEffect(() => {
    let mounted = true;

    const check = async () => {
      const start = performance.now();
      try {
        const res = await fetch(`${API_BASE}/health`, {
          signal: AbortSignal.timeout(5000),
        });
        const ms = Math.round(performance.now() - start);
        if (mounted && res.ok) {
          logger.api('GET', '/health', res.status, ms);
          setOnline(true);
          setLatency(ms);
        } else if (mounted) {
          logger.warn(`[useBackendStatus] /health returned ${res.status}`);
          setOnline(false);
          setLatency(null);
        }
      } catch (err: any) {
        if (mounted) {
          logger.warn(`[useBackendStatus] /health unreachable — ${err?.message}`);
          setOnline(false);
          setLatency(null);
        }
      }
    };

    check();
    const interval = setInterval(check, 30_000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  return { online, latency };
}
