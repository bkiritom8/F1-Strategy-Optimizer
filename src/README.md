# Shared Backend Logic

Core Python libraries and FastAPI application for the F1 Strategy Optimizer, deployed on Cloud Run `f1-strategy-api-dev`.

## Directory Structure

```
src/
├── api/
│   ├── main.py              # FastAPI app factory, middleware, startup/shutdown
│   └── routes/
│       ├── simulate.py      # POST /simulate/race + GET /simulate/race/stream (SSE)
│       ├── strategy.py      # Strategy prediction endpoints
│       ├── drivers.py       # Driver/team lookup
│       └── ...
├── ingestion/               # Jolpica + FastF1 connectors
├── llm/                     # Gemini Pro (Vertex AI) integration
│   ├── connectors.py
│   ├── cache.py             # Two-layer semantic cache (TurboQuant-compressed embeddings)
│   ├── turboquant.py        # TurboQuant_prod PQ codec for embedding compression
│   └── prompts/             # Prompt templates + structured output parsers
├── preprocessing/           # Shared data cleaning + feature engineering
├── common/                  # Logging, config, environment variable loaders
├── security/                # Auth, sessions, sanitization
│   ├── jwt_handler.py       # JWT token issuance + validation
│   ├── sessions.py          # Firestore-backed session management
│   └── sanitizer.py
└── simulation/
    ├── coordinator.py       # Scenario hashing, Redis cache, background task dispatch
    └── streamer.py          # SSE frame generator from Redis list
```

## Key Modules

### API (`api/`)

FastAPI loads promoted ML models from GCS at startup, with rule-based fallback if models are unavailable.

Key endpoints:
- `POST /api/v1/simulate/race` — start a Monte Carlo race simulation
- `GET /api/v1/simulate/race/stream` — SSE stream of simulation frames
- `POST /api/v1/llm/chat` — strategy chat via Gemini Pro
- `GET /api/v1/rag/query` — natural-language F1 history query

### Simulation (`simulation/`)

- `coordinator.py`: Hashes scenario params, checks Redis cache, dispatches background simulation jobs, returns `scenario_id`
- `streamer.py`: Reads frames from Redis list keyed by `scenario_id`, yields SSE events consumed by the frontend `RaceSimulator` component

### LLM (`llm/`)

Gemini Pro via Vertex AI for strategy recommendations. Prompt templates enforce structured JSON output for parse-strategy and chat endpoints.

### Security (`security/`)

- JWT-based authentication with configurable expiry
- Firestore-backed sessions (no server-side state in stateless Cloud Run)
- Input sanitization at all public endpoints

## Running Locally

```bash
pip install -r requirements-api.txt

# Requires GCP ADC credentials
uvicorn src.api.main:app --reload --port 8000

# With Redis for simulation endpoints
REDIS_HOST=localhost uvicorn src.api.main:app --reload --port 8000
```

## Docker

```bash
docker build -f docker/Dockerfile.api -t api:latest .
docker run -p 8000:8000 api:latest
```

Cloud Build builds `api:latest` automatically on every push to `pipeline`.

## Maintenance

- Keep `requirements-api.txt` in sync with `docker/requirements-api.txt`
- Add new endpoints to the `endpoints.ts` registry in `frontend/services/`
- `SIMULATION_ENDPOINT` env var configures the external simulation service — rule-based fallback activates if unavailable

---

**Status**: Complete — deployed on Cloud Run `f1-strategy-api-dev` | **Last Updated**: 2026-04-08
