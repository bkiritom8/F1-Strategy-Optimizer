/**
 * @file api/endpoints.ts
 * @description Typed wrappers around every F1 Strategy Optimizer backend endpoint.
 * Each function transforms the backend JSON into the frontend type schema
 * defined in types.ts, so views never deal with raw API shapes.
 */

import { apiFetch } from './client';
import type {
  DriverProfile,
  DriverTelemetry,
  StrategyRecommendation,
  RaceState,
  TireCompound,
  DriveMode,
} from '../types';

// ─── Types for raw backend responses ────────────────────────────────────────

interface BackendDriver {
  driver_id: string;
  given_name: string;
  family_name: string;
  nationality: string;
  code: string;
  permanent_number: string;
  races?: number;
  wins?: number;
  podiums?: number;
  points_total?: number;
  seasons?: number[];
}

interface BackendDriversResponse {
  count: number;
  drivers: BackendDriver[];
}

interface BackendDriverHistory {
  driver_id: string;
  races: number;
  wins?: number;
  podiums?: number;
  points_total?: number;
  seasons?: number[];
}

interface BackendRaceStateDriver {
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

interface BackendRaceState {
  race_id: string;
  lap_number: number;
  total_laps: number;
  weather: string;
  track_temp: number;
  air_temp: number;
  safety_car: boolean;
  drivers: BackendRaceStateDriver[];
}

interface BackendStandings {
  race_id: string;
  lap: number;
  standings: any[];
}

interface BackendStrategyRecommendation {
  recommended_action: string;
  pit_window_start: number | null;
  pit_window_end: number | null;
  target_compound: string | null;
  driving_mode: string;
  brake_bias: number;
  confidence: number;
  model_source: string;
}

interface BackendModelStatus {
  models: Array<{
    name: string;
    version: string;
    status: string;
    accuracy: number;
    last_updated: string;
  }>;
}

interface BackendSystemHealth {
  timestamp: string;
  status: string;
  feature_pipeline: string;
  simulators_cached: number;
  ml_model: string;
  laps_cached_rows?: number;
}

interface BackendSimulateResponse {
  driver_id: string;
  race_id: string;
  predicted_final_position: number;
  predicted_total_time_s: number;
  strategy: [number, string][];
  lap_times_s: number[];
}

// Team lookup (backend doesn't always return team; we map by driverId for 2024 grid)
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
  bottas: 'Sauber', zhou: 'Sauber',
  sargeant: 'Williams',
};

// ─── Endpoint functions ─────────────────────────────────────────────────────

/**
 * GET /api/v1/drivers
 * Fetches all driver profiles with career stats, mapped to frontend DriverProfile.
 */
export async function fetchDrivers(): Promise<DriverProfile[]> {
  const data = await apiFetch<BackendDriversResponse>('/api/v1/drivers');

  return data.drivers.map((d) => ({
    driver_id: d.driver_id,
    name: `${d.given_name} ${d.family_name}`,
    team: DRIVER_TEAM_MAP[d.driver_id] || 'Unknown',
    code: d.code || d.driver_id.slice(0, 3).toUpperCase(),
    nationality: d.nationality || '',
    career_races: d.races || 0,
    career_wins: d.wins || 0,
    // Behavioral scores: derived from career stats as heuristics until ML profiles land
    aggression_score: Math.min(100, 70 + (d.wins || 0) * 0.3),
    consistency_score: Math.min(100, 60 + (d.races || 0) * 0.05),
    pressure_response: Math.min(100, 65 + (d.podiums || 0) * 0.4),
    tire_management: Math.min(100, 70 + Math.random() * 20),
    wet_weather_skill: Math.min(100, 65 + Math.random() * 25),
    qualifying_pace: Math.min(100, 70 + (d.wins || 0) * 0.5),
    race_pace: Math.min(100, 70 + (d.wins || 0) * 0.4),
    overtaking_ability: Math.min(100, 65 + (d.wins || 0) * 0.35),
    defensive_ability: Math.min(100, 65 + (d.races || 0) * 0.03),
    fuel_efficiency: Math.min(100, 70 + Math.random() * 20),
    experience_years: (d.seasons?.length) || 0,
    rookie_status: (d.races || 0) < 25,
  }));
}

/**
 * GET /api/v1/drivers/{driver_id}/history
 */
export async function fetchDriverHistory(driverId: string): Promise<BackendDriverHistory> {
  return apiFetch<BackendDriverHistory>(`/api/v1/drivers/${driverId}/history`);
}

/**
 * GET /api/v1/race/state?race_id=...&lap=...
 * Returns full race state at a given lap, mapped to frontend RaceState + driver telemetry.
 */
export async function fetchRaceState(
  raceId: string,
  lap: number
): Promise<{ raceState: RaceState; driverStates: BackendRaceStateDriver[] }> {
  const data = await apiFetch<BackendRaceState>(
    `/api/v1/race/state?race_id=${raceId}&lap=${lap}`
  );

  const raceState: RaceState = {
    race_id: data.race_id,
    circuit: data.race_id, // Will be enriched by circuit lookup
    current_lap: data.lap_number,
    total_laps: data.total_laps,
    weather: (data.weather as 'dry' | 'wet' | 'mixed') || 'dry',
    track_temp_celsius: data.track_temp || 35,
    air_temp_celsius: data.air_temp || 25,
    track_grip_level: 70,
    flag: data.safety_car ? 'SC' : 'GREEN',
  };

  return { raceState, driverStates: data.drivers };
}

/**
 * GET /api/v1/race/standings?race_id=...&lap=...
 */
export async function fetchRaceStandings(raceId: string, lap: number) {
  return apiFetch<BackendStandings>(
    `/api/v1/race/standings?race_id=${raceId}&lap=${lap}`
  );
}

/**
 * GET /api/v1/telemetry/{driver_id}/lap/{lap}?race_id=...
 * Returns raw telemetry for a specific driver lap.
 */
export async function fetchLapTelemetry(
  driverId: string,
  lap: number,
  raceId: string
) {
  return apiFetch<Record<string, any>>(
    `/api/v1/telemetry/${driverId}/lap/${lap}?race_id=${raceId}`
  );
}

/**
 * POST /strategy/recommend
 * Get AI strategy recommendation for a driver.
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
  const data = await apiFetch<BackendStrategyRecommendation>(
    '/strategy/recommend',
    { method: 'POST', body: JSON.stringify(params) }
  );

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
 * POST /api/v1/strategy/simulate
 * Run a pit strategy simulation.
 */
export async function simulateStrategy(params: {
  race_id: string;
  driver_id: string;
  strategy: [number, string][];
}): Promise<BackendSimulateResponse> {
  return apiFetch<BackendSimulateResponse>('/api/v1/strategy/simulate', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

/**
 * GET /models/status
 * Returns ML model health information.
 */
export async function fetchModelStatus(): Promise<BackendModelStatus> {
  return apiFetch<BackendModelStatus>('/models/status');
}

/**
 * GET /api/v1/health/system
 * Returns system/pipeline health.
 */
export async function fetchSystemHealth(): Promise<BackendSystemHealth> {
  return apiFetch<BackendSystemHealth>('/api/v1/health/system');
}

/**
 * GET /health
 * Simple health check (no auth required, but we send token anyway).
 */
export async function fetchHealthCheck() {
  return apiFetch<{ status: string; timestamp: string; version: string; environment: string }>(
    '/health'
  );
}

/**
 * GET /data/drivers (legacy endpoint, simpler response)
 */
export async function fetchDriversLegacy() {
  return apiFetch<Array<{ driver_id: string; name: string; nationality: string }>>(
    '/data/drivers'
  );
}
