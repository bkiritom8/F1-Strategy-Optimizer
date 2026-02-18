"""
FastF1 ingestion — sessions from 2018 onwards.
Populates: lap_features, telemetry_features, weather, driver_profiles.

Driver profile metrics:
  aggression_score  = mean of per-lap max throttle (from telemetry)
  consistency_score = 1 / stddev(lap_time_seconds)
  total_laps        = count of laps with telemetry data

FastF1 cache stored at /tmp/fastf1_cache (configurable via FASTF1_CACHE env var).

Usage:
    python -m src.ingestion.fastf1_ingestion [--start-year 2018] [--end-year 2024]
"""

import argparse
import datetime
import logging
import os
import time
from typing import Optional

import fastf1
import pandas as pd

from src.database.connection import ManagedConnection

logger = logging.getLogger(__name__)

FASTF1_CACHE = os.environ.get("FASTF1_CACHE", "/tmp/fastf1_cache")
START_YEAR = 2018
_SESSION_DELAY = 1.0  # seconds between session loads


def _setup_cache() -> None:
    os.makedirs(FASTF1_CACHE, exist_ok=True)
    fastf1.Cache.enable_cache(FASTF1_CACHE)
    logger.info("FastF1 cache: %s", FASTF1_CACHE)


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------


def _ingest_weather(
    conn,
    session: fastf1.core.Session,
    season: int,
    round_num: int,
    circuit_id: str,
    session_type: str,
) -> None:
    weather = session.weather_data
    if weather is None or len(weather) == 0:
        return
    for _, row in weather.iterrows():
        ts = row.get("Time")
        ts_str = str(ts) if pd.notna(ts) else None

        def _f(col: str) -> Optional[float]:
            v = row.get(col)
            return float(v) if pd.notna(v) else None

        try:
            conn.run(
                """INSERT INTO weather
                     (season, round, circuit_id, session_type,
                      air_temp, track_temp, humidity, pressure,
                      wind_speed, wind_direction, rainfall, timestamp)
                   VALUES
                     (:season, :round, :circuit_id, :session_type,
                      :air_temp, :track_temp, :humidity, :pressure,
                      :wind_speed, :wind_direction, :rainfall, :timestamp)
                   ON CONFLICT (season, round, circuit_id, session_type, timestamp)
                   DO NOTHING""",
                season=season,
                round=round_num,
                circuit_id=circuit_id,
                session_type=session_type,
                air_temp=_f("AirTemp"),
                track_temp=_f("TrackTemp"),
                humidity=_f("Humidity"),
                pressure=_f("Pressure"),
                wind_speed=_f("WindSpeed"),
                wind_direction=_f("WindDirection"),
                rainfall=bool(row.get("Rainfall", False)),
                timestamp=ts_str,
            )
        except Exception as exc:
            logger.debug("weather row insert failed: %s", exc)


# ---------------------------------------------------------------------------
# Lap features
# ---------------------------------------------------------------------------


def _ingest_lap_features(
    conn,
    session: fastf1.core.Session,
    season: int,
    round_num: int,
    circuit_id: str,
) -> None:
    laps = session.laps
    if laps is None or len(laps) == 0:
        return
    weather = session.weather_data

    for _, lap in laps.iterrows():
        lap_time = lap.get("LapTime")
        lap_time_s = lap_time.total_seconds() if pd.notna(lap_time) else None

        def _sector(col: str) -> Optional[float]:
            v = lap.get(col)
            return v.total_seconds() if pd.notna(v) else None

        # Nearest weather reading at lap start
        track_temp: Optional[float] = None
        air_temp: Optional[float] = None
        if weather is not None and len(weather) > 0:
            lap_start = lap.get("LapStartTime")
            if pd.notna(lap_start):
                mask = weather.get("Time", pd.Series(dtype="object")) <= lap_start
                if mask.any():
                    w = weather[mask].iloc[-1]
                    track_temp = (
                        float(w["TrackTemp"]) if pd.notna(w.get("TrackTemp")) else None
                    )
                    air_temp = (
                        float(w["AirTemp"]) if pd.notna(w.get("AirTemp")) else None
                    )

        track_status = str(lap.get("TrackStatus", ""))
        is_sc = track_status in {"4", "5", "6", "7"}

        driver_id = str(lap.get("Driver", "")).lower()
        compound = lap.get("Compound")
        tyre_life = lap.get("TyreLife")
        stint = lap.get("Stint")

        try:
            conn.run(
                """INSERT INTO lap_features
                     (season, round, circuit_id, driver_id, lap_number,
                      lap_time_seconds, sector1_time, sector2_time, sector3_time,
                      compound, tyre_life, stint_number, fuel_load_estimate,
                      track_temp, air_temp, is_safety_car)
                   VALUES
                     (:season, :round, :circuit_id, :driver_id, :lap_number,
                      :lap_time_seconds, :s1, :s2, :s3,
                      :compound, :tyre_life, :stint, :fuel_load,
                      :track_temp, :air_temp, :is_sc)
                   ON CONFLICT (season, round, driver_id, lap_number) DO NOTHING""",
                season=season,
                round=round_num,
                circuit_id=circuit_id,
                driver_id=driver_id,
                lap_number=int(lap.get("LapNumber", 0)),
                lap_time_seconds=lap_time_s,
                s1=_sector("Sector1Time"),
                s2=_sector("Sector2Time"),
                s3=_sector("Sector3Time"),
                compound=str(compound) if pd.notna(compound) else None,
                tyre_life=int(tyre_life) if pd.notna(tyre_life) else None,
                stint=int(stint) if pd.notna(stint) else None,
                fuel_load=None,  # not directly available from FastF1
                track_temp=track_temp,
                air_temp=air_temp,
                is_sc=is_sc,
            )
        except Exception as exc:
            logger.debug("lap_features insert failed: %s", exc)


# ---------------------------------------------------------------------------
# Telemetry features
# ---------------------------------------------------------------------------


def _ingest_telemetry_features(
    conn,
    session: fastf1.core.Session,
    season: int,
    round_num: int,
    circuit_id: str,
) -> None:
    laps = session.laps
    if laps is None or len(laps) == 0:
        return

    for driver_abbr in laps["Driver"].unique():
        driver_laps = laps.pick_driver(driver_abbr)
        driver_id = str(driver_abbr).lower()

        for _, lap in driver_laps.iterrows():
            lap_number = int(lap.get("LapNumber", 0))
            try:
                tel = lap.get_telemetry()
                if tel is None or len(tel) == 0:
                    continue

                def _agg(col: str, func: str) -> Optional[float]:
                    series = tel.get(col, pd.Series(dtype=float))
                    if series.empty:
                        return None
                    val = getattr(series, func)()
                    return float(val) if pd.notna(val) else None

                conn.run(
                    """INSERT INTO telemetry_features
                         (season, round, circuit_id, driver_id, lap_number,
                          mean_throttle, std_throttle, mean_brake, std_brake,
                          mean_speed, max_speed)
                       VALUES
                         (:season, :round, :circuit_id, :driver_id, :lap_number,
                          :mean_throttle, :std_throttle, :mean_brake, :std_brake,
                          :mean_speed, :max_speed)
                       ON CONFLICT (season, round, driver_id, lap_number) DO NOTHING""",
                    season=season,
                    round=round_num,
                    circuit_id=circuit_id,
                    driver_id=driver_id,
                    lap_number=lap_number,
                    mean_throttle=_agg("Throttle", "mean"),
                    std_throttle=_agg("Throttle", "std"),
                    mean_brake=_agg("Brake", "mean"),
                    std_brake=_agg("Brake", "std"),
                    mean_speed=_agg("Speed", "mean"),
                    max_speed=_agg("Speed", "max"),
                )
            except Exception as exc:
                logger.debug(
                    "telemetry driver=%s lap=%d: %s", driver_abbr, lap_number, exc
                )


# ---------------------------------------------------------------------------
# Driver profiles
# ---------------------------------------------------------------------------


def compute_driver_profiles(conn) -> None:
    """Compute aggression/consistency/total_laps and upsert into driver_profiles."""
    logger.info("Computing driver profiles…")

    rows = conn.run("""SELECT driver_id,
                  AVG(mean_throttle) AS aggression_score,
                  COUNT(*)           AS total_laps
           FROM   telemetry_features
           WHERE  mean_throttle IS NOT NULL
           GROUP BY driver_id""")

    if not rows:
        logger.info("No telemetry data yet; skipping driver profile computation.")
        return

    for row in rows:
        driver_id = row[0]
        aggression_score = float(row[1]) if row[1] is not None else None
        total_laps = int(row[2])

        std_rows = conn.run(
            """SELECT STDDEV(lap_time_seconds)
               FROM   lap_features
               WHERE  driver_id = :driver_id
                 AND  lap_time_seconds IS NOT NULL""",
            driver_id=driver_id,
        )
        std_val = std_rows[0][0] if std_rows and std_rows[0][0] is not None else None
        consistency_score = (
            1.0 / float(std_val) if std_val and float(std_val) > 0 else None
        )

        conn.run(
            """INSERT INTO driver_profiles
                 (driver_id, aggression_score, consistency_score, total_laps)
               VALUES
                 (:driver_id, :aggression, :consistency, :total_laps)
               ON CONFLICT (driver_id) DO UPDATE SET
                 aggression_score  = EXCLUDED.aggression_score,
                 consistency_score = EXCLUDED.consistency_score,
                 total_laps        = EXCLUDED.total_laps,
                 updated_at        = NOW()""",
            driver_id=driver_id,
            aggression=aggression_score,
            consistency=consistency_score,
            total_laps=total_laps,
        )

    logger.info("Driver profiles updated for %d drivers", len(rows))


# ---------------------------------------------------------------------------
# Session loader
# ---------------------------------------------------------------------------


def _circuit_id(session: fastf1.core.Session) -> str:
    name = session.event.get(
        "OfficialEventName", session.event.get("EventName", "unknown")
    )
    return str(name).lower().replace(" ", "_")


def ingest_session(
    conn,
    season: int,
    round_num: int,
    session_type: str = "R",
) -> None:
    try:
        session = fastf1.get_session(season, round_num, session_type)
        session.load(weather=True, laps=True, telemetry=True)
        cid = _circuit_id(session)
        _ingest_weather(conn, session, season, round_num, cid, session_type)
        _ingest_lap_features(conn, session, season, round_num, cid)
        _ingest_telemetry_features(conn, session, season, round_num, cid)
    except Exception as exc:
        logger.warning(
            "Session %d/%d/%s could not be loaded: %s",
            season,
            round_num,
            session_type,
            exc,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_ingestion(start_year: int = START_YEAR, end_year: Optional[int] = None) -> None:
    current_year = end_year or datetime.date.today().year
    _setup_cache()
    logger.info("Starting FastF1 ingestion %d–%d", start_year, current_year)

    with ManagedConnection() as conn:
        for season in range(start_year, current_year + 1):
            logger.info("Season %d…", season)
            try:
                schedule = fastf1.get_event_schedule(season, include_testing=False)
            except Exception as exc:
                logger.warning("Could not get schedule for %d: %s", season, exc)
                continue

            for _, event in schedule.iterrows():
                round_num = int(event.get("RoundNumber", 0))
                if round_num == 0:
                    continue
                event_name = event.get("EventName", "")
                logger.info("  Round %d: %s", round_num, event_name)
                ingest_session(conn, season, round_num, "R")
                time.sleep(_SESSION_DELAY)

        compute_driver_profiles(conn)

    logger.info("FastF1 ingestion complete")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Ingest FastF1 telemetry data")
    parser.add_argument("--start-year", type=int, default=START_YEAR)
    parser.add_argument("--end-year", type=int, default=None)
    args = parser.parse_args()
    run_ingestion(start_year=args.start_year, end_year=args.end_year)
