"""LLM provider abstraction with circuit breaker and fallback chain.

Providers (in priority order):
  1. GeminiFlashProvider    — gemini-2.5-flash   (primary, best quality)
  2. GeminiFallbackProvider — gemini-1.5-flash   (cheaper, still good)
  3. RuleBasedProvider      — deterministic logic (always available, no I/O)

Each provider has an independent CircuitBreaker that opens after
FAILURE_THRESHOLD consecutive errors, then attempts recovery after
RECOVERY_TIMEOUT_S seconds. With 25 Cloud Run instances each maintaining
their own breaker state this means all instances converge on a failing
provider within a few minutes without requiring shared state.

Swapping the primary model is a one-line change to LLM_PRIMARY_MODEL in
rag/config.py (or the LLM_PRIMARY_MODEL env var). The fallback model is
controlled by LLM_FALLBACK_MODEL.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# Tuneable via env vars — no code change needed to swap models
_PRIMARY_MODEL = os.environ.get("LLM_PRIMARY_MODEL", "gemini-2.5-flash")
_FALLBACK_MODEL = os.environ.get("LLM_FALLBACK_MODEL", "gemini-1.5-flash")

FAILURE_THRESHOLD = int(os.environ.get("LLM_CB_FAILURE_THRESHOLD", "5"))
RECOVERY_TIMEOUT_S = float(os.environ.get("LLM_CB_RECOVERY_TIMEOUT_S", "30"))


# ── Circuit breaker ────────────────────────────────────────────────────────────


class _CBState(Enum):
    CLOSED = "closed"        # healthy, pass requests through
    OPEN = "open"            # failing, reject fast
    HALF_OPEN = "half_open"  # recovery probe — one request gets through


@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = FAILURE_THRESHOLD
    recovery_timeout_s: float = RECOVERY_TIMEOUT_S
    _failures: int = field(default=0, init=False, repr=False)
    _state: _CBState = field(default=_CBState.CLOSED, init=False, repr=False)
    _opened_at: float = field(default=0.0, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    @property
    def state(self) -> _CBState:
        if self._state == _CBState.OPEN:
            if time.monotonic() - self._opened_at >= self.recovery_timeout_s:
                # Transition to half-open; let one probe through
                self._state = _CBState.HALF_OPEN
                logger.info("CircuitBreaker[%s] → HALF_OPEN (probing recovery)", self.name)
        return self._state

    def is_available(self) -> bool:
        s = self.state
        return s in (_CBState.CLOSED, _CBState.HALF_OPEN)

    async def on_success(self) -> None:
        async with self._lock:
            if self._state != _CBState.CLOSED:
                logger.info("CircuitBreaker[%s] → CLOSED (recovered)", self.name)
            self._failures = 0
            self._state = _CBState.CLOSED

    async def on_failure(self) -> None:
        async with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                if self._state != _CBState.OPEN:
                    logger.warning(
                        "CircuitBreaker[%s] → OPEN after %d failures",
                        self.name, self._failures,
                    )
                self._state = _CBState.OPEN
                self._opened_at = time.monotonic()


# ── Base provider ──────────────────────────────────────────────────────────────


class LLMProvider(ABC):
    """Abstract provider. All concrete implementations must be async-safe."""

    name: str = "base"

    def __init__(self) -> None:
        self.circuit = CircuitBreaker(name=self.name)

    @abstractmethod
    async def generate(
        self,
        question: str,
        context_docs: list[Any],
        structured_inputs: dict[str, Any] | None,
        model_predictions: dict[str, Any] | None,
    ) -> str:
        """Generate and return answer text. Must not block the event loop."""
        ...

    async def try_generate(
        self,
        question: str,
        context_docs: list[Any],
        structured_inputs: dict[str, Any] | None,
        model_predictions: dict[str, Any] | None,
    ) -> str | None:
        """Call generate() with circuit breaker protection.

        Returns None if the circuit is open or the call fails.
        """
        if not self.circuit.is_available():
            logger.debug("Provider %s circuit=%s — skipping", self.name, self.circuit.state.value)
            return None
        try:
            result = await self.generate(question, context_docs, structured_inputs, model_predictions)
            await self.circuit.on_success()
            return result
        except Exception as exc:
            await self.circuit.on_failure()
            logger.error("Provider %s error: %s", self.name, exc)
            return None


# ── Gemini providers ───────────────────────────────────────────────────────────


class GeminiProvider(LLMProvider):
    """Wraps GeminiClient for a given model name."""

    def __init__(self, model_name: str) -> None:
        self.name = model_name
        super().__init__()
        self._client: Any = None  # lazy-init

    def _get_client(self) -> Any:
        if self._client is None:
            from rag.config import RagConfig
            from src.llm.gemini_client import GeminiClient
            cfg = RagConfig()
            # Override the model name so this provider uses its own model
            cfg_copy = cfg.model_copy(update={"LLM_MODEL": self.name})
            self._client = GeminiClient(config=cfg_copy)
        return self._client

    async def generate(
        self,
        question: str,
        context_docs: list[Any],
        structured_inputs: dict[str, Any] | None,
        model_predictions: dict[str, Any] | None,
    ) -> str:
        client = self._get_client()
        return await client.async_generate(
            question,
            context_docs=context_docs,
            structured_inputs=structured_inputs,
            model_predictions=model_predictions,
        )


# ── Rule-based fallback — always available, zero I/O ──────────────────────────


class RuleBasedProvider(LLMProvider):
    """Deterministic strategy advisor.

    Never fails. Used as last resort when both Gemini providers are in
    circuit-open state. Produces a structured text response from race inputs
    without any network I/O.
    """

    name = "rule_based"

    async def generate(
        self,
        question: str,
        context_docs: list[Any],
        structured_inputs: dict[str, Any] | None,
        model_predictions: dict[str, Any] | None,
    ) -> str:
        return _rule_based_response(question, structured_inputs, model_predictions)

    async def try_generate(self, question, context_docs, structured_inputs, model_predictions) -> str | None:
        # Rule-based never trips the circuit breaker — always return a result
        return await self.generate(question, context_docs, structured_inputs, model_predictions)


def _rule_based_response(
    question: str,
    structured_inputs: dict[str, Any] | None,
    model_predictions: dict[str, Any] | None,
) -> str:
    """Generate a deterministic F1 strategy response from available data."""
    lines: list[str] = [
        "⚠️ AI models temporarily unavailable — rule-based strategy advice:\n"
    ]

    if structured_inputs:
        lap = structured_inputs.get("current_lap") or 0
        total = structured_inputs.get("total_laps") or 66
        tire_age = structured_inputs.get("tire_age_laps") or 0
        compound = (structured_inputs.get("tire_compound") or "UNKNOWN").upper()
        position = structured_inputs.get("position") or 0
        sc = structured_inputs.get("safety_car") or False
        pct = lap / max(total, 1)

        lines.append(f"Race situation: Lap {lap}/{total}, P{position}, {compound} tyres ({tire_age} laps old)")

        # Safety car window
        if sc:
            lines.append("🟡 Safety car deployed — strong pit opportunity. Box this lap if tyres are older than 10 laps.")

        # Tyre age guidance
        if tire_age >= 30:
            lines.append("🔴 Tyres critically worn. Pit at the earliest safe opportunity.")
        elif tire_age >= 20:
            lines.append("🟠 Tyres approaching end of life. Begin planning pit entry.")
        elif tire_age >= 10 and pct > 0.4:
            lines.append("🟡 Tyre performance degrading. Monitor lap time delta closely.")
        else:
            lines.append("🟢 Tyres performing within normal range. Continue current strategy.")

        # Race phase guidance
        if pct < 0.3:
            lines.append("Early race: prioritise track position. Avoid pitting unless safety car or tyre failure.")
        elif pct < 0.6:
            lines.append("Mid race: standard pit window. Undercut viable if within 2s of car ahead.")
        else:
            lines.append("Late race: assess whether remaining laps justify a pit stop time loss.")

    else:
        lines.append(
            "No live race data provided. General advice: monitor tyre degradation, "
            "target pit stops during safety car periods, and balance track position "
            "against tyre performance when deciding pit timing."
        )

    # Include model predictions if available
    if model_predictions:
        lines.append("\nML model predictions (generated before LLM outage):")
        for k, v in model_predictions.items():
            lines.append(f"  • {k.replace('_', ' ').title()}: {v}")

    lines.append(f"\nQuestion asked: {question}")
    return "\n".join(lines)


# ── Provider chain ─────────────────────────────────────────────────────────────


class ProviderChain:
    """Tries providers in order. Falls back on failure or open circuit.

    Always succeeds because RuleBasedProvider is the last entry and never fails.
    """

    def __init__(self, providers: list[LLMProvider]) -> None:
        self._providers = providers

    async def generate(
        self,
        question: str,
        context_docs: list[Any],
        structured_inputs: dict[str, Any] | None,
        model_predictions: dict[str, Any] | None,
    ) -> tuple[str, str]:
        """Return (answer_text, provider_name_used)."""
        for provider in self._providers:
            result = await provider.try_generate(
                question, context_docs, structured_inputs, model_predictions
            )
            if result is not None:
                return result, provider.name
        # Should never reach here because RuleBasedProvider always returns
        raise RuntimeError("All LLM providers exhausted — including rule-based fallback")

    def status(self) -> dict[str, str]:
        """Return circuit state for each provider — used by /llm/health."""
        return {p.name: p.circuit.state.value for p in self._providers}


# ── Module-level singleton ─────────────────────────────────────────────────────

_chain: ProviderChain | None = None


def get_provider_chain() -> ProviderChain:
    """Return the shared ProviderChain singleton, creating it on first call."""
    global _chain
    if _chain is None:
        _chain = ProviderChain(providers=[
            GeminiProvider(_PRIMARY_MODEL),
            GeminiProvider(_FALLBACK_MODEL),
            RuleBasedProvider(),
        ])
        logger.info(
            "ProviderChain initialised: %s → %s → rule_based",
            _PRIMARY_MODEL, _FALLBACK_MODEL,
        )
    return _chain
