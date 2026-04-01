"""Dynamic micro-batcher for LLM requests.

Instead of each request independently racing to Gemini, the batcher collects
requests arriving within a 100ms window and fires them all concurrently via
asyncio.gather. This provides:

  - Controlled, predictable Vertex AI QPM consumption
  - Natural backpressure: requests queue in asyncio (zero threads blocked)
    while the active batch is in flight
  - A single code path for concurrency limits (the semaphore inside the batcher)

Flow:
  HTTP request → cache check (instant) ─── hit  → return immediately
                                         └── miss → batcher.enqueue()
                                                          │
                                        ┌─────────────────┘
                                        ▼
                              Collect up to MAX_BATCH_SIZE
                              requests over MAX_WAIT_MS
                                        │
                                        ▼
                         asyncio.gather(provider(r1), provider(r2), ...)
                         each call guarded by semaphore (MAX_CONCURRENT)
                                        │
                              Results → individual Futures
                              answered to their waiting coroutines

Configuration via env vars (no code change needed to tune):
  LLM_BATCH_MAX_SIZE      default 50
  LLM_BATCH_MAX_WAIT_MS   default 100
  LLM_BATCH_MAX_CONCURRENT default 20
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_MAX_BATCH = int(os.environ.get("LLM_BATCH_MAX_SIZE", "50"))
_MAX_WAIT_MS = float(os.environ.get("LLM_BATCH_MAX_WAIT_MS", "100"))
_MAX_CONCURRENT = int(os.environ.get("LLM_BATCH_MAX_CONCURRENT", "20"))


@dataclass
class BatchItem:
    question: str
    context_docs: list[Any]
    structured_inputs: dict[str, Any] | None
    model_predictions: dict[str, Any] | None
    future: asyncio.Future = field(default_factory=asyncio.Future)
    enqueued_at: float = field(default_factory=time.monotonic)


class MicroBatcher:
    """Collects LLM requests into micro-batches and fires them concurrently.

    Must be started with start() before first use. Call stop() on shutdown.
    """

    def __init__(
        self,
        max_batch_size: int = _MAX_BATCH,
        max_wait_ms: float = _MAX_WAIT_MS,
        max_concurrent: int = _MAX_CONCURRENT,
    ) -> None:
        self._max_batch = max_batch_size
        self._max_wait_s = max_wait_ms / 1000.0
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._queue: asyncio.Queue[BatchItem] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._stopped = False

        logger.info(
            "MicroBatcher created (batch=%d, wait=%.0fms, concurrent=%d)",
            max_batch_size, max_wait_ms, max_concurrent,
        )

    def start(self) -> None:
        """Start the background drain loop. Call once at app startup."""
        if self._task is None or self._task.done():
            self._stopped = False
            self._task = asyncio.create_task(self._drain_loop(), name="llm-batcher")
            self._task.add_done_callback(self._on_task_done)
            logger.info("MicroBatcher started")

    def stop(self) -> None:
        """Signal the drain loop to exit cleanly."""
        self._stopped = True
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("MicroBatcher stopped")

    def _on_task_done(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.error("MicroBatcher drain loop crashed: %s — restarting", exc)
            # Auto-restart so a transient crash doesn't take down the batcher
            if not self._stopped:
                self._task = asyncio.create_task(self._drain_loop(), name="llm-batcher")
                self._task.add_done_callback(self._on_task_done)

    async def enqueue(
        self,
        question: str,
        context_docs: list[Any],
        structured_inputs: dict[str, Any] | None,
        model_predictions: dict[str, Any] | None,
    ) -> tuple[str, str]:
        """Add a request to the next batch and await its result.

        Returns (answer_text, provider_name).
        Raises on LLM error (all providers failed).
        """
        loop = asyncio.get_running_loop()
        item = BatchItem(
            question=question,
            context_docs=context_docs,
            structured_inputs=structured_inputs,
            model_predictions=model_predictions,
            future=loop.create_future(),
        )
        await self._queue.put(item)
        return await item.future  # suspend until the batch resolves this future

    # ── Internal drain loop ────────────────────────────────────────────────────

    async def _drain_loop(self) -> None:
        """Continuously collect items and fire batches."""
        while not self._stopped:
            batch = await self._collect_batch()
            if not batch:
                continue
            # Fire the batch concurrently but don't await — start next collection
            # immediately so the window for the next batch starts accumulating
            asyncio.create_task(self._fire_batch(batch), name="llm-batch-fire")

    async def _collect_batch(self) -> list[BatchItem]:
        """Block until at least one item arrives, then collect for up to max_wait_s."""
        batch: list[BatchItem] = []
        deadline = asyncio.get_event_loop().time() + self._max_wait_s

        # Wait for the first item (no timeout — we block here until work arrives)
        try:
            first = await self._queue.get()
            batch.append(first)
        except asyncio.CancelledError:
            return batch

        # Drain remaining items within the window
        while len(batch) < self._max_batch:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=remaining)
                batch.append(item)
            except asyncio.TimeoutError:
                break

        logger.debug("Collected batch of %d (queue depth: %d)", len(batch), self._queue.qsize())
        return batch

    async def _fire_batch(self, batch: list[BatchItem]) -> None:
        """Fire all items in the batch concurrently."""
        from src.llm.provider import get_provider_chain
        chain = get_provider_chain()

        async def _one(item: BatchItem) -> None:
            if item.future.done():
                return  # client gave up (connection dropped)
            async with self._semaphore:
                wait_ms = (time.monotonic() - item.enqueued_at) * 1000
                logger.debug("Firing LLM request (waited %.1fms in queue)", wait_ms)
                try:
                    answer, provider = await chain.generate(
                        item.question,
                        item.context_docs,
                        item.structured_inputs,
                        item.model_predictions,
                    )
                    if not item.future.done():
                        item.future.set_result((answer, provider))
                except Exception as exc:
                    if not item.future.done():
                        item.future.set_exception(exc)

        await asyncio.gather(*[_one(item) for item in batch], return_exceptions=True)


# ── Module-level singleton ─────────────────────────────────────────────────────

_batcher: MicroBatcher | None = None


def get_batcher() -> MicroBatcher:
    """Return the shared MicroBatcher singleton."""
    global _batcher
    if _batcher is None:
        _batcher = MicroBatcher()
    return _batcher
