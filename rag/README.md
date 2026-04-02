# Retreival-Augmented Generation (RAG) Architecture

This directory houses the logic for natural-language Q&A operations querying 76 years of F1 context using Vertex AI Vector Search and Gemini 2.5 Flash.

## Structure

- `config.py`: Exposes `RagConfig` controlling environment parameters and thresholds.
- `chunker.py`: Transforms Parquet and CSV chunks into isolated LangChain `Document` chunks.
- `document_fetcher.py`: Integrates external PDF materials like the FIA regulations and specific circuit guides.
- `embedder.py`: Communicates with `text-embedding-004` (768-dim) generating vectors.
- `vector_store.py`: Upserts and Queries the Vertex AI Vector Search endpoint utilizing metadata filters (season, circuit, etc.).
- `retriever.py`: `F1Retriever` fetching top-k hits and prompting the Gemini engine for final answer extraction.
- `ingestion_job.py`: Standalone Cloud Job process indexing the documents to the vector DB.

## Query
The deployed endpoint is accessible via `/rag/query`.
