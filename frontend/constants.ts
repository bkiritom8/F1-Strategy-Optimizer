
/**
 * Application Constants
 * Defines the visual theme, team identities, and static mock data for the Apex Intelligence platform.
 */

import { TireCompound, DriverProfile, DriverTelemetry, RaceState, StrategyRecommendation } from './types';
import { TRACK_REGISTRY } from './components/tracks/TrackMaps';

export const APP_NAME = "Apex Intelligence";

export const COLORS = {
  dark: {
    bg: '#0F0F0F',
    secondary: '#1A1A1A',
    tertiary: '#252525',
    text: '#FFFFFF',
    textSecondary: '#6B7280',
    border: 'rgba(255, 255, 255, 0.05)',
    card: '#1A1A1A',
  },
  light: {
    bg: '#FCFBF7', // Warm Paper
    secondary: '#F0EFE9',
    tertiary: '#E5E4DE',
    text: '#1A1A1A',
    textSecondary: '#6B7280',
    border: 'rgba(0, 0, 0, 0.05)',
    card: '#FFFFFF',
  },
  accent: {
    red: '#E10600',
    green: '#00D2BE',
    yellow: '#FFF200',
    purple: '#9B59B6',
    blue: '#3498DB',
  },
  tires: {
    SOFT: '#FF3333',
    MEDIUM: '#FFD700',
    HARD: '#FFFFFF',
    INTERMEDIATE: '#39B54A',
    WET: '#3498DB',
  },
  modes: {
    PUSH: '#E10600',
    BALANCED: '#FFF200',
    CONSERVE: '#00D2BE',
  }
};

export const TEAM_COLORS: Record<string, string> = {
  'Red Bull': '#3671C6',
  'Mercedes': '#27F4D2',
  'Ferrari': '#E8002D',
  'McLaren': '#FF8000',
  'Aston Martin': '#229971',
  'Alpine': '#FF87BC',
  'Williams': '#64C4FF',
  'Haas': '#B6BABD',
  'RB': '#6692FF',
  'Sauber': '#52E252',
};

/**
 * F1 GLOSSARY
 * Beginner-friendly definitions for technical terms.
 */
export const F1_GLOSSARY: Record<string, string> = {
  ERS: "Energy Recovery System - harvester and storage of kinetic/heat energy to provide up to 160hp of electrical boost.",
  DRS: "Drag Reduction System - adjustable rear wing that opens to reduce air resistance and increase top speed by ~10-12 km/h.",
  'Tire Cliff': "The point where a tire's rubber has degraded so much that performance drops off immediately and drastically.",
  Undercut: "Pitting earlier than a rival to use the speed of fresh tires to jump ahead when the rival eventually pits.",
  'Brake Bias': "The distribution of braking force between the front and rear wheels, adjusted by the driver for different corners.",
  'Dirty Air': "Turbulent air left behind by a leading car, which reduces the aerodynamic downforce (grip) for the car following.",
  Delta: "The time difference between two cars, or between a driver's current lap and their best lap.",
  Apex: "The innermost point of the line taken through a curve, where the car is closest to the inside of the corner.",
  Stint: "The period between pit stops during which a driver is on track with a single set of tires.",
};

export const MOCK_DRIVERS: DriverProfile[] = [
  {
    driver_id: 'vst', name: 'Max Verstappen', team: 'Red Bull', code: 'VER', nationality: 'NED', career_races: 185, career_wins: 54,
    aggression_score: 92, consistency_score: 95, pressure_response: 98, tire_management: 89, wet_weather_skill: 96,
    qualifying_pace: 97, race_pace: 99, overtaking_ability: 94, defensive_ability: 95, fuel_efficiency: 90,
    experience_years: 9, rookie_status: false
  },
  {
    driver_id: 'ham', name: 'Lewis Hamilton', team: 'Mercedes', code: 'HAM', nationality: 'GBR', career_races: 332, career_wins: 103,
    aggression_score: 85, consistency_score: 96, pressure_response: 95, tire_management: 97, wet_weather_skill: 98,
    qualifying_pace: 94, race_pace: 96, overtaking_ability: 92, defensive_ability: 91, fuel_efficiency: 93,
    experience_years: 17, rookie_status: false
  },
  {
    driver_id: 'nor', name: 'Lando Norris', team: 'McLaren', code: 'NOR', nationality: 'GBR', career_races: 104, career_wins: 1,
    aggression_score: 88, consistency_score: 91, pressure_response: 89, tire_management: 90, wet_weather_skill: 92,
    qualifying_pace: 95, race_pace: 93, overtaking_ability: 91, defensive_ability: 88, fuel_efficiency: 87,
    experience_years: 5, rookie_status: false
  },
  {
    driver_id: 'lec', name: 'Charles Leclerc', team: 'Ferrari', code: 'LEC', nationality: 'MON', career_races: 125, career_wins: 5,
    aggression_score: 94, consistency_score: 87, pressure_response: 91, tire_management: 85, wet_weather_skill: 88,
    qualifying_pace: 99, race_pace: 92, overtaking_ability: 93, defensive_ability: 86, fuel_efficiency: 85,
    experience_years: 6, rookie_status: false
  },
  {
    driver_id: 'alo', name: 'Fernando Alonso', team: 'Aston Martin', code: 'ALO', nationality: 'ESP', career_races: 380, career_wins: 32,
    aggression_score: 91, consistency_score: 94, pressure_response: 96, tire_management: 95, wet_weather_skill: 94,
    qualifying_pace: 92, race_pace: 95, overtaking_ability: 97, defensive_ability: 98, fuel_efficiency: 96,
    experience_years: 21, rookie_status: false
  }
];

export const MOCK_RACE_STATE: RaceState = {
  race_id: 'monaco-2024',
  circuit: 'Circuit de Monaco',
  current_lap: 23,
  total_laps: TRACK_REGISTRY.find(t => t.id === 'monaco')?.laps || 78,
  weather: 'dry',
  track_temp_celsius: 42,
  air_temp_celsius: 26,
  track_grip_level: 65,
  flag: 'GREEN'
};

/**
 * Generates live telemetry for a specific driver.
 */
export const getMockTelemetry = (driverId: string, pos: number): DriverTelemetry => ({
  driver_id: driverId,
  position: pos,
  gap_to_leader: (pos - 1) * 2.5,
  gap_to_ahead: 1.2,
  gap_to_behind: 0.8,
  current_lap_time: 74250,
  last_lap_time: 74500,
  best_lap_time: 73800,
  speed_kph: 285,
  ers_deployment: 45,
  ers_mode: 'BALANCED',
  fuel_remaining_kg: 42.5,
  tire_compound: 'MEDIUM',
  tire_age_laps: 12,
  tire_wear_percent: 78,
  tire_temp_fl: 98,
  tire_temp_fr: 102,
  tire_temp_rl: 105,
  tire_temp_rr: 108,
  aero_loss_percent: pos > 1 ? 12 : 0,
  drs_active: pos > 1 && pos % 2 === 0,
  g_force_lateral: (Math.random() * 4 + 1),
  g_force_longitudinal: (Math.random() * 2 - 1),
  tire_grip_remaining: 100 - (12 * 0.8)
});

/**
 * Generates the AI-recommended strategy for a driver.
 */
export const getMockStrategy = (driverId: string): StrategyRecommendation => ({
  driver_id: driverId,
  current_lap: 23,
  pit_recommendation: {
    recommended_pit_lap: 32,
    confidence: 0.88,
    tire_compound: 'HARD',
    expected_position_after_pit: 5,
    win_probability: 0.15,
    podium_probability: 0.45
  },
  driving_style: {
    mode: 'BALANCED',
    ers_target_mode: 'HARVEST',
    reason: 'Charge battery for Turn 10 attack; protect rear tire thermals.',
    fuel_target_kg_per_lap: 1.82
  },
  brake_bias: {
    recommended_bias: 57.5,
    reason: 'Shifting rearward to help rotate the car in Turn 6/10.'
  },
  warnings: [
    { type: 'TIRE_CLIFF', severity: 'MEDIUM', message: 'Front left temperature rising in Sector 2', laps_until_critical: 8 },
    { type: 'AERO_WAKE', severity: 'CRITICAL', message: 'Dirty air from NOR increasing front wear by 14%', laps_until_critical: 2 }
  ]
});

export const MOCK_STRATEGIES = [
  { name: 'Optimal 2-Stop', win_prob: 0.22, podium_prob: 0.45, risk: 'Low', stints: [{comp: 'MEDIUM', laps: 32}, {comp: 'HARD', laps: 28}, {comp: 'SOFT', laps: 18}] },
  { name: 'Aggressive Undercut', win_prob: 0.18, podium_prob: 0.38, risk: 'High', stints: [{comp: 'MEDIUM', laps: 28}, {comp: 'HARD', laps: 30}, {comp: 'SOFT', laps: 20}] },
  { name: 'Conserve 1-Stop', win_prob: 0.04, podium_prob: 0.12, risk: 'Low', stints: [{comp: 'MEDIUM', laps: 45}, {comp: 'HARD', laps: 33}] },
];

export const MOCK_VALIDATION = [
  { race: 'Bahrain GP', predicted_winner: 'Max Verstappen', actual_winner: 'Max Verstappen', podium_acc: 100, pit_acc: 95 },
  { race: 'Saudi Arabian GP', predicted_winner: 'Sergio Perez', actual_winner: 'Max Verstappen', podium_acc: 66, pit_acc: 88 },
  { race: 'Australian GP', predicted_winner: 'Max Verstappen', actual_winner: 'Carlos Sainz', podium_acc: 33, pit_acc: 45 },
  { race: 'Japanese GP', predicted_winner: 'Max Verstappen', actual_winner: 'Max Verstappen', podium_acc: 100, pit_acc: 92 },
  { race: 'Chinese GP', predicted_winner: 'Max Verstappen', actual_winner: 'Max Verstappen', podium_acc: 100, pit_acc: 98 },
];
