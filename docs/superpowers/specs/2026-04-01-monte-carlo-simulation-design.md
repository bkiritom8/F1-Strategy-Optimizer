# Monte Carlo Race Simulation + Visual Replay Design

**Date:** 2026-04-01
**Status:** Approved
**Scope:** Coordinator, streaming layer, frontend visualizer, data layer, endpoint contracts

---

## Overview

When a user submits a what-if query (driver swap, pit strategy change) or uses the pit strategy tool, the system runs a Monte Carlo race simulation driven by the external simulation engine and RL agent, streams lap-by-lap car positions via SSE, and animates 20 colored dots on a 2D circuit SVG in the frontend — completing a 1.5-hour race replay in ~30 seconds. The LLM text analysis streams in parallel.

General chat questions do not trigger a simulation.

---

## Scope Boundaries

| Component | Owner | Our Role |
|---|---|---|
| Monte Carlo simulation engine | External team | Define request/response contract |
| RL strategy agent (PPO) | External team | Define request/response contract |
| SimulationCoordinator | This spec | Build |
| SSE streaming layer | This spec | Build |
| Redis cache + Cloud Tasks queue | This spec | Build |
| Frontend RaceSimulator component | This spec | Build |
| Year-aware car performance table | This spec | Build |
| Driver skills → LLM/model context | This spec | Build |

---

## Endpoint Contracts

### Simulation Engine Contract

**Request:**
```json
POST /internal/simulate
{
  "race_id": "monaco_2025",
  "scenario": {
    "driver_overrides": [{ "slot": 4, "driver_id": "hamilton", "car_id": "mclaren_2025" }],
    "strategy_overrides": [{ "driver_id": "hamilton", "pit_laps": [28, 52], "compounds": ["MEDIUM", "HARD"] }]
  },
  "drivers": [
    {
      "driver_id": "norris",
      "car_offset_ms": -550,
      "grid_position": 1,
      "start_compound": "MEDIUM",
      "skills": { "aggression": 0.78, "consistency": 0.82, "tire_management": 0.76, "pressure_response": 0.80 }
    }
  ],
  "n_trials": 50,
  "total_laps": 78
}
```

**Response (SSE stream, one frame per lap):**
```json
{ "type": "lap", "lap": 1, "cars": [
  { "id": "norris", "track_pct": 0.142, "position": 1, "compound": "MEDIUM", "gap_ms": 0, "lap_time_ms": 74531, "tire_age": 1 }
]}

{ "type": "complete", "p10_finish": 1, "p50_finish": 2, "p90_finish": 4,
  "llm_context": { "winner": "norris", "fastest_lap": "hamilton", "safety_cars": 1, "total_pit_stops": 38 }}
```

### RL Agent Contract

**Request:**
```json
POST /rl/decide
{
  "obs": [0.142, 25, 0.78, 0.82, 3, 0.042, 28.5, 0.0, 1, 0]
}
```

**Response:**
```json
{ "action": "pit", "compound": "HARD", "confidence": 0.87 }
```

*29 observation features match the existing `F1RaceEnv` observation space in `ml/rl/environment.py`.*

---

## System Architecture

```
What-if query or pit strategy trigger
          │
          ▼
   LLM tool call: get_strategy_recommendation
          │
          ▼
   SimulationCoordinator  (src/api/routes/simulate.py)
   ├─ hash(race_id + scenario) → Redis lookup
   ├─ cache hit  → return job_id, stream from cache
   └─ cache miss → enqueue Cloud Task → return job_id
          │
          ▼ Cloud Tasks queue
   SimulationWorker (Cloud Run job)
   ├─ determine n_trials from queue depth
   ├─ POST /internal/simulate → stream lap frames
   ├─ write result to Redis (TTL 1h) + GCS (permanent)
   └─ publish job_id → Pub/Sub
          │
          ▼ SSE: GET /simulate/race/stream?job_id=xxx
   Client receives lap frames + final context frame
          │
          ▼
   RaceSimulator (frontend/components/simulation/RaceSimulator.tsx)
   ├─ renders circuit SVG from TrackMaps.tsx
   ├─ overlays 20 team-colored dots at track_pct
   ├─ animates over 30s regardless of race length
   └─ pit stops: dot blinks + compound color change
```

---

## SimulationCoordinator

**File:** `src/api/routes/simulate.py`

**Endpoints:**
- `POST /api/v1/simulate/race` — accepts scenario, returns `{ job_id, cached: bool }`
- `GET /api/v1/simulate/race/stream` — SSE stream for a given `job_id`

**Scenario hashing:**
```python
import hashlib, json

def scenario_hash(race_id: str, scenario: dict) -> str:
    payload = json.dumps({"race_id": race_id, "scenario": scenario}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
```

**Load-dependent trial count:**
```python
def n_trials(queue_depth: int) -> int:
    if queue_depth < 100:   return 50
    if queue_depth < 500:   return 20
    return 10
```

**Cache TTL:** 1 hour for race simulations. Scenarios with `strategy_overrides` get a 15-minute TTL (more unique, less reuse value).

---

## SSE Streaming Layer

The SSE endpoint streams frames as `text/event-stream`. Each frame is a JSON line prefixed with `data: `.

LLM text and simulation frames share the same SSE connection via event type discrimination:

```
data: {"event": "llm_token", "token": "Hamilton's pace..."}
data: {"event": "sim_lap", "lap": 1, "cars": [...]}
data: {"event": "sim_complete", "p50_finish": 2, ...}
data: {"event": "done"}
```

This matches the existing streaming pattern in `AIChatbot.tsx` — the frontend already handles SSE, just needs new event types.

---

## Scale & Caching

| Queue Depth | Trials | Strategy |
|---|---|---|
| 0–100 | 50 | Full simulation |
| 100–500 | 20 | Reduced trials |
| 500–1000 | 10 | Minimal trials |
| 1000+ | — | Serve nearest cached scenario |

**Cache infrastructure:**
- Redis via Cloud Memorystore (~$15/month, fits $70 budget)
- Key: `sim:{scenario_hash}` → serialised position log + final stats
- GCS backup: `gs://f1optimizer-data-lake/simulations/{scenario_hash}.json` (permanent, for replay)

**Nearest cached scenario** (overloaded fallback): when queue depth exceeds 1000, look up Redis for a cached result with the same `race_id` regardless of scenario details, serve it with an `"approximate": true` flag in the response. If no same-race cache exists, serve the most recently cached simulation of any race.

---

## Data Layer

### Year-Aware Car Performance Table

**Script:** `pipeline/scripts/build_car_performance.py`
**Output:** `frontend/public/data/car_performance.json`

Process:
1. Load `race_results.parquet` from GCS
2. For each constructor + season: compute mean finishing position delta vs field median
3. Convert to milliseconds using avg lap time per season
4. Write JSON keyed by `{ constructor: { year: offset_ms } }`

Example output:
```json
{
  "mclaren": { "2021": -120, "2022": -280, "2023": -410, "2024": -540, "2025": -550 },
  "red_bull": { "2021": -580, "2022": -620, "2023": -640, "2024": -580, "2025": -600 }
}
```

Replaces the static `CAR_PERFORMANCE_OFFSET_MS` dict in `ml/rl/driver_profiles.py` as the source of truth for simulation scenarios.

### Driver Skills → Simulation Context

`frontend/public/data/drivers.json` skill scores (0–99) are mapped to simulation inputs:

| JSON field | Simulation use |
|---|---|
| `tire_management` | Multiplier on deg rate: `deg_rate × (1 - (skill/99) × 0.3)` |
| `aggression` | Overtake attempt probability boost |
| `wet_weather_skill` | Lap time delta modifier when `track_condition = wet` |
| `qualifying_pace` | Start position accuracy in scenario generation |
| `consistency` | Lap time variance (σ) |

These map onto the `skills` object in the simulation engine request payload.

---

## Frontend RaceSimulator Component

**File:** `frontend/components/simulation/RaceSimulator.tsx`

**Layout:** Sits alongside the chat panel. Appears when a `job_id` is present in the chat response.

**Track rendering:**
- Imports the relevant `TrackMaps.tsx` component (e.g. `MonacoTrack`) by `race_id`
- Renders at 600×400px
- Overlays 20 `<circle>` SVG elements positioned using `getPointAtLength(track_pct × pathLength)`

**Animation:**
- Total playback duration: 30 seconds regardless of race length
- Frame interval: `30000ms / total_laps`
- Pit stop visual: dot moves to pit lane position for 1 frame, compound color updates
- Team colors from existing `TEAM_COLORS` map in frontend

**Compound colors:**
```typescript
const COMPOUND_COLORS = { SOFT: '#E8002D', MEDIUM: '#FFF200', HARD: '#FFFFFF', INTERMEDIATE: '#39B54A', WET: '#0067FF' }
```

**Position label:** On hover over a dot, show `{ driver_code, position, gap, compound, lap_time }`

---

## New Files

| File | Purpose |
|---|---|
| `src/api/routes/simulate.py` | SimulationCoordinator endpoints |
| `src/simulation/coordinator.py` | Hash, cache, queue logic |
| `src/simulation/streamer.py` | SSE frame builder + Pub/Sub subscriber |
| `pipeline/scripts/build_car_performance.py` | One-time car performance table script |
| `frontend/components/simulation/RaceSimulator.tsx` | Visual race replay component |
| `frontend/components/simulation/index.ts` | Module exports |

## Modified Files

| File | Change |
|---|---|
| `src/api/routes/llm.py` | Wire `job_id` into chat response when simulation triggered |
| `src/llm/gemini_client.py` | Pass `llm_context` from final sim frame into LLM prompt |
| `frontend/views/AIChatbot.tsx` | Handle `sim_lap` + `sim_complete` SSE events, render RaceSimulator |
| `frontend/public/data/car_performance.json` | New file (generated by script) |

---

## What We Are NOT Building

- The Monte Carlo simulation engine (external team)
- The PPO RL agent or its training (external team)
- Any modifications to `ml/rl/` directory
- Fine-tuning the LLM
- Monitoring dashboards

---

## Success Criteria

1. What-if query → simulation animation starts within 3s of submission
2. 30-second race replay plays smoothly at 60fps
3. LLM text and simulation animate simultaneously
4. Cache hit rate >80% under sustained load (shared scenarios)
5. System degrades gracefully at 1000 concurrent (serves cached or reduced-trial results, no errors)
6. Year-aware car offsets visible in simulation (McLaren 2021 vs 2024 performance differs)
