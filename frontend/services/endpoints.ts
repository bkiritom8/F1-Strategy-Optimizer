/**
 * @file services/endpoints.ts
 * @description API endpoint wrappers with three-tier fallback:
 *   1. Try Cloud Run backend (live API)
 *   2. Fetch from /data/*.json (real pipeline data, bundled as static files)
 *   3. Use hardcoded mock constants
 *
 * The static data files in public/data/ are extracted from the F1-Strategy-Optimizer
 * repo's data pipeline by running: node scripts/extract-pipeline-data.mjs
 *
 * All functions log their activity via the shared `logger` utility so that
 * request lifecycles are fully traceable in the browser DevTools console
 * during development.
 */

import { apiFetch } from './client';
import { logger } from './logger';
import type {
  DriverProfile,
  StrategyRecommendation,
  RaceState,
  TireCompound,
  DriveMode,
} from '../types';

/**
 * Common logging and error handling for service layer.
 */
const handleApiError = (context: string, error: any, fallback: any) => {
  logger.error(`[Service:${context}]`, {
    message: error instanceof Error ? error.message : String(error),
  });
  return fallback;
};

// ─── Backend types ──────────────────────────────────────────────────────────

export interface BackendModelStatus {
  models: Array<{
    name: string;
    version: string;
    status: 'active' | 'training' | 'offline';
    accuracy: number;
    last_updated: string;
    type: 'supervised' | 'rl';
  }>;
}

export interface ModelBiasReport {
  model_name: string;
  timestamp: string;
  slices: Array<{
    name: string;
    disparity_score: number;
    impact: 'low' | 'medium' | 'high';
  }>;
}

export interface FeatureImportance {
  model_name: string;
  features: Array<{
    name: string;
    importance: number;
  }>;
}

export interface ValidationStats {
  race_id: string;
  accuracy: number;
  precision: number;
  recall: number;
  f1_score: number;
  samples: number;
}

export interface BackendSystemHealth {
  timestamp: string;
  status: string;
  feature_pipeline: string;
  simulators_cached: number;
  ml_model: string;
  laps_cached_rows?: number;
}

export interface PredictiveMetric {
  probability: number;
  timestamp: string;
  model_version: string;
}

export interface BackendRaceStateDriver {
  driver_id: string;
  position: number;
  gap_to_leader: number;
  gap_to_ahead: number;
  lap_time_ms: number;
  tire_compound: string;
  tire_age_laps: number;
  pit_stops_count: number;
  fuel_remaining_kg: number;
}

// ─── Static data types ──────────────────────────────────────────────────────

interface StaticDriver {
  id: string;
  name: string;
  code: string | null;
  number: string | null;
  nationality: string | null;
  dob: string | null;
  career_races: number;
  career_wins: number;
  career_podiums: number;
  career_poles: number;
  first_season: number;
  last_season: number;
  experience_years: number;
  rookie_status: boolean;
  is_legend: boolean;
  aggression_score: number;
  consistency_score: number;
  pressure_response: number;
  tire_management: number;
  wet_weather_skill: number;
  qualifying_pace: number;
  race_pace: number;
  overtaking_ability: number;
  defensive_ability: number;
  fuel_efficiency: number;
}

interface StaticCircuit {
  id: string;
  name: string;
  lat: number;
  lng: number;
  locality: string;
  country: string;
}

interface StaticRace {
  round: number;
  name: string;
  date: string;
  circuit: { id: string; name: string; country: string };
  results: Array<{
    position: number;
    driver: { id: string; code: string; name: string };
    constructor: string;
    grid: number;
    laps: number;
    status: string;
    points: number;
    time: string | null;
    fastestLap: { rank: number; lap: number; time: string | null } | null;
  }>;
}

interface PipelineReports {
  anomaly: {
    timestamp: string;
    total: number;
    critical: number;
    warnings: number;
    items: Array<{ severity: string; dataset: string; check: string; count: number; detail: string }>;
  };
  bias: {
    timestamp: string;
    totalRows: number;
    slices: Record<string, Array<{ slice: string; count: number; representation_pct: number; mean_lap_time_s: number | null; missing_pct: number }>>;
    findings: string[];
  };
}

// ─── Team mapping ───────────────────────────────────────────────────────────

const DRIVER_TEAM_MAP: Record<string, string> = {
  max_verstappen: 'Red Bull', perez: 'Red Bull',
  hamilton: 'Ferrari', leclerc: 'Ferrari',
  norris: 'McLaren', piastri: 'McLaren',
  russell: 'Mercedes', antonelli: 'Mercedes',
  alonso: 'Aston Martin', stroll: 'Aston Martin',
  gasly: 'Alpine', doohan: 'Alpine',
  tsunoda: 'RB', lawson: 'RB',
  albon: 'Williams', sainz: 'Williams',
  hulkenberg: 'Sauber', bortoleto: 'Sauber',
  ocon: 'Haas', bearman: 'Haas',
  ricciardo: 'RB', kevin_magnussen: 'Haas',
  bottas: 'Sauber', zhou: 'Sauber', sargeant: 'Williams',
};

// ─── Helper: fetch static JSON from public/data/ ────────────────────────────

/**
 * Fetches a static JSON file pre-bundled in `public/data/` by the data
 * extraction pipeline. Used as a secondary fallback when the live API is
 * unavailable but real data is needed.
 *
 * @param filename - Filename relative to `public/data/` (e.g. 'drivers.json').
 * @returns Parsed JSON typed as T.
 * @throws {Error} When the HTTP response is not OK.
 */
async function fetchStatic<T>(filename: string): Promise<T> {
  logger.debug(`[endpoints] fetchStatic: /data/${filename}`);
  const res = await fetch(`/data/${filename}`);
  if (!res.ok) {
    const err = `Static data ${filename}: ${res.status}`;
    logger.warn(`[endpoints] ${err}`);
    throw new Error(err);
  }
  logger.info(`[endpoints] Static data loaded: /data/${filename}`);
  return res.json();
}

// ─── Endpoint functions ─────────────────────────────────────────────────────

/**
 * Fetch driver profiles.
 * 1. Try backend /api/v1/drivers
 * 2. Fall back to static /data/drivers.json (860+ drivers from pipeline)
 */
export async function fetchDrivers(): Promise<DriverProfile[]> {
  // Try backend first
  logger.info('[endpoints] fetchDrivers: attempting live backend…');
  try {
    const data = await apiFetch<{ count: number; drivers: any[] }>('/api/v1/drivers');
    return data.drivers.map((d: any) => ({
      driver_id: d.driver_id,
      name: `${d.given_name} ${d.family_name}`,
      team: DRIVER_TEAM_MAP[d.driver_id] || 'Unknown',
      code: d.code || d.driver_id.slice(0, 3).toUpperCase(),
      nationality: d.nationality || '',
      career_races: d.races || 0,
      career_wins: d.wins || 0,
      aggression_score: Math.round(Math.min(100, 70 + (d.wins || 0) * 0.3) * 100) / 100,
      consistency_score: Math.round(Math.min(100, 60 + (d.races || 0) * 0.05) * 100) / 100,
      pressure_response: Math.round(Math.min(100, 65 + (d.podiums || 0) * 0.4) * 100) / 100,
      tire_management: Math.round(Math.min(100, 70 + (d.tire_management || 0)) * 100) / 100,
      wet_weather_skill: Math.round(Math.min(100, 65 + (d.wet_weather_skill || 0)) * 100) / 100,
      qualifying_pace: Math.round(Math.min(100, 70 + (d.wins || 0) * 0.5) * 100) / 100,
      race_pace: Math.round(Math.min(100, 70 + (d.wins || 0) * 0.4) * 100) / 100,
      overtaking_ability: Math.round(Math.min(100, 65 + (d.wins || 0) * 0.35) * 100) / 100,
      defensive_ability: Math.round(Math.min(100, 65 + (d.races || 0) * 0.03) * 100) / 100,
      fuel_efficiency: Math.round(Math.min(100, 70 + (d.fuel_efficiency || 0)) * 100) / 100,
      experience_years: d.seasons?.length || 0,
      rookie_status: (d.races || 0) < 25,
    }));
  } catch (err: any) {
    logger.warn(`[endpoints] fetchDrivers: live API unavailable — ${err?.message}. Falling back to static data.`);
  }

  // Try static pipeline data (real career stats from GCS Parquets)
  try {
    logger.info('[endpoints] fetchDrivers: loading from static pipeline data…');
    const staticDrivers = await fetchStatic<StaticDriver[]>('drivers.json');
    return staticDrivers.map((d) => ({
      driver_id:          d.id,
      name:               d.name,
      team:               DRIVER_TEAM_MAP[d.id] || 'Unknown',
      code:               d.code || d.id.slice(0, 3).toUpperCase(),
      nationality:        d.nationality || '',
      career_races:       d.career_races,
      career_wins:        d.career_wins,
      aggression_score:   d.aggression_score,
      consistency_score:  d.consistency_score,
      pressure_response:  d.pressure_response,
      tire_management:    d.tire_management,
      wet_weather_skill:  d.wet_weather_skill,
      qualifying_pace:    d.qualifying_pace,
      race_pace:          d.race_pace,
      overtaking_ability: d.overtaking_ability,
      defensive_ability:  d.defensive_ability,
      fuel_efficiency:    d.fuel_efficiency,
      experience_years:   d.experience_years,
      rookie_status:      d.rookie_status,
    }));
  } catch (err: any) {
    logger.error(`[endpoints] fetchDrivers: static file unavailable — ${err?.message}`);
    throw err;
  }
}

/**
 * Fetches the full career history for a single driver.
 *
 * @param driverId - Ergast-format driver slug (e.g. 'max_verstappen').
 * @returns Raw backend response containing season-by-season statistics.
 */
export async function fetchDriverHistory(driverId: string) {
  logger.debug(`[endpoints] fetchDriverHistory: ${driverId}`);
  return apiFetch<any>(`/api/v1/drivers/${driverId}/history`);
}

/**
 * Fetches the full race state at a specific lap number.
 * Returns normalised `RaceState` (weather, flags, temps) and an array of
 * per-driver states (position, gap, compound, fuel, pit count).
 *
 * @param raceId - Race identifier string (e.g. '2024_1').
 * @param lap    - Lap number (1-based).
 * @returns Normalised race state and driver state array.
 */
export async function fetchRaceState(
  raceId: string,
  lap: number,
): Promise<{ raceState: RaceState; driverStates: BackendRaceStateDriver[] }> {
  logger.debug(`[endpoints] fetchRaceState: race=${raceId} lap=${lap}`);
  const data = await apiFetch<any>(`/api/v1/race/state?race_id=${raceId}&lap=${lap}`);
  return {
    raceState: {
      race_id: data.race_id,
      circuit: data.race_id,
      current_lap: data.lap_number,
      total_laps: data.total_laps,
      weather: data.weather || 'dry',
      track_temp_celsius: data.track_temp || 35,
      air_temp_celsius: data.air_temp || 25,
      track_grip_level: 70,
      flag: data.safety_car ? 'SC' : 'GREEN',
    },
    driverStates: data.drivers,
  };
}

/**
 * Fetches the driver standings table at a specific lap.
 *
 * @param raceId - Race identifier string.
 * @param lap    - Lap number.
 * @returns Raw backend standings payload.
 */
export async function fetchRaceStandings(raceId: string, lap: number) {
  logger.debug(`[endpoints] fetchRaceStandings: race=${raceId} lap=${lap}`);
  return apiFetch<any>(`/api/v1/race/standings?race_id=${raceId}&lap=${lap}`);
}

/**
 * Fetches detailed per-lap telemetry for a single driver.
 *
 * @param driverId - Driver slug.
 * @param lap      - Lap number.
 * @param raceId   - Race identifier.
 * @returns Raw telemetry payload (speed, throttle, brake, gear, DRS, minis).
 */
export async function fetchLapTelemetry(driverId: string, lap: number, raceId: string) {
  logger.debug(`[endpoints] fetchLapTelemetry: driver=${driverId} lap=${lap} race=${raceId}`);
  return apiFetch<any>(`/api/v1/telemetry/${driverId}/lap/${lap}?race_id=${raceId}`);
}

/**
 * Fetch strategy recommendation.
 */
export async function fetchStrategyRecommendation(params: {
  race_id: string;
  driver_id: string;
  current_lap: number;
  current_compound: string;
  fuel_level: number;
  track_temp: number;
  air_temp: number;
}): Promise<StrategyRecommendation> {
  const data = await apiFetch<any>('/strategy/recommend', {
    method: 'POST',
    body: JSON.stringify(params),
  });
  return {
    driver_id: params.driver_id,
    current_lap: params.current_lap,
    pit_recommendation: {
      recommended_pit_lap: data.pit_window_start || params.current_lap + 10,
      confidence: data.confidence,
      tire_compound: (data.target_compound as TireCompound) || 'HARD',
      expected_position_after_pit: 5,
      win_probability: data.confidence * 0.25,
      podium_probability: data.confidence * 0.5,
    },
    driving_style: {
      mode: (data.driving_mode as DriveMode) || 'BALANCED',
      ers_target_mode: 'BALANCED',
      reason: data.recommended_action === 'PIT_SOON'
        ? 'Pit window approaching; manage thermals for in-lap.'
        : 'Continue current pace; tires within operating window.',
      fuel_target_kg_per_lap: 1.82,
    },
    brake_bias: {
      recommended_bias: data.brake_bias,
      reason: `Bias set to ${data.brake_bias}% (source: ${data.model_source})`,
    },
    warnings: [],
  };
}

/**
 * Runs a full Monte Carlo strategy simulation on the backend.
 *
 * @param params.race_id    - Race the simulation applies to.
 * @param params.driver_id  - Target driver slug.
 * @param params.strategy   - Array of [lap, compound] pit-stop tuples.
 * @returns Simulation results with predicted finish position and lap times.
 */
export async function simulateStrategy(params: {
  race_id:   string;
  driver_id: string;
  strategy:  [number, string][];
}) {
  logger.info(`[endpoints] simulateStrategy: driver=${params.driver_id} race=${params.race_id}`);
  return apiFetch<any>('/api/v1/strategy/simulate', {
    method: 'POST',
    body:   JSON.stringify(params),
  });
}

/**
 * Fetches the status and inventory of all ML models in the registry.
 * Covers 6 supervised models and 1 RL agent.
 *
 * @returns List of models with versioning, accuracy, and lifecycle status.
 */
export async function fetchModelStatus(): Promise<BackendModelStatus> {
  const endpoint = '/api/v1/models/status';
  logger.info(`[endpoints] fetchModelStatus: requesting ${endpoint}`);
  try {
    return await apiFetch<BackendModelStatus>(endpoint);
  } catch (err: any) {
    logger.warn(`[endpoints] fetchModelStatus: live API failed (${err.message}). Returning registry-aware mock.`);
    return {
      models: [
        { name: 'tire_degradation', version: '2.1.4', status: 'active', accuracy: 0.94, last_updated: '2024-03-24T08:00:00Z', type: 'supervised' },
        { name: 'driving_style', version: '1.0.8', status: 'active', accuracy: 0.88, last_updated: '2024-03-22T14:20:00Z', type: 'supervised' },
        { name: 'safety_car', version: '1.2.0', status: 'active', accuracy: 0.91, last_updated: '2024-03-23T10:30:00Z', type: 'supervised' },
        { name: 'pit_window', version: '3.0.1', status: 'active', accuracy: 0.95, last_updated: '2024-03-24T09:00:00Z', type: 'supervised' },
        { name: 'overtake_prob', version: '1.1.0', status: 'active', accuracy: 0.84, last_updated: '2024-03-20T16:45:00Z', type: 'supervised' },
        { name: 'race_outcome', version: '2.0.0', status: 'active', accuracy: 0.89, last_updated: '2024-03-24T12:00:00Z', type: 'supervised' },
        { name: 'rl_strategy_agent', version: '1.0.0-rc', status: 'active', accuracy: 0.87, last_updated: '2024-03-24T15:30:00Z', type: 'rl' },
      ],
    };
  }
}

/**
 * Fetches bias analysis for a specific model.
 * Evaluates performance across slices like Season, Circuit Type, and Compound.
 *
 * @param modelName - The name of the model from the registry.
 */
export async function fetchModelBiasReport(modelName: string): Promise<ModelBiasReport> {
  logger.debug(`[endpoints] fetchModelBiasReport: ${modelName}`);
  try {
    return await apiFetch<ModelBiasReport>(`/api/v1/models/${modelName}/bias`);
  } catch (err) {
    return handleApiError('fetchModelBiasReport', err, {
      model_name: modelName,
      timestamp: new Date().toISOString(),
      slices: [
        { name: 'Season (Shift)', disparity_score: 0.02, impact: 'low' },
        { name: 'Circuit (Street vs Perm)', disparity_score: 0.08, impact: 'medium' },
        { name: 'Tyre Compound (Thermals)', disparity_score: 0.12, impact: 'high' },
      ],
    });
  }
}

/**
 * Fetches SHAP-based feature importance for a model.
 *
 * @param modelName - The name of the model.
 */
export async function fetchFeatureImportance(modelName: string): Promise<FeatureImportance> {
  logger.debug(`[endpoints] fetchFeatureImportance: ${modelName}`);
  try {
    return await apiFetch<FeatureImportance>(`/api/v1/models/${modelName}/features`);
  } catch (err) {
    return handleApiError('fetchFeatureImportance', err, {
      model_name: modelName,
      features: [
        { name: 'track_temp', importance: 0.35 },
        { name: 'tire_age', importance: 0.28 },
        { name: 'fuel_load', importance: 0.15 },
        { name: 'air_pressure', importance: 0.12 },
        { name: 'driver_consistency', importance: 0.10 },
      ],
    });
  }
}

/**
 * Fetches real-time probability of a successful overtake between two drivers.
 * Uses the 'overtake_prob' model from the registry.
 *
 * @param driverId - Attacking driver.
 * @param opponentId - Defending driver.
 */
export async function fetchOvertakeProb(driverId: string, opponentId: string): Promise<PredictiveMetric> {
  logger.debug(`[endpoints] fetchOvertakeProb: attacker=${driverId} defender=${opponentId}`);
  try {
    return await apiFetch<PredictiveMetric>(`/api/v1/race/predict/overtake?driver_id=${driverId}&opponent_id=${opponentId}`);
  } catch (err) {
    logger.error(`[endpoints] fetchOvertakeProb failed`, { message: String(err) });
    throw err;
  }
}

/**
 * Fetches probability of a Safety Car (SC) or VSC deployment for a specific race.
 * Uses the 'safety_car' model from the registry.
 *
 * @param raceId - The race identifier (e.g. '2024_1').
 */
export async function fetchSafetyCarProb(raceId: string): Promise<PredictiveMetric> {
  logger.debug(`[endpoints] fetchSafetyCarProb: ${raceId}`);
  try {
    return await apiFetch<PredictiveMetric>(`/api/v1/race/predict/safety_car?race_id=${raceId}`);
  } catch (err) {
    logger.error(`[endpoints] fetchSafetyCarProb failed`, { message: String(err) });
    throw err;
  }
}

/**
 * Fetches validation metrics for a specific race.
 * Connects to the primary MLOps validation endpoint.
 *
 * @param raceId - Race identifier.
 */
export async function fetchValidationStats(raceId: string): Promise<ValidationStats> {
  logger.info(`[endpoints] fetchValidationStats: ${raceId}`);
  try {
    return await apiFetch<ValidationStats>(`/api/v1/validation/race/${raceId}`);
  } catch (err) {
    logger.error(`[endpoints] fetchValidationStats failed`, { message: String(err) });
    throw err;
  }
}

/**
 * Fetch system health with pipeline report data.
 */
export async function fetchSystemHealth(): Promise<BackendSystemHealth> {
  try {
    return await apiFetch<BackendSystemHealth>('/api/v1/health/system');
  } catch {
    try {
      const h = await apiFetch<any>('/health');
      return {
        timestamp: h.timestamp,
        status: h.status,
        feature_pipeline: 'not_loaded',
        simulators_cached: 0,
        ml_model: 'fallback',
      };
    } catch {
      throw new Error('System health unavailable');
    }
  }
}

/**
 * Probes the backend health endpoint.
 * Primarily used by `useBackendStatus` to determine live/mock mode.
 *
 * @returns Basic status, version, timestamp, and environment string.
 */
export async function fetchHealthCheck() {
  return apiFetch<{ status: string; timestamp: string; version: string; environment: string }>('/health');
}

// ─── Static data loaders (for views that need pipeline data directly) ────────

/**
 * Loads all F1 circuits from the pre-built static file.
 * Contains 77+ circuits with GPS coordinates, locality, and country.
 */
export async function fetchStaticCircuits(): Promise<StaticCircuit[]> {
  return fetchStatic<StaticCircuit[]>('circuits.json');
}

/**
 * Loads the full 2024 season race results from the static data file.
 * Includes driver finishes, fastest laps, grid positions, and points.
 */
export async function fetchStaticRaces2024(): Promise<StaticRace[]> {
  return fetchStatic<StaticRace[]>('races-2024.json');
}

/**
 * Loads the list of all seasons present in the pipeline dataset (1950–2026).
 */
export async function fetchStaticSeasons(): Promise<number[]> {
  return fetchStatic<number[]>('seasons.json');
}

/**
 * Loads anomaly-detection and demographic-bias quality reports produced by
 * the data pipeline. Returns null-equivalent when the file is absent.
 */
export async function fetchPipelineReports(): Promise<PipelineReports> {
  return fetchStatic<PipelineReports>('pipeline-reports.json');
}
