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

GCS Parquet schemas (actual):
    drivers.parquet       — driverId, givenName, familyName, dateOfBirth, nationality,
                            permanentNumber, code, url
    race_results.parquet  — number, position, positionText, points, Driver (dict),
                            Constructor (dict), grid, laps, status, Time (dict),
                            season, round, raceName, circuitId, FastestLap
    circuits.parquet      — circuitId, circuitName, Location (dict with lat/long/locality/country), url
"""

import argparse
import ast
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
    "lauda", "stewart", "ascari", "moss", "hill",
    "mansell", "villeneuve",
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


def _parse_dict_col(val):
    """Safely parse a column value that may be a dict, str repr of dict, or None."""
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            return ast.literal_eval(val)
        except Exception:
            return {}
    return {}


def _expand_race_results(df: pd.DataFrame) -> pd.DataFrame:
    """
    Flatten the nested Driver and Constructor columns in race_results.
    Input columns: Driver (dict), Constructor (dict), ...
    Output adds: driverid, givenname, familyname, constructorid
    """
    df = df.copy()
    driver_ids, given_names, family_names, constructor_ids = [], [], [], []
    for _, row in df.iterrows():
        d = _parse_dict_col(row.get("Driver") or row.get("driver"))
        c = _parse_dict_col(row.get("Constructor") or row.get("constructor"))
        driver_ids.append(d.get("driverId", d.get("driverid", "")))
        given_names.append(d.get("givenName", d.get("givenname", "")))
        family_names.append(d.get("familyName", d.get("familyname", "")))
        constructor_ids.append(c.get("constructorId", c.get("constructorid", "")))
    df["driverid"]      = driver_ids
    df["givenname"]     = given_names
    df["familyname"]    = family_names
    df["constructorid"] = constructor_ids
    return df


def _expand_circuits(df: pd.DataFrame) -> pd.DataFrame:
    """
    Flatten the nested Location column in circuits.
    Input columns: circuitId, circuitName, Location (dict), url
    Output adds: lat, lng, locality, country, name (alias of circuitName)
    """
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    lats, lngs, localities, countries = [], [], [], []
    for _, row in df.iterrows():
        loc = _parse_dict_col(row.get("location"))
        try:
            lat = float(loc.get("lat", 0) or 0)
        except (ValueError, TypeError):
            lat = 0.0
        try:
            lng = float(loc.get("long", loc.get("lng", 0)) or 0)
        except (ValueError, TypeError):
            lng = 0.0
        if math.isnan(lat): lat = 0.0
        if math.isnan(lng): lng = 0.0
        lats.append(lat)
        lngs.append(lng)
        localities.append(loc.get("locality", ""))
        countries.append(loc.get("country", ""))
    df["lat"]      = lats
    df["lng"]      = lngs
    df["locality"] = localities
    df["country"]  = countries
    # circuitname → name alias for compatibility
    if "circuitname" in df.columns and "name" not in df.columns:
        df["name"] = df["circuitname"]
    return df


def compute_driver_scores(wins: int, podiums: int, poles: int, races: int) -> dict:
    """Derive 10 skill scores from real career statistics."""
    if races == 0:
        return {k: 50.0 for k in [
            "aggression_score", "consistency_score", "pressure_response",
            "tire_management", "wet_weather_skill", "qualifying_pace",
            "race_pace", "overtaking_ability", "defensive_ability", "fuel_efficiency"
        ]}

    win_rate  = wins   / races
    pod_rate  = podiums / races
    pole_rate = poles  / races
    lead_wins = max(0, wins - poles)

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
) -> list:
    drivers_df = drivers_df.copy()
    results_df = results_df.copy()
    drivers_df.columns = [c.lower() for c in drivers_df.columns]
    results_df.columns = [c.lower() for c in results_df.columns]

    # Flatten nested Driver/Constructor columns in race_results
    results_df = _expand_race_results(results_df)

    # ── Career stats aggregation ─────────────────────────────────────────────
    pos_col    = next((c for c in results_df.columns if c == "position"), None)
    grid_col   = next((c for c in results_df.columns if c == "grid"), None)
    season_col = next((c for c in results_df.columns if c in ("season", "year")), None)
    round_col  = next((c for c in results_df.columns if c == "round"), None)
    driver_col = "driverid"  # added by _expand_race_results

    if driver_col not in results_df.columns or pos_col is None:
        log.warning("race_results missing required columns; skipping stats")
        stats = pd.DataFrame(columns=["driverid", "career_races", "career_wins", "career_podiums", "career_poles", "first_season", "last_season"])
    else:
        agg = (
            results_df[results_df[pos_col].notna()]
            .assign(
                _pos  = lambda d: pd.to_numeric(d[pos_col],  errors="coerce"),
                _grid = lambda d: pd.to_numeric(d[grid_col], errors="coerce") if grid_col else 0,
            )
            .dropna(subset=["_pos"])
            .assign(
                is_win    = lambda d: (d["_pos"] == 1).astype(int),
                is_podium = lambda d: (d["_pos"] <= 3).astype(int),
                is_pole   = lambda d: (d["_grid"] == 1).astype(int) if grid_col else 0,
            )
            .groupby(driver_col)
            .agg(
                career_races    =("is_win",    "count"),
                career_wins     =("is_win",    "sum"),
                career_podiums  =("is_podium", "sum"),
                career_poles    =("is_pole",   "sum"),
                first_season    =(season_col,  "min") if season_col else ("is_win", "count"),
                last_season     =(season_col,  "max") if season_col else ("is_win", "count"),
            )
            .reset_index()
            .rename(columns={driver_col: "driverid"})
        )
        stats = agg

    # ── Normalise drivers_df id column ───────────────────────────────────────
    id_col = next(
        (c for c in drivers_df.columns if c in ("driverid", "driver_id", "driverref")),
        drivers_df.columns[0]
    )
    drivers_df = drivers_df.rename(columns={id_col: "driverid"})
    merged = drivers_df.merge(stats, on="driverid", how="left")

    for col in ["career_races", "career_wins", "career_podiums", "career_poles", "first_season", "last_season"]:
        merged[col] = pd.to_numeric(merged.get(col, 0), errors="coerce").fillna(0).astype(int)

    # ── Filter ───────────────────────────────────────────────────────────────
    is_modern = merged["last_season"] >= MODERN_CUTOFF_SEASON
    is_legend = merged["driverid"].isin(LEGEND_IDS)
    subset = merged[is_modern | is_legend].copy()
    log.info(f"Drivers: {len(subset)} total ({is_modern.sum()} modern, {is_legend.sum()} legends)")

    # ── Build records ────────────────────────────────────────────────────────
    records = []
    for _, row in subset.iterrows():
        given  = str(row.get("givenname",  row.get("given_name",  ""))).strip()
        family = str(row.get("familyname", row.get("family_name", ""))).strip()
        name   = f"{given} {family}".strip() or str(row["driverid"])

        w, p, po, r = int(row["career_wins"]), int(row["career_podiums"]), int(row["career_poles"]), int(row["career_races"])
        scores = compute_driver_scores(w, p, po, r)
        fs, ls = int(row["first_season"]), int(row["last_season"])

        records.append({
            "id":             str(row["driverid"]),
            "name":           name,
            "code":           str(row.get("code", "")) or None,
            "number":         str(row.get("permanentnumber", row.get("number", ""))) or None,
            "nationality":    str(row.get("nationality", "")) or None,
            "dob":            str(row.get("dateofbirth", row.get("dob", ""))) or None,
            "career_races":   r,
            "career_wins":    w,
            "career_podiums": p,
            "career_poles":   po,
            "first_season":   fs,
            "last_season":    ls,
            "experience_years": max(1, ls - fs + 1) if ls > 0 else 1,
            "rookie_status":  r < 25,
            "is_legend":      str(row["driverid"]) in LEGEND_IDS,
            **scores,
        })

    return sorted(records, key=lambda d: (-d["career_races"], d["name"]))


def build_circuits_json(circuits_df: pd.DataFrame) -> list:
    circuits_df = _expand_circuits(circuits_df)
    records = []
    for _, row in circuits_df.iterrows():
        lat = float(row.get("lat", 0) or 0)
        lng = float(row.get("lng", 0) or 0)
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


def build_races_2024_json(results_df: pd.DataFrame, circuits_df: pd.DataFrame) -> list:
    results_df  = results_df.copy()
    results_df.columns  = [c.lower() for c in results_df.columns]
    results_df = _expand_race_results(results_df)

    circuits_df = _expand_circuits(circuits_df)

    season_col = next((c for c in results_df.columns if c in ("season", "year")), None)
    if season_col is None:
        log.warning("No season column; returning empty races list")
        return []

    r2024 = results_df[pd.to_numeric(results_df[season_col], errors="coerce") == 2024].copy()
    if r2024.empty:
        log.warning("No 2024 results found")
        return []

    circ_map = circuits_df.set_index("circuitid")[["name", "country"]].to_dict("index")

    round_col   = next((c for c in r2024.columns if c == "round"), None)
    circuit_col = next((c for c in r2024.columns if "circuitid" in c or "circuit_id" in c), None)
    date_col    = next((c for c in r2024.columns if c == "date"), None)
    name_col    = next((c for c in r2024.columns if c in ("racename", "race_name", "name")), None)
    pos_col     = next((c for c in r2024.columns if c in ("position", "positionorder")), None)
    driver_col  = "driverid"  # flattened by _expand_race_results
    constr_col  = "constructorid"  # flattened by _expand_race_results
    grid_col    = next((c for c in r2024.columns if c == "grid"), None)
    laps_col    = next((c for c in r2024.columns if c == "laps"), None)
    status_col  = next((c for c in r2024.columns if c == "status"), None)
    points_col  = next((c for c in r2024.columns if c == "points"), None)
    time_col    = next((c for c in r2024.columns if c in ("time", "racetime")), None)

    group_keys = [k for k in [round_col, circuit_col] if k]
    if not group_keys:
        return []

    rounds = []
    for group_vals, grp in r2024.groupby(group_keys):
        rnd, circ_id = (group_vals if len(group_keys) == 2 else (group_vals, ""))
        circ_info = circ_map.get(str(circ_id), {"name": str(circ_id), "country": ""})
        date_val  = str(grp[date_col].iloc[0]) if date_col else ""
        race_name = str(grp[name_col].iloc[0]) if name_col else f"Round {rnd}"

        results = []
        sorted_grp = grp.sort_values(pos_col) if pos_col else grp
        for _, row in sorted_grp.iterrows():
            try: pos = int(float(row.get(pos_col, 0)))
            except: pos = 0
            try: grid = int(float(row.get(grid_col, 0)))
            except: grid = 0
            try: laps = int(float(row.get(laps_col, 0)))
            except: laps = 0
            try: pts = float(row.get(points_col, 0))
            except: pts = 0.0

            drv_id = str(row.get(driver_col, ""))
            results.append({
                "position":    pos,
                "driver":      {"id": drv_id, "code": drv_id[:3].upper(), "name": drv_id},
                "constructor": str(row.get(constr_col, "")) if constr_col else "",
                "grid":        grid,
                "laps":        laps,
                "status":      str(row.get(status_col, "")) if status_col else "",
                "points":      pts,
                "time":        str(row.get(time_col, "")) if time_col else None,
                "fastestLap":  None,
            })

        rounds.append({
            "round":   int(rnd),
            "name":    race_name,
            "date":    date_val,
            "circuit": {"id": str(circ_id), "name": circ_info.get("name", str(circ_id)), "country": circ_info.get("country", "")},
            "results": results,
        })

    return sorted(rounds, key=lambda r: r["round"])


def build_seasons_json(results_df: pd.DataFrame) -> list:
    results_df = results_df.copy()
    results_df.columns = [c.lower() for c in results_df.columns]
    season_col = next((c for c in results_df.columns if c in ("season", "year")), None)
    if not season_col:
        return list(range(1950, 2027))
    return sorted(int(s) for s in pd.to_numeric(results_df[season_col], errors="coerce").dropna().unique())


def build_pipeline_reports_json(results_df, drivers_df, circuits_df) -> dict:
    results_df  = results_df.copy()
    drivers_df  = drivers_df.copy()
    circuits_df = circuits_df.copy()
    results_df.columns  = [c.lower() for c in results_df.columns]
    drivers_df.columns  = [c.lower() for c in drivers_df.columns]
    circuits_df.columns = [c.lower() for c in circuits_df.columns]

    season_col = next((c for c in results_df.columns if c in ("season", "year")), None)
    seasons = sorted(int(s) for s in pd.to_numeric(results_df[season_col], errors="coerce").dropna().unique()) if season_col else []
    driver_id_col = next((c for c in drivers_df.columns if "driverid" in c or "driver_id" in c), None)
    total_drivers  = drivers_df[driver_id_col].nunique() if driver_id_col else len(drivers_df)
    total_circuits = len(circuits_df)
    total_races    = results_df.groupby([season_col, "round"]).ngroups if season_col and "round" in results_df.columns else 0

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    return {
        "anomaly": {"timestamp": now, "total": 0, "critical": 0, "warnings": 0, "items": []},
        "bias": {
            "timestamp": now,
            "totalRows": len(results_df),
            "summary": {
                "total_drivers":  int(total_drivers),
                "total_circuits": int(total_circuits),
                "total_races":    int(total_races),
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
    log.info(f"Wrote {path} ({path.stat().st_size / 1024:.1f} KB)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", default="f1optimizer-data-lake")
    parser.add_argument("--out",    default="frontend/public/data")
    args = parser.parse_args()

    out_dir = Path(args.out)
    client  = storage.Client()

    drivers_df  = _load_parquet(client, args.bucket, "processed/drivers.parquet")
    results_df  = _load_parquet(client, args.bucket, "processed/race_results.parquet")
    circuits_df = _load_parquet(client, args.bucket, "processed/circuits.parquet")

    write_json(build_drivers_json(drivers_df, results_df),                          out_dir / "drivers.json")
    write_json(build_circuits_json(circuits_df),                                    out_dir / "circuits.json")
    write_json(build_races_2024_json(results_df, circuits_df),                      out_dir / "races-2024.json")
    write_json(build_seasons_json(results_df),                                      out_dir / "seasons.json")
    write_json(build_pipeline_reports_json(results_df, drivers_df, circuits_df),    out_dir / "pipeline-reports.json")

    log.info("Done.")


if __name__ == "__main__":
    main()
