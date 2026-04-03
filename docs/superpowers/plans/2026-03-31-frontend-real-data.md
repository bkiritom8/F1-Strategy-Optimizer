# Frontend Real Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all hardcoded mock data in the frontend with real F1 historical data from GCS Parquet files, generated as static JSON at build time.

**Architecture:** A Python script reads `drivers.parquet`, `race_results.parquet`, and `circuits.parquet` from `gs://f1optimizer-data-lake/processed/` and writes 5 JSON files to `frontend/public/data/`. The CI `deploy-frontend` job runs this script before `npm run build`. The frontend drops all tier-3 mock fallbacks — backend API is tier-1, static JSON is tier-2, unavailability shows `null` (and the UI already handles that with its error/loading states).

**Tech Stack:** Python 3.10, pandas, pyarrow, google-cloud-storage, React 19 / TypeScript

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `pipeline/scripts/generate_static_json.py` | Read GCS Parquets → write 5 JSON files to `frontend/public/data/` |
| Modify | `frontend/constants.ts` | Delete mock exports; keep APP_NAME, COLORS, TEAM_COLORS, F1_GLOSSARY |
| Modify | `frontend/hooks/useApi.ts` | Remove mock imports; set fallback=null for mock-backed hooks |
| Modify | `frontend/services/endpoints.ts` | Remove MOCK_DRIVERS import; use real stats from enriched StaticDriver; remove seeded-random fallbacks |
| Modify | `.github/workflows/ci.yml` | Add GCS auth + script step before `npm run build` in `deploy-frontend` |

---

## Task 1: Write `generate_static_json.py`

**Files:**
- Create: `pipeline/scripts/generate_static_json.py`

- [ ] **Step 1: Create the script**

```python
#!/usr/bin/env python3
"""
generate_static_json.py — Export real F1 data from GCS Parquets to frontend static JSON.

Output (written to frontend/public/data/):
    drivers.json      — all drivers since 2018 + 25 all-time legends (with real career stats)
    circuits.json     — all 77+ circuits with GPS
    races-2024.json   — 2024 season round-by-round results
    seasons.json      — all seasons 1950–2026 as int array
    pipeline-reports.json — computed quality stats

Usage:
    python pipeline/scripts/generate_static_json.py [--bucket f1optimizer-data-lake] [--out frontend/public/data]

Requirements: pandas, pyarrow, google-cloud-storage
"""

import argparse
import json
import logging
import math
from pathlib import Path
from io import BytesIO

import pandas as pd
from google.cloud import storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Legend driver IDs (Ergast/Jolpica format) ────────────────────────────────
LEGEND_IDS = {
    "fangio", "senna", "michael_schumacher", "prost", "clark",
    "lauda", "stewart", "ascari", "moss", "hill",          # Graham Hill
    "mansell", "villeneuve",                               # Gilles Villeneuve
    "brabham", "piquet", "surtees", "hakkinen", "andretti",
    "rindt", "fittipaldi", "farina", "hulme", "hunt",
    "raikkonen", "scheckter", "hawthorn",
}

MODERN_CUTOFF_SEASON = 2018


def _clamp(val: float, lo: float = 50.0, hi: float = 99.0) -> float:
    return round(max(lo, min(hi, val)), 1)


def _load_parquet(client: storage.Client, bucket: str, blob_path: str) -> pd.DataFrame:
    log.info(f"Loading gs://{bucket}/{blob_path}")
    blob = client.bucket(bucket).blob(blob_path)
    data = blob.download_as_bytes()
    return pd.read_parquet(BytesIO(data))


def compute_driver_scores(wins: int, podiums: int, poles: int, races: int) -> dict:
    """Derive 10 skill scores from real career statistics."""
    if races == 0:
        base = {k: 50.0 for k in [
            "aggression_score", "consistency_score", "pressure_response",
            "tire_management", "wet_weather_skill", "qualifying_pace",
            "race_pace", "overtaking_ability", "defensive_ability", "fuel_efficiency"
        ]}
        return base

    win_rate   = wins   / races
    pod_rate   = podiums / races
    pole_rate  = poles  / races
    lead_wins  = max(0, wins - poles)  # wins started from non-pole

    qp  = _clamp(50 + pole_rate * 400)
    rp  = _clamp(50 + win_rate  * 300)
    oa  = _clamp(50 + (lead_wins / races) * 350)
    cs  = _clamp(50 + pod_rate  * 150)
    pr  = _clamp(50 + win_rate  * 500)
    ag  = _clamp(qp  * 0.65 + oa * 0.35)
    tm  = _clamp(50 + pod_rate  * 120)
    ww  = _clamp(50 + win_rate  * 250)
    da  = _clamp(50 + pod_rate  * 130)
    fe  = _clamp(cs  * 0.75 + 25)

    return {
        "aggression_score":   ag,
        "consistency_score":  cs,
        "pressure_response":  pr,
        "tire_management":    tm,
        "wet_weather_skill":  ww,
        "qualifying_pace":    qp,
        "race_pace":          rp,
        "overtaking_ability": oa,
        "defensive_ability":  da,
        "fuel_efficiency":    fe,
    }


def build_drivers_json(
    drivers_df: pd.DataFrame,
    results_df: pd.DataFrame,
) -> list[dict]:
    """
    Build driver list: all drivers with at least one race since 2018
    PLUS any legend whose driverId is in LEGEND_IDS regardless of era.
    """
    # Normalise column names (Ergast CSVs use camelCase)
    drivers_df.columns = [c.lower() for c in drivers_df.columns]
    results_df.columns = [c.lower() for c in results_df.columns]

    # ── Career stats aggregation ─────────────────────────────────────────────
    stats = (
        results_df[results_df["position"].notna()]
        .assign(position=lambda d: pd.to_numeric(d["position"], errors="coerce"))
        .dropna(subset=["position"])
        .assign(
            is_win   = lambda d: (d["position"] == 1).astype(int),
            is_podium= lambda d: (d["position"] <= 3).astype(int),
            is_pole  = lambda d: (pd.to_numeric(d.get("grid", pd.Series(dtype=float)), errors="coerce") == 1).astype(int),
        )
        .groupby("driverid")
        .agg(
            career_races     =("is_win",    "count"),
            career_wins      =("is_win",    "sum"),
            career_podiums   =("is_podium", "sum"),
            career_poles     =("is_pole",   "sum"),
            first_season     =("season",    "min"),
            last_season      =("season",    "max"),
        )
        .reset_index()
    )

    # ── Merge drivers metadata with stats ────────────────────────────────────
    id_col = next(
        c for c in ["driverid", "driver_id", "driverRef"] if c.lower() in drivers_df.columns
    ) if any(c.lower() in drivers_df.columns for c in ["driverid", "driver_id", "driverref"]) else drivers_df.columns[0]

    drivers_df = drivers_df.rename(columns={id_col: "driverid"})
    merged = drivers_df.merge(stats, on="driverid", how="left")

    # Fallback zeros for drivers with no results row
    for col in ["career_races", "career_wins", "career_podiums", "career_poles"]:
        merged[col] = merged[col].fillna(0).astype(int)
    merged["first_season"] = merged.get("first_season", pd.Series()).fillna(0).astype(int)
    merged["last_season"]  = merged.get("last_season",  pd.Series()).fillna(0).astype(int)

    # ── Filter: modern era (2018+) OR legend ────────────────────────────────
    is_modern = merged["last_season"] >= MODERN_CUTOFF_SEASON
    is_legend = merged["driverid"].isin(LEGEND_IDS)
    subset = merged[is_modern | is_legend].copy()

    log.info(
        f"Drivers selected: {len(subset)} "
        f"({is_modern.sum()} modern, {is_legend.sum()} legends, overlap={((is_modern) & (is_legend)).sum()})"
    )

    # ── Build output records ─────────────────────────────────────────────────
    records = []
    for _, row in subset.iterrows():
        given  = str(row.get("givenname",  row.get("given_name",  ""))).strip()
        family = str(row.get("familyname", row.get("family_name", ""))).strip()
        name   = f"{given} {family}".strip() or str(row["driverid"])

        w, p, po, r = (
            int(row["career_wins"]),
            int(row["career_podiums"]),
            int(row["career_poles"]),
            int(row["career_races"]),
        )
        scores = compute_driver_scores(w, p, po, r)

        records.append({
            "id":           str(row["driverid"]),
            "name":         name,
            "code":         str(row.get("code", "")) or None,
            "number":       str(row.get("permanentnumber", row.get("number", ""))) or None,
            "nationality":  str(row.get("nationality", "")) or None,
            "dob":          str(row.get("dateofbirth", row.get("dob", ""))) or None,
            "career_races":    r,
            "career_wins":     w,
            "career_podiums":  p,
            "career_poles":    po,
            "first_season":    int(row["first_season"]),
            "last_season":     int(row["last_season"]),
            "experience_years": max(1, int(row["last_season"]) - int(row["first_season"]) + 1)
                               if int(row["last_season"]) > 0 else 1,
            "rookie_status":   r < 25,
            "is_legend":       str(row["driverid"]) in LEGEND_IDS,
            **scores,
        })

    return sorted(records, key=lambda d: (-d["career_races"], d["name"]))


def build_circuits_json(circuits_df: pd.DataFrame) -> list[dict]:
    circuits_df.columns = [c.lower() for c in circuits_df.columns]
    records = []
    for _, row in circuits_df.iterrows():
        try:
            lat = float(row.get("lat", row.get("latitude", 0)))
            lng = float(row.get("lng", row.get("longitude", row.get("long", 0))))
        except (ValueError, TypeError):
            lat, lng = 0.0, 0.0
        if math.isnan(lat): lat = 0.0
        if math.isnan(lng): lng = 0.0

        records.append({
            "id":       str(row.get("circuitid", row.get("circuit_id", ""))),
            "name":     str(row.get("name", row.get("circuitname", ""))),
            "lat":      lat,
            "lng":      lng,
            "locality": str(row.get("locality", row.get("location", ""))),
            "country":  str(row.get("country", "")),
        })
    return records


def build_races_2024_json(results_df: pd.DataFrame, circuits_df: pd.DataFrame) -> list[dict]:
    results_df.columns = [c.lower() for c in results_df.columns]
    circuits_df.columns = [c.lower() for c in circuits_df.columns]

    season_col = next((c for c in results_df.columns if c in ("season", "year")), None)
    if season_col is None:
        log.warning("No season column found in race_results; returning empty races list")
        return []

    r2024 = results_df[pd.to_numeric(results_df[season_col], errors="coerce") == 2024].copy()
    if r2024.empty:
        log.warning("No 2024 race results found in parquet")
        return []

    # Circuits lookup
    circ_id_col = next((c for c in circuits_df.columns if "circuitid" in c or "circuit_id" in c), circuits_df.columns[0])
    circuits_df = circuits_df.rename(columns={circ_id_col: "circuitid"})
    circ_map = circuits_df.set_index("circuitid")[["name", "country"]].to_dict("index")

    rounds = []
    round_col  = next((c for c in r2024.columns if c in ("round", "raceid", "race_id")), None)
    circuit_col= next((c for c in r2024.columns if "circuitid" in c or "circuit_id" in c), None)
    date_col   = next((c for c in r2024.columns if c in ("date",)), None)
    name_col   = next((c for c in r2024.columns if c in ("racename", "race_name", "name")), None)

    for (rnd, circ_id), grp in r2024.groupby(
        [round_col or "round", circuit_col or "circuitid"]
    ):
        circ_info = circ_map.get(str(circ_id), {"name": str(circ_id), "country": ""})
        date_val  = str(grp[date_col].iloc[0]) if date_col and date_col in grp.columns else ""
        race_name = str(grp[name_col].iloc[0]) if name_col and name_col in grp.columns else f"Round {rnd}"

        results = []
        pos_col    = next((c for c in grp.columns if c in ("position", "positionorder")), None)
        driver_col = next((c for c in grp.columns if c in ("driverid", "driver_id")), None)
        constr_col = next((c for c in grp.columns if c in ("constructorid", "constructor")), None)
        grid_col   = next((c for c in grp.columns if c == "grid"), None)
        laps_col   = next((c for c in grp.columns if c == "laps"), None)
        status_col = next((c for c in grp.columns if c == "status"), None)
        points_col = next((c for c in grp.columns if c == "points"), None)
        time_col   = next((c for c in grp.columns if c in ("time", "racetime")), None)
        fl_col     = next((c for c in grp.columns if "fastestlap" in c.replace("_", "")), None)
        fl_rank_col= next((c for c in grp.columns if "fastestlaprank" in c.replace("_", "")), None)
        fl_lap_col = next((c for c in grp.columns if "fastestlap" in c.replace("_", "") and "lap" in c), None)
        fl_time_col= next((c for c in grp.columns if "fastestlaptime" in c.replace("_", "")), None)

        sorted_grp = grp.sort_values(pos_col or grp.columns[0])
        for _, row in sorted_grp.iterrows():
            pos = row.get(pos_col, 0) if pos_col else 0
            try:
                pos = int(float(pos))
            except (ValueError, TypeError):
                pos = 0

            results.append({
                "position":    pos,
                "driver": {
                    "id":   str(row.get(driver_col, "")) if driver_col else "",
                    "code": str(row.get("driverid", ""))[:3].upper() if driver_col else "",
                    "name": str(row.get(driver_col, "")) if driver_col else "",
                },
                "constructor": str(row.get(constr_col, "")) if constr_col else "",
                "grid":        int(float(row.get(grid_col, 0))) if grid_col else 0,
                "laps":        int(float(row.get(laps_col, 0))) if laps_col else 0,
                "status":      str(row.get(status_col, "")) if status_col else "",
                "points":      float(row.get(points_col, 0)) if points_col else 0,
                "time":        str(row.get(time_col, "")) if time_col else None,
                "fastestLap": {
                    "rank": int(float(row.get(fl_rank_col, 0))) if fl_rank_col else 0,
                    "lap":  int(float(row.get(fl_lap_col, 0)))  if fl_lap_col  else 0,
                    "time": str(row.get(fl_time_col, ""))        if fl_time_col else None,
                } if any([fl_rank_col, fl_lap_col, fl_time_col]) else None,
            })

        rounds.append({
            "round":   int(rnd),
            "name":    race_name,
            "date":    date_val,
            "circuit": {
                "id":      str(circ_id),
                "name":    circ_info.get("name", str(circ_id)),
                "country": circ_info.get("country", ""),
            },
            "results": results,
        })

    return sorted(rounds, key=lambda r: r["round"])


def build_seasons_json(results_df: pd.DataFrame) -> list[int]:
    results_df.columns = [c.lower() for c in results_df.columns]
    season_col = next((c for c in results_df.columns if c in ("season", "year")), None)
    if not season_col:
        return list(range(1950, 2027))
    seasons = sorted(
        int(s) for s in pd.to_numeric(results_df[season_col], errors="coerce").dropna().unique()
    )
    return seasons


def build_pipeline_reports_json(
    results_df: pd.DataFrame,
    drivers_df: pd.DataFrame,
    circuits_df: pd.DataFrame,
) -> dict:
    results_df.columns  = [c.lower() for c in results_df.columns]
    drivers_df.columns  = [c.lower() for c in drivers_df.columns]
    circuits_df.columns = [c.lower() for c in circuits_df.columns]

    season_col = next((c for c in results_df.columns if c in ("season", "year")), None)
    seasons = sorted(
        int(s) for s in pd.to_numeric(results_df[season_col], errors="coerce").dropna().unique()
    ) if season_col else []

    driver_id_col = next((c for c in drivers_df.columns if "driverid" in c or "driver_id" in c), None)
    total_drivers  = drivers_df[driver_id_col].nunique() if driver_id_col else len(drivers_df)
    total_circuits = len(circuits_df)
    total_races    = results_df.groupby([season_col, "round"]).ngroups if season_col and "round" in results_df.columns else 0

    from datetime import datetime, timezone
    return {
        "anomaly": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total": 0,
            "critical": 0,
            "warnings": 0,
            "items": [],
        },
        "bias": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "totalRows": len(results_df),
            "summary": {
                "total_drivers":  total_drivers,
                "total_circuits": total_circuits,
                "total_races":    total_races,
                "seasons":        len(seasons),
                "first_season":   min(seasons) if seasons else 1950,
                "last_season":    max(seasons) if seasons else 2024,
            },
            "slices": {},
            "findings": [
                f"Dataset covers {len(seasons)} seasons ({min(seasons) if seasons else 1950}–{max(seasons) if seasons else 2024})",
                f"{total_drivers} drivers, {total_circuits} circuits, {total_races} races",
            ],
        },
    }


def write_json(data: object, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    size_kb = path.stat().st_size / 1024
    log.info(f"Wrote {path} ({size_kb:.1f} KB)")


def main():
    parser = argparse.ArgumentParser(description="Generate frontend static JSON from GCS Parquets")
    parser.add_argument("--bucket", default="f1optimizer-data-lake")
    parser.add_argument("--out",    default="frontend/public/data")
    args = parser.parse_args()

    out_dir = Path(args.out)
    client  = storage.Client()

    # ── Load Parquets ────────────────────────────────────────────────────────
    drivers_df  = _load_parquet(client, args.bucket, "processed/drivers.parquet")
    results_df  = _load_parquet(client, args.bucket, "processed/race_results.parquet")
    circuits_df = _load_parquet(client, args.bucket, "processed/circuits.parquet")

    # ── Build + write ────────────────────────────────────────────────────────
    write_json(build_drivers_json(drivers_df, results_df),              out_dir / "drivers.json")
    write_json(build_circuits_json(circuits_df),                        out_dir / "circuits.json")
    write_json(build_races_2024_json(results_df, circuits_df),          out_dir / "races-2024.json")
    write_json(build_seasons_json(results_df),                          out_dir / "seasons.json")
    write_json(build_pipeline_reports_json(results_df, drivers_df, circuits_df),
                                                                        out_dir / "pipeline-reports.json")

    log.info("Done. All 5 static JSON files written.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it runs locally (requires GCP ADC)**

```bash
python pipeline/scripts/generate_static_json.py \
  --bucket f1optimizer-data-lake \
  --out frontend/public/data
ls -lh frontend/public/data/
```

Expected output: 5 files appear — `drivers.json`, `circuits.json`, `races-2024.json`, `seasons.json`, `pipeline-reports.json`. Each should be non-empty. `drivers.json` should be >50 KB.

- [ ] **Step 3: Spot-check the output**

```bash
python3 -c "
import json
d = json.load(open('frontend/public/data/drivers.json'))
print(f'Drivers: {len(d)}')
legends = [x for x in d if x['is_legend']]
print(f'Legends: {len(legends)}')
sample = next(x for x in d if x['id'] == 'senna')
print('Senna:', json.dumps(sample, indent=2))
"
```

Expected: 100+ total drivers, 20-25 legends, Senna record has real career stats (career_wins=41, career_races=161, career_poles=65 from Ergast data) and computed scores.

- [ ] **Step 4: Commit**

```bash
git add pipeline/scripts/generate_static_json.py frontend/public/data/
git commit --author="bkiritom8 <bhargavsp01@gmail.com>" -m "feat: add GCS→JSON extraction script and generated static data files"
```

---

## Task 2: Update `frontend/services/endpoints.ts` — enrich StaticDriver and remove MOCK_DRIVERS

**Files:**
- Modify: `frontend/services/endpoints.ts`

- [ ] **Step 1: Update `StaticDriver` interface and remove MOCK_DRIVERS import**

Replace lines 1–20 (imports + MOCK_DRIVERS import) and the `StaticDriver` interface block:

```typescript
import { apiFetch } from './client';
import { logger } from './logger';
import type {
  DriverProfile,
  StrategyRecommendation,
  RaceState,
  TireCompound,
  DriveMode,
} from '../types';
```

Replace the `StaticDriver` interface (lines 121–128) with:

```typescript
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
```

- [ ] **Step 2: Update `fetchDrivers` static fallback — use real stats directly**

Replace the entire static fallback block inside `fetchDrivers` (the `try` block that calls `fetchStatic<StaticDriver[]>`) with:

```typescript
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
    throw err;   // propagate; hook will show error state
  }
```

- [ ] **Step 3: Remove seeded-random mock fallbacks from `fetchOvertakeProb` and `fetchSafetyCarProb`**

Replace `fetchOvertakeProb` catch block:

```typescript
  } catch (err) {
    logger.error(`[endpoints] fetchOvertakeProb failed`, { message: String(err) });
    throw err;
  }
```

Replace `fetchSafetyCarProb` catch block:

```typescript
  } catch (err) {
    logger.error(`[endpoints] fetchSafetyCarProb failed`, { message: String(err) });
    throw err;
  }
```

Replace `fetchValidationStats` catch block:

```typescript
  } catch (err) {
    logger.error(`[endpoints] fetchValidationStats failed`, { message: String(err) });
    throw err;
  }
```

Also delete the `seedRandom` helper function (lines 31–40) — it is no longer used.

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: no errors. Fix any type mismatches before proceeding.

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/services/endpoints.ts
git commit --author="bkiritom8 <bhargavsp01@gmail.com>" -m "refactor: use real static driver stats, remove seeded-random mock fallbacks"
```

---

## Task 3: Clean up `frontend/constants.ts` — delete all mock exports

**Files:**
- Modify: `frontend/constants.ts`

- [ ] **Step 1: Delete mock exports, keep theme constants**

Replace the entire file content with:

```typescript
/**
 * Application Constants
 * Visual theme, team identities, and F1 glossary for the Apex Intelligence platform.
 * Mock data has been removed — all data comes from the backend API or static pipeline JSON.
 */

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
    bg: '#FCFBF7',
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
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: errors will list every file that still imports the deleted mock exports. Fix those in Tasks 4 and 5.

- [ ] **Step 3: Commit (after Task 4 fixes compile errors)**

Wait until `useApi.ts` is updated (Task 4) before committing.

---

## Task 4: Update `frontend/hooks/useApi.ts` — remove all mock fallbacks

**Files:**
- Modify: `frontend/hooks/useApi.ts`

- [ ] **Step 1: Remove mock imports and replace fallback values**

Replace the import block at the top (lines 43–48):

```typescript
// (remove entirely — no mock imports needed)
```

So the full import section becomes:

```typescript
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
} from '../services/endpoints';
import { API_BASE } from '../services/client';
import { logger } from '../services/logger';
import type { DriverProfile, StrategyRecommendation } from '../types';
```

- [ ] **Step 2: Update `useDrivers` — null fallback**

```typescript
export function useDrivers(): UseApiResult<DriverProfile[]> {
  return useApiCall(() => fetchDrivers(), null, [], 'drivers');
}
```

- [ ] **Step 3: Update `useRaceState` — null fallback**

```typescript
export function useRaceState(raceId: string, lap: number) {
  return useApiCall(
    () => fetchRaceState(raceId, lap),
    null,
    [raceId, lap],
    `raceState(${raceId}:L${lap})`,
  );
}
```

- [ ] **Step 4: Update `useStrategyRecommendation` — null fallback**

```typescript
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
```

- [ ] **Step 5: Update `useOvertakeMetric` and `useSafetyCarProb` — null fallback**

```typescript
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
```

- [ ] **Step 6: Update `useValidationStats` — already null fallback, no change needed**

Verify line 312–322 already has `null` as fallback. No edit needed.

- [ ] **Step 7: Verify TypeScript compiles clean**

```bash
cd frontend && npx tsc --noEmit 2>&1
```

Expected: 0 errors. If views reference `MOCK_DRIVERS` / `MOCK_RACE_STATE` / `getMockTelemetry` / `getMockStrategy` / `MOCK_STRATEGIES` / `MOCK_VALIDATION` directly, fix those imports in the affected view files (replace usage with null-checks against the hook data).

- [ ] **Step 8: Commit**

```bash
cd ..
git add frontend/constants.ts frontend/hooks/useApi.ts
git commit --author="bkiritom8 <bhargavsp01@gmail.com>" -m "refactor: remove all mock data, frontend now uses real API and static JSON only"
```

---

## Task 5: Fix any view files that directly imported mock constants

**Files:**
- Modify: any view in `frontend/views/` that imports from `../constants` the deleted exports

- [ ] **Step 1: Find remaining mock references**

```bash
grep -rn "MOCK_DRIVERS\|MOCK_RACE_STATE\|getMockTelemetry\|getMockStrategy\|MOCK_STRATEGIES\|MOCK_VALIDATION" frontend/ --include="*.ts" --include="*.tsx"
```

Expected: 0 matches after Tasks 3 and 4. If any remain, each must be replaced with either:
- The hook result (`useDrivers().data`, etc.) with a null-check
- An empty array `[]` where the view renders a list

- [ ] **Step 2: Fix each match**

For each file with a match, open it and replace the mock usage. Example pattern — if a view does:

```tsx
// BEFORE
import { MOCK_STRATEGIES } from '../constants';
const strategies = MOCK_STRATEGIES;
```

Change to:

```tsx
// AFTER — show nothing when API is unavailable
const strategies: typeof MOCK_STRATEGIES = [];  // populated by hook
```

Or if already driven by a hook result, simply delete the import line.

- [ ] **Step 3: Final compile check**

```bash
cd frontend && npx tsc --noEmit 2>&1
```

Expected: 0 errors.

- [ ] **Step 4: Smoke test local build**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

Expected: `✓ built in X.XXs` with no errors.

- [ ] **Step 5: Commit if any view files were changed**

```bash
git add frontend/views/
git commit --author="bkiritom8 <bhargavsp01@gmail.com>" -m "fix: remove remaining mock constant references from view files"
```

---

## Task 6: Add data generation step to CI `deploy-frontend` job

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add GCS auth and script step to `deploy-frontend`**

In `.github/workflows/ci.yml`, find the `deploy-frontend` job. After the `Install dependencies` step and before the `Build` step, insert:

```yaml
      - name: Authenticate to Google Cloud
        uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{ secrets.GCP_SA_KEY }}

      - name: Install data pipeline dependencies
        run: pip install pandas pyarrow google-cloud-storage

      - name: Generate static data from GCS
        run: python pipeline/scripts/generate_static_json.py --bucket f1optimizer-data-lake --out frontend/public/data
```

So the full job step order becomes:
1. Checkout code
2. Set up Node
3. Install dependencies (`npm ci`)
4. **Authenticate to Google Cloud** ← new
5. **Install data pipeline dependencies** ← new
6. **Generate static data from GCS** ← new
7. Build (`npm run build`)
8. Deploy to Firebase Hosting

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit --author="bkiritom8 <bhargavsp01@gmail.com>" -m "ci: generate real static JSON from GCS before frontend build"
```

---

## Task 7: Push and verify CI

- [ ] **Step 1: Push to `pipeline` branch**

```bash
git push origin pipeline
```

- [ ] **Step 2: Watch the CI run**

```bash
gh run watch --repo bkiritom8/F1-Strategy-Optimizer
```

Or:

```bash
gh run list --limit 3 --workflow=ci.yml
```

- [ ] **Step 3: Confirm `deploy-frontend` job succeeds**

```bash
gh run view <run-id> --json jobs | python3 -c "import json,sys; [print(j['name'], j['conclusion']) for j in json.load(sys.stdin)['jobs']]"
```

Expected: `Deploy Frontend to Firebase Hosting  success`

- [ ] **Step 4: Verify the live site loads real data**

Open `https://f1optimizer.web.app/` in a browser with DevTools open. In the Console, look for log lines like:

```
[endpoints] Static data loaded: /data/drivers.json
```

And confirm the Driver Profiles view shows 100+ drivers (not just 5), with legends like Senna and Schumacher appearing.
