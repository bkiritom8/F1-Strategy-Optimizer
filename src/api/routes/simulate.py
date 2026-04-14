"""
Simulation API routes.

POST /api/v1/simulate/race   — submit a scenario, returns job_id
GET  /api/v1/simulate/race/stream — SSE stream of lap frames for job_id
"""

from __future__ import annotations

import json
import logging
import math
import os
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.security.https_middleware import get_current_user
from src.security.iam_simulator import Permission, iam_simulator
from src.simulation.constructor_pace import ConstructorPaceStore
from src.simulation.coordinator import SimulationCoordinator, scenario_hash
from src.simulation.streamer import frames_to_sse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/simulate", tags=["simulation"])

SIMULATION_ENDPOINT = os.environ.get(
    "SIMULATION_ENDPOINT", "http://simulation-worker/internal/simulate"
)

_coordinator: SimulationCoordinator | None = None
_constructor_store: ConstructorPaceStore | None = None


def _get_coordinator() -> SimulationCoordinator:
    global _coordinator
    if _coordinator is None:
        _coordinator = SimulationCoordinator()
    return _coordinator


def _get_constructor_store() -> ConstructorPaceStore:
    global _constructor_store
    if _constructor_store is None:
        _constructor_store = ConstructorPaceStore()
    return _constructor_store


def _parse_season(race_id: str) -> int | None:
    try:
        return int(race_id.split("_")[0])
    except (ValueError, IndexError, AttributeError):
        return None


# ---------- Request / Response models ----------


class DriverInput(BaseModel):
    driver_id: str
    constructor_id: str | None = None
    car_offset_ms: float = 0.0
    grid_position: int
    start_compound: str = "MEDIUM"
    skills: dict[str, float] = Field(default_factory=dict)


class ScenarioInput(BaseModel):
    driver_overrides: list[dict] = Field(default_factory=list)
    strategy_overrides: list[dict] = Field(default_factory=list)


class SimulateRequest(BaseModel):
    race_id: str
    scenario: ScenarioInput = Field(default_factory=ScenarioInput)
    drivers: list[DriverInput] = Field(default_factory=list)
    total_laps: int = 57


class SimulateResponse(BaseModel):
    job_id: str
    cached: bool


# ---------- Background worker ----------


async def _run_simulation(
    job_id: str,
    payload: dict,
    coordinator: SimulationCoordinator,
) -> None:
    """
    Calls external simulation endpoint, pipes SSE frames into Redis.
    Falls back to rule-based placeholder if endpoint unavailable.
    """
    coordinator.set_status(job_id, "running")
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", SIMULATION_ENDPOINT, json=payload) as resp:
                if resp.status_code != 200:
                    raise httpx.HTTPStatusError(
                        f"Simulation endpoint returned {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        frame = json.loads(line[6:])
                        coordinator.push_frame(job_id, frame)
                        if frame.get("type") == "complete":
                            coordinator.cache_result(
                                job_id,
                                frame,
                                has_strategy_overrides=bool(
                                    payload.get("scenario", {}).get(
                                        "strategy_overrides"
                                    )
                                ),
                            )
                    except json.JSONDecodeError:
                        pass
        coordinator.set_status(job_id, "complete")

    except Exception as exc:
        logger.warning(
            "Simulation endpoint unavailable, using rule-based fallback: %s", exc
        )
        _run_rule_based_fallback(job_id, payload, coordinator)


def _run_rule_based_fallback(
    job_id: str,
    payload: dict,
    coordinator: SimulationCoordinator,
) -> None:
    """
    Rule-based lap position generator used when simulation endpoint is unavailable.
    Produces plausible but non-ML lap frames so the frontend always has data.
    """
    drivers = payload.get("drivers", [])
    total_laps = payload.get("total_laps", 57)

    # Sort by grid position for starting order
    sorted_drivers = sorted(drivers, key=lambda d: d.get("grid_position", 99))

    for lap in range(1, total_laps + 1):
        cars = []
        for idx, driver in enumerate(sorted_drivers):
            lap_fraction = lap / total_laps
            # Smooth progression around the track
            track_pct = (lap_fraction + idx * 0.03) % 1.0
            cars.append(
                {
                    "id": driver.get("driver_id", f"car_{idx}"),
                    "track_pct": round(track_pct, 4),
                    "position": idx + 1,
                    "compound": driver.get("start_compound", "MEDIUM"),
                    "gap_ms": idx * 1200,
                    "lap_time_ms": 90000
                    + idx * 200
                    + round(driver.get("car_offset_ms", 0.0)),
                    "tire_age": lap,
                }
            )
        coordinator.push_frame(job_id, {"type": "lap", "lap": lap, "cars": cars})

    # Final frame
    coordinator.push_frame(
        job_id,
        {
            "type": "complete",
            "p10_finish": 1,
            "p50_finish": 1,
            "p90_finish": 3,
            "llm_context": {
                "winner": (
                    sorted_drivers[0].get("driver_id", "unknown")
                    if sorted_drivers
                    else "unknown"
                ),
                "fastest_lap": (
                    sorted_drivers[0].get("driver_id", "unknown")
                    if sorted_drivers
                    else "unknown"
                ),
                "safety_cars": 0,
                "total_pit_stops": len(sorted_drivers) * 1,
            },
        },
    )
    coordinator.cache_result(job_id, {"fallback": True})
    coordinator.set_status(job_id, "complete")


# ---------- Endpoints ----------


@router.post("/race", response_model=SimulateResponse)
async def start_simulation(
    request: SimulateRequest,
    background_tasks: BackgroundTasks,
) -> SimulateResponse:
    """Submit a race scenario for simulation. Returns job_id immediately."""

    coordinator = _get_coordinator()
    store = _get_constructor_store()
    season = _parse_season(request.race_id)

    # Resolve car_offset_ms from constructor pace store
    drivers_with_offsets = []
    for driver in request.drivers:
        offset_ms = driver.car_offset_ms
        if driver.constructor_id and season is not None:
            offset_ms = store.get_offset_ms(driver.constructor_id, season)
        drivers_with_offsets.append({**driver.model_dump(), "car_offset_ms": offset_ms})

    # Include drivers in hash so different constructor selections produce distinct jobs
    scenario_dict = request.scenario.model_dump()
    scenario_dict["drivers"] = drivers_with_offsets
    job_id = scenario_hash(request.race_id, scenario_dict)

    # Cache hit: replay existing frames
    if coordinator.replay_from_cache(job_id):
        return SimulateResponse(job_id=job_id, cached=True)

    # Cache miss: kick off background simulation
    coordinator.set_status(job_id, "pending")
    payload = request.model_dump()
    payload["drivers"] = drivers_with_offsets
    payload["n_trials"] = coordinator.n_trials(coordinator.get_queue_depth())
    background_tasks.add_task(_run_simulation, job_id, payload, coordinator)

    return SimulateResponse(job_id=job_id, cached=False)


@router.get("/race/stream")
async def stream_simulation(
    job_id: str = Query(..., min_length=1),
) -> StreamingResponse:
    """SSE stream of lap frames for a given job_id."""

    coordinator = _get_coordinator()

    async def event_stream():
        async for line in frames_to_sse(job_id, coordinator):
            yield line

    return StreamingResponse(event_stream(), media_type="text/event-stream")
