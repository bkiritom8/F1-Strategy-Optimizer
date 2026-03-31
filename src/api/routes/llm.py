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
    safety_car: bool | None = None


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    race_inputs: RaceInputs | None = None


class ChatResponse(BaseModel):
    answer: str
    latency_ms: float
    model: str
    cache_hit: bool = False


@router.post("/chat", response_model=ChatResponse)
async def llm_chat(
    request: ChatRequest,
    current_user=Depends(get_current_user),
) -> ChatResponse:
    """
    Ask an F1 strategy question. Optionally provide structured race inputs
    (driver, circuit, lap, tire compound, etc.) to enrich the answer with
    live ML model predictions.

    Cache behaviour:
      - Generic questions (no race_inputs): checked against pre-warmed cache first.
      - Race-context questions (with race_inputs): checked against semantic
        real-time cache keyed on question meaning + bucketed race state.

    Requires: DATA_READ permission.
    """
    if not iam_simulator.check_permission(current_user, Permission.DATA_READ):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    from src.llm.gemini_client import get_client
    from src.llm.cache import get_generic_cache, get_realtime_cache
    from rag.config import RagConfig

    start = time.time()
    structured = request.race_inputs.model_dump() if request.race_inputs else None

    # ── Layer 1: pre-warmed generic cache ─────────────────────────────────────
    if not structured:
        cached = get_generic_cache().lookup(request.question)
        if cached:
            return ChatResponse(
                answer=cached,
                latency_ms=round((time.time() - start) * 1000, 2),
                model=RagConfig().LLM_MODEL,
                cache_hit=True,
            )

    # ── Layer 2: semantic real-time cache ─────────────────────────────────────
    if structured:
        cached = get_realtime_cache().lookup(request.question, structured)
        if cached:
            return ChatResponse(
                answer=cached,
                latency_ms=round((time.time() - start) * 1000, 2),
                model=RagConfig().LLM_MODEL,
                cache_hit=True,
            )

    # ── Cache miss: run ML models + Gemini ────────────────────────────────────
    try:
        client = get_client()

        model_predictions: dict | None = None
        if structured:
            from src.llm.model_bridge import get_predictions

            model_predictions = get_predictions(structured) or None

        answer = client.generate(
            request.question,
            structured_inputs=structured,
            model_predictions=model_predictions,
        )
        latency_ms = round((time.time() - start) * 1000, 2)

        # Store in real-time cache if race context was provided
        if structured:
            get_realtime_cache().store(
                request.question, structured, answer, model_predictions or {}
            )

        return ChatResponse(
            answer=answer,
            latency_ms=latency_ms,
            model=RagConfig().LLM_MODEL,
            cache_hit=False,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.error("LLM chat error: %s", exc)
        raise HTTPException(status_code=500, detail="Error generating response")
