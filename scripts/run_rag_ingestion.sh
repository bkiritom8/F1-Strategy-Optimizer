#!/bin/bash
set -e

export GOOGLE_CLOUD_PROJECT="f1optimizer"
export VECTOR_SEARCH_INDEX_ID="${VECTOR_SEARCH_INDEX_ID:-}"
export VECTOR_SEARCH_ENDPOINT_ID="${VECTOR_SEARCH_ENDPOINT_ID:-}"
export VECTOR_SEARCH_DEPLOYED_INDEX_ID="${VECTOR_SEARCH_DEPLOYED_INDEX_ID:-f1_rag_deployed}"

echo "================================================"
echo "F1 RAG Ingestion Job"
echo "Project: $GOOGLE_CLOUD_PROJECT"
echo "Index ID: ${VECTOR_SEARCH_INDEX_ID:-NOT SET}"
echo "Endpoint ID: ${VECTOR_SEARCH_ENDPOINT_ID:-NOT SET}"
echo "================================================"

python -m rag.ingestion_job
