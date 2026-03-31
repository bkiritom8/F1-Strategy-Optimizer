# Apex Intelligence: Frontend API Requirements for Backend

**Author:** Ajith Srikanth (Frontend / PM)
**For:** Bhargav Pamidighantam (Backend / Infra)
**Date:** March 30, 2026
**Frontend repo:** github.com/dreamerskymaster/apex-f1
**Backend deploy:** Cloud Run `f1-strategy-api-dev` (last deployed Mar 19)

---

## How the Frontend Works

The frontend has a three-tier fallback chain for every API call:

1. **Live API** (Cloud Run) via authenticated `apiFetch()` with JWT
2. **Static JSON** files in `public/data/` (real pipeline data, bundled at build)
3. **Hardcoded mocks** in `constants.ts` (last resort)

Every endpoint below shows what the frontend sends, what it expects back, and the current status. If an endpoint returns 404 or errors out, the UI silently falls back and shows "MOCK" in the sidebar badge instead of "LIVE".

---

## AUTH (Working)

### `POST /token`

Authenticates and returns a JWT. Frontend auto-calls this on first request.

**Request:** `Content-Type: application/x-www-form-urlencoded`
```
username=admin&password=admin
```

**Response:**
```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer"
}
```

**Status:** Working. Token cached in sessionStorage for 25 min.

---

## HEALTH & MONITORING (Working)

### `GET /health`

Frontend polls this every 30 seconds to show the green "LIVE" / yellow "MOCK" indicator in the sidebar.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-03-30T12:00:00.000Z",
  "version": "1.0.0",
  "environment": "local"
}
```

**Status:** Working.

---

### `GET /api/v1/health/system`

Used by: `SystemMonitoringHealth.tsx`

**Response:**
```json
{
  "timestamp": "2026-03-30T12:00:00.000Z",
  "status": "healthy",
  "feature_pipeline": "loaded",
  "simulators_cached": 2,
  "ml_model": "loaded",
  "laps_cached_rows": 45000
}
```

**Status:** Working (currently returns "fallback" for ml_model since no model.pkl in GCS).

---

## DRIVERS (Working)

### `GET /api/v1/drivers`

Used by: `DriverProfiles.tsx`, `RaceCommandCenter.tsx`

**Response:**
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
      "permanent_number": "1",
      "races": 209,
      "wins": 63,
      "podiums": 111,
      "points_total": 2985.5,
      "seasons": [2015, 2016, "...", 2024]
    }
  ]
}
```

**Status:** Working (loads from FeaturePipeline). Frontend computes aggression/consistency/pressure scores from these stats.

**Important:** The frontend needs `races`, `wins`, `podiums`, and `seasons` fields for the scatter/radar charts. If those are missing, driver profiles fall back to random seeded values.

---

### `GET /api/v1/drivers/{driver_id}/history`

Used by: `DriverProfiles.tsx` (on click)

**Response:** Season-by-season career breakdown.
```json
{
  "driver_id": "max_verstappen",
  "races": 209,
  "wins": 63,
  "podiums": 111,
  "points_total": 2985.5,
  "seasons": [2015, 2016, "...", 2024]
}
```

**Status:** Working.

---

## RACE STATE & TELEMETRY (Needs Redeploy)

### `GET /api/v1/race/state?race_id={id}&lap={n}`

Used by: `RaceCommandCenter.tsx`

**Query params:**
- `race_id` (string): e.g. `"2024_1"` (year_round)
- `lap` (int): lap number (1-based)

**Response:**
```json
{
  "race_id": "2024_1",
  "lap_number": 23,
  "total_laps": 57,
  "weather": "dry",
  "track_temp": 42.5,
  "air_temp": 28.0,
  "safety_car": false,
  "drivers": [
    {
      "driver_id": "max_verstappen",
      "position": 1,
      "gap_to_leader": 0.0,
      "gap_to_ahead": 0.0,
      "lap_time_ms": 74523,
      "tire_compound": "MEDIUM",
      "tire_age_laps": 12,
      "pit_stops_count": 1,
      "fuel_remaining_kg": 42.5
    }
  ]
}
```

**Status:** 404 on Cloud Run (Dockerfile was missing `ml/` and `pipeline/`; fixed locally, needs redeploy).

**Enhancement request:** Add `drs_active: boolean` per driver for pre-2026 races. Also add `sector_times_ms: [number, number, number]` per driver.

---

### `GET /api/v1/race/standings?race_id={id}&lap={n}`

Used by: `RaceCommandCenter.tsx` (position tower)

**Response:**
```json
{
  "race_id": "2024_1",
  "lap": 23,
  "standings": [
    { "position": 1, "driver_id": "max_verstappen", "gap": "+0.000" },
    { "position": 2, "driver_id": "norris", "gap": "+2.345" }
  ]
}
```

**Status:** Same as race/state (needs redeploy).

---

### `GET /api/v1/telemetry/{driver_id}/lap/{lap}?race_id={id}`

Used by: `LapByLapAnalysis.tsx`, `RaceCommandCenter.tsx`

**Response:** Single row from the feature pipeline state vector.
```json
{
  "lap_number": 23,
  "speed_kph": 312.5,
  "throttle_pct": 0.92,
  "brake_pct": 0.0,
  "gear": 8,
  "drs_status": 1,
  "tire_compound": "MEDIUM",
  "tire_age_laps": 12,
  "fuel_remaining_kg": 42.5,
  "sector_1_ms": 24100,
  "sector_2_ms": 28300,
  "sector_3_ms": 22100
}
```

**Status:** Needs redeploy. **Note:** DRS data needs to be kept for pre-2026 races (not dropped during feature engineering). Sector times should also be included. Albert Park has 4 DRS zones.

---

## STRATEGY (Partially Working)

### `POST /strategy/recommend`

Used by: `RaceCommandCenter.tsx`

**Request:**
```json
{
  "race_id": "2024_1",
  "driver_id": "max_verstappen",
  "current_lap": 23,
  "current_compound": "MEDIUM",
  "fuel_level": 42.5,
  "track_temp": 38.0,
  "air_temp": 25.0,
  "regulation_set": "2025"
}
```

**Response:**
```json
{
  "recommended_action": "CONTINUE",
  "pit_window_start": null,
  "pit_window_end": null,
  "target_compound": "HARD",
  "driving_mode": "BALANCED",
  "brake_bias": 52.5,
  "confidence": 0.65,
  "model_source": "rule_based_fallback"
}
```

**Status:** Working with rule-based fallback. `model_source` tells the frontend which path was used.

---

### `POST /api/v1/strategy/simulate`

Used by: `PitStrategySimulator.tsx` (not yet wired in frontend, uses mocks)

**Request:**
```json
{
  "race_id": "2024_1",
  "driver_id": "max_verstappen",
  "strategy": [[18, "MEDIUM"], [38, "HARD"]],
  "regulation_set": "2025"
}
```

**Response:**
```json
{
  "driver_id": "max_verstappen",
  "race_id": "2024_1",
  "predicted_final_position": 2,
  "predicted_total_time_s": 5412.3,
  "strategy": [[18, "MEDIUM"], [38, "HARD"]],
  "lap_times_s": [74.5, 74.8, 75.1],
  "win_probability": 0.22,
  "podium_probability": 0.40
}
```

**Status:** Endpoint exists in code, needs redeploy.

**Enhancement (nice to have):** New endpoint `GET /api/v1/strategy/recommend/top?race_id=2024_1&driver_id=max_verstappen` that auto-ranks top 3 strategies with labels like "Aggressive Undercut", "Conservative 1-Stop", "Early Two-Stop".

---

## PREDICTIONS (Placeholder, needs real models)

### `GET /api/v1/race/predict/overtake?driver_id={id}&opponent_id={id}`

Used by: `RaceCommandCenter.tsx`

**Response:**
```json
{
  "probability": 0.18,
  "timestamp": "2026-03-30T12:00:00Z",
  "model_version": "1.1.0"
}
```

**Status:** Returns random values. Needs real overtake probability model.

---

### `GET /api/v1/race/predict/safety_car?race_id={id}`

Used by: `RaceCommandCenter.tsx`

**Response:**
```json
{
  "probability": 0.08,
  "timestamp": "2026-03-30T12:00:00Z",
  "model_version": "1.2.0"
}
```

**Status:** Returns random values. Needs real safety car model.

---

## MODEL REGISTRY (Hardcoded, needs real data)

### `GET /api/v1/models/status`

Used by: `SystemMonitoringHealth.tsx`

**Response:**
```json
{
  "models": [
    {
      "name": "tire_degradation",
      "version": "2.1.4",
      "status": "active",
      "accuracy": 0.94,
      "last_updated": "2024-03-24T08:00:00Z",
      "type": "supervised"
    }
  ]
}
```

**Frontend expects these model names:** `tire_degradation`, `fuel_consumption`, `driving_style`, `safety_car`, `pit_window`, `overtake_prob`

**Status:** Hardcoded. Should read from GCS model metadata or MLflow.

---

### `GET /api/v1/models/{model_name}/bias`

Used by: `ModelEngineering.tsx`

**Response:**
```json
{
  "model_name": "tire_degradation",
  "timestamp": "2026-03-30T12:00:00Z",
  "slices": [
    { "name": "Circuit Type (Street vs Permanent)", "disparity_score": 0.08, "impact": "medium" }
  ]
}
```

**Status:** Hardcoded slices. Should compute from real model evaluation.

---

### `GET /api/v1/models/{model_name}/features`

Used by: `ModelEngineering.tsx` (SHAP bar chart)

**Response:**
```json
{
  "model_name": "tire_degradation",
  "features": [
    { "name": "track_temp", "importance": 0.35 },
    { "name": "tire_age_laps", "importance": 0.28 }
  ]
}
```

**Status:** Hardcoded. The `ml/` directory already generates `shap_bar.png`; this endpoint should serve the raw values.

---

## VALIDATION (Needs real data)

### `GET /api/v1/validation/race/{race_id}`

Used by: `ValidationPerformance.tsx`

**Response:**
```json
{
  "race_id": "2024_1",
  "accuracy": 0.925,
  "precision": 0.912,
  "recall": 0.898,
  "f1_score": 0.905,
  "samples": 1420
}
```

**Status:** Returns seeded deterministic values. Should compute from actual predictions vs ground truth.

---

## ADMIN

### `POST /api/v1/jobs/ingestion`

Used by: `AdminPage.tsx`

**Request:** `{ "action": "start" }` or `{ "action": "stop" }`

**Response:** `{ "status": "success", "action": "start" }`

**Status:** Working.

---

## NOT USING BACKEND (No Action Needed)

| View | Data Source | Notes |
|------|-----------|-------|
| `AIChatbot.tsx` | NVIDIA NIM API (Kimi K2.5) | Proxied via Vite, not our backend |
| `TrackExplorer.tsx` | Static SVG maps + `public/data/circuits.json` | No backend dependency |
| `PitStrategySimulator.tsx` | Hardcoded `MOCK_STRATEGIES` | Not yet wired to simulate endpoint |

---

## DATA CORRECTNESS NOTES

1. **DRS:** FeaturePipeline currently drops DRS column. Keep `drs_status` for pre-2026 races. Albert Park = 4 DRS zones.
2. **Sectors:** Add `sector_1_ms`, `sector_2_ms`, `sector_3_ms` to telemetry responses.
3. **2026 Regs:** `regulation_set: "2026"` accepted but no Active Aero logic yet. `driving_mode` returns `"X_MODE_Z_MODE"` as placeholder.

---

## PRIORITY SUMMARY

### Must Have (demo)
1. Redeploy Cloud Run with fixed Dockerfile
2. `/api/v1/drivers` with real career stats
3. `/api/v1/race/state` returning simulation data
4. `/strategy/recommend` working (rule-based is fine)

### Should Have (grading)
5. Overtake prediction with real model
6. Safety car prediction with real model
7. Model registry from GCS/MLflow
8. Validation metrics from real predictions
9. DRS + sector times in telemetry

### Nice to Have (polish)
10. Real SHAP values in features endpoint
11. Real bias analysis in bias endpoint
12. Auto-ranked top 3 strategies
13. WebSocket for live telemetry streaming

---

## QUICK REFERENCE TABLE

| Method | Path | Status |
|--------|------|--------|
| POST | `/token` | Working |
| GET | `/health` | Working |
| GET | `/api/v1/health/system` | Working |
| GET | `/api/v1/drivers` | Working |
| GET | `/api/v1/drivers/{id}/history` | Working |
| GET | `/api/v1/race/state` | Needs redeploy |
| GET | `/api/v1/race/standings` | Needs redeploy |
| GET | `/api/v1/telemetry/{id}/lap/{n}` | Needs redeploy + DRS |
| POST | `/strategy/recommend` | Working (rule-based) |
| POST | `/api/v1/strategy/simulate` | Needs redeploy |
| GET | `/api/v1/race/predict/overtake` | Placeholder (random) |
| GET | `/api/v1/race/predict/safety_car` | Placeholder (random) |
| GET | `/api/v1/models/status` | Hardcoded |
| GET | `/api/v1/models/{name}/bias` | Hardcoded |
| GET | `/api/v1/models/{name}/features` | Hardcoded |
| GET | `/api/v1/validation/race/{id}` | Seeded mock |
| POST | `/api/v1/jobs/ingestion` | Working |
