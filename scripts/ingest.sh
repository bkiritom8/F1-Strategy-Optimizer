#!/usr/bin/env bash
# scripts/ingest.sh
# Full data ingestion pipeline:
#   1. Build and push the ingest Docker image
#   2. Create or update the Cloud Run ingest job
#   3. Execute all 10 ingest tasks and wait for completion
#      (tasks 0-8: FastF1 telemetry 2018-2026, task 9: Jolpica historical 1996-2017)
#   4. Preprocess raw GCS data into ml_features Parquet files
#   5. Build year-aware car performance table for the frontend
#   6. Run RAG document ingestion into Vertex AI Vector Search
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
#   GCS buckets and Artifact Registry already provisioned (run deploy.sh --skip-ingest first,
#   or run terraform apply before calling this script)

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-f1optimizer}"
REGION="${REGION:-us-central1}"
INGEST_IMAGE="us-central1-docker.pkg.dev/${PROJECT_ID}/f1-optimizer/ingest:latest"
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

  echo "=== [1/3] Building and pushing ingest image ==="
  gcloud builds submit . \
    --project="$PROJECT_ID" \
    --config=- <<EOF
steps:
- name: 'gcr.io/cloud-builders/docker'
  args: ['build', '--platform', 'linux/amd64',
         '-t', '${INGEST_IMAGE}',
         '-f', 'docker/Dockerfile.ingest', '.']
- name: 'gcr.io/cloud-builders/docker'
  args: ['push', '${INGEST_IMAGE}']
options:
  logging: LEGACY
  defaultLogsBucketBehavior: REGIONAL_USER_OWNED_BUCKET
EOF

  echo "=== [2/3] Deploying Cloud Run ingest job ==="
  if gcloud run jobs describe "$INGEST_JOB" \
      --region="$REGION" --project="$PROJECT_ID" &>/dev/null; then
    gcloud run jobs update "$INGEST_JOB" \
      --image="$INGEST_IMAGE" \
      --region="$REGION" \
      --project="$PROJECT_ID" \
      --service-account="f1-ingest-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
      --tasks=10 \
      --max-retries=2 \
      --set-env-vars="GCS_BUCKET=f1optimizer-data-lake"
  else
    gcloud run jobs create "$INGEST_JOB" \
      --image="$INGEST_IMAGE" \
      --region="$REGION" \
      --project="$PROJECT_ID" \
      --service-account="f1-ingest-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
      --tasks=10 \
      --max-retries=2 \
      --set-env-vars="GCS_BUCKET=f1optimizer-data-lake"
  fi

  echo "Executing ingest job (tasks 0-8: FastF1 2018-2026, task 9: Jolpica 1996-2017)..."
  echo "This may take 20-40 minutes."
  gcloud run jobs execute "$INGEST_JOB" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --wait

  echo "=== [3/3] Preprocessing features and building car performance table ==="
  PYTHONPATH=. python ml/preprocessing/preprocess_data.py

  python pipeline/scripts/build_car_performance.py \
    --input gs://f1optimizer-data-lake/processed/race_results.parquet \
    --output frontend/public/data/car_performance.json

else
  echo "Skipping data ingestion (--skip-data-ingest)"
fi

# -- RAG ingestion -------------------------------------------------------------
if [[ "$SKIP_RAG" == "false" ]]; then
  echo ""
  echo "=== RAG ingestion ==="
  GOOGLE_CLOUD_PROJECT="$PROJECT_ID" \
  VECTOR_SEARCH_DEPLOYED_INDEX_ID="${VECTOR_SEARCH_DEPLOYED_INDEX_ID:-f1_rag_deployed}" \
    python -m rag.ingestion_job
else
  echo "Skipping RAG ingestion (--skip-rag)"
fi

echo ""
echo "Ingestion complete."
