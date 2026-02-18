"""
Full historical ingestion from the Jolpica F1 API (api.jolpi.ca/ergast/f1).
Supports pagination and rate limiting.  Writes into Cloud SQL via pg8000.

Usage:
    python -m src.ingestion.ergast_ingestion [--start-season 1950] [--end-season 2026]
"""

import argparse
import logging
import time
from typing import Any, Optional

import requests

from src.database.connection import ManagedConnection

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.jolpi.ca/ergast/f1"
_RATE_LIMIT_DELAY = 0.5  # seconds between every HTTP request
_PAGE_SIZE = 100
_TIMEOUT = 30


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _get(url: str, params: Optional[dict] = None) -> dict:
    """GET with rate-limiting and up to 3 retries."""
    if params is None:
        params = {}
    params["format"] = "json"

    for attempt in range(3):
        time.sleep(_RATE_LIMIT_DELAY)
        try:
            resp = requests.get(url, params=params, timeout=_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as exc:
            if attempt < 2:
                logger.warning(
                    "Request failed (attempt %d/3): %s. Retrying…", attempt + 1, exc
                )
                time.sleep(_RATE_LIMIT_DELAY * (attempt + 2))
            else:
                raise


def _paginate(url: str, table_key: str, inner_key: str) -> list[dict]:
    """Fetch every page from a paginated Ergast endpoint."""
    results: list[dict] = []
    offset = 0

    while True:
        data = _get(url, {"limit": _PAGE_SIZE, "offset": offset})
        mr = data.get("MRData", {})
        total = int(mr.get("total", 0))
        page = mr.get(table_key, {}).get(inner_key, [])
        results.extend(page)
        offset += _PAGE_SIZE
        if offset >= total:
            break

    return results


# ---------------------------------------------------------------------------
# Individual ingestors
# ---------------------------------------------------------------------------


def ingest_seasons(conn: Any) -> list[int]:
    logger.info("Ingesting seasons…")
    seasons = _paginate(f"{_BASE_URL}/seasons.json/", "SeasonTable", "Seasons")
    years: list[int] = []
    for s in seasons:
        year = int(s["season"])
        conn.run(
            "INSERT INTO seasons (season, url) VALUES (:season, :url)"
            " ON CONFLICT (season) DO UPDATE SET url = EXCLUDED.url",
            season=year,
            url=s.get("url", ""),
        )
        years.append(year)
    logger.info("Ingested %d seasons", len(years))
    return years


def ingest_drivers(conn: Any) -> None:
    logger.info("Ingesting drivers…")
    drivers = _paginate(f"{_BASE_URL}/drivers.json/", "DriverTable", "Drivers")
    for d in drivers:
        conn.run(
            """INSERT INTO drivers (driver_id, code, given_name, family_name, date_of_birth, nationality)
               VALUES (:driver_id, :code, :given_name, :family_name, :dob, :nationality)
               ON CONFLICT (driver_id) DO UPDATE SET
                 code         = EXCLUDED.code,
                 given_name   = EXCLUDED.given_name,
                 family_name  = EXCLUDED.family_name,
                 date_of_birth= EXCLUDED.date_of_birth,
                 nationality  = EXCLUDED.nationality,
                 updated_at   = NOW()""",
            driver_id=d["driverId"],
            code=d.get("code"),
            given_name=d.get("givenName", ""),
            family_name=d.get("familyName", ""),
            dob=d.get("dateOfBirth"),
            nationality=d.get("nationality", ""),
        )
    logger.info("Ingested %d drivers", len(drivers))


def ingest_constructors(conn: Any) -> None:
    logger.info("Ingesting constructors…")
    constructors = _paginate(
        f"{_BASE_URL}/constructors.json/", "ConstructorTable", "Constructors"
    )
    for c in constructors:
        conn.run(
            """INSERT INTO constructors (constructor_id, name, nationality)
               VALUES (:constructor_id, :name, :nationality)
               ON CONFLICT (constructor_id) DO UPDATE SET
                 name        = EXCLUDED.name,
                 nationality = EXCLUDED.nationality,
                 updated_at  = NOW()""",
            constructor_id=c["constructorId"],
            name=c.get("name", ""),
            nationality=c.get("nationality", ""),
        )
    logger.info("Ingested %d constructors", len(constructors))


def ingest_races(conn: Any, season: int) -> list[dict]:
    data = _get(f"{_BASE_URL}/{season}/races.json/")
    races = data["MRData"]["RaceTable"]["Races"]
    for race in races:
        circuit = race.get("Circuit", {})
        loc = circuit.get("Location", {})
        race_time_raw = race.get("time", "")
        race_time = race_time_raw.replace("Z", "") if race_time_raw else None
        conn.run(
            """INSERT INTO races
                 (season, round, circuit_id, circuit_name, country, locality,
                  lat, lng, race_name, race_date, race_time, url)
               VALUES
                 (:season, :round, :circuit_id, :circuit_name, :country, :locality,
                  :lat, :lng, :race_name, :race_date, :race_time, :url)
               ON CONFLICT (season, round) DO UPDATE SET
                 circuit_id   = EXCLUDED.circuit_id,
                 circuit_name = EXCLUDED.circuit_name,
                 race_name    = EXCLUDED.race_name,
                 race_date    = EXCLUDED.race_date""",
            season=season,
            round=int(race["round"]),
            circuit_id=circuit.get("circuitId", ""),
            circuit_name=circuit.get("circuitName", ""),
            country=loc.get("country", ""),
            locality=loc.get("locality", ""),
            lat=float(loc["lat"]) if loc.get("lat") else None,
            lng=float(loc["long"]) if loc.get("long") else None,
            race_name=race.get("raceName", ""),
            race_date=race.get("date"),
            race_time=race_time,
            url=race.get("url", ""),
        )
    return races


def ingest_results(conn: Any, season: int, round_num: int) -> None:
    try:
        data = _get(f"{_BASE_URL}/{season}/{round_num}/results.json/")
        races = data["MRData"]["RaceTable"]["Races"]
        if not races:
            return
        for r in races[0].get("Results", []):
            driver = r.get("Driver", {})
            constructor = r.get("Constructor", {})
            fl = r.get("FastestLap", {})
            pos_text = r.get("positionText", "")
            position = int(r["position"]) if pos_text.isdigit() else None
            conn.run(
                """INSERT INTO race_results
                     (season, round, driver_id, constructor_id, grid, position,
                      position_text, points, laps, status, time_millis,
                      fastest_lap, fastest_lap_time, fastest_lap_speed)
                   VALUES
                     (:season, :round, :driver_id, :constructor_id, :grid, :position,
                      :pos_text, :points, :laps, :status, :time_millis,
                      :fastest_lap, :fastest_lap_time, :fastest_lap_speed)
                   ON CONFLICT (season, round, driver_id) DO UPDATE SET
                     position = EXCLUDED.position,
                     points   = EXCLUDED.points,
                     status   = EXCLUDED.status""",
                season=season,
                round=round_num,
                driver_id=driver.get("driverId", ""),
                constructor_id=constructor.get("constructorId", ""),
                grid=int(r.get("grid", 0)),
                position=position,
                pos_text=pos_text,
                points=float(r.get("points", 0)),
                laps=int(r.get("laps", 0)),
                status=r.get("status", ""),
                time_millis=int(r["Time"]["millis"]) if r.get("Time") else None,
                fastest_lap=int(fl["lap"]) if fl else None,
                fastest_lap_time=fl.get("Time", {}).get("time") if fl else None,
                fastest_lap_speed=(
                    float(fl["AverageSpeed"]["speed"])
                    if fl and fl.get("AverageSpeed")
                    else None
                ),
            )
    except Exception as exc:
        logger.warning("results %d/%d: %s", season, round_num, exc)


def _parse_lap_time(time_str: str) -> Optional[int]:
    """Convert 'M:SS.mmm' or 'SS.mmm' to milliseconds."""
    if not time_str:
        return None
    try:
        if ":" in time_str:
            m, s = time_str.split(":", 1)
            return int((int(m) * 60 + float(s)) * 1000)
        return int(float(time_str) * 1000)
    except (ValueError, IndexError):
        return None


def ingest_lap_times(conn: Any, season: int, round_num: int) -> None:
    try:
        offset = 0
        while True:
            data = _get(
                f"{_BASE_URL}/{season}/{round_num}/laps.json/",
                {"limit": _PAGE_SIZE, "offset": offset},
            )
            mr = data["MRData"]
            total = int(mr["total"])
            races = mr["RaceTable"]["Races"]
            if not races:
                break
            for lap in races[0].get("Laps", []):
                lap_num = int(lap["number"])
                for t in lap.get("Timings", []):
                    conn.run(
                        """INSERT INTO lap_times (season, round, driver_id, lap, position, time_millis)
                           VALUES (:season, :round, :driver_id, :lap, :position, :time_millis)
                           ON CONFLICT (season, round, driver_id, lap) DO NOTHING""",
                        season=season,
                        round=round_num,
                        driver_id=t.get("driverId", ""),
                        lap=lap_num,
                        position=int(t.get("position", 0)),
                        time_millis=_parse_lap_time(t.get("time", "")),
                    )
            offset += _PAGE_SIZE
            if offset >= total:
                break
    except Exception as exc:
        logger.warning("lap_times %d/%d: %s", season, round_num, exc)


def ingest_pit_stops(conn: Any, season: int, round_num: int) -> None:
    try:
        data = _get(f"{_BASE_URL}/{season}/{round_num}/pitstops.json/")
        races = data["MRData"]["RaceTable"]["Races"]
        if not races:
            return
        for ps in races[0].get("PitStops", []):
            conn.run(
                """INSERT INTO pit_stops (season, round, driver_id, stop, lap, duration_millis)
                   VALUES (:season, :round, :driver_id, :stop, :lap, :duration_millis)
                   ON CONFLICT (season, round, driver_id, stop) DO NOTHING""",
                season=season,
                round=round_num,
                driver_id=ps.get("driverId", ""),
                stop=int(ps.get("stop", 0)),
                lap=int(ps.get("lap", 0)),
                duration_millis=_parse_lap_time(ps.get("duration", "")),
            )
    except Exception as exc:
        logger.warning("pit_stops %d/%d: %s", season, round_num, exc)


def ingest_qualifying(conn: Any, season: int, round_num: int) -> None:
    try:
        data = _get(f"{_BASE_URL}/{season}/{round_num}/qualifying.json/")
        races = data["MRData"]["RaceTable"]["Races"]
        if not races:
            return
        for r in races[0].get("QualifyingResults", []):
            driver = r.get("Driver", {})
            constructor = r.get("Constructor", {})
            conn.run(
                """INSERT INTO qualifying
                     (season, round, driver_id, constructor_id, number, position, q1, q2, q3)
                   VALUES
                     (:season, :round, :driver_id, :constructor_id, :number, :position, :q1, :q2, :q3)
                   ON CONFLICT (season, round, driver_id) DO UPDATE SET
                     position = EXCLUDED.position,
                     q1 = EXCLUDED.q1, q2 = EXCLUDED.q2, q3 = EXCLUDED.q3""",
                season=season,
                round=round_num,
                driver_id=driver.get("driverId", ""),
                constructor_id=constructor.get("constructorId", ""),
                number=int(r.get("number", 0)),
                position=int(r.get("position", 0)),
                q1=r.get("Q1"),
                q2=r.get("Q2"),
                q3=r.get("Q3"),
            )
    except Exception as exc:
        logger.warning("qualifying %d/%d: %s", season, round_num, exc)


def ingest_driver_standings(conn: Any, season: int, round_num: int) -> None:
    try:
        data = _get(f"{_BASE_URL}/{season}/{round_num}/driverStandings.json/")
        lists = data["MRData"]["StandingsTable"]["StandingsLists"]
        if not lists:
            return
        for standing in lists[0].get("DriverStandings", []):
            driver = standing.get("Driver", {})
            constructors = standing.get("Constructors", [{}])
            constructor_id = (
                constructors[0].get("constructorId", "") if constructors else ""
            )
            conn.run(
                """INSERT INTO driver_standings
                     (season, round, driver_id, constructor_id, points, position, wins)
                   VALUES
                     (:season, :round, :driver_id, :constructor_id, :points, :position, :wins)
                   ON CONFLICT (season, round, driver_id) DO UPDATE SET
                     points = EXCLUDED.points, position = EXCLUDED.position, wins = EXCLUDED.wins""",
                season=season,
                round=round_num,
                driver_id=driver.get("driverId", ""),
                constructor_id=constructor_id,
                points=float(standing.get("points", 0)),
                position=int(standing.get("position", 0)),
                wins=int(standing.get("wins", 0)),
            )
    except Exception as exc:
        logger.warning("driver_standings %d/%d: %s", season, round_num, exc)


def ingest_constructor_standings(conn: Any, season: int, round_num: int) -> None:
    try:
        data = _get(f"{_BASE_URL}/{season}/{round_num}/constructorStandings.json/")
        lists = data["MRData"]["StandingsTable"]["StandingsLists"]
        if not lists:
            return
        for standing in lists[0].get("ConstructorStandings", []):
            constructor = standing.get("Constructor", {})
            conn.run(
                """INSERT INTO constructor_standings
                     (season, round, constructor_id, points, position, wins)
                   VALUES
                     (:season, :round, :constructor_id, :points, :position, :wins)
                   ON CONFLICT (season, round, constructor_id) DO UPDATE SET
                     points = EXCLUDED.points, position = EXCLUDED.position, wins = EXCLUDED.wins""",
                season=season,
                round=round_num,
                constructor_id=constructor.get("constructorId", ""),
                points=float(standing.get("points", 0)),
                position=int(standing.get("position", 0)),
                wins=int(standing.get("wins", 0)),
            )
    except Exception as exc:
        logger.warning("constructor_standings %d/%d: %s", season, round_num, exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_ingestion(start_season: int = 1950, end_season: Optional[int] = None) -> None:
    """Run full historical ingestion from the Ergast API."""
    logger.info("Starting Ergast ingestion from season %d", start_season)

    with ManagedConnection() as conn:
        all_seasons = ingest_seasons(conn)
        ingest_drivers(conn)
        ingest_constructors(conn)

        target = sorted(s for s in all_seasons if s >= start_season)
        if end_season is not None:
            target = [s for s in target if s <= end_season]

        for season in target:
            logger.info("Season %d …", season)
            try:
                races = ingest_races(conn, season)
            except Exception as exc:
                logger.info("Season %d not yet available, skipping: %s", season, exc)
                continue
            for race in races:
                rnd = int(race["round"])
                logger.info("  Round %d: %s", rnd, race.get("raceName", ""))
                ingest_results(conn, season, rnd)
                ingest_lap_times(conn, season, rnd)
                ingest_pit_stops(conn, season, rnd)
                ingest_qualifying(conn, season, rnd)
                ingest_driver_standings(conn, season, rnd)
                ingest_constructor_standings(conn, season, rnd)

    logger.info("Ergast ingestion complete")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Ingest F1 historical data from Ergast API"
    )
    parser.add_argument("--start-season", type=int, default=1950)
    parser.add_argument("--end-season", type=int, default=2026)
    args = parser.parse_args()
    run_ingestion(start_season=args.start_season, end_season=args.end_season)
