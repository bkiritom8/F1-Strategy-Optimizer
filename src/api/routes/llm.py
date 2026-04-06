"""POST /llm/chat — standalone Gemini 2.5 Flash Q&A endpoint."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from src.security.https_middleware import get_current_user
from src.security.iam_simulator import iam_simulator, Permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm", tags=["llm"])

# ── RAG retriever singleton ────────────────────────────────────────────────────
_retriever = None


def _get_retriever():
    """Return the F1Retriever singleton if Vector Search is configured, else None."""
    global _retriever
    if _retriever is None:
        from rag.config import RagConfig

        if RagConfig().is_configured:
            from rag.retriever import F1Retriever

            _retriever = F1Retriever()
    return _retriever


def _execute_strategy_tool(tool_name: str, args: dict) -> dict:
    """Execute a Gemini function-call tool request and return a result dict.

    Returns rich simulation data: lap times, sector splits, grid/finish position,
    pit window, tire recommendation, and race time estimate.
    ML model outputs (tire degradation, pit window, driving style, safety car,
    overtake probability, race outcome) override rule-based fallbacks when available.
    """
    if tool_name != "get_strategy_recommendation":
        return {"error": f"Unknown tool: {tool_name}"}

    race_id = str(args.get("race_id", "unknown"))
    driver_id = str(args.get("driver_id", "unknown"))
    lap = int(args.get("current_lap", 1))
    compound = str(args.get("current_compound", "MEDIUM")).upper()
    fuel_level = float(args.get("fuel_level", max(0.0, 1.0 - lap / 80)))
    track_temp = float(args.get("track_temp", 44.0))
    air_temp = float(args.get("air_temp", 26.0))
    grid_position = int(args.get("grid_position", 5))
    tire_age = int(args.get("tire_age_laps", lap))

    # ── Circuit-specific base lap times (seconds) ──────────────────────────────
    circuit_key = race_id.split("_")[-1].lower() if "_" in race_id else "default"
    _BASE_TIMES: dict[str, float] = {
        "monaco": 72.9,
        "monza": 81.5,
        "spa": 105.8,
        "silverstone": 88.2,
        "bahrain": 93.4,
        "suzuka": 91.6,
        "singapore": 99.4,
        "default": 90.0,
    }
    base_lap_time = _BASE_TIMES.get(circuit_key, _BASE_TIMES["default"])

    # ── Sector split ratios (S1, S2, S3 as fraction of lap) ───────────────────
    _SECTOR_SPLITS: dict[str, tuple[float, float, float]] = {
        "monaco": (0.265, 0.500, 0.235),
        "monza": (0.330, 0.345, 0.325),
        "spa": (0.310, 0.415, 0.275),
        "silverstone": (0.295, 0.390, 0.315),
        "bahrain": (0.305, 0.380, 0.315),
        "default": (0.300, 0.400, 0.300),
    }
    s1_frac, s2_frac, s3_frac = _SECTOR_SPLITS.get(
        circuit_key, _SECTOR_SPLITS["default"]
    )

    # ── Compound performance delta (seconds per lap vs MEDIUM baseline) ────────
    _COMPOUND_DELTA = {
        "SOFT": -0.6,
        "MEDIUM": 0.0,
        "HARD": +0.55,
        "INTERMEDIATE": +2.5,
        "WET": +5.0,
    }
    compound_delta = _COMPOUND_DELTA.get(compound, 0.0)

    # ── Rule-based fallback deg rates ─────────────────────────────────────────
    _DEG_RATE_FALLBACK = {
        "SOFT": 0.065,
        "MEDIUM": 0.042,
        "HARD": 0.028,
        "INTERMEDIATE": 0.050,
        "WET": 0.045,
    }

    # ── Try ML models (override rule-based values where available) ─────────────
    total_laps = {
        "monaco": 78,
        "monza": 53,
        "spa": 44,
        "silverstone": 52,
        "bahrain": 57,
        "default": 57,
    }.get(circuit_key, 57)

    ml_preds: dict = {}
    try:
        from src.llm.model_bridge import get_predictions

        ml_preds = get_predictions(
            {
                "current_lap": lap,
                "total_laps": total_laps,
                "tire_age_laps": tire_age,
                "tire_compound": compound,
                "position": grid_position,
                "driver": driver_id,
                "circuit": circuit_key,
                "gap_to_leader": 2.0,
            }
        )
    except Exception:
        pass

    # Parse ML tire degradation: "+0.285s/lap" → 0.285
    deg_rate = _DEG_RATE_FALLBACK.get(compound, 0.042)
    if "tire_degradation" in ml_preds:
        try:
            deg_rate = abs(
                float(ml_preds["tire_degradation"].replace("s/lap", "").strip())
            )
        except (ValueError, AttributeError):
            pass

    # Parse ML pit window: "pit in ~12 laps" → laps_to_pit = 12
    _CLIFF = {"SOFT": 18, "MEDIUM": 28, "HARD": 38}
    cliff = _CLIFF.get(compound, 28)
    laps_left_in_stint = max(0, cliff - tire_age)
    if "pit_window" in ml_preds:
        import re as _re

        m = _re.search(r"(\d+)", ml_preds["pit_window"])
        if m:
            laps_left_in_stint = max(0, int(m.group(1)))

    remaining = total_laps - lap
    pit_soon = laps_left_in_stint == 0 or (laps_left_in_stint <= 5 and remaining > 5)

    # Driving style from ML model; fall back to rule-based
    _STYLE_MAP = {"PUSH": "PUSH", "NEUTRAL": "BALANCED", "BALANCE": "BALANCED"}
    if "recommended_driving_style" in ml_preds:
        driving_mode = _STYLE_MAP.get(
            ml_preds["recommended_driving_style"].upper(), "BALANCED"
        )
    else:
        driving_mode = "PUSH" if not pit_soon and tire_age < cliff - 5 else "BALANCED"

    _NEXT_COMPOUND = {
        "SOFT": "MEDIUM",
        "MEDIUM": "HARD",
        "HARD": "MEDIUM",
        "INTERMEDIATE": "SOFT",
        "WET": "INTERMEDIATE",
    }
    next_compound = _NEXT_COMPOUND.get(compound, "HARD")

    # ── Projected finish position ──────────────────────────────────────────────
    # Use race outcome tier from ML if available, else rule-based nudge
    # Classes are exactly: "Podium" (P1-3), "Points" (P4-10), "Outside" (P11+)
    _OUTCOME_POSITION: dict[str, int] = {
        "Podium": 2,
        "Points": 7,
        "Outside": 15,
    }
    if "predicted_race_outcome" in ml_preds:
        finish_position = _OUTCOME_POSITION.get(
            ml_preds["predicted_race_outcome"].lower(), grid_position
        )
        finish_position = max(1, min(20, finish_position))
    else:
        strategy_bonus = -1 if not pit_soon and tire_age < cliff else 0
        finish_position = max(1, min(20, grid_position + strategy_bonus))

    # ── Lap time & race time estimate ─────────────────────────────────────────
    deg_penalty = deg_rate * tire_age
    temp_correction = max(0.0, (track_temp - 35.0) * 0.03)
    fuel_penalty = fuel_level * 0.45
    avg_lap_time = (
        base_lap_time + compound_delta + deg_penalty + temp_correction + fuel_penalty
    )

    sector_1 = round(avg_lap_time * s1_frac, 3)
    sector_2 = round(avg_lap_time * s2_frac, 3)
    sector_3 = round(avg_lap_time - sector_1 - sector_2, 3)

    next_compound_delta = _COMPOUND_DELTA.get(next_compound, 0.0)
    laps_done_time = lap * avg_lap_time
    remaining_lap_time = base_lap_time + next_compound_delta + temp_correction
    pit_stop_time = 22.5
    pit_count = 1 if pit_soon or lap > cliff else 0
    total_race_time = (
        laps_done_time + remaining * remaining_lap_time + pit_count * pit_stop_time
    )

    result = {
        "race_id": race_id,
        "driver_id": driver_id,
        "circuit": circuit_key,
        "total_laps": total_laps,
        "current_lap": lap,
        "fuel_level": round(fuel_level, 2),
        "track_temp_c": track_temp,
        "air_temp_c": air_temp,
        # Lap time data
        "avg_lap_time_s": round(avg_lap_time, 3),
        "sector_1_avg_s": sector_1,
        "sector_2_avg_s": sector_2,
        "sector_3_avg_s": sector_3,
        "current_compound": compound,
        "tire_deg_per_lap_s": round(deg_rate, 3),
        "tire_age_laps": tire_age,
        # Grid / position
        "grid_position": grid_position,
        "projected_finish_position": finish_position,
        "total_race_time_estimate_s": round(total_race_time, 1),
        # Pit recommendation
        "recommended_action": "PIT_SOON" if pit_soon else "CONTINUE",
        "pit_window_start": lap + 1 if pit_soon else lap + max(1, laps_left_in_stint),
        "pit_window_end": lap + 5 if pit_soon else lap + max(6, laps_left_in_stint + 5),
        "target_compound": next_compound,
        "driving_mode": driving_mode,
        "brake_bias": 52.5,
        "confidence": 0.72,
        "model_source": "ml" if ml_preds else "rule_based",
    }
    # Append any extra ML signals that the rule-based path can't produce
    for key in (
        "safety_car_probability",
        "overtake_probability",
        "predicted_race_outcome",
    ):
        if key in ml_preds:
            result[key] = ml_preds[key]
    return result


class RaceInputs(BaseModel):
    driver: str | None = None
    circuit: str | None = None
    current_lap: int | None = None
    total_laps: int | None = None
    tire_compound: str | None = None
    tire_age_laps: int | None = None
    weather: str | None = None
    track_temp: float | None = None
    air_temp: float | None = None
    position: int | None = None
    gap_to_leader: float | None = None
    fuel_remaining_kg: float | None = None


class ChatHistory(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    race_inputs: RaceInputs | None = None
    history: list[ChatHistory] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    latency_ms: float
    model: str
    job_id: str | None = None  # present when a simulation was triggered
    simulation_race_id: str | None = None  # circuit for the frontend to load


class StrategyParseRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=500)


class StrategyParseResponse(BaseModel):
    driver_id: str
    strategy: list[list]  # e.g. [[15, "HARD"], [40, "MEDIUM"]]


async def _fire_simulation(
    job_id: str,
    race_id: str,
    coordinator,
) -> None:
    """Fire-and-forget simulation background task."""
    from src.api.routes.simulate import _run_simulation

    payload = {
        "race_id": race_id,
        "scenario": {},
        "drivers": [],
        "total_laps": 57,
        "n_trials": coordinator.n_trials(coordinator.get_queue_depth()),
    }
    coordinator.set_status(job_id, "pending")
    await _run_simulation(job_id, payload, coordinator)


@router.post("/chat", response_model=ChatResponse)
async def llm_chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
) -> ChatResponse:
    """
    Ask an F1 strategy question. Optionally provide structured race inputs
    (driver, circuit, lap, tire compound, etc.) to enrich the answer.

    Requires: DATA_READ permission.
    """
    if not iam_simulator.check_permission(current_user, Permission.DATA_READ):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    from src.llm.gemini_client import get_client
    from rag.config import RagConfig

    try:
        client = get_client()
        start = time.time()
        structured = request.race_inputs.model_dump() if request.race_inputs else None

        # Retrieve RAG context if Vector Search is configured
        retriever = _get_retriever()
        try:
            context_docs = retriever.retrieve(request.question) if retriever else []
        except Exception as rag_exc:
            logger.warning(
                "RAG retrieval failed, proceeding without context: %s", rag_exc
            )
            context_docs = []

        answer = client.generate_with_tools(
            request.question,
            _execute_strategy_tool,
            structured_inputs=structured,
            context_docs=context_docs,
            history=[{"role": h.role, "content": h.content} for h in request.history],
        )
        latency_ms = round((time.time() - start) * 1000, 2)

        # If this was a simulation question, kick off the simulation job
        job_id = None
        simulation_race_id = None
        from src.llm.gemini_client import GeminiClient

        if GeminiClient._is_simulation_question(request.question):
            try:
                from src.api.routes.simulate import ScenarioInput
                from src.simulation.coordinator import (
                    SimulationCoordinator,
                    scenario_hash,
                )

                circuit = (
                    request.race_inputs.circuit
                    if request.race_inputs and request.race_inputs.circuit
                    else "monaco"
                )
                race_id = f"2025_{circuit.lower().replace(' ', '_')}"
                scenario = ScenarioInput()
                job_id = scenario_hash(race_id, scenario.model_dump())
                simulation_race_id = race_id
                coord = SimulationCoordinator()
                if not coord.replay_from_cache(job_id):
                    background_tasks.add_task(_fire_simulation, job_id, race_id, coord)
            except Exception as sim_exc:
                logger.warning("Failed to trigger simulation: %s", sim_exc)

        return ChatResponse(
            answer=answer,
            latency_ms=latency_ms,
            model=RagConfig().LLM_MODEL,
            job_id=job_id,
            simulation_race_id=simulation_race_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.error("LLM chat error: %s", exc)
        raise HTTPException(status_code=500, detail="Error generating response")


@router.post("/parse-strategy", response_model=StrategyParseResponse)
async def parse_strategy(
    request: StrategyParseRequest,
    current_user=Depends(get_current_user),
) -> StrategyParseResponse:
    """
    Parse a natural language strategy request into a structured JSON payload
    using Gemini. Validates against the /strategy/simulate schemas.

    Requires: DATA_READ permission.
    """
    if not iam_simulator.check_permission(current_user, Permission.DATA_READ):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    from src.llm.gemini_client import get_client

    try:
        client = get_client()
        result = client.parse_strategy_json(request.prompt)
        return StrategyParseResponse(
            driver_id=result.get("driver_id", ""),
            strategy=result.get("strategy", []),
        )
    except Exception as exc:
        logger.error("LLM parse strategy error: %s", exc)
        raise HTTPException(status_code=500, detail="Error parsing strategy")
