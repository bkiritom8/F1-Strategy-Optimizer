"""Async-safe wrapper for the Vertex AI embedding call.

_embed_one() in cache.py calls the Vertex AI SDK synchronously.
Calling it directly from an async FastAPI route blocks the uvicorn event loop.
This module wraps it with asyncio.to_thread so it runs in the thread-pool
executor and the event loop stays free.
"""

from __future__ import annotations

import asyncio

from src.llm.cache import _embed_one


async def async_embed(text: str) -> list[float]:
    """Embed text without blocking the event loop."""
    return await asyncio.to_thread(_embed_one, text)
