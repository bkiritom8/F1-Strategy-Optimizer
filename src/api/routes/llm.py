"""POST /llm/chat — standalone Gemini 2.5 Flash Q&A endpoint."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException
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
    """
    if tool_name != "get_strategy_recommendation":
        return {"error": f"Unknown tool: {tool_name}"}

    import math

    race_id = str(args.get("race_id", "unknown"))
    driver_id = str(args.get("driver_id", "unknown"))
    lap = int(args.get("current_lap", 1))
    compound = str(args.get("current_compound", "MEDIUM")).upper()
    fuel_level = float(args.get("fuel_level", max(0.0, 1.0 - lap / 80)))
    track_temp = float(args.get("track_temp", 44.0))
    air_temp = float(args.get("air_temp", 26.0))
    grid_position = int(args.get("grid_position", 5))

    # ── Circuit-specific base lap times (seconds) ──────────────────────────────
    circuit_key = race_id.split("_")[-1].lower() if "_" in race_id else "default"
    _BASE_TIMES: dict[str, float] = {
        "monaco": 72.9, "monza": 81.5, "spa": 105.8, "silverstone": 88.2,
        "bahrain": 93.4, "suzuka": 91.6, "singapore": 99.4, "default": 90.0,
    }
    base_lap_time = _BASE_TIMES.get(circuit_key, _BASE_TIMES["default"])

    # ── Sector split ratios (S1, S2, S3 as fraction of lap) ───────────────────
    _SECTOR_SPLITS: dict[str, tuple[float, float, float]] = {
        "monaco":      (0.265, 0.500, 0.235),
        "monza":       (0.330, 0.345, 0.325),
        "spa":         (0.310, 0.415, 0.275),
        "silverstone": (0.295, 0.390, 0.315),
        "bahrain":     (0.305, 0.380, 0.315),
        "default":     (0.300, 0.400, 0.300),
    }
    s1_frac, s2_frac, s3_frac = _SECTOR_SPLITS.get(circuit_key, _SECTOR_SPLITS["default"])

    # ── Compound performance delta (seconds per lap vs MEDIUM baseline) ────────
    _COMPOUND_DELTA = {"SOFT": -0.6, "MEDIUM": 0.0, "HARD": +0.55,
                       "INTERMEDIATE": +2.5, "WET": +5.0}
    compound_delta = _COMPOUND_DELTA.get(compound, 0.0)

    # ── Tire degradation: seconds lost per lap on current compound ─────────────
    tire_age = int(args.get("tire_age_laps", lap))
    _DEG_RATE = {"SOFT": 0.065, "MEDIUM": 0.042, "HARD": 0.028,
                 "INTERMEDIATE": 0.050, "WET": 0.045}
    deg_rate = _DEG_RATE.get(compound, 0.042)
    deg_penalty = deg_rate * tire_age

    # ── Track temperature correction (+0.03s per °C above 35°C) ───────────────
    temp_correction = max(0.0, (track_temp - 35.0) * 0.03)

    # ── Fuel load correction (fuel burn ~0.12s/kg, ~2.3 kg/lap at start) ──────
    fuel_penalty = fuel_level * 0.45  # heavier car = slower

    avg_lap_time = base_lap_time + compound_delta + deg_penalty + temp_correction + fuel_penalty

    # ── Sector times ───────────────────────────────────────────────────────────
    sector_1 = round(avg_lap_time * s1_frac, 3)
    sector_2 = round(avg_lap_time * s2_frac, 3)
    sector_3 = round(avg_lap_time - sector_1 - sector_2, 3)

    # ── Pit strategy decision ──────────────────────────────────────────────────
    total_laps = {"monaco": 78, "monza": 53, "spa": 44, "silverstone": 52,
                  "bahrain": 57, "default": 57}.get(circuit_key, 57)
    remaining = total_laps - lap
    # Pit when tires older than compound-specific cliff (laps)
    _CLIFF = {"SOFT": 18, "MEDIUM": 28, "HARD": 38}
    cliff = _CLIFF.get(compound, 28)
    pit_soon = tire_age >= cliff or (remaining > 15 and deg_rate * (remaining) > 1.5)

    _NEXT_COMPOUND = {"SOFT": "MEDIUM", "MEDIUM": "HARD", "HARD": "MEDIUM",
                      "INTERMEDIATE": "SOFT", "WET": "INTERMEDIATE"}
    next_compound = _NEXT_COMPOUND.get(compound, "HARD")

    # ── Projected finish position ──────────────────────────────────────────────
    strategy_bonus = -1 if not pit_soon and tire_age < cliff else 0
    finish_position = max(1, min(20, grid_position + strategy_bonus))

    # ── Total race time estimate ────────────────────────────────────────────────
    # Laps already done at current pace + remaining laps at next-compound pace
    next_compound_delta = _COMPOUND_DELTA.get(next_compound, 0.0)
    laps_done_time = lap * avg_lap_time
    remaining_lap_time = base_lap_time + next_compound_delta + temp_correction
    pit_stop_time = 22.5  # Monaco pit lane loss ~22.5s
    pit_count = 1 if pit_soon or lap > cliff else 0
    total_race_time = laps_done_time + remaining * remaining_lap_time + pit_count * pit_stop_time

    return {
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
        "tire_deg_per_lap_s": round(deg_rate, 3),
        "tire_age_laps": tire_age,
        # Grid / position
        "grid_position": grid_position,
        "projected_finish_position": finish_position,
        "total_race_time_estimate_s": round(total_race_time, 1),
        # Pit recommendation
        "recommended_action": "PIT_SOON" if pit_soon else "CONTINUE",
        "pit_window_start": lap + 1 if pit_soon else lap + max(1, cliff - tire_age),
        "pit_window_end": lap + 5 if pit_soon else lap + max(6, cliff - tire_age + 5),
        "target_compound": next_compound,
        "driving_mode": "PUSH" if not pit_soon and tire_age < cliff - 5 else "BALANCED",
        "brake_bias": 52.5,
        "confidence": 0.72,
        "model_source": "rule_based",
    }


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


class StrategyParseRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=500)


class StrategyParseResponse(BaseModel):
    driver_id: str
    strategy: list[list]  # e.g. [[15, "HARD"], [40, "MEDIUM"]]


@router.post("/chat", response_model=ChatResponse)
async def llm_chat(
    request: ChatRequest,
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
        return ChatResponse(
            answer=answer,
            latency_ms=latency_ms,
            model=RagConfig().LLM_MODEL,
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
