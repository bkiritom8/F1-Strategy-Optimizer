"""Gemini 2.5 Flash client for F1 strategy Q&A."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from vertexai.generative_models import FunctionDeclaration, GenerativeModel, Part, Tool
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
    "to answer confidently, say so clearly.\n\n"
    "When strategy simulation data is available from the tool, ALWAYS lead your answer "
    "with a structured data summary using this exact format before any prose:\n\n"
    "**Simulation Data**\n"
    "• Grid Position: P{grid_position} → Projected Finish: P{projected_finish}\n"
    "• Avg Lap Time: {avg_lap_time}s  |  Race Time Est: {race_time}\n"
    "• Sector Times: S1 {s1}s · S2 {s2}s · S3 {s3}s\n"
    "• Tire: {compound} (age {tire_age} laps) — deg {deg_rate}s/lap\n"
    "• Pit Window: Lap {pit_start}–{pit_end} → {next_compound}\n\n"
    "Then provide your strategic analysis."
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


_STRATEGY_TOOL = Tool(
    function_declarations=[
        FunctionDeclaration(
            name="get_strategy_recommendation",
            description=(
                "Get an F1 race strategy recommendation for a specific driver and race scenario. "
                "Call this for any what-if question, driver swap scenario, pit strategy question, "
                "or 'simulate' request. Returns lap times, sector splits, grid/finish position, "
                "pit window, tire compound, and race time estimate."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "race_id": {
                        "type": "string",
                        "description": "Race identifier e.g. '2025_monaco', '2025_bahrain', '2024_1'",
                    },
                    "driver_id": {
                        "type": "string",
                        "description": (
                            "Driver slug e.g. 'hamilton', 'max_verstappen', "
                            "'leclerc', 'norris', 'piastri', 'russell'"
                        ),
                    },
                    "current_lap": {
                        "type": "integer",
                        "description": "Lap number to simulate from. Monaco has 78 laps.",
                    },
                    "current_compound": {
                        "type": "string",
                        "description": "Current tire compound: SOFT, MEDIUM, or HARD",
                    },
                    "fuel_level": {
                        "type": "number",
                        "description": "Fuel remaining as fraction 0.0 (empty) to 1.0 (full). Estimate from lap.",
                    },
                    "track_temp": {
                        "type": "number",
                        "description": "Track surface temperature in Celsius (Monaco typical: 42-50°C)",
                    },
                    "air_temp": {
                        "type": "number",
                        "description": "Air temperature in Celsius",
                    },
                    "grid_position": {
                        "type": "integer",
                        "description": "Starting grid position (1 = pole). Estimate based on driver/team if not given.",
                    },
                    "tire_age_laps": {
                        "type": "integer",
                        "description": "Number of laps on the current tire set.",
                    },
                },
                "required": [
                    "race_id",
                    "driver_id",
                    "current_lap",
                    "current_compound",
                    "fuel_level",
                    "track_temp",
                    "air_temp",
                ],
            },
        )
    ]
)


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
        sim_context: dict | None = None,
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

        if sim_context:
            parts.append(
                "\n\n**Monte Carlo Simulation Result (50 trials):**\n"
                f"- P10 finish: P{sim_context.get('p10_finish', '?')}\n"
                f"- P50 finish: P{sim_context.get('p50_finish', '?')}\n"
                f"- P90 finish: P{sim_context.get('p90_finish', '?')}\n"
                f"- Winner: {sim_context.get('winner', '?')}\n"
                f"- Fastest lap: {sim_context.get('fastest_lap', '?')}\n"
                f"- Safety cars: {sim_context.get('safety_cars', 0)}"
            )

        parts.append(f"\nQuestion: {question}")
        parts.append("\nAnswer:")
        return "\n".join(parts)

    def generate(
        self,
        question: str,
        context_docs: list = [],
        structured_inputs: dict | None = None,
    ) -> str:
        """Call Gemini and return the answer text."""
        self._ensure_initialized()
        prompt = self.build_prompt(
            question,
            context_docs=context_docs,
            structured_inputs=structured_inputs,
        )
        response = self._model.generate_content(  # type: ignore[union-attr]
            prompt,
            generation_config={
                "temperature": self._config.LLM_TEMPERATURE,
                "max_output_tokens": self._config.MAX_OUTPUT_TOKENS,
            },
        )
        # Safely extract text — response.text raises on MAX_TOKENS finish_reason
        # in newer Vertex AI SDK versions; extract from candidates directly instead.
        if response.candidates:
            parts = response.candidates[0].content.parts
            if parts:
                return "".join(p.text for p in parts if hasattr(p, "text"))
        return response.text  # type: ignore[return-value]

    @staticmethod
    def _is_simulation_question(question: str) -> bool:
        """Return True if the question is asking for a simulation/what-if/strategy."""
        q = question.lower()
        triggers = [
            "what if",
            "simulate",
            "put ",
            "swap",
            "replace",
            "in the car",
            "pit stop",
            "pit window",
            "strategy for",
            "lap time",
            "sector",
            "undercut",
            "overcut",
            "stint",
            "tyre",
            "tire",
            "compound",
            "qualify",
            "race pace",
            "what would happen",
        ]
        return any(t in q for t in triggers)

    def generate_with_tools(
        self,
        question: str,
        tool_executor: Callable[[str, dict], dict],
        structured_inputs: dict | None = None,
        context_docs: list = [],
        history: list[dict] | None = None,
    ) -> str:
        """Call Gemini with function-calling tools enabled.

        For simulation/what-if questions the tool is called eagerly before
        the first Gemini turn so the model always receives real data.
        For other questions Gemini decides whether to call the tool.

        ``history`` is a list of dicts with ``role`` ("user" or "assistant")
        and ``content`` keys representing prior conversation turns.
        """
        from vertexai.generative_models import Content

        self._ensure_initialized()

        # Convert history dicts to Vertex AI Content objects
        formatted_history: list[Content] = []
        if history:
            for turn in history:
                role = "model" if turn.get("role") == "assistant" else "user"
                formatted_history.append(
                    Content(role=role, parts=[Part.from_text(turn.get("content", ""))])
                )

        model_with_tools = GenerativeModel(
            self._config.LLM_MODEL,
            tools=[_STRATEGY_TOOL],
        )
        chat = model_with_tools.start_chat(history=formatted_history)
        gen_config = {
            "temperature": self._config.LLM_TEMPERATURE,
            "max_output_tokens": self._config.MAX_OUTPUT_TOKENS,
        }

        # ── Eager tool call for simulation questions ───────────────────────────
        # If the question looks like a what-if/simulation, call the tool directly
        # and inject the result into the prompt so Gemini always has real data.
        eager_sim_context = ""
        if self._is_simulation_question(question):
            # Derive args from structured_inputs if available, else use sensible defaults
            si = structured_inputs or {}
            race_id = f"2025_{si.get('circuit', 'monaco').lower().replace(' ', '_')}"
            driver_id = si.get("driver", "unknown").lower().replace(" ", "_")
            current_lap = int(si.get("current_lap") or 25)
            compound = str(si.get("tire_compound") or "MEDIUM").upper()
            fuel_level = max(0.0, 1.0 - current_lap / 80)
            track_temp = float(si.get("track_temp") or 44.0)
            air_temp = float(si.get("air_temp") or 26.0)

            # Parse grid/lap from question text as a fallback
            import re as _re

            lap_match = _re.search(r"\blap\s+(\d+)\b", question, _re.IGNORECASE)
            if lap_match:
                current_lap = int(lap_match.group(1))

            try:
                sim_result = tool_executor(
                    "get_strategy_recommendation",
                    {
                        "race_id": race_id,
                        "driver_id": driver_id,
                        "current_lap": current_lap,
                        "current_compound": compound,
                        "fuel_level": round(fuel_level, 2),
                        "track_temp": track_temp,
                        "air_temp": air_temp,
                        "grid_position": int(si.get("position") or 5),
                        "tire_age_laps": int(si.get("tire_age_laps") or current_lap),
                    },
                )
                logger.info("Eager simulation tool called: %s", sim_result)
                eager_sim_context = (
                    "\n\nSimulation results (use these exact numbers in your response):\n"
                    + "\n".join(f"  {k}: {v}" for k, v in sim_result.items())
                )
            except Exception as exc:
                logger.warning("Eager simulation tool failed: %s", exc)

        initial_message = (
            self.build_prompt(
                question,
                context_docs=context_docs,
                structured_inputs=structured_inputs,
            )
            + eager_sim_context
        )
        response = chat.send_message(initial_message, generation_config=gen_config)

        tool_called = bool(eager_sim_context)
        for _ in range(3):
            if not response.candidates:
                break
            fn_parts = [
                p for p in response.candidates[0].content.parts if p.function_call
            ]
            if not fn_parts:
                break

            tool_called = True
            tool_responses: list[Part] = []
            for part in fn_parts:
                fc = part.function_call
                logger.info("Gemini tool call: %s(%s)", fc.name, dict(fc.args))
                try:
                    result = tool_executor(fc.name, dict(fc.args))
                    logger.info("Tool result: %s", result)
                except Exception as exc:
                    result = {"error": str(exc)}
                tool_responses.append(
                    Part.from_function_response(
                        name=fc.name, response={"result": result}
                    )
                )
            response = chat.send_message(tool_responses, generation_config=gen_config)

        logger.info("Tool called: %s", tool_called)
        if response.candidates:
            parts = response.candidates[0].content.parts
            if parts:
                text = "".join(
                    getattr(p, "text", "") for p in parts if not p.function_call
                )
                if text:
                    return text
        try:
            return response.text
        except Exception:
            return "Unable to generate a response. Please try again."

    def parse_strategy_json(self, prompt: str) -> dict:
        """Parse natural language into a structured JSON strategy."""
        self._ensure_initialized()
        system_instructions = (
            "You are an F1 strategy parser. Extract the driver ID and the pit stop strategy from the user's prompt. "
            "Return ONLY a raw JSON object with this exact schema:\n"
            "{\n"
            '  "driver_id": "string",\n'
            '  "strategy": [[lap_number, "compound_name_upper_case"]]\n'
            "}\n"
            "Examples:\n"
            '\'Put Max on hards on lap 15\' -> {"driver_id": "max_verstappen", "strategy": [[15, "HARD"]]}\n'
            '\'Charles pits lap 20 for meds, then 40 for hards\' -> {"driver_id": "leclerc", "strategy": [[20, "MEDIUM"], [40, "HARD"]]}\n'
            "Valid Compounds: SOFT, MEDIUM, HARD, INTERMEDIATE, WET.\n"
            "If driver isn't mentioned, leave driver_id as an empty string. "
            "No markdown blocks, no backticks, ONLY valid JSON object."
        )
        response = self._model.generate_content(  # type: ignore[union-attr]
            f"{system_instructions}\n\nPrompt: {prompt}",
            generation_config={
                "temperature": 0.0,
                "response_mime_type": "application/json",
            },
        )
        import json

        try:
            text = response.text.replace("```json", "").replace("```", "").strip()
            if len(text) > 2000:
                raise ValueError("Generated JSON response exceeded safe length limits.")
            return json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error(
                "Failed to decode JSON from Gemini response: %s", exc, exc_info=True
            )
            raise ValueError(f"LLM returned invalid JSON: {exc}")
        except Exception as exc:
            logger.error(
                "Unexpected error during strategy parsing: %s", exc, exc_info=True
            )
            raise


# Module-level singleton — shared across requests
_client: GeminiClient | None = None


def get_client() -> GeminiClient:
    """Return the module-level GeminiClient singleton."""
    global _client
    if _client is None:
        _client = GeminiClient()
    return _client
