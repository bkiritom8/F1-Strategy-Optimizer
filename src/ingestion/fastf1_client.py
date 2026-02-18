"""
FastF1 client for high-frequency telemetry data (2018+).
Provides lap telemetry, car data, and session information.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import fastf1
import pandas as pd
from fastf1.core import Session
from pydantic import BaseModel
from prometheus_client import Counter, Histogram
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Prometheus metrics
TELEMETRY_REQUESTS = Counter(
    "fastf1_telemetry_requests_total",
    "Total FastF1 telemetry requests",
    ["year", "event", "session_type", "status"],
)
TELEMETRY_LATENCY = Histogram(
    "fastf1_telemetry_latency_seconds",
    "FastF1 telemetry request latency",
    ["session_type"],
)
TELEMETRY_POINTS = Counter(
    "fastf1_telemetry_points_total", "Total telemetry data points retrieved", ["driver"]
)


class TelemetryPoint(BaseModel):
    """Single telemetry data point"""

    timestamp: str
    session_time: float
    driver_number: int
    speed: float
    throttle: float
    brake: bool
    gear: int
    rpm: int
    drs: int
    distance: float


class LapData(BaseModel):
    """Lap-level data"""

    lap_number: int
    driver_number: int
    lap_time: Optional[float] = None
    sector_1_time: Optional[float] = None
    sector_2_time: Optional[float] = None
    sector_3_time: Optional[float] = None
    compound: Optional[str] = None
    tyre_life: Optional[int] = None
    stint: Optional[int] = None
    fresh_tyre: Optional[bool] = None
    team: Optional[str] = None
    driver: Optional[str] = None
    is_personal_best: Optional[bool] = None


class SessionInfo(BaseModel):
    """Session metadata"""

    event_name: str
    session_type: str
    date: str
    circuit_key: str
    circuit_name: str
    country: str
    year: int
    round_number: int


class FastF1Client:
    """FastF1 client for telemetry data retrieval"""

    def __init__(self, cache_dir: str = "/tmp/fastf1_cache", enable_cache: bool = True):
        self.cache_dir = Path(cache_dir)
        self.enable_cache = enable_cache

        if self.enable_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            fastf1.Cache.enable_cache(str(self.cache_dir))
            logger.info(f"FastF1 cache enabled at {self.cache_dir}")
        else:
            logger.info("FastF1 cache disabled")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _load_session(self, year: int, event: int | str, session_type: str) -> Session:
        """Load FastF1 session with retry logic"""
        try:
            session = fastf1.get_session(year, event, session_type)
            session.load()
            return session

        except Exception as e:
            logger.error(f"Error loading session {year}/{event}/{session_type}: {e}")
            raise

    def get_session_info(
        self, year: int, event: int | str, session_type: str = "R"
    ) -> Optional[SessionInfo]:
        """Get session metadata"""
        try:
            with TELEMETRY_LATENCY.labels(session_type=session_type).time():
                session = self._load_session(year, event, session_type)

            info = SessionInfo(
                event_name=session.event["EventName"],
                session_type=session.name,
                date=session.date.strftime("%Y-%m-%d"),
                circuit_key=session.event["EventName"],
                circuit_name=session.event["Location"],
                country=session.event["Country"],
                year=year,
                round_number=session.event["RoundNumber"],
            )

            TELEMETRY_REQUESTS.labels(
                year=year, event=str(event), session_type=session_type, status="success"
            ).inc()

            logger.info(f"Retrieved session info for {year} {event} {session_type}")
            return info

        except Exception as e:
            TELEMETRY_REQUESTS.labels(
                year=year, event=str(event), session_type=session_type, status="error"
            ).inc()
            logger.error(f"Error getting session info: {e}")
            return None

    def get_lap_data(
        self,
        year: int,
        event: int | str,
        session_type: str = "R",
        driver: Optional[str] = None,
    ) -> List[LapData]:
        """Get lap-level data for all drivers or a specific driver"""
        try:
            session = self._load_session(year, event, session_type)
            laps = session.laps

            if driver:
                laps = laps.pick_driver(driver)

            lap_data = []
            for _, lap in laps.iterrows():
                data = LapData(
                    lap_number=(
                        int(lap["LapNumber"]) if pd.notna(lap["LapNumber"]) else 0
                    ),
                    driver_number=(
                        int(lap["DriverNumber"]) if pd.notna(lap["DriverNumber"]) else 0
                    ),
                    lap_time=(
                        float(lap["LapTime"].total_seconds())
                        if pd.notna(lap["LapTime"])
                        else None
                    ),
                    sector_1_time=(
                        float(lap["Sector1Time"].total_seconds())
                        if pd.notna(lap["Sector1Time"])
                        else None
                    ),
                    sector_2_time=(
                        float(lap["Sector2Time"].total_seconds())
                        if pd.notna(lap["Sector2Time"])
                        else None
                    ),
                    sector_3_time=(
                        float(lap["Sector3Time"].total_seconds())
                        if pd.notna(lap["Sector3Time"])
                        else None
                    ),
                    compound=lap.get("Compound"),
                    tyre_life=(
                        int(lap["TyreLife"]) if pd.notna(lap.get("TyreLife")) else None
                    ),
                    stint=int(lap["Stint"]) if pd.notna(lap.get("Stint")) else None,
                    fresh_tyre=(
                        bool(lap.get("FreshTyre"))
                        if pd.notna(lap.get("FreshTyre"))
                        else None
                    ),
                    team=lap.get("Team"),
                    driver=lap.get("Driver"),
                    is_personal_best=(
                        bool(lap.get("IsPersonalBest"))
                        if pd.notna(lap.get("IsPersonalBest"))
                        else None
                    ),
                )
                lap_data.append(data)

            logger.info(
                f"Retrieved {len(lap_data)} laps for {year} {event} {session_type}"
            )
            return lap_data

        except Exception as e:
            logger.error(f"Error getting lap data: {e}")
            return []

    def get_telemetry(
        self,
        year: int,
        event: int | str,
        session_type: str = "R",
        driver: Optional[str] = None,
        lap_number: Optional[int] = None,
    ) -> pd.DataFrame:
        """Get high-frequency telemetry data (10Hz)"""
        try:
            session = self._load_session(year, event, session_type)

            if not driver:
                # Get telemetry for all drivers
                telemetry = session.laps.get_telemetry()
            else:
                laps = session.laps.pick_driver(driver)
                if lap_number:
                    lap = laps[laps["LapNumber"] == lap_number].iloc[0]
                    telemetry = lap.get_telemetry()
                else:
                    telemetry = laps.get_telemetry()

            TELEMETRY_POINTS.labels(driver=driver if driver else "all").inc(
                len(telemetry)
            )

            logger.info(f"Retrieved {len(telemetry)} telemetry points")
            return telemetry

        except Exception as e:
            logger.error(f"Error getting telemetry: {e}")
            return pd.DataFrame()

    def get_car_data(
        self,
        year: int,
        event: int | str,
        session_type: str = "R",
        driver: Optional[str] = None,
        lap_number: Optional[int] = None,
    ) -> pd.DataFrame:
        """Get car data (speed, throttle, brake, gear, RPM, DRS)"""
        try:
            session = self._load_session(year, event, session_type)

            if driver:
                laps = session.laps.pick_driver(driver)
                if lap_number:
                    lap = laps[laps["LapNumber"] == lap_number].iloc[0]
                    car_data = lap.get_car_data()
                else:
                    car_data = laps.get_car_data()
            else:
                car_data = session.laps.get_car_data()

            logger.info(f"Retrieved {len(car_data)} car data points")
            return car_data

        except Exception as e:
            logger.error(f"Error getting car data: {e}")
            return pd.DataFrame()

    def get_weather_data(
        self, year: int, event: int | str, session_type: str = "R"
    ) -> pd.DataFrame:
        """Get weather data for session"""
        try:
            session = self._load_session(year, event, session_type)
            weather = session.weather_data

            logger.info(f"Retrieved {len(weather)} weather data points")
            return weather

        except Exception as e:
            logger.error(f"Error getting weather data: {e}")
            return pd.DataFrame()

    def get_available_events(self, year: int) -> List[Dict[str, Any]]:
        """Get list of available events for a year"""
        try:
            schedule = fastf1.get_event_schedule(year)

            events = []
            for _, event in schedule.iterrows():
                events.append(
                    {
                        "round_number": int(event["RoundNumber"]),
                        "event_name": event["EventName"],
                        "location": event["Location"],
                        "country": event["Country"],
                        "event_date": event["EventDate"].strftime("%Y-%m-%d"),
                        "event_format": event["EventFormat"],
                    }
                )

            logger.info(f"Retrieved {len(events)} events for {year}")
            return events

        except Exception as e:
            logger.error(f"Error getting events for {year}: {e}")
            return []

    def extract_driver_behavior(
        self, year: int, event: int | str, driver: str, session_type: str = "R"
    ) -> Dict[str, Any]:
        """Extract driver behavioral metrics from telemetry"""
        try:
            session = self._load_session(year, event, session_type)
            laps = session.laps.pick_driver(driver)

            # Calculate behavioral metrics
            fastest_lap = laps.pick_fastest()
            telemetry = fastest_lap.get_telemetry()

            # Throttle aggressiveness
            throttle_mean = telemetry["Throttle"].mean()
            throttle_std = telemetry["Throttle"].std()

            # Braking metrics
            brake_count = telemetry["Brake"].sum()

            # Speed variance (consistency)
            speed_std = telemetry["Speed"].std()

            # Gear changes (smoothness)
            gear_changes = (telemetry["nGear"].diff() != 0).sum()

            metrics = {
                "driver": driver,
                "year": year,
                "event": str(event),
                "throttle_mean": float(throttle_mean),
                "throttle_std": float(throttle_std),
                "brake_applications": int(brake_count),
                "speed_consistency": float(speed_std),
                "gear_changes_per_lap": int(gear_changes),
                "avg_speed": float(telemetry["Speed"].mean()),
                "max_speed": float(telemetry["Speed"].max()),
            }

            logger.info(f"Extracted behavior metrics for {driver}")
            return metrics

        except Exception as e:
            logger.error(f"Error extracting driver behavior: {e}")
            return {}

    def clear_cache(self):
        """Clear FastF1 cache directory"""
        if self.cache_dir.exists():
            import shutil

            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True)
            logger.info(f"Cache cleared: {self.cache_dir}")


if __name__ == "__main__":
    # Example usage
    client = FastF1Client()

    # Get available events for 2024
    events = client.get_available_events(2024)
    print(f"2024 Events: {len(events)}")

    # Get session info
    session_info = client.get_session_info(2024, 1, "R")
    if session_info:
        print(f"Session: {session_info.event_name}")

    # Get lap data for Verstappen
    lap_data = client.get_lap_data(2024, 1, "R", driver="VER")
    print(f"Verstappen laps: {len(lap_data)}")
