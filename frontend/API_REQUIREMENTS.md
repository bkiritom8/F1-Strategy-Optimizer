# Apex Intelligence - API Endpoints & Data Requirements

## Executive Summary

This document outlines all API endpoints and data schemas required to power the Apex Intelligence F1 dashboard. Inspired by f1-tempo.com's telemetry visualization, our system extends beyond basic telemetry to include AI-driven strategy recommendations, driver profiling, and real-time race optimization.

---

## Dashboard Views & Data Needs

| View | Primary Data Needs | Update Frequency |
|------|-------------------|------------------|
| **Race Command Center** | Live telemetry, positions, race state, strategy alerts | Real-time (1-10 Hz) |
| **Driver Profiles** | Driver stats, behavioral scores, career history | Static / Per race |
| **Strategy Simulator** | Pit scenarios, tire models, Monte Carlo results | On-demand |
| **AI Strategist Chat** | Context-aware Q&A, strategy explanations | On-demand |
| **Post-Race Analysis** | Lap times, sector data, historical comparisons | Post-race batch |
| **Model Validation** | Prediction accuracy, ground truth comparisons | Per race |
| **MLOps Health** | Model latency, drift metrics, system status | Real-time (5s) |

---

## 1. Core Race Data Endpoints

### 🏁 Race State & Session Management

#### `GET /api/v1/race/state`
**Purpose:** Get current race session state  
**Update Frequency:** 1 Hz

```typescript
interface RaceState {
  race_id: string;               // e.g., 'monaco-2024'
  circuit: string;               // 'Circuit de Monaco'
  current_lap: number;           // 23
  total_laps: number;            // 78
  weather: 'dry' | 'wet' | 'mixed';
  track_temp_celsius: number;    // 42
  air_temp_celsius: number;      // 26
  track_grip_level: number;      // 0-100 scale
  flag: 'GREEN' | 'YELLOW' | 'RED' | 'SC' | 'VSC';
  session_status: 'pre_race' | 'formation' | 'racing' | 'suspended' | 'finished';
  safety_car_deployed: boolean;
  virtual_safety_car: boolean;
}
```

#### `GET /api/v1/race/standings`
**Purpose:** Live race positions (Position Tower)  
**Update Frequency:** 1-2 Hz

```typescript
interface RaceStandings {
  standings: Array<{
    position: number;
    driver_id: string;
    driver_code: string;       // 'VER', 'HAM'
    team: string;
    gap_to_leader: number;     // seconds
    gap_to_ahead: number;      // seconds
    interval: string;          // '+1.234' or 'LAP'
    last_lap_time_ms: number;
    best_lap_time_ms: number;
    tire_compound: TireCompound;
    tire_age_laps: number;
    pit_stops: number;
    status: 'racing' | 'pit' | 'out' | 'retired';
  }>;
}
```

#### `GET /api/v1/circuits/{circuit_id}`
**Purpose:** Get circuit metadata and characteristics

```typescript
interface Circuit {
  circuit_id: string;
  name: string;
  country: string;
  length_km: number;
  corners: number;
  drs_zones: number;
  lap_record_ms: number;
  lap_record_holder: string;
  tire_wear_factor: number;      // 0-1 scale
  fuel_consumption_factor: number;
  overtaking_difficulty: 'low' | 'medium' | 'high';
  sector_lengths: [number, number, number];
  track_map_svg_url: string;
}
```

---

## 2. Telemetry Endpoints (f1-tempo.com Style)

### 📡 Real-Time Car Telemetry

#### `GET /api/v1/telemetry/{driver_id}/live`
**Purpose:** Real-time telemetry stream for single driver  
**Update Frequency:** 10 Hz (every 100ms)

```typescript
interface DriverTelemetry {
  driver_id: string;
  timestamp_ms: number;
  
  // Position & Gaps
  position: number;
  gap_to_leader: number;
  gap_to_ahead: number;
  gap_to_behind: number;
  
  // Lap Times
  current_lap_time_ms: number;
  last_lap_time_ms: number;
  best_lap_time_ms: number;
  sector_1_ms: number | null;
  sector_2_ms: number | null;
  sector_3_ms: number | null;
  
  // Car Performance
  speed_kph: number;
  throttle_percent: number;      // 0-100
  brake_percent: number;         // 0-100
  gear: number;                  // 1-8
  rpm: number;
  drs_active: boolean;
  
  // ERS System
  ers_deployment: number;        // 0-100 battery %
  ers_mode: ERSMode;
  
  // Fuel
  fuel_remaining_kg: number;
  fuel_consumption_rate: number; // kg/lap
  
  // Tires
  tire_compound: TireCompound;
  tire_age_laps: number;
  tire_wear_percent: number;     // grip remaining
  tire_temp_fl: number;
  tire_temp_fr: number;
  tire_temp_rl: number;
  tire_temp_rr: number;
  tire_pressure_fl: number;
  tire_pressure_fr: number;
  tire_pressure_rl: number;
  tire_pressure_rr: number;
  
  // Brakes
  brake_temp_fl: number;
  brake_temp_fr: number;
  brake_temp_rl: number;
  brake_temp_rr: number;
  brake_bias_percent: number;    // 50-60 typically
  
  // G-Forces
  g_force_lateral: number;
  g_force_longitudinal: number;
  
  // Aero
  aero_loss_percent: number;     // dirty air effect
  
  // Position on Track
  track_position_percent: number; // 0-100 around lap
  distance_to_car_ahead_m: number;
}
```

#### `GET /api/v1/telemetry/all/snapshot`
**Purpose:** Snapshot of all drivers' telemetry (Command Center overview)  
**Update Frequency:** 1-2 Hz  
**Response:** Array of `DriverTelemetry` objects

#### `GET /api/v1/telemetry/{driver_id}/lap/{lap_number}`
**Purpose:** Historical lap telemetry for analysis/replay

```typescript
interface LapTelemetry {
  driver_id: string;
  lap_number: number;
  lap_time_ms: number;
  sector_times_ms: [number, number, number];
  is_personal_best: boolean;
  is_overall_best: boolean;
  telemetry_points: Array<{
    distance_m: number;        // 0 to track_length
    time_ms: number;
    speed_kph: number;
    throttle: number;
    brake: number;
    gear: number;
    drs: boolean;
    ers_deploy: number;
  }>;
  tire_wear_start: number;
  tire_wear_end: number;
  fuel_start_kg: number;
  fuel_end_kg: number;
}
```

---

## 3. Driver Profile Endpoints

### 👤 Driver Profiles & Behavioral Analysis

#### `GET /api/v1/drivers`
**Purpose:** List all driver profiles with ML-extracted behavioral scores

```typescript
interface DriverProfile {
  driver_id: string;
  name: string;
  code: string;              // 'VER', 'HAM'
  team: string;
  nationality: string;
  photo_url: string;
  helmet_url: string;
  
  // Career Stats
  career_races: number;
  career_wins: number;
  career_poles: number;
  career_podiums: number;
  career_points: number;
  championships: number;
  experience_years: number;
  rookie_status: boolean;
  
  // ML-Extracted Behavioral Scores (0-100)
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
  first_lap_skill: number;
  
  // Comparison to Grid Average
  overall_rating: number;
  rating_trend: 'improving' | 'stable' | 'declining';
}
```

#### `GET /api/v1/drivers/{driver_id}/history`
**Purpose:** Historical performance data for driver scatter plots

```typescript
interface DriverHistory {
  driver_id: string;
  race_history: Array<{
    race_id: string;
    circuit: string;
    date: string;
    grid_position: number;
    finish_position: number;
    points_scored: number;
    fastest_lap: boolean;
    pit_stops: number;
    avg_lap_time_ms: number;
    tire_wear_rate: number;
    fuel_efficiency: number;
  }>;
  season_stats: {
    wins: number;
    podiums: number;
    points: number;
    avg_finish: number;
    avg_grid: number;
  };
}
```

---

## 4. Strategy Recommendation Endpoints (AI/ML)

### 🤖 AI-Powered Strategy Recommendations

#### `GET /api/v1/strategy/{driver_id}/recommendation`
**Purpose:** Real-time AI strategy recommendation  
**Update Frequency:** Every lap or on significant state change

```typescript
interface StrategyRecommendation {
  driver_id: string;
  generated_at: string;        // ISO timestamp
  current_lap: number;
  
  // Pit Stop Recommendation
  pit_recommendation: {
    recommended_pit_lap: number;
    pit_window_start: number;
    pit_window_end: number;
    confidence: number;         // 0-1
    tire_compound: TireCompound;
    expected_position_after_pit: number;
    undercut_available: boolean;
    overcut_available: boolean;
    win_probability: number;
    podium_probability: number;
    reasoning: string;
  };
  
  // Driving Style Recommendation
  driving_style: {
    mode: DriveMode;
    ers_target_mode: ERSMode;
    target_lap_time_ms: number;
    fuel_target_kg_per_lap: number;
    reason: string;
  };
  
  // Brake Bias Recommendation
  brake_bias: {
    recommended_bias: number;   // 50-60%
    current_bias: number;
    delta: number;
    reason: string;
  };
  
  // Warnings & Alerts
  warnings: Array<{
    type: 'TIRE_CLIFF' | 'FUEL_CRITICAL' | 'AERO_WAKE' | 'BRAKE_TEMP' | 'WEATHER_CHANGE';
    severity: Severity;
    message: string;
    laps_until_critical: number;
  }>;
}
```

#### `POST /api/v1/strategy/simulate`
**Purpose:** Run Monte Carlo simulation for pit strategy scenarios

```typescript
// Request
interface SimulationRequest {
  driver_id: string;
  current_lap: number;
  scenarios: Array<{
    pit_laps: number[];
    tire_compounds: TireCompound[];
  }>;
  num_simulations: number;      // e.g., 10000
}

// Response
interface SimulationResponse {
  simulations_run: number;
  strategies: Array<{
    name: string;
    pit_laps: number[];
    compounds: TireCompound[];
    win_probability: number;
    podium_probability: number;
    expected_position: number;
    position_std_dev: number;
    risk_level: 'LOW' | 'MEDIUM' | 'HIGH';
    expected_total_time_ms: number;
    stints: Array<{
      compound: TireCompound;
      start_lap: number;
      end_lap: number;
      avg_pace_ms: number;
    }>;
  }>;
}
```

#### `POST /api/v1/ai/chat`
**Purpose:** AI Strategist conversational interface

```typescript
// Request
interface ChatRequest {
  message: string;
  context: {
    race_state: RaceState;
    selected_driver_id: string | null;
    conversation_history: Array<{role: string, content: string}>;
  };
}

// Response
interface ChatResponse {
  response: string;
  suggestions: string[];      // Follow-up prompts
  data_visualizations: Array<{
    type: 'chart' | 'table' | 'comparison';
    data: object;
  }> | null;
}
```

---

## 5. ML Model Predictions & Validation

### 📊 Model Outputs & Ground Truth Validation

#### `GET /api/v1/models/tire-degradation/predict`
**Purpose:** Predict tire degradation curve  
**Query Params:** `driver_id`, `compound`, `fuel_load_kg`, `track_temp`

```typescript
interface TireDegradationPrediction {
  compound: TireCompound;
  degradation_curve: Array<{
    lap: number;
    grip_remaining: number;     // 0-100
    predicted_lap_time_delta_ms: number;
    cliff_probability: number;  // 0-1
  }>;
  optimal_stint_length: number;
  cliff_lap_estimate: number;
  model_confidence: number;
}
```

#### `GET /api/v1/models/fuel-consumption/predict`
**Purpose:** Predict fuel consumption rate

```typescript
interface FuelPrediction {
  current_fuel_kg: number;
  consumption_rate_kg_per_lap: number;
  laps_remaining_at_current_rate: number;
  fuel_at_finish_kg: number;
  target_consumption_for_finish: number;
  lift_and_coast_required: boolean;
  model_confidence: number;
}
```

#### `GET /api/v1/validation/race/{race_id}`
**Purpose:** Get prediction vs actual results for model validation

```typescript
interface RaceValidation {
  race_id: string;
  race_name: string;
  date: string;
  predictions: {
    predicted_winner: string;
    predicted_podium: string[];
    predicted_positions: Record<string, number>;
  };
  actual_results: {
    actual_winner: string;
    actual_podium: string[];
    actual_positions: Record<string, number>;
  };
  accuracy_metrics: {
    winner_correct: boolean;
    podium_accuracy: number;     // 0-100%
    position_mae: number;        // Mean Absolute Error
    pit_timing_accuracy: number; // 0-100%
  };
}
```

---

## 6. MLOps Health & Monitoring

#### `GET /api/v1/health/models`
**Purpose:** Health status of all ML models

```typescript
interface ModelHealth {
  models: Array<{
    model_name: string;
    version: string;
    status: 'healthy' | 'degraded' | 'error';
    last_prediction_ms: number;
    avg_latency_ms: number;
    p99_latency_ms: number;
    predictions_last_hour: number;
    error_rate: number;
    drift_detected: boolean;
    last_retrained: string;
  }>;
  overall_status: 'healthy' | 'degraded' | 'error';
}
```

#### `GET /api/v1/health/system`
**Purpose:** System health metrics for dashboard

```typescript
interface SystemHealth {
  api_status: 'online' | 'degraded' | 'offline';
  api_latency_p99_ms: number;
  database_status: 'connected' | 'error';
  feature_store_lag_seconds: number;
  data_freshness_seconds: number;
  active_connections: number;
  cpu_usage_percent: number;
  memory_usage_percent: number;
  cost_today_usd: number;
  cost_month_usd: number;
  uptime_percent: number;
}
```

---

## 7. Data Types Reference

```typescript
// Tire Compounds
type TireCompound = 'SOFT' | 'MEDIUM' | 'HARD' | 'INTERMEDIATE' | 'WET';

// Driving Modes
type DriveMode = 'PUSH' | 'BALANCED' | 'CONSERVE';

// ERS Modes
type ERSMode = 'HOTLAP' | 'OVERTAKE' | 'BALANCED' | 'HARVEST';

// Alert Severity
type Severity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

// Race Flags
type RaceFlag = 'GREEN' | 'YELLOW' | 'RED' | 'SC' | 'VSC';

// Weather Conditions
type Weather = 'dry' | 'wet' | 'mixed';

// Driver Status
type DriverStatus = 'racing' | 'pit' | 'out' | 'retired';

// Session Status
type SessionStatus = 'pre_race' | 'formation' | 'racing' | 'suspended' | 'finished';
```

---

## 8. Endpoint Summary

| Method | Endpoint | Purpose | Frequency |
|--------|----------|---------|-----------|
| GET | `/api/v1/race/state` | Race session state | 1 Hz |
| GET | `/api/v1/race/standings` | Position tower | 1-2 Hz |
| GET | `/api/v1/circuits/{id}` | Circuit metadata | Static |
| GET | `/api/v1/telemetry/{driver_id}/live` | Live car telemetry | 10 Hz |
| GET | `/api/v1/telemetry/all/snapshot` | All drivers snapshot | 1-2 Hz |
| GET | `/api/v1/telemetry/{driver}/lap/{lap}` | Historical lap data | On-demand |
| GET | `/api/v1/drivers` | All driver profiles | Static |
| GET | `/api/v1/drivers/{id}/history` | Driver race history | Per race |
| GET | `/api/v1/strategy/{driver_id}/recommendation` | AI strategy rec | Per lap |
| POST | `/api/v1/strategy/simulate` | Monte Carlo sim | On-demand |
| POST | `/api/v1/ai/chat` | AI strategist chat | On-demand |
| GET | `/api/v1/models/tire-degradation/predict` | Tire deg prediction | On-demand |
| GET | `/api/v1/models/fuel-consumption/predict` | Fuel prediction | On-demand |
| GET | `/api/v1/validation/race/{race_id}` | Model validation | Post-race |
| GET | `/api/v1/health/models` | ML model health | 5s |
| GET | `/api/v1/health/system` | System metrics | 5s |

---

## 9. f1-tempo.com Feature Comparison

| Feature | f1-tempo.com | Apex Intelligence |
|---------|--------------|-------------------|
| Live Telemetry | ✅ Speed, throttle, brake, gear | ✅ + ERS, fuel, tire temps, G-forces |
| Lap Timing | ✅ Lap times, sector times | ✅ + Gap analysis, delta tracking |
| Position Tracking | ✅ Basic positions | ✅ + Intervals, pit status, tire info |
| Driver Profiles | ❌ Not available | ✅ ML-extracted behavioral scores |
| Strategy Recommendations | ❌ Not available | ✅ AI pit/driving/brake recs |
| Monte Carlo Simulation | ❌ Not available | ✅ 10K scenario simulations |
| AI Chat Interface | ❌ Not available | ✅ Conversational strategist |
| Tire Degradation Model | ❌ Not available | ✅ XGBoost predictions |
| Model Validation | ❌ Not available | ✅ Ground truth comparison |
| MLOps Monitoring | ❌ Not available | ✅ Full observability |

> **Key Differentiator:** f1-tempo.com is a visualization tool for existing data. Apex Intelligence is a **predictive system** that uses ML models to recommend optimal strategies in real-time.

---

## Implementation Notes

### Data Sources
- **Ergast API** - Historical race results (1950-2024)
- **FastF1 Library** - Telemetry data (2018+, 10 Hz)
- **OpenF1 API** - Real-time data (2023+)

### Backend Stack
- **FastAPI** - REST API framework
- **BigQuery** - Feature store & data warehouse
- **Vertex AI** - Model serving
- **Cloud Run** - Serverless deployment
- **Pub/Sub** - Real-time telemetry streaming

### Real-Time Considerations
- Use WebSocket for 10 Hz telemetry streams
- Implement connection pooling for high-frequency endpoints
- Cache static data (circuits, driver profiles) aggressively
- Use Server-Sent Events (SSE) for race state updates
