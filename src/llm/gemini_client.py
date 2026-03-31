"""Gemini 2.5 Flash client for F1 strategy Q&A."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from vertexai.generative_models import GenerativeModel
import vertexai

from rag.config import RagConfig

if TYPE_CHECKING:
    from langchain_core.documents import Document

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an expert F1 race strategy analyst with deep knowledge of "
    "76 years of Formula 1 (1950-2026). Answer the user's question directly "
    "and specifically. For what-if scenarios, reason through the strategic "
    "trade-offs clearly. Include relevant statistics, historical precedents, "
    "and technical reasoning when appropriate. If you lack sufficient data "
    "to answer confidently, say so clearly."
)

_FIELD_LABELS: dict[str, str] = {
    "driver": "Driver",
    "circuit": "Circuit",
    "current_lap": "Lap",
    "total_laps": "Total Laps",
    "tire_compound": "Tire Compound",
    "tire_age_laps": "Tire Age (laps)",
    "weather": "Weather",
    "track_temp": "Track Temp (°C)",
    "air_temp": "Air Temp (°C)",
    "position": "Position",
    "gap_to_leader": "Gap to Leader (s)",
    "fuel_remaining_kg": "Fuel Remaining (kg)",
}


class GeminiClient:
    """Wraps Gemini 2.5 Flash for F1 strategy Q&A.

    Lazily initializes Vertex AI on first generate() call.
    Shared by /llm/chat and rag/retriever.py.
    """

    def __init__(self, config: RagConfig | None = None) -> None:
        self._config = config or RagConfig()
        self._model: GenerativeModel | None = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        vertexai.init(project=self._config.PROJECT_ID, location=self._config.REGION)
        self._model = GenerativeModel(self._config.LLM_MODEL)
        self._initialized = True

    def build_prompt(
        self,
        question: str,
        context_docs: list = [],
        structured_inputs: dict | None = None,
        model_predictions: dict | None = None,
    ) -> str:
        """Assemble the full prompt from system message, optional context, and question."""
        parts = [SYSTEM_PROMPT]

        # RAG context docs — reserved for RAG integration
        if context_docs:
            doc_lines = []
            for doc in context_docs:
                doc_lines.append("---")
                doc_lines.append(doc.page_content)
            doc_lines.append("---")
            parts.append("\nContext:\n" + "\n".join(doc_lines))

        # Structured race inputs
        if structured_inputs:
            non_null = {k: v for k, v in structured_inputs.items() if v is not None}
            if non_null:
                context_pairs = [
                    f"{_FIELD_LABELS.get(k, k)}: {v}"
                    for k, v in non_null.items()
                    if k in _FIELD_LABELS
                ]
                if context_pairs:
                    parts.append("\nRace Context:\n" + " | ".join(context_pairs))

        # ML model predictions — injected as factual context for the LLM to reason over
        if model_predictions:
            _PRED_LABELS: dict[str, str] = {
                "tire_degradation":         "Tire Degradation",
                "pit_window":               "Pit Window",
                "safety_car_probability":   "Safety Car Probability",
                "recommended_driving_style": "Recommended Driving Style",
                "overtake_probability":     "Overtake Probability",
                "predicted_race_outcome":   "Predicted Race Outcome",
            }
            pred_lines = [
                f"  {_PRED_LABELS.get(k, k)}: {v}"
                for k, v in model_predictions.items()
            ]
            if pred_lines:
                parts.append("\nML Model Predictions:\n" + "\n".join(pred_lines))

        parts.append(f"\nQuestion: {question}")
        parts.append("\nAnswer:")
        return "\n".join(parts)

    def generate(
        self,
        question: str,
        context_docs: list = [],
        structured_inputs: dict | None = None,
        model_predictions: dict | None = None,
    ) -> str:
        """Call Gemini and return the answer text."""
        self._ensure_initialized()
        prompt = self.build_prompt(
            question,
            context_docs=context_docs,
            structured_inputs=structured_inputs,
            model_predictions=model_predictions,
        )
        response = self._model.generate_content(  # type: ignore[union-attr]
            prompt,
            generation_config={
                "temperature": self._config.LLM_TEMPERATURE,
                "max_output_tokens": self._config.MAX_OUTPUT_TOKENS,
            },
        )
        return response.text


# Module-level singleton — shared across requests
_client: GeminiClient | None = None


def get_client() -> GeminiClient:
    """Return the module-level GeminiClient singleton."""
    global _client
    if _client is None:
        _client = GeminiClient()
    return _client
