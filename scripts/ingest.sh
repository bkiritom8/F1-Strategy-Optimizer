#!/usr/bin/env bash
# scripts/ingest.sh
# Full data ingestion pipeline:
#   1. Execute Cloud Run ingest job (10 tasks in parallel, wait for completion)
#      - Tasks 0-8: FastF1 10Hz telemetry (2018-2026, one year per task)
#      - Task 9:    Jolpica historical data (1950-2017)
#   2. Verify GCS uploads
#   3. Preprocess raw GCS data into ml_features Parquet files
#   4. Build year-aware car performance table for the frontend
#   5. Run RAG document ingestion into Vertex AI Vector Search
#
# Usage:
#   bash scripts/ingest.sh [options]
#
# Options:
#   --skip-data-ingest   Skip Cloud Run job execution and preprocessing
#   --skip-rag           Skip RAG ingestion
#
# Prerequisites:
#   gcloud auth application-default login
#   Infra already provisioned and ingest image already built (run deploy.sh first)

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-f1optimizer}"
REGION="${REGION:-us-central1}"
INGEST_JOB="f1-ingest"

SKIP_DATA_INGEST=false
SKIP_RAG=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-data-ingest) SKIP_DATA_INGEST=true; shift ;;
    --skip-rag)         SKIP_RAG=true;         shift ;;
    *) echo "Unknown flag: $1" >&2; exit 1 ;;
  esac
done

# -- Data ingestion ------------------------------------------------------------
if [[ "$SKIP_DATA_INGEST" == "false" ]]; then

  echo "=== [1/4] Executing Cloud Run ingest job (10 parallel tasks) ==="
  echo "Tasks 0-8: FastF1 telemetry 2018-2026 | Task 9: Jolpica historical 1950-2017"
  echo "This may take 20-40 minutes. Containers are deleted automatically on completion."
  gcloud run jobs execute "$INGEST_JOB" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --wait

  echo ""
  echo "=== [2/4] Verifying GCS uploads ==="
  python pipeline/scripts/verify_upload.py \
    --bucket f1optimizer-data-lake

  echo ""
  echo "=== [3/4] Preprocessing features ==="
  PYTHONPATH=. python ml/preprocessing/preprocess_data.py

  echo ""
  echo "=== [4/4] Building car performance table ==="
  python pipeline/scripts/build_car_performance.py \
    --output gs://f1optimizer-data-lake/processed/car_performance.json \
    --local-output frontend/public/data/car_performance.json

else
  echo "Skipping data ingestion (--skip-data-ingest)"
fi

# -- RAG ingestion -------------------------------------------------------------
if [[ "$SKIP_RAG" == "false" ]]; then
  echo ""
  echo "=== RAG ingestion ==="

  # Pull Vector Search IDs from Terraform outputs
  VECTOR_SEARCH_INDEX_ID=$(terraform -chdir=infra/terraform output -raw rag_index_id 2>/dev/null || echo "")
  VECTOR_SEARCH_ENDPOINT_ID=$(terraform -chdir=infra/terraform output -raw rag_endpoint_id 2>/dev/null || echo "")
  VECTOR_SEARCH_DEPLOYED_INDEX_ID=$(terraform -chdir=infra/terraform output -raw rag_deployed_index_id 2>/dev/null || echo "f1_rag_deployed")

  GOOGLE_CLOUD_PROJECT="$PROJECT_ID" \
  VECTOR_SEARCH_INDEX_ID="$VECTOR_SEARCH_INDEX_ID" \
  VECTOR_SEARCH_ENDPOINT_ID="$VECTOR_SEARCH_ENDPOINT_ID" \
  VECTOR_SEARCH_DEPLOYED_INDEX_ID="$VECTOR_SEARCH_DEPLOYED_INDEX_ID" \
    python -m rag.ingestion_job
else
  echo "Skipping RAG ingestion (--skip-rag)"
fi

echo ""
echo "Ingestion complete."
