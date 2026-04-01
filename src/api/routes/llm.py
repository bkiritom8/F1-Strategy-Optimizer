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


def _execute_strategy_tool(tool_name: str, args: dict) -> dict:
    """Execute a Gemini function-call tool request and return a result dict.

    Currently supports ``get_strategy_recommendation``.  Uses the same
    rule-based fallback as the /strategy/recommend endpoint so that the
    LLM always gets real strategy data even when the ML model isn't loaded.
    """
    if tool_name != "get_strategy_recommendation":
        return {"error": f"Unknown tool: {tool_name}"}

    lap = int(args.get("current_lap", 1))
    compound = str(args.get("current_compound", "MEDIUM")).upper()
    fuel_level = float(args.get("fuel_level", max(0.0, 1.0 - lap / 80)))
    track_temp = float(args.get("track_temp", 44.0))
    air_temp = float(args.get("air_temp", 26.0))

    pit_soon = lap >= 35
    # Simple compound rotation: SOFT→MEDIUM→HARD→MEDIUM
    next_compound = (
        "MEDIUM" if compound == "SOFT" else "HARD" if compound == "MEDIUM" else "MEDIUM"
    )

    return {
        "race_id": args.get("race_id", "unknown"),
        "driver_id": args.get("driver_id", "unknown"),
        "current_lap": lap,
        "fuel_level": round(fuel_level, 2),
        "track_temp_c": track_temp,
        "air_temp_c": air_temp,
        "recommended_action": "PIT_SOON" if pit_soon else "CONTINUE",
        "pit_window_start": lap + 1 if pit_soon else None,
        "pit_window_end": lap + 5 if pit_soon else None,
        "target_compound": next_compound,
        "driving_mode": "BALANCED",
        "brake_bias": 52.5,
        "confidence": 0.65,
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


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    race_inputs: RaceInputs | None = None


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
        answer = client.generate_with_tools(
            request.question,
            _execute_strategy_tool,
            structured_inputs=structured,
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
