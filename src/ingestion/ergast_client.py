"""
Ergast API client for historical F1 data (1950-2024).
Implements retry logic, rate limiting, and circuit breaker pattern.
"""

import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from pydantic import BaseModel
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
from prometheus_client import Counter, Histogram

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Prometheus metrics
API_REQUESTS = Counter(
    "ergast_api_requests_total", "Total Ergast API requests", ["endpoint", "status"]
)
API_LATENCY = Histogram(
    "ergast_api_latency_seconds", "Ergast API request latency", ["endpoint"]
)
RATE_LIMIT_HITS = Counter(
    "ergast_api_rate_limit_hits_total", "Number of rate limit hits"
)


class Race(BaseModel):
    """Race data model"""

    season: int
    round: int
    raceName: str
    circuitId: str
    circuitName: str
    date: str
    time: Optional[str] = None
    url: str


class Driver(BaseModel):
    """Driver data model"""

    driverId: str
    driverNumber: Optional[int] = None
    code: Optional[str] = None
    givenName: str
    familyName: str
    dateOfBirth: str
    nationality: str
    url: str


class Constructor(BaseModel):
    """Constructor data model"""

    constructorId: str
    name: str
    nationality: str
    url: str


class Result(BaseModel):
    """Race result data model"""

    number: int
    position: Optional[int] = None
    positionText: str
    points: float
    driverId: str
    constructorId: str
    grid: int
    laps: int
    status: str
    time: Optional[str] = None
    fastestLap: Optional[Dict[str, Any]] = None


class CircuitBreaker:
    """Circuit breaker for API failures"""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: type = requests.RequestException,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
                logger.info("Circuit breaker entering HALF_OPEN state")
            else:
                raise Exception("Circuit breaker is OPEN")

        try:
            result = func(*args, **kwargs)
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
                logger.info("Circuit breaker CLOSED")
            return result

        except self.expected_exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                logger.error(
                    f"Circuit breaker OPEN after {self.failure_count} failures"
                )

            raise e


class ErgastClient:
    """Ergast API client with retry logic and rate limiting"""

    BASE_URL = "https://ergast.com/api/f1/"
    RATE_LIMIT_DELAY = 0.5  # 2 requests per second max

    def __init__(
        self, base_url: Optional[str] = None, timeout: int = 30, max_retries: int = 3
    ):
        self.base_url = base_url or self.BASE_URL
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "F1-Strategy-Optimizer/1.0"})
        self.circuit_breaker = CircuitBreaker()
        self.last_request_time = 0

        logger.info(f"Ergast client initialized with base URL: {self.base_url}")

    def _rate_limit(self):
        """Enforce rate limiting"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            sleep_time = self.RATE_LIMIT_DELAY - elapsed
            time.sleep(sleep_time)
            RATE_LIMIT_HITS.inc()
        self.last_request_time = time.time()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _make_request(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make HTTP request with retry logic"""
        self._rate_limit()

        url = urljoin(self.base_url, endpoint)
        params = params or {}
        params["limit"] = params.get("limit", 1000)  # Max results

        start_time = time.time()

        try:
            response = self.circuit_breaker.call(
                self.session.get, url, params=params, timeout=self.timeout
            )

            response.raise_for_status()

            API_REQUESTS.labels(endpoint=endpoint, status="success").inc()

            API_LATENCY.labels(endpoint=endpoint).observe(time.time() - start_time)

            data = response.json()
            return data

        except requests.HTTPError as e:
            API_REQUESTS.labels(
                endpoint=endpoint, status=f"error_{e.response.status_code}"
            ).inc()
            logger.error(f"HTTP error for {url}: {e}")
            raise

        except requests.RequestException as e:
            API_REQUESTS.labels(endpoint=endpoint, status="error_network").inc()
            logger.error(f"Request error for {url}: {e}")
            raise

    def get_seasons(self, start_year: int = 1950, end_year: int = 2024) -> List[int]:
        """Get list of F1 seasons"""
        try:
            response = self._make_request("seasons.json")
            seasons_data = response["MRData"]["SeasonTable"]["Seasons"]

            seasons = [
                int(season["season"])
                for season in seasons_data
                if start_year <= int(season["season"]) <= end_year
            ]

            logger.info(
                f"Retrieved {len(seasons)} seasons from {start_year} to {end_year}"
            )
            return sorted(seasons)

        except Exception as e:
            logger.error(f"Error fetching seasons: {e}")
            return []

    def get_races(self, year: int) -> List[Race]:
        """Get all races for a season"""
        try:
            endpoint = f"{year}.json"
            response = self._make_request(endpoint)

            races_data = response["MRData"]["RaceTable"]["Races"]

            races = []
            for race_data in races_data:
                circuit = race_data["Circuit"]
                race = Race(
                    season=int(race_data["season"]),
                    round=int(race_data["round"]),
                    raceName=race_data["raceName"],
                    circuitId=circuit["circuitId"],
                    circuitName=circuit["circuitName"],
                    date=race_data["date"],
                    time=race_data.get("time"),
                    url=race_data["url"],
                )
                races.append(race)

            logger.info(f"Retrieved {len(races)} races for {year}")
            return races

        except Exception as e:
            logger.error(f"Error fetching races for {year}: {e}")
            return []

    def get_drivers(self, year: Optional[int] = None) -> List[Driver]:
        """Get all drivers (optionally for a specific year)"""
        try:
            endpoint = f"{year}/drivers.json" if year else "drivers.json"
            response = self._make_request(endpoint)

            drivers_data = response["MRData"]["DriverTable"]["Drivers"]

            drivers = []
            for driver_data in drivers_data:
                driver = Driver(
                    driverId=driver_data["driverId"],
                    driverNumber=driver_data.get("permanentNumber"),
                    code=driver_data.get("code"),
                    givenName=driver_data["givenName"],
                    familyName=driver_data["familyName"],
                    dateOfBirth=driver_data["dateOfBirth"],
                    nationality=driver_data["nationality"],
                    url=driver_data["url"],
                )
                drivers.append(driver)

            logger.info(
                f"Retrieved {len(drivers)} drivers" + (f" for {year}" if year else "")
            )
            return drivers

        except Exception as e:
            logger.error(f"Error fetching drivers: {e}")
            return []

    def get_results(self, year: int, round_num: int) -> List[Result]:
        """Get race results for a specific race"""
        try:
            endpoint = f"{year}/{round_num}/results.json"
            response = self._make_request(endpoint)

            races_data = response["MRData"]["RaceTable"]["Races"]
            if not races_data:
                logger.warning(f"No results found for {year} round {round_num}")
                return []

            results_data = races_data[0]["Results"]

            results = []
            for result_data in results_data:
                result = Result(
                    number=int(result_data["number"]),
                    position=(
                        int(result_data["position"])
                        if result_data.get("position")
                        else None
                    ),
                    positionText=result_data["positionText"],
                    points=float(result_data["points"]),
                    driverId=result_data["Driver"]["driverId"],
                    constructorId=result_data["Constructor"]["constructorId"],
                    grid=int(result_data["grid"]),
                    laps=int(result_data["laps"]),
                    status=result_data["status"],
                    time=result_data.get("Time", {}).get("time"),
                    fastestLap=result_data.get("FastestLap"),
                )
                results.append(result)

            logger.info(
                f"Retrieved {len(results)} results for {year} round {round_num}"
            )
            return results

        except Exception as e:
            logger.error(f"Error fetching results for {year} round {round_num}: {e}")
            return []

    def get_lap_times(
        self, year: int, round_num: int, lap: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get lap times for a specific race"""
        try:
            if lap:
                endpoint = f"{year}/{round_num}/laps/{lap}.json"
            else:
                endpoint = f"{year}/{round_num}/laps.json"

            response = self._make_request(endpoint)

            races_data = response["MRData"]["RaceTable"]["Races"]
            if not races_data:
                logger.warning(f"No lap times found for {year} round {round_num}")
                return []

            laps_data = races_data[0].get("Laps", [])

            lap_times = []
            for lap_data in laps_data:
                lap_number = int(lap_data["number"])
                for timing in lap_data["Timings"]:
                    lap_times.append(
                        {
                            "lap": lap_number,
                            "driver_id": timing["driverId"],
                            "position": int(timing["position"]),
                            "time": timing["time"],
                        }
                    )

            logger.info(
                f"Retrieved {len(lap_times)} lap times for {year} round {round_num}"
            )
            return lap_times

        except Exception as e:
            logger.error(f"Error fetching lap times for {year} round {round_num}: {e}")
            return []

    def get_standings(
        self, year: int, standings_type: str = "drivers"
    ) -> List[Dict[str, Any]]:
        """Get championship standings (drivers or constructors)"""
        try:
            endpoint = f"{year}/{standings_type}Standings.json"
            response = self._make_request(endpoint)

            standings_data = response["MRData"]["StandingsTable"]["StandingsLists"]
            if not standings_data:
                return []

            if standings_type == "drivers":
                standings = standings_data[0]["DriverStandings"]
            else:
                standings = standings_data[0]["ConstructorStandings"]

            logger.info(
                f"Retrieved {len(standings)} {standings_type} standings for {year}"
            )
            return standings

        except Exception as e:
            logger.error(f"Error fetching standings for {year}: {e}")
            return []

    def close(self):
        """Close the session"""
        self.session.close()
        logger.info("Ergast client session closed")


if __name__ == "__main__":
    # Example usage
    client = ErgastClient()

    # Get recent seasons
    seasons = client.get_seasons(2020, 2024)
    print(f"Seasons: {seasons}")

    # Get races for 2024
    races_2024 = client.get_races(2024)
    print(f"2024 Races: {len(races_2024)}")

    # Get all drivers
    drivers = client.get_drivers()
    print(f"Total drivers: {len(drivers)}")

    client.close()
