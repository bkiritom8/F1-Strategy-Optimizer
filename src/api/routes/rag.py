from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from src.security.https_middleware import get_current_user
from src.security.iam_simulator import iam_simulator, Permission
import logging
import hashlib
import json
from functools import lru_cache

if TYPE_CHECKING:
    from rag.retriever import F1Retriever

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag", tags=["rag"])

# Module-level singleton — initialized on first request
_retriever: F1Retriever | None = None

# LRU cache for repeated queries (max 128 entries)
_CACHE_MAX_SIZE = 128
_query_cache: dict = {}
_cache_keys: list = []


def _cache_key(query: str, filters: dict | None, top_k: int) -> str:
    """Generate a cache key from query parameters."""
    payload = {"query": query, "filters": filters or {}, "top_k": top_k}
    return hashlib.md5(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def get_retriever() -> F1Retriever:
    """Return singleton F1Retriever, creating it on first call."""
    global _retriever
    if _retriever is None:
        from rag.retriever import F1Retriever

        _retriever = F1Retriever()
    return _retriever


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    filters: dict | None = None
    top_k: int = Field(default=5, ge=1, le=10)


class SourceDoc(BaseModel):
    content: str
    metadata: dict


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceDoc]
    query: str
    num_sources: int
    latency_ms: float


class HealthResponse(BaseModel):
    status: str  # "ready" | "not_configured"
    index_configured: bool
    endpoint_configured: bool
    model: str


@router.post("/query", response_model=QueryResponse)
async def query_rag(request: QueryRequest, current_user=Depends(get_current_user)):
    """
    Run a RAG query against F1 data.
    Returns 503 if VECTOR_SEARCH_INDEX_ID or VECTOR_SEARCH_ENDPOINT_ID are not set.
    Requires: DATA_READ permission.
    """
    if not iam_simulator.check_permission(current_user, Permission.DATA_READ):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    retriever = get_retriever()
    if not retriever.config.is_configured:
        raise HTTPException(
            status_code=503,
            detail="RAG index not configured",
        )

    # Check cache first
    key = _cache_key(request.query, request.filters, request.top_k)
    if key in _query_cache:
        logger.debug("Cache hit for query: %s", request.query[:50])
        result = _query_cache[key]
    else:
        result = retriever.query(
            request.query, filters=request.filters, top_k=request.top_k
        )
        # Store in cache, evict oldest if full
        if len(_query_cache) >= _CACHE_MAX_SIZE:
            oldest = _cache_keys.pop(0)
            _query_cache.pop(oldest, None)
        _query_cache[key] = result
        _cache_keys.append(key)

    return QueryResponse(
        answer=result["answer"],
        sources=[
            SourceDoc(content=s["content"], metadata=s["metadata"])
            for s in result["sources"]
        ],
        query=result["query"],
        num_sources=result["num_sources"],
        latency_ms=result["latency_ms"],
    )


@router.get("/health", response_model=HealthResponse)
async def rag_health():
    """
    Check RAG configuration status.
    Always returns 200 — does not require index to be configured.
    """
    try:
        retriever = get_retriever()
        config = retriever.config
        index_configured = bool(config.VECTOR_SEARCH_INDEX_ID)
        endpoint_configured = bool(config.VECTOR_SEARCH_ENDPOINT_ID)
        rag_status = (
            "ready" if (index_configured and endpoint_configured) else "not_configured"
        )
        model = config.LLM_MODEL
    except Exception:
        index_configured = False
        endpoint_configured = False
        rag_status = "not_configured"
        model = "unknown"

    return HealthResponse(
        status=rag_status,
        index_configured=index_configured,
        endpoint_configured=endpoint_configured,
        model=model,
    )
