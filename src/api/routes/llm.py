"""POST /llm/chat — F1 strategy Q&A with batching, caching, and fallback chain.

Request flow:
  1. Per-user rate limit check (10 req/min, token bucket)
  2. Generic cache check (pre-warmed 20 common F1 questions, async embed)
  3. Real-time semantic cache check (race-context queries, async embed)
  4. Cache miss → enqueue into MicroBatcher
       Batcher fires batch of up to 50 requests concurrently every 100ms
       Provider chain: gemini-2.5-flash → gemini-1.5-flash → rule_based
       Each provider wrapped in a circuit breaker
  5. Store answer in real-time cache (async)
"""

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
    Ask an F1 strategy question with optional live race context.

    Rate limit: 10 requests/minute per user (configurable via LLM_RATE_LIMIT_RPM).
    Cache: generic pre-warmed cache + semantic real-time cache (race context).
    Fallback chain: gemini-2.5-flash → gemini-1.5-flash → rule-based advisor.
    """
    if not iam_simulator.check_permission(current_user, Permission.DATA_READ):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    from src.llm.rate_limiter import get_rate_limiter
    from src.llm.cache import get_generic_cache, get_realtime_cache
    from src.llm.batcher import get_batcher
    from rag.config import RagConfig

    start = time.time()
    structured = request.race_inputs.model_dump() if request.race_inputs else None
    user_id = current_user.username

    # ── Step 1: per-user rate limit ───────────────────────────────────────────
    if not await get_rate_limiter().is_allowed(user_id):
        raise HTTPException(
            status_code=429,
            detail="LLM rate limit exceeded. Default: 10 requests/minute per user.",
            headers={"Retry-After": "60"},
        )

    # ── Step 2: generic cache (no race context) ───────────────────────────────
    if not structured:
        cached = await get_generic_cache().async_lookup(request.question)
        if cached:
            return ChatResponse(
                answer=cached,
                latency_ms=round((time.time() - start) * 1000, 2),
                model="generic_cache",
                cache_hit=True,
            )

    # ── Step 3: real-time semantic cache (race context) ───────────────────────
    if structured:
        cached = await get_realtime_cache().async_lookup(request.question, structured)
        if cached:
            return ChatResponse(
                answer=cached,
                latency_ms=round((time.time() - start) * 1000, 2),
                model="realtime_cache",
                cache_hit=True,
            )

    # ── Step 4: cache miss → batcher → provider chain ─────────────────────────
    model_predictions: dict | None = None
    if structured:
        try:
            from src.llm.model_bridge import get_predictions
            model_predictions = get_predictions(structured) or None
        except Exception as exc:
            logger.warning("model_bridge failed (non-fatal): %s", exc)

    try:
        batcher = get_batcher()
        answer, provider_name = await batcher.enqueue(
            question=request.question,
            context_docs=[],
            structured_inputs=structured,
            model_predictions=model_predictions,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.error("LLM batcher error: %s", exc)
        raise HTTPException(status_code=500, detail="Error generating response")

    latency_ms = round((time.time() - start) * 1000, 2)

    # ── Step 5: store in real-time cache if race context was provided ─────────
    if structured:
        # Fire-and-forget — don't block the response on cache write
        import asyncio
        asyncio.create_task(
            get_realtime_cache().async_store(
                request.question, structured, answer, model_predictions or {}
            ),
            name="llm-cache-store",
        )

    return ChatResponse(
        answer=answer,
        latency_ms=latency_ms,
        model=provider_name,
        cache_hit=False,
    )


@router.get("/providers", tags=["llm"])
async def provider_status(current_user=Depends(get_current_user)) -> dict:
    """Return circuit breaker state for each LLM provider.

    Useful for monitoring: CLOSED = healthy, OPEN = failing, HALF_OPEN = recovering.
    """
    if not iam_simulator.check_permission(current_user, Permission.DATA_READ):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    from src.llm.provider import get_provider_chain
    return {
        "providers": get_provider_chain().status(),
        "batcher": _batcher_status(),
    }


def _batcher_status() -> dict:
    try:
        from src.llm.batcher import get_batcher
        b = get_batcher()
        return {
            "running": b._task is not None and not b._task.done(),
            "queue_depth": b._queue.qsize(),
            "max_batch_size": b._max_batch,
            "max_wait_ms": int(b._max_wait_s * 1000),
            "max_concurrent": b._semaphore._value,
        }
    except Exception:
        return {"running": False}
