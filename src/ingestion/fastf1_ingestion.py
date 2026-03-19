"""
fastf1_ingestion.py — Fetch F1 telemetry data using the FastF1 library.

FastF1 covers 2018–present with 10Hz car telemetry.
Data is cached locally to data/raw/fastf1_cache/ to avoid re-downloading.
CSVs are saved to data/raw/fastf1/<year>/<round>/<session_type>/<data_type>.csv

Usage:
    ingestion = FastF1Ingestion(
        output_dir="data/raw/fastf1",
        cache_dir="data/raw/fastf1_cache",
    )
    ingestion.fetch_laps(2024, 1, "R")
    ingestion.fetch_telemetry(2024, 1, "R", "VER")
    ingestion.ingest_season(2024, session_types=["R", "Q"])
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import pandas as pd

from .fastf1_extractor import (
    enable_cache, load_session, extract_laps,
    extract_telemetry, extract_weather,
    _FASTF1_AVAILABLE,
)

logger = logging.getLogger(__name__)

if not _FASTF1_AVAILABLE:
    logger.warning("FastF1 not installed. FastF1Ingestion will raise on use.")


class FastF1Ingestion:
    """
    Fetch and persist F1 telemetry data using the FastF1 library.

    FastF1 provides 10Hz car telemetry, lap timing, tyre compound, and weather
    data for sessions from 2018 onward. This class wraps the FastF1 API with
    local CSV persistence and structured logging.

    Parameters
    ----------
    output_dir : str
        Root directory for CSV output (default: data/raw/fastf1)
    cache_dir : str
        FastF1 cache directory (default: data/raw/fastf1_cache)
    """

    def __init__(
        self,
        output_dir: str = "data/raw/fastf1",
        cache_dir: str = "data/raw/fastf1_cache",
    ) -> None:
        if not _FASTF1_AVAILABLE:
            raise ImportError(
                "fastf1 package is required. Install with: pip install fastf1"
            )
        self.output_dir = Path(output_dir)
        self.cache_dir = Path(cache_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        enable_cache(str(self.cache_dir))
        logger.info(
            "FastF1Ingestion initialized — output: %s, cache: %s",
            self.output_dir,
            self.cache_dir,
        )

    def _session_dir(self, year: int, round_num: int, session_type: str) -> Path:
        out = self.output_dir / str(year) / str(round_num) / session_type
        out.mkdir(parents=True, exist_ok=True)
        return out

    def fetch_session(
        self, year: int, round_num: int, session_type: str = "R"
    ) -> "fastf1.core.Session":
        """
        Load a FastF1 session object (downloads if not cached).

        Parameters
        ----------
        year : int
        round_num : int
        session_type : str
            One of: FP1, FP2, FP3, Q, S, R

        Returns
        -------
        fastf1.core.Session
        """
        return load_session(year, round_num, session_type)

    def fetch_laps(
        self,
        year: int,
        round_num: int,
        session_type: str = "R",
        session: Optional["fastf1.core.Session"] = None,
    ) -> pd.DataFrame:
        """
        Fetch lap timing data for a session.

        Columns include: Driver, LapNumber, LapTime, Sector1Time, Sector2Time,
        Sector3Time, Compound, TyreLife, FreshTyre, TrackStatus, IsAccurate, etc.

        Parameters
        ----------
        year : int
        round_num : int
        session_type : str
        session : fastf1.core.Session, optional
            Pre-loaded session (avoids double-loading)

        Returns
        -------
        pd.DataFrame
        """
        if session is None:
            session = self.fetch_session(year, round_num, session_type)
        laps = extract_laps(session, year, round_num, session_type)
        out_path = self._session_dir(year, round_num, session_type) / "laps.csv"
        laps.to_csv(out_path, index=False)
        logger.info("Saved laps: %s (%d rows)", out_path, len(laps))
        return laps

    def fetch_telemetry(
        self,
        year: int,
        round_num: int,
        session_type: str = "R",
        driver: Optional[str] = None,
        session: Optional["fastf1.core.Session"] = None,
    ) -> pd.DataFrame:
        """
        Fetch 10Hz car telemetry for a session.

        Columns include: Time, RPM, Speed, nGear, Throttle, Brake, DRS, Source,
        Distance, X, Y, Z, Driver, LapNumber.

        Parameters
        ----------
        year : int
        round_num : int
        session_type : str
        driver : str, optional
            Three-letter driver code (e.g. "VER"). If None, fetches all drivers.
        session : fastf1.core.Session, optional

        Returns
        -------
        pd.DataFrame
        """
        if session is None:
            session = self.fetch_session(year, round_num, session_type)
        combined = extract_telemetry(session, year, round_num, session_type, driver)
        if combined.empty:
            logger.warning(
                "No telemetry found for %d/%d/%s driver=%s",
                year,
                round_num,
                session_type,
                driver,
            )
            return combined
        suffix = f"_{driver}" if driver else "_all"
        out_path = (
            self._session_dir(year, round_num, session_type) / f"telemetry{suffix}.csv"
        )
        combined.to_csv(out_path, index=False)
        logger.info("Saved telemetry: %s (%d rows)", out_path, len(combined))
        return combined

    def fetch_weather(
        self,
        year: int,
        round_num: int,
        session_type: str = "R",
        session: Optional["fastf1.core.Session"] = None,
    ) -> pd.DataFrame:
        """
        Fetch weather data for a session.

        Columns: Time, AirTemp, Humidity, Pressure, Rainfall, TrackTemp, WindDirection, WindSpeed.
        """
        if session is None:
            session = self.fetch_session(year, round_num, session_type)
        weather = extract_weather(session, year, round_num, session_type)
        out_path = self._session_dir(year, round_num, session_type) / "weather.csv"
        weather.to_csv(out_path, index=False)
        logger.info("Saved weather: %s (%d rows)", out_path, len(weather))
        return weather

    def ingest_session_all(
        self, year: int, round_num: int, session_type: str = "R"
    ) -> None:
        """
        Fetch all data types (laps, telemetry, weather) for one session.

        Loads the session once and reuses for all calls.
        """
        logger.info("Ingesting all data: %d round %d %s", year, round_num, session_type)
        try:
            session = self.fetch_session(year, round_num, session_type)
            self.fetch_laps(year, round_num, session_type, session=session)
            self.fetch_telemetry(year, round_num, session_type, session=session)
            self.fetch_weather(year, round_num, session_type, session=session)
        except Exception:
            logger.exception(
                "Failed to ingest %d round %d %s", year, round_num, session_type
            )

    def ingest_season(
        self,
        year: int,
        session_types: Optional[List[str]] = None,
        max_rounds: int = 25,
    ) -> None:
        """
        Ingest all sessions for a full season.

        Parameters
        ----------
        year : int
        session_types : list of str, optional
            Session types to fetch (default: ["R"] — race only)
        max_rounds : int
        """
        if year < 2018:
            logger.warning("FastF1 only supports 2018+. Skipping year %d.", year)
            return
        if session_types is None:
            session_types = ["R"]
        logger.info(
            "Starting FastF1 season ingest: %d, sessions: %s, max_rounds: %d",
            year,
            session_types,
            max_rounds,
        )
        for rnd in range(1, max_rounds + 1):
            for stype in session_types:
                try:
                    self.ingest_session_all(year, rnd, stype)
                except Exception:
                    logger.warning(
                        "Skipping %d round %d %s after error", year, rnd, stype
                    )
        logger.info("FastF1 season %d ingest complete", year)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    ingestion = FastF1Ingestion()
    # Ingest recent races
    for season_year in range(2022, 2026):
        ingestion.ingest_season(season_year, session_types=["R", "Q"])
