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

# Real career stats for legends — used when not present in GCS drivers.parquet
LEGEND_STUBS: dict = {
    "fangio":             {"name": "Juan Manuel Fangio",  "nationality": "Argentine",  "dob": "1911-06-24", "career_races": 51,  "career_wins": 24, "career_podiums": 35,  "career_poles": 29, "first_season": 1950, "last_season": 1958},
    "senna":              {"name": "Ayrton Senna",         "nationality": "Brazilian",  "dob": "1960-03-21", "career_races": 161, "career_wins": 41, "career_podiums": 80,  "career_poles": 65, "first_season": 1984, "last_season": 1994},
    "michael_schumacher": {"name": "Michael Schumacher",  "nationality": "German",     "dob": "1969-01-03", "career_races": 307, "career_wins": 91, "career_podiums": 155, "career_poles": 68, "first_season": 1991, "last_season": 2012},
    "prost":              {"name": "Alain Prost",          "nationality": "French",     "dob": "1955-02-24", "career_races": 202, "career_wins": 51, "career_podiums": 106, "career_poles": 33, "first_season": 1980, "last_season": 1993},
    "clark":              {"name": "Jim Clark",            "nationality": "British",    "dob": "1936-03-04", "career_races": 72,  "career_wins": 25, "career_podiums": 32,  "career_poles": 33, "first_season": 1960, "last_season": 1968},
    "lauda":              {"name": "Niki Lauda",           "nationality": "Austrian",   "dob": "1949-02-22", "career_races": 171, "career_wins": 25, "career_podiums": 54,  "career_poles": 24, "first_season": 1971, "last_season": 1985},
    "stewart":            {"name": "Jackie Stewart",       "nationality": "British",    "dob": "1939-06-11", "career_races": 99,  "career_wins": 27, "career_podiums": 43,  "career_poles": 17, "first_season": 1965, "last_season": 1973},
    "ascari":             {"name": "Alberto Ascari",       "nationality": "Italian",    "dob": "1918-07-13", "career_races": 32,  "career_wins": 13, "career_podiums": 17,  "career_poles": 14, "first_season": 1950, "last_season": 1955},
    "moss":               {"name": "Stirling Moss",        "nationality": "British",    "dob": "1929-09-17", "career_races": 66,  "career_wins": 16, "career_podiums": 24,  "career_poles": 16, "first_season": 1951, "last_season": 1962},
    "hill":               {"name": "Graham Hill",          "nationality": "British",    "dob": "1929-02-15", "career_races": 176, "career_wins": 14, "career_podiums": 51,  "career_poles": 13, "first_season": 1958, "last_season": 1975},
    "mansell":            {"name": "Nigel Mansell",        "nationality": "British",    "dob": "1953-08-08", "career_races": 187, "career_wins": 31, "career_podiums": 59,  "career_poles": 32, "first_season": 1980, "last_season": 1995},
    "villeneuve":         {"name": "Gilles Villeneuve",    "nationality": "Canadian",   "dob": "1950-01-18", "career_races": 67,  "career_wins": 6,  "career_podiums": 13,  "career_poles": 2,  "first_season": 1977, "last_season": 1982},
    "brabham":            {"name": "Jack Brabham",         "nationality": "Australian", "dob": "1926-04-02", "career_races": 126, "career_wins": 14, "career_podiums": 31,  "career_poles": 13, "first_season": 1955, "last_season": 1970},
    "piquet":             {"name": "Nelson Piquet",        "nationality": "Brazilian",  "dob": "1952-08-17", "career_races": 204, "career_wins": 23, "career_podiums": 60,  "career_poles": 24, "first_season": 1978, "last_season": 1991},
    "surtees":            {"name": "John Surtees",         "nationality": "British",    "dob": "1934-02-11", "career_races": 111, "career_wins": 6,  "career_podiums": 24,  "career_poles": 8,  "first_season": 1960, "last_season": 1972},
    "hakkinen":           {"name": "Mika Häkkinen",        "nationality": "Finnish",    "dob": "1968-09-28", "career_races": 161, "career_wins": 20, "career_podiums": 51,  "career_poles": 26, "first_season": 1991, "last_season": 2001},
    "andretti":           {"name": "Mario Andretti",       "nationality": "American",   "dob": "1940-02-28", "career_races": 128, "career_wins": 12, "career_podiums": 19,  "career_poles": 18, "first_season": 1968, "last_season": 1982},
    "rindt":              {"name": "Jochen Rindt",         "nationality": "Austrian",   "dob": "1942-04-18", "career_races": 60,  "career_wins": 6,  "career_podiums": 13,  "career_poles": 10, "first_season": 1964, "last_season": 1970},
    "fittipaldi":         {"name": "Emerson Fittipaldi",   "nationality": "Brazilian",  "dob": "1946-12-12", "career_races": 144, "career_wins": 14, "career_podiums": 35,  "career_poles": 6,  "first_season": 1970, "last_season": 1980},
    "farina":             {"name": "Nino Farina",          "nationality": "Italian",    "dob": "1906-10-30", "career_races": 33,  "career_wins": 5,  "career_podiums": 20,  "career_poles": 5,  "first_season": 1950, "last_season": 1955},
    "hulme":              {"name": "Denny Hulme",          "nationality": "New Zealander", "dob": "1936-06-18", "career_races": 112, "career_wins": 8, "career_podiums": 33, "career_poles": 1,  "first_season": 1965, "last_season": 1974},
    "hunt":               {"name": "James Hunt",           "nationality": "British",    "dob": "1947-08-29", "career_races": 92,  "career_wins": 10, "career_podiums": 23,  "career_poles": 14, "first_season": 1973, "last_season": 1979},
    "raikkonen":          {"name": "Kimi Räikkönen",       "nationality": "Finnish",    "dob": "1979-10-17", "career_races": 353, "career_wins": 21, "career_podiums": 103, "career_poles": 18, "first_season": 2001, "last_season": 2021},
    "scheckter":          {"name": "Jody Scheckter",       "nationality": "South African", "dob": "1950-01-29", "career_races": 112, "career_wins": 10, "career_podiums": 33, "career_poles": 3, "first_season": 1972, "last_season": 1980},
    "hawthorn":           {"name": "Mike Hawthorn",        "nationality": "British",    "dob": "1929-04-10", "career_races": 45,  "career_wins": 3,  "career_podiums": 18,  "career_poles": 4,  "first_season": 1952, "last_season": 1958},
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
        agg_dict = {
            "career_races":   ("is_win",    "count"),
            "career_wins":    ("is_win",    "sum"),
            "career_podiums": ("is_podium", "sum"),
            "career_poles":   ("is_pole",   "sum"),
        }
        if season_col:
            agg_dict["first_season"] = (season_col, "min")
            agg_dict["last_season"]  = (season_col, "max")

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
            .agg(**agg_dict)
            .reset_index()
            .rename(columns={driver_col: "driverid"})
        )
        if "first_season" not in agg.columns:
            agg["first_season"] = 0
            agg["last_season"]  = 0
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

    # ── Inject legend stubs for any legends absent from GCS parquet ──────────
    present_ids = {r["id"] for r in records}
    for lid, stub in LEGEND_STUBS.items():
        if lid not in present_ids:
            w, p, po, r_count = stub["career_wins"], stub["career_podiums"], stub.get("career_poles", 0), stub["career_races"]
            scores = compute_driver_scores(w, p, po, r_count)
            fs, ls = stub["first_season"], stub["last_season"]
            records.append({
                "id":             lid,
                "name":           stub["name"],
                "code":           None,
                "number":         None,
                "nationality":    stub.get("nationality"),
                "dob":            stub.get("dob"),
                "career_races":   r_count,
                "career_wins":    w,
                "career_podiums": p,
                "career_poles":   po,
                "first_season":   fs,
                "last_season":    ls,
                "experience_years": max(1, ls - fs + 1),
                "rookie_status":  False,
                "is_legend":      True,
                **scores,
            })
            log.info(f"Injected legend stub: {lid} ({stub['name']})")

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
        if len(group_keys) == 2:
            rnd, circ_id = group_vals
        else:
            rnd = group_vals if round_col else 0
            circ_id = group_vals if circuit_col and not round_col else ""
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
