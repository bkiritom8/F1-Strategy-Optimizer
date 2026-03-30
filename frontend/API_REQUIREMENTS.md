# Apex Intelligence: API Integration Status

## Backend: F1 Strategy Optimizer
- **Cloud Run URL**: `https://f1-strategy-api-dev-694267183904.us-central1.run.app`
- **Local Dev**: `http://localhost:8000` (proxied via Vite on port 3000)
- **Auth**: JWT via POST `/token` (admin/admin for dev)
- **Swagger Docs**: `/docs`

---

## Endpoint Integration Map

| # | Endpoint | Method | Frontend View | Hook | Status |
|---|----------|--------|---------------|------|--------|
| 1 | `/token` | POST | All (auto-auth) | `api/client.ts` | LINKED |
| 2 | `/health` | GET | Sidebar status badge | `useBackendStatus()` | LINKED |
| 3 | `/api/v1/drivers` | GET | Driver Profiles, Command Center | `useDrivers()` | LINKED |
| 4 | `/api/v1/drivers/{id}/history` | GET | Driver Profiles (detail) | `useDriverHistory()` | LINKED |
| 5 | `/api/v1/race/state` | GET | Race Command Center | `fetchRaceState()` | LINKED |
| 6 | `/api/v1/race/standings` | GET | Race Command Center | `useRaceStandings()` | LINKED |
| 7 | `/api/v1/telemetry/{driver}/lap/{lap}` | GET | Post-Race Analysis | `useLapTelemetry()` | LINKED |
| 8 | `/strategy/recommend` | POST | Race Command Center | `fetchStrategyRecommendation()` | LINKED |
| 9 | `/api/v1/strategy/simulate` | POST | Strategy Simulator | `simulateStrategy()` | LINKED |
| 10 | `/models/status` | GET | MLOps Health | `useModelStatus()` | LINKED |
| 11 | `/api/v1/health/system` | GET | MLOps Health | `useSystemHealth()` | LINKED |
| 12 | `/data/drivers` | GET | Legacy fallback | `fetchDriversLegacy()` | LINKED |

---

## Data Flow Per View

### Race Command Center
```
useDrivers() -> GET /api/v1/drivers -> 860+ drivers from GCS Parquet
fetchRaceState('2024_1', 23) -> GET /api/v1/race/state -> lap state, positions, weather
useBackendStatus() -> GET /health -> connection indicator
Fallback: MOCK_DRIVERS, MOCK_RACE_STATE, getMockTelemetry()
```

### Driver Profiles
```
useDrivers() -> GET /api/v1/drivers -> searchable grid with scatter/radar charts
useDriverHistory(id) -> GET /api/v1/drivers/{id}/history -> career stats
Fallback: MOCK_DRIVERS (5 drivers)
```

### Strategy Simulator
```
simulateStrategy() -> POST /api/v1/strategy/simulate -> Monte Carlo results
Fallback: MOCK_STRATEGIES
```

### MLOps Health
```
useSystemHealth() -> GET /api/v1/health/system -> pipeline status, ML model state
useModelStatus() -> GET /models/status -> model registry (tire_deg, fuel_consumption)
useBackendStatus() -> GET /health -> latency measurement
Fallback: static mock data
```

### AI Strategist
```
NVIDIA NIM API -> Apex AI Strategist engine
Not linked to FastAPI backend (uses external LLM)
```

### Circuit Directory
```
Static SVG track maps (26 circuits) from components/tracks/TrackMaps.tsx
No backend dependency
```

### Post-Race Analysis
```
useLapTelemetry(driver, lap, race) -> GET /api/v1/telemetry/{driver}/lap/{lap}
Fallback: generated mock data
```

### Model Validation
```
Currently uses MOCK_VALIDATION from constants.ts
Backend endpoint GET /api/v1/validation/race/{id} defined but not yet deployed
```

---

## Backend Response Schemas

### GET /api/v1/drivers (from FeaturePipeline, GCS Parquet)
```json
{
  "count": 860,
  "drivers": [
    {
      "driver_id": "max_verstappen",
      "given_name": "Max",
      "family_name": "Verstappen",
      "nationality": "Dutch",
      "code": "VER",
      "permanent_number": "3",
      "races": 185,
      "wins": 54,
      "podiums": 98,
      "points_total": 2586.5,
      "seasons": [2015, 2016, ..., 2024]
    }
  ]
}
```

### GET /api/v1/race/state (from RaceSimulator)
```json
{
  "race_id": "2024_1",
  "lap_number": 23,
  "total_laps": 57,
  "weather": "dry",
  "track_temp": 42,
  "air_temp": 26,
  "safety_car": false,
  "drivers": [
    {
      "driver_id": "max_verstappen",
      "position": 1,
      "gap_to_leader": 0.0,
      "gap_to_ahead": 0.0,
      "lap_time_ms": 92608,
      "tire_compound": "MEDIUM",
      "tire_age_laps": 12,
      "pit_stops_count": 1,
      "fuel_remaining_kg": 42.5
    }
  ]
}
```

### POST /strategy/recommend
```json
// Request
{
  "race_id": "2024_1",
  "driver_id": "max_verstappen",
  "current_lap": 23,
  "current_compound": "MEDIUM",
  "fuel_level": 42.5,
  "track_temp": 42.0,
  "air_temp": 26.0
}

// Response
{
  "recommended_action": "CONTINUE",
  "pit_window_start": 30,
  "pit_window_end": 35,
  "target_compound": "HARD",
  "driving_mode": "BALANCED",
  "brake_bias": 52.5,
  "confidence": 0.87,
  "model_source": "rule_based_fallback"
}
```

### GET /api/v1/health/system
```json
{
  "timestamp": "2026-03-23T...",
  "status": "healthy",
  "feature_pipeline": "not_loaded",
  "simulators_cached": 0,
  "ml_model": "fallback"
}
```

### GET /models/status
```json
{
  "models": [
    { "name": "tire_degradation", "version": "1.2.0", "status": "active", "accuracy": 0.92, "last_updated": "2024-01-15T10:30:00Z" },
    { "name": "fuel_consumption", "version": "1.1.0", "status": "active", "accuracy": 0.89, "last_updated": "2024-01-10T14:20:00Z" }
  ]
}
```

---

## Graceful Degradation

Every hook returns `{ data, loading, error, isLive }`:
- `data`: Always populated (real API data or mock fallback)
- `loading`: True during fetch
- `error`: Error message if API call failed
- `isLive`: True only if data came from the real backend

The `ConnectionBadge` component shows "Live API" (green) or "Mock Data" (yellow).
The sidebar footer shows "FastAPI Connected (Xms)" or "Using Mock Data".

---

## Environment Routing

| Context | API_BASE | How |
|---------|----------|-----|
| `npm run dev` | `""` | Vite proxy to localhost:8000 |
| Production build | `https://f1-strategy-api-dev-694267183904.us-central1.run.app` | Direct HTTPS |

Set in `services/client.ts` via `import.meta.env.PROD`.
