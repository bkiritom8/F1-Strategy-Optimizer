# LLM Issues

## 1. Frontend Bypasses Backend — Direct Gemini API Call — FIXED

**File**: `frontend/views/AIChatbot.tsx` (lines 125–191)

The chatbot was calling `https://generativelanguage.googleapis.com/v1beta/...` directly from the browser using `VITE_GEMINI_API_KEY`, bypassing the FastAPI backend entirely. This means:
- Tool use (ML model enrichment, strategy recommendation) was completely skipped
- RAG context was never injected into responses
- Backend system prompt (`src/llm/gemini_client.py`) was not used — the frontend used its own simpler prompt
- The model used was `gemini-2.0-flash-lite` (cheap/fast) instead of the backend's `gemini-2.5-flash` (smarter, tool-aware)

**Fixed**: Routed all chat requests through `apiFetch('/api/v1/llm/chat')` using the existing authenticated backend client. Chat history is now sent as `{role, content}` pairs matching the `ChatHistory` schema. Simulation panel now uses `job_id`/`simulation_race_id` from the backend response instead of client-side keyword detection.

---

## 2. RAG Pipeline Built But Never Deployed

**Files**: `rag/ingestion_job.py`, `rag/config.py`, `rag/retriever.py`

The entire RAG pipeline is implemented and tested but was never run against GCP. As a result:
- No Vertex AI Vector Search index exists
- `VECTOR_SEARCH_INDEX_ID` and `VECTOR_SEARCH_ENDPOINT_ID` env vars are empty
- The chat endpoint gracefully falls back to zero-context mode
- Questions about F1 calendar data, circuit lap counts, FIA regulations, etc. are answered from Gemini's training data only (which can be wrong or outdated)

The circuit guide data for all 24 circuits IS hardcoded in `rag/document_fetcher.py` but is never retrieved.

**Fix needed**: Run `python rag/ingestion_job.py` to create the index, deploy it to a Vertex AI endpoint, then set the env vars in Cloud Run.

---

## 3. LLM Response Cache Defined but Disconnected

**File**: `src/llm/cache.py`

Two cache layers exist:
- `GenericF1Cache`: Pre-warmed with 20 common F1 questions, TTL-based
- `RealtimeF1Cache`: Semantic cache for race-context queries (TurboQuant-backed embeddings)

Neither is instantiated or called in the `llm_chat()` endpoint (`src/api/routes/llm.py`). Every chat request hits the Gemini API cold.

**Fix needed**: Wire `GenericF1Cache` into `llm_chat()` — check cache before `client.generate_with_tools()`, store result after.

---

## 4. High Latency (15–25s)

Root causes, in order of impact:

| Cause | Impact | Notes |
|---|---|---|
| Gemini API generation | 8–12s | Inherent to `gemini-2.5-flash` with tool use |
| ML model GCS load | 3–8s | Lazy-loaded on first strategy question; cached after |
| `vertexai.init()` cold start | 1–2s | Only on first request after Cloud Run cold start |
| No response caching | Full Gemini RTT every request | See issue #3 |
| `MAX_OUTPUT_TOKENS=4096` | Unnecessary ceiling | Most answers are <500 tokens |

**Partial fix**: Routing through the backend at least removes the perception problem — the backend response is non-streaming, so the frontend now shows the spinner until the full answer arrives (same wall time, but unified behavior). Streaming SSE from the backend would be the real fix.

---

## 5. Welcome Message Mismatch — FIXED

**File**: `frontend/views/AIChatbot.tsx` (line 84)

The initial message said "powered by Google Gemini" and the subtitle referenced `gemini-2.0-flash-lite` — both updated to reflect the actual backend model (`gemini-2.5-flash via Vertex AI`).
