# Retrieval-Augmented Generation (RAG)

Natural-language Q&A over 76 years of F1 context using Vertex AI Vector Search and Gemini. Query endpoint: `GET /api/v1/rag/query`.

## Architecture

```
GCS Parquet/CSV → chunker.py → embedder.py (text-embedding-004, 768-dim)
                                      ↓
                     Vertex AI Vector Search (upsert via vector_store.py)
                                      ↓
User query → embedder.py → vector_store.py (top-k + metadata filter)
                                      ↓
                         retriever.py (F1Retriever + Gemini prompt)
                                      ↓
                              Structured answer
```

## Components

| File | Purpose |
|---|---|
| `config.py` | `RagConfig` — environment params, similarity thresholds, top-k settings |
| `chunker.py` | Parquet/CSV → LangChain `Document` chunks with F1-aware metadata (season, circuit, driver) |
| `document_fetcher.py` | External PDF ingestion (FIA regulations, circuit guides, technical directives) |
| `embedder.py` | `text-embedding-004` (768-dim) vector generation via Vertex AI |
| `vector_store.py` | Upserts and queries Vertex AI Vector Search; supports metadata filters (season, circuit, event type) |
| `retriever.py` | `F1Retriever` — fetches top-k hits, constructs Gemini prompt, returns structured answer |
| `ingestion_job.py` | Standalone Cloud Job for re-indexing documents into the vector DB |

## Querying

```bash
# Via the deployed API
curl "https://f1-strategy-api-dev.run.app/api/v1/rag/query?q=What+strategy+won+Monaco+2019"

# Locally
curl "http://localhost:8000/api/v1/rag/query?q=Hamilton+fastest+lap+2020"
```

## Re-indexing

Run after new season data lands or source documents change:

```bash
# Submit as Cloud Run Job
gcloud run jobs execute f1-rag-ingest --region=us-central1 --project=f1optimizer

# Or via helper script
bash scripts/run_rag_ingestion.sh
```

## Embedding Model

- **Model**: `text-embedding-004`
- **Dimensions**: 768
- **Provider**: Vertex AI
- **Query caching**: `F1Retriever` caches query embeddings to reduce latency on repeated queries

## Metadata Filters

Vector search supports filtering by:

| Filter | Example |
|---|---|
| `season` | `2023` |
| `circuit` | `monza` |
| `event_type` | `race`, `qualifying`, `practice` |
| `driver` | `hamilton` |

---

**Status**: Complete — vector index populated, `/rag/query` endpoint live on Cloud Run
