# F1 RAG Pipeline

## Current Status (2026-03-26)

The RAG pipeline is implemented and tested. Cloud Build test gate passes (≥60% coverage). Index and endpoint are **not yet provisioned** — the pipeline gracefully returns empty results / 503 until the three Vector Search env vars are set.

### What's Done
- [x] `rag/config.py` — `RagConfig` with all env vars and defaults
- [x] `rag/chunker.py` — GCS Parquet + CSV rows → natural-language Documents (telemetry, race results, pit stops, lap times, driver bios, standings)
- [x] `rag/document_fetcher.py` — FIA regulations + circuit guides → Documents (HTTP download + GCS cache)
- [x] `rag/embedder.py` — Vertex AI `text-embedding-004`, batched (250/batch, 1s sleep)
- [x] `rag/vector_store.py` — Vertex AI Vector Search create/upsert/query + GCS metadata JSON
- [x] `rag/retriever.py` — `F1Retriever`: lazy init, top-k retrieval, Gemini 1.5 Flash generation
- [x] `rag/ingestion_job.py` — one-shot ingestion entry point
- [x] `src/api/` — `/rag/query` (POST) and `/rag/health` (GET) routes wired up
- [x] `tests/unit/rag/` — 24 unit tests, ≥60% coverage gate in Cloud Build
- [x] `docker/requirements-rag.txt` — `langchain_core`, `vertexai`, GCP libs

### TODO

#### Infrastructure (required before RAG is live)
- [ ] Run `python rag/ingestion_job.py` to create Vertex AI Vector Search index — prints `INDEX CREATED: <id>`
- [ ] Deploy index to endpoint in GCP Console (Vertex AI → Vector Search → Deploy to endpoint)
- [ ] Set Cloud Run env vars: `VECTOR_SEARCH_INDEX_ID`, `VECTOR_SEARCH_ENDPOINT_ID`, `VECTOR_SEARCH_DEPLOYED_INDEX_ID`
- [ ] Re-run `python rag/ingestion_job.py` to upsert all vectors

#### Quality & Coverage
- [ ] Evaluate retrieval quality on sample queries (Monaco 2019, tire strategies, Hamilton vs Verstappen)
- [ ] Tune `TOP_K` (currently 5) and `LLM_TEMPERATURE` (currently 0.2) based on answer quality
- [ ] Add season/race/driver filter tests to `test_retriever.py`
- [ ] Write `test_vector_store.py` tests for `create_index`, `upsert_vectors`, `query_index` (currently 0% — need full GCP mock)

#### Chunker Improvements
- [ ] Add qualifying result chunks (`qualifying_*.parquet`)
- [ ] Add constructor/team standing chunks
- [ ] Add per-driver season summary chunks (aggregated stats, not row-per-lap)

#### Production Hardening
- [ ] Add retry logic to `embedder.py` for Vertex AI 429 rate limit responses
- [ ] Add `/rag/query` response caching (Redis or in-memory LRU) for repeated queries
- [ ] Add `latency_ms` monitoring to Cloud Monitoring (target: <2s end-to-end)
- [ ] Add index freshness check to `/rag/health` response
- [ ] Periodic re-ingestion job (weekly cron via Cloud Scheduler) as new race data arrives

#### Integration
- [ ] Wire RAG context into `/recommend` — use retrieved docs to augment strategy reasoning
- [ ] Expose RAG query in React frontend AI chat view (`/ai` route)

Retrieval-Augmented Generation over 76 years of F1 race data (1950–2026).

## Architecture

```
GCS (raw/ + processed/ Parquet)
        │
        ▼
rag/chunker.py          ← converts rows to natural-language Documents
        │
        ▼
rag/embedder.py         ← Vertex AI text-embedding-004 (768-dim)
        │
        ▼
Vertex AI Vector Search ← streaming upsert, DOT_PRODUCT_DISTANCE
        │
        ▼
rag/retriever.py        ← top-k retrieval + Gemini generation
        │
        ▼
FastAPI /rag/query      ← JSON response with answer + sources
```

## How It Works

1. **Chunker** reads every `.parquet` and `.csv` file from GCS, converts each row to a natural-language sentence using F1-specific templates (telemetry, race results, pit stops, lap times, driver bios, standings).
2. **Embedder** batches all sentences through `text-embedding-004` (250 sentences/batch, 1s sleep between batches).
3. **Vector Store** upserts 768-dim vectors to Vertex AI Vector Search with STREAM_UPDATE, saving a metadata JSON to GCS so vector IDs can be resolved back to document text.
4. **Retriever** embeds the query, queries the deployed index for top-k neighbors, optionally filters by season/race/driver, then passes retrieved context to Gemini for answer generation.

## First-Time Setup

### Step 1: Run ingestion job (creates index)

```bash
bash scripts/run_rag_ingestion.sh
```

The job will print:
```
INDEX CREATED: <index_id>
Next steps:
  1. Deploy the index to an endpoint in GCP Console
  2. Set VECTOR_SEARCH_INDEX_ID=<index_id>
  3. Set VECTOR_SEARCH_ENDPOINT_ID=<endpoint_id>
  4. Set VECTOR_SEARCH_DEPLOYED_INDEX_ID=<deployed_id>
  5. Re-run this job to upsert vectors
```

### Step 2: Deploy index to endpoint

1. Go to GCP Console → Vertex AI → Vector Search
2. Click your index → Deploy to endpoint
3. Create a new endpoint named `f1-rag-endpoint`
4. Note the endpoint ID

### Step 3: Set environment variables

```bash
export VECTOR_SEARCH_INDEX_ID=<index_id>
export VECTOR_SEARCH_ENDPOINT_ID=<endpoint_id>
export VECTOR_SEARCH_DEPLOYED_INDEX_ID=f1_rag_deployed
```

For Cloud Run, set these in the service environment variables.

### Step 4: Re-run ingestion job (upserts vectors)

```bash
bash scripts/run_rag_ingestion.sh
```

### Step 5: Restart Cloud Run service

```bash
gcloud run services update f1-strategy-api-dev \
  --update-env-vars VECTOR_SEARCH_INDEX_ID=$VECTOR_SEARCH_INDEX_ID,\
VECTOR_SEARCH_ENDPOINT_ID=$VECTOR_SEARCH_ENDPOINT_ID \
  --region=us-central1 \
  --project=f1optimizer
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PROJECT_ID` | `f1optimizer` | GCP project ID |
| `REGION` | `us-central1` | GCP region |
| `EMBEDDING_MODEL` | `text-embedding-004` | Vertex AI embedding model |
| `EMBEDDING_DIMENSION` | `768` | Embedding vector dimensions |
| `LLM_MODEL` | `gemini-1.5-flash` | Gemini model for generation |
| `VECTOR_SEARCH_INDEX_ID` | *(empty)* | **Required** — Vertex AI index ID |
| `VECTOR_SEARCH_ENDPOINT_ID` | *(empty)* | **Required** — Vertex AI endpoint ID |
| `VECTOR_SEARCH_DEPLOYED_INDEX_ID` | `f1_rag_deployed` | Deployed index ID |
| `GCS_DATA_BUCKET` | `f1optimizer-data-lake` | GCS bucket for F1 data |
| `GCS_MODELS_BUCKET` | `f1optimizer-models` | GCS bucket for RAG metadata |
| `METADATA_GCS_PATH` | `rag/metadata.json` | Path for vector→document metadata |
| `CHUNK_SIZE` | `512` | Max tokens per chunk |
| `CHUNK_OVERLAP` | `50` | Token overlap between chunks |
| `TOP_K` | `5` | Number of documents to retrieve |
| `MAX_OUTPUT_TOKENS` | `1024` | Max Gemini output tokens |
| `LLM_TEMPERATURE` | `0.2` | Gemini temperature (0=deterministic) |
| `EMBEDDING_BATCH_SIZE` | `250` | Texts per embedding API call |
| `EMBEDDING_BATCH_SLEEP_SECONDS` | `1.0` | Sleep between embedding batches |

## API Endpoints

### POST /rag/query

Query F1 data using natural language.

```bash
curl -X POST http://localhost:8000/rag/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What was Hamilton'\''s average lap time at Monaco in 2019?",
    "filters": {"season": 2019, "race": "monaco"},
    "top_k": 5
  }'
```

Response:
```json
{
  "answer": "Lewis Hamilton averaged 74.8 seconds per lap at Monaco in 2019...",
  "sources": [
    {"content": "In the 2019 Monaco Grand Prix, Lewis Hamilton...", "metadata": {...}}
  ],
  "query": "What was Hamilton's average lap time at Monaco in 2019?",
  "num_sources": 3,
  "latency_ms": 342.5
}
```

Returns `503` if `VECTOR_SEARCH_INDEX_ID` or `VECTOR_SEARCH_ENDPOINT_ID` are not set.

### GET /rag/health

Check RAG configuration status. Always returns 200.

```bash
curl http://localhost:8000/rag/health
```

Response (not configured):
```json
{
  "status": "not_configured",
  "index_configured": false,
  "endpoint_configured": false,
  "model": "gemini-1.5-flash"
}
```

Response (ready):
```json
{
  "status": "ready",
  "index_configured": true,
  "endpoint_configured": true,
  "model": "gemini-1.5-flash"
}
```

## Cost Estimates

| Operation | Unit | Cost |
|---|---|---|
| Embedding ingestion (one-time, ~500k docs) | Per 1M characters | ~$0.025 |
| Vector Search index hosting | Per month | ~$65 |
| Per-query embedding | Per 1K characters | ~$0.00025 |
| Per-query Gemini (1K tokens in + 1K out) | Per query | ~$0.001 |
| **Estimated monthly total** | | ~$70–80 |

## Dependencies

The RAG pipeline uses `langchain_core` (not the top-level `langchain` package) for the `Document` type:

```python
from langchain_core.documents import Document  # correct
# NOT: from langchain.schema import Document   # removed in LangChain v0.2+
```

`langchain_core` must be present in `docker/requirements-rag.txt`. Tests use `pytest.importorskip("langchain_core")` as a guard.

## Adding New Data Sources

To chunk a new data type, extend `rag/chunker.py`:

1. Add a new template in `chunk_parquet` or `chunk_csv` (detect by column names or filename prefix)
2. Ensure the template produces grammatical natural-language sentences
3. Set appropriate metadata fields (`season`, `race`, `driver`, `session`)
4. Re-run the ingestion job — `save_metadata` merges new documents with existing ones

Example — adding qualifying results:
```python
elif filename.startswith("qualifying"):
    text = (
        f"{get(row, 'driverRef')} qualified P{get(row, 'position')} "
        f"for the {get(row, 'year')} {get(row, 'raceName')} "
        f"with a best lap of {get(row, 'q3')}."
    )
```
