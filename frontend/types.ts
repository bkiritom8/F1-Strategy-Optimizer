
/**
 * @file types.ts
 * @description Core type definitions for the Apex Intelligence platform.
 * Defines the schema for telemetry, driver profiles, and strategy recommendations.
 */

export type TireCompound = 'SOFT' | 'MEDIUM' | 'HARD' | 'INTERMEDIATE' | 'WET';
export type DriveMode = 'PUSH' | 'BALANCED' | 'CONSERVE';
export type ERSMode = 'HOTLAP' | 'OVERTAKE' | 'BALANCED' | 'HARVEST';
export type Severity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

/**
 * Represents the static metadata and behavioral scores for an F1 driver.
 */
export interface DriverProfile {
  driver_id: string;
  name: string;
  team: string;
  code: string;
  nationality: string;
  career_races: number;
  career_wins: number;
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
  experience_years: number;
  rookie_status: boolean;
  last_season?: number;
}

/**
 * Represents real-time car and environment data for a single driver.
 */
export interface DriverTelemetry {
  driver_id: string;
  position: number;
  gap_to_leader: number;
  gap_to_ahead: number;
  gap_to_behind: number;
  current_lap_time: number;
  last_lap_time: number;
  best_lap_time: number;
  speed_kph: number;
  ers_deployment: number;
  ers_mode: ERSMode;
  fuel_remaining_kg: number;
  tire_compound: TireCompound;
  tire_age_laps: number;
  tire_wear_percent: number;
  tire_temp_fl: number;
  tire_temp_fr: number;
  tire_temp_rl: number;
  tire_temp_rr: number;
  aero_loss_percent: number;
  drs_active: boolean;
  g_force_lateral: number;
  g_force_longitudinal: number;
  tire_grip_remaining: number;
}

/**
 * AI-generated guidance for race strategy and car adjustments.
 */
export interface StrategyRecommendation {
  driver_id: string;
  current_lap: number;
  pit_recommendation: {
    recommended_pit_lap: number;
    confidence: number;
    tire_compound: TireCompound;
    expected_position_after_pit: number;
    win_probability: number;
    podium_probability: number;
  };
  driving_style: {
    mode: DriveMode;
    ers_target_mode: ERSMode;
    reason: string;
    fuel_target_kg_per_lap: number;
  };
  brake_bias: {
    recommended_bias: number;
    reason: string;
  };
  warnings: Array<{
    type: string;
    severity: Severity;
    message: string;
    laps_until_critical: number;
  }>;
}

/**
 * Global session state for the current Grand Prix.
 */
export interface RaceState {
  race_id: string;
  circuit: string;
  current_lap: number;
  total_laps: number;
  weather: 'dry' | 'wet' | 'mixed';
  track_temp_celsius: number;
  air_temp_celsius: number;
  track_grip_level: number;
  flag: 'GREEN' | 'YELLOW' | 'RED' | 'SC' | 'VSC';
}
