# Constructor Pace Model — Design Spec

**Date:** 2026-04-13
**Status:** Approved
**Scope:** Offline preprocessing script + sim coordinator integration

---

## Problem

The race simulator has no way to model car performance independently of driver skill. `constructor_enc` is just a label-encoded team integer — it carries no pace information. `car_performance.json` does not exist on disk. When a user selects a constructor in the sim, the simulation has no data to apply a meaningful pace delta.

---

## Goal

Produce a `constructor_pace.json` artifact covering 1996–2026 that gives each constructor a `pace_delta_s` (seconds/lap relative to field median) per season, with driver skill mathematically isolated. Wire this into the race sim so selecting a constructor applies the correct car pace to each simulated lap.

---

## Data Strategy (Two Tiers)

| Tier | Years | Source | Signal |
|------|-------|--------|--------|
| 1 | 2018–2026 | `telemetry_laps_all.parquet` (FastF1 qualifying laps) | High — hot lap, fresh tyres, low fuel |
| 2 | 2003–2017 | `race_results.parquet` (Ergast qualifying times) | Medium — qualifying time relative to pole |
| 3 | 1996–2002 | `race_results.parquet` (Ergast race finish times) | Lower — affected by reliability/strategy noise |

**2025:** Included normally (demo data, modelled from available race results).
**2026:** Included with `"limited_data": true` — the frontend shows a warning prompt before the sim runs.

---

## Model

A linear mixed-effects model (via `statsmodels.MixedLM`) fit separately per tier:

```
relative_pace ~ C(constructor_season) + C(circuit_category)
groups = driver_id
```

Where:
- `relative_pace = lap_time / session_median_lap_time - 1.0` (dimensionless, negative = faster)
- `constructor_season` is a compound key e.g. `"red_bull_2024"`
- `circuit_category` is one of `street`, `high_speed`, `balanced` (derived from circuit metadata)
- `driver_id` absorbs driver skill as a random effect — the constructor fixed-effect coefficients are the car pace signal

The fixed-effect coefficients for `constructor_season` are extracted, denormalised back to seconds/lap using the session median, and written as `pace_delta_s`.

---

## Output Format

Written to two locations:
- `gs://f1optimizer-data-lake/processed/constructor_pace.json` (API/sim reads)
- `frontend/public/data/constructor_pace.json` (frontend reads)

```json
{
  "version": "2026-04-13",
  "reference": "field_median",
  "constructors": {
    "red_bull": {
      "display_name": "Red Bull Racing",
      "seasons": {
        "2024": { "pace_delta_s": -0.312, "data_tier": 1, "limited_data": false },
        "2023": { "pace_delta_s": -0.445, "data_tier": 1, "limited_data": false },
        "2026": { "pace_delta_s": -0.150, "data_tier": 1, "limited_data": true },
        "2005": { "pace_delta_s": -0.080, "data_tier": 2, "limited_data": false },
        "1999": { "pace_delta_s":  0.210, "data_tier": 3, "limited_data": false }
      }
    }
  }
}
```

**Field definitions:**
- `pace_delta_s`: seconds/lap vs field median. Negative = faster than median. Applied directly to `lap_time_ms` in the sim.
- `data_tier`: 1/2/3 — used for UI tooltip quality indicators only, no sim logic depends on it.
- `limited_data`: `true` only for 2026 — triggers a frontend warning prompt before the sim starts.

---

## Architecture

```
DATA SOURCES
├── 2018–2026: gs://.../processed/telemetry_laps_all.parquet  (FastF1 quali laps)
├── 2003–2017: gs://.../processed/race_results.parquet        (Ergast quali times)
└── 1996–2002: gs://.../processed/race_results.parquet        (Ergast race finish times)

pipeline/scripts/build_constructor_pace.py
  ├── Tier 1: qualifying laps → normalise → MixedLM → pace_delta_s
  ├── Tier 2: Ergast quali times → normalise → MixedLM → pace_delta_s
  ├── Tier 3: race finish times → normalise → MixedLM → pace_delta_s
  └── Merge tiers → flag 2026 as limited_data → write JSON to GCS + local

src/simulation/constructor_pace.py   ← new ConstructorPaceStore
  • Loads constructor_pace.json at startup (GCS preferred, local fallback)
  • get_offset_ms(constructor_id, season) -> float  (pace_delta_s * 1000, ms)
  • is_limited_data(constructor_id, season) -> bool

src/api/routes/simulate.py
  • DriverInput gains: constructor_id: str | None = None
  • Season derived from race_id ("2024_1" → 2024)
  • start_simulation resolves constructor_id → car_offset_ms before hashing
  • scenario_hash updated to include drivers list (fix pre-existing cache gap)
  • Fallback applies car_offset_ms to lap_time_ms

frontend/public/data/constructor_pace.json
  • Constructor selector in sim UI reads this
  • limited_data: true → warning modal shown before sim starts
```

---

## New Files

| File | Purpose |
|------|---------|
| `pipeline/scripts/build_constructor_pace.py` | Offline script: fits mixed-effects model, writes JSON |
| `src/simulation/constructor_pace.py` | `ConstructorPaceStore` — loads JSON, resolves offsets |
| `tests/unit/simulation/test_constructor_pace_store.py` | Unit tests for the store |
| `tests/unit/pipeline/test_build_constructor_pace.py` | Unit tests for the build script |

---

## Changed Files

| File | Change |
|------|--------|
| `src/api/routes/simulate.py` | Add `constructor_id` to `DriverInput`; resolve offset; fix hash |
| `tests/unit/simulation/test_simulate_route.py` | Tests for constructor resolution + cache isolation |

---

## Testing

**`tests/unit/simulation/test_constructor_pace_store.py`**
- `get_offset_ms` returns `pace_delta_s * 1000` for known constructor/season
- `get_offset_ms` returns `0.0` for unknown constructor
- `get_offset_ms` returns `0.0` for unknown season
- `is_limited_data` returns `True` for 2026, `False` for all other seasons

**`tests/unit/simulation/test_simulate_route.py`** (extend existing)
- `car_offset_ms` populated from constructor lookup when `constructor_id` is set
- `car_offset_ms` stays `0.0` when `constructor_id` is `None`
- Different `constructor_id` → different `job_id` hash (cache isolation)
- Fallback sim applies `car_offset_ms` to `lap_time_ms`

**`tests/unit/pipeline/test_build_constructor_pace.py`**
- `relative_pace` normalisation: `lap_time / session_median - 1.0`
- Tier assignment: ≥2018 → tier 1, 2003–2017 → tier 2, 1996–2002 → tier 3
- 2026 entries have `limited_data: true`, all others `false`
- Output JSON has all required top-level keys

GCS/mixed-effects integration tests run only in the Vertex AI test job.

---

## Explicit Non-Goals (v1)

- Per-circuit-type pace breakdown (street / high-speed / balanced) — future extension
- Serving this as a real-time ML endpoint — it is a preprocessing artifact only
- Within-season development trajectory — average season pace only

---

## Run Command

```bash
# Build and upload constructor pace table (run after new season data lands)
python pipeline/scripts/build_constructor_pace.py \
  --output gs://f1optimizer-data-lake/processed/constructor_pace.json \
  --local-output frontend/public/data/constructor_pace.json
```
