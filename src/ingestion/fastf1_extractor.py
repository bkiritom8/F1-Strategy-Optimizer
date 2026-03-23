"""fastf1_extractor.py — FastF1 session loading, telemetry, timedelta normalization."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

try:
    import fastf1  # type: ignore[import]
    _FASTF1_AVAILABLE = True
except ImportError:
    _FASTF1_AVAILABLE = False

SESSION_LABELS = {
    "FP1": "Practice 1", "FP2": "Practice 2", "FP3": "Practice 3",
    "Q": "Qualifying", "S": "Sprint", "R": "Race",
}


def enable_cache(cache_dir: str) -> None:
    if _FASTF1_AVAILABLE:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        fastf1.Cache.enable_cache(cache_dir)


def load_session(year: int, round_num: int, session_type: str) -> "fastf1.core.Session":
    if year < 2018:
        raise ValueError(f"FastF1 only supports 2018+. Got year={year}")
    label = SESSION_LABELS.get(session_type, session_type)
    logger.info("Loading session: %d Round %d %s (%s)", year, round_num, session_type, label)
    session = fastf1.get_session(year, round_num, session_type)
    session.load(telemetry=True, laps=True, weather=True)
    logger.info("Session loaded: %s %d — %d laps", session.event["EventName"], year, len(session.laps))
    return session


def normalize_timedeltas(df: pd.DataFrame) -> pd.DataFrame:
    """Convert timedelta64 columns to float seconds."""
    for col in df.select_dtypes(include=["timedelta64[ns]"]).columns:
        df[col] = df[col].dt.total_seconds()
    return df


def extract_laps(session, year: int, round_num: int, session_type: str) -> pd.DataFrame:
    laps = session.laps.copy()
    laps["season"] = year
    laps["round"] = round_num
    laps["session_type"] = session_type
    return normalize_timedeltas(laps)


def extract_telemetry(
    session, year: int, round_num: int, session_type: str,
    driver: Optional[str] = None,
) -> pd.DataFrame:
    laps = session.laps
    if driver is not None:
        laps = laps.pick_driver(driver)
    frames: List[pd.DataFrame] = []
    for _, lap in laps.iterlaps():
        try:
            tel = lap.get_telemetry()
            if tel is not None and not tel.empty:
                tel["Driver"] = lap["Driver"]
                tel["LapNumber"] = lap["LapNumber"]
                tel["season"] = year
                tel["round"] = round_num
                tel["session_type"] = session_type
                frames.append(tel)
        except Exception:
            logger.debug("Telemetry unavailable for %s lap %s", lap.get("Driver"), lap.get("LapNumber"))
    if not frames:
        return pd.DataFrame()
    return normalize_timedeltas(pd.concat(frames, ignore_index=True))


def extract_weather(session, year: int, round_num: int, session_type: str) -> pd.DataFrame:
    weather = session.weather_data.copy()
    weather["season"] = year
    weather["round"] = round_num
    weather["session_type"] = session_type
    return normalize_timedeltas(weather)
