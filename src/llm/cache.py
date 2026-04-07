"""Two-layer LLM response cache.

Layer 1 — Pre-warmed generic cache
    Common F1 strategy questions are embedded and answered at startup.
    Any incoming question with cosine similarity >= GENERIC_THRESHOLD (0.85)
    against a pre-warmed entry is served instantly without hitting Gemini.

Layer 2 — Semantic real-time cache
    For driver/race-context queries, the cache key combines:
      - The question embedding
      - A bucketed race state hash (lap rounded to 3, tire age to 5)
    Entries are invalidated on pit stops, safety car events, or when the
    lap bucket crosses a boundary. Max 256 entries with LRU eviction.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import vertexai
from src.llm.turboquant import TurboQuantVector, get_codec

logger = logging.getLogger(__name__)

# ── Tuning constants ──────────────────────────────────────────────────────────
GENERIC_THRESHOLD = 0.85  # cosine similarity to hit pre-warmed cache
REALTIME_THRESHOLD = 0.88  # higher bar for race-context cache (state must also match)
REALTIME_MAX_AGE_S = 180  # 3 minutes — entries expire after this regardless
REALTIME_MAX_SIZE = 256

# ── Common F1 strategy questions to pre-warm ──────────────────────────────────
GENERIC_QUESTIONS: list[str] = [
    "What is an undercut strategy in F1?",
    "What is an overcut strategy in F1?",
    "When should a driver use soft tyres?",
    "When should a driver use hard tyres?",
    "How does DRS work in Formula 1?",
    "What is a safety car in F1 and how does it affect strategy?",
    "What is tyre degradation and why does it matter?",
    "How many pit stops do teams typically make in a race?",
    "What is the difference between a one-stop and two-stop strategy?",
    "How does fuel load affect lap time?",
    "What is a virtual safety car (VSC)?",
    "How does track position affect F1 strategy?",
    "What is a stint in F1?",
    "How does weather affect tyre strategy?",
    "What is the pit window in F1?",
    "What does 'boxing' mean in F1?",
    "How does the safety car restart work?",
    "What is brake bias and how does it affect driving style?",
    "What is ERS deployment strategy in F1?",
    "How do teams decide when to pit during a safety car period?",
]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _embed_one(text: str) -> list[float]:
    """Embed a single text. Caller must have called vertexai.init() first."""
    from vertexai.language_models import TextEmbeddingModel

    model = TextEmbeddingModel.from_pretrained("text-embedding-004")
    return model.get_embeddings([text])[0].values


def _bucket_state(race_inputs: dict) -> str:
    """Build a bucketed state string from race_inputs for cache key hashing."""
    lap = int(race_inputs.get("current_lap") or 0)
    tire_age = int(race_inputs.get("tire_age_laps") or 0)
    compound = str(race_inputs.get("tire_compound") or "").upper()
    driver = str(race_inputs.get("driver") or "").upper()
    position = int(race_inputs.get("position") or 0)

    # Round continuous values to reduce cache misses across similar states
    lap_bucket = (lap // 3) * 3  # lap 20-22 → bucket 21
    tire_age_bucket = (tire_age // 5) * 5  # age 10-14 → bucket 10

    state_str = f"{driver}|{position}|{compound}|{lap_bucket}|{tire_age_bucket}"
    return hashlib.md5(state_str.encode(), usedforsecurity=False).hexdigest()[:8]


# ── Layer 1: Pre-warmed generic cache ─────────────────────────────────────────


@dataclass
class _GenericEntry:
    question: str
    embedding: TurboQuantVector
    answer: str


class GenericCache:
    """Pre-warmed cache for common F1 strategy questions."""

    def __init__(self) -> None:
        self._entries: list[_GenericEntry] = []
        self._ready = False
        self._lock = threading.Lock()

    def warm(self, client: Any, project: str, region: str) -> None:
        """Embed all GENERIC_QUESTIONS and pre-generate answers. Runs in background."""

        def _run() -> None:
            try:
                vertexai.init(project=project, location=region)
                logger.info(
                    "GenericCache: warming %d questions…", len(GENERIC_QUESTIONS)
                )
                entries: list[_GenericEntry] = []
                for q in GENERIC_QUESTIONS:
                    try:
                        emb = _embed_one(q)
                        answer = client.generate(q)
                        entries.append(
                            _GenericEntry(question=q, embedding=get_codec().encode(emb), answer=answer)
                        )
                        logger.debug("GenericCache: warmed — %s", q[:60])
                        time.sleep(0.5)  # stay within embedding quota
                    except Exception as exc:
                        logger.warning("GenericCache: skipping %r — %s", q[:50], exc)
                with self._lock:
                    self._entries = entries
                    self._ready = True
                logger.info("GenericCache: ready — %d entries", len(entries))
            except Exception as exc:
                logger.error("GenericCache: warm failed — %s", exc)

        t = threading.Thread(target=_run, daemon=True, name="llm-cache-warm")
        t.start()

    def lookup(self, question: str) -> str | None:
        """Synchronous lookup — safe to call from threads (e.g. warm thread).

        From async route handlers use async_lookup() instead.
        """
        if not self._ready:
            return None
        try:
            vertexai.init()  # no-op if already initialized
            q_emb = _embed_one(question)
        except Exception:
            return None

        codec = get_codec()
        q_prepared = codec.prepare_query(q_emb)
        with self._lock:
            best_score, best_answer = 0.0, None
            for entry in self._entries:
                score = codec.score(q_prepared, entry.embedding)
                if score > best_score:
                    best_score, best_answer = score, entry.answer

        if best_score >= GENERIC_THRESHOLD:
            logger.debug("GenericCache hit (%.3f): %s", best_score, question[:60])
            return best_answer
        return None

    async def async_lookup(self, question: str) -> str | None:
        """Async-safe lookup — runs the blocking embed call in a thread."""
        import asyncio

        if not self._ready:
            return None
        try:
            vertexai.init()
            q_emb = await asyncio.to_thread(_embed_one, question)
        except Exception:
            return None

        codec = get_codec()
        q_prepared = codec.prepare_query(q_emb)
        with self._lock:
            best_score, best_answer = 0.0, None
            for entry in self._entries:
                score = codec.score(q_prepared, entry.embedding)
                if score > best_score:
                    best_score, best_answer = score, entry.answer

        if best_score >= GENERIC_THRESHOLD:
            logger.debug("GenericCache hit (%.3f): %s", best_score, question[:60])
            return best_answer
        return None


# ── Layer 2: Semantic real-time cache ─────────────────────────────────────────


@dataclass
class _RealtimeEntry:
    embedding: TurboQuantVector
    state_hash: str
    answer: str
    model_predictions: dict
    created_at: float = field(default_factory=time.time)


class RealtimeCache:
    """Semantic cache for race-context queries, keyed on question meaning + bucketed state."""

    def __init__(self) -> None:
        self._entries: list[_RealtimeEntry] = []
        self._lock = threading.Lock()
        # Track last known state per driver for invalidation
        self._driver_states: dict[str, dict] = {}

    def _is_expired(self, entry: _RealtimeEntry) -> bool:
        return (time.time() - entry.created_at) > REALTIME_MAX_AGE_S

    def _invalidate_driver(self, driver: str) -> None:
        driver_key = driver.upper()
        with self._lock:
            self._entries = [e for e in self._entries if driver_key not in e.state_hash]
        logger.debug("RealtimeCache: invalidated entries for %s", driver)

    def _detect_invalidation(self, driver: str, race_inputs: dict) -> None:
        """Invalidate cache entries when a significant state change is detected."""
        key = driver.upper()
        prev = self._driver_states.get(key, {})

        pit_occurred = (
            prev.get("tire_compound")
            and prev.get("tire_compound") != race_inputs.get("tire_compound")
        ) or (
            (race_inputs.get("tire_age_laps") or 0)
            < (prev.get("tire_age_laps") or 0) - 2
        )

        sc_occurred = race_inputs.get("safety_car") and not prev.get("safety_car")

        if pit_occurred or sc_occurred:
            reason = "pit stop" if pit_occurred else "safety car"
            logger.info("RealtimeCache: invalidating %s — %s detected", driver, reason)
            self._invalidate_driver(driver)

        self._driver_states[key] = dict(race_inputs)

    def lookup(self, question: str, race_inputs: dict) -> str | None:
        """Synchronous lookup — safe to call from threads only.

        From async route handlers use async_lookup() instead.
        """
        driver = str(race_inputs.get("driver") or "")
        if driver:
            self._detect_invalidation(driver, race_inputs)

        state_hash = _bucket_state(race_inputs)

        try:
            q_emb = _embed_one(question)
        except Exception:
            return None

        codec = get_codec()
        q_prepared = codec.prepare_query(q_emb)
        with self._lock:
            self._entries = [e for e in self._entries if not self._is_expired(e)]
            best_score, best_entry = 0.0, None
            for entry in self._entries:
                if entry.state_hash != state_hash:
                    continue
                score = codec.score(q_prepared, entry.embedding)
                if score > best_score:
                    best_score, best_entry = score, entry

        if best_score >= REALTIME_THRESHOLD and best_entry:
            logger.debug("RealtimeCache hit (%.3f) state=%s", best_score, state_hash)
            return best_entry.answer
        return None

    async def async_lookup(self, question: str, race_inputs: dict) -> str | None:
        """Async-safe lookup — runs the blocking embed call in a thread."""
        import asyncio

        driver = str(race_inputs.get("driver") or "")
        if driver:
            self._detect_invalidation(driver, race_inputs)

        state_hash = _bucket_state(race_inputs)

        try:
            q_emb = await asyncio.to_thread(_embed_one, question)
        except Exception:
            return None

        codec = get_codec()
        q_prepared = codec.prepare_query(q_emb)
        with self._lock:
            self._entries = [e for e in self._entries if not self._is_expired(e)]
            best_score, best_entry = 0.0, None
            for entry in self._entries:
                if entry.state_hash != state_hash:
                    continue
                score = codec.score(q_prepared, entry.embedding)
                if score > best_score:
                    best_score, best_entry = score, entry

        if best_score >= REALTIME_THRESHOLD and best_entry:
            logger.debug("RealtimeCache hit (%.3f) state=%s", best_score, state_hash)
            return best_entry.answer
        return None

    def store(
        self, question: str, race_inputs: dict, answer: str, model_predictions: dict
    ) -> None:
        """Synchronous store — safe to call from threads only.

        From async route handlers use async_store() instead.
        """
        try:
            q_emb = _embed_one(question)
            state_hash = _bucket_state(race_inputs)
        except Exception:
            return

        with self._lock:
            if len(self._entries) >= REALTIME_MAX_SIZE:
                self._entries.sort(key=lambda e: e.created_at)
                self._entries = self._entries[REALTIME_MAX_SIZE // 4 :]
            self._entries.append(
                _RealtimeEntry(
                    embedding=get_codec().encode(q_emb),
                    state_hash=state_hash,
                    answer=answer,
                    model_predictions=model_predictions,
                )
            )

    async def async_store(
        self, question: str, race_inputs: dict, answer: str, model_predictions: dict
    ) -> None:
        """Async-safe store — runs the blocking embed call in a thread."""
        import asyncio

        try:
            q_emb = await asyncio.to_thread(_embed_one, question)
            state_hash = _bucket_state(race_inputs)
        except Exception:
            return

        with self._lock:
            if len(self._entries) >= REALTIME_MAX_SIZE:
                self._entries.sort(key=lambda e: e.created_at)
                self._entries = self._entries[REALTIME_MAX_SIZE // 4 :]
            self._entries.append(
                _RealtimeEntry(
                    embedding=get_codec().encode(q_emb),
                    state_hash=state_hash,
                    answer=answer,
                    model_predictions=model_predictions,
                )
            )


# ── Singletons ────────────────────────────────────────────────────────────────

_generic_cache: GenericCache | None = None
_realtime_cache: RealtimeCache | None = None


def get_generic_cache() -> GenericCache:
    global _generic_cache
    if _generic_cache is None:
        _generic_cache = GenericCache()
    return _generic_cache


def get_realtime_cache() -> RealtimeCache:
    global _realtime_cache
    if _realtime_cache is None:
        _realtime_cache = RealtimeCache()
    return _realtime_cache
