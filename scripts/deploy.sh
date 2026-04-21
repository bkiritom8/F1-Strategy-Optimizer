#!/usr/bin/env bash
# scripts/deploy.sh
# Full DivergeX deployment in order:
#   1. Terraform        -- provision all GCP infrastructure
#   2. Data ingestion   -- build ingest image, run Cloud Run job, preprocess features
#   3. Cloud Build      -- build api/ml/rag images, deploy API to Cloud Run, train ML models
#   4. ML pipeline      -- submit KFP training DAG to Vertex AI Pipelines
#   5. RAG ingestion    -- embed and index F1 documents into Vector Search
#   6. Frontend         -- build React app and deploy to Firebase Hosting
#
# Usage:
#   bash scripts/deploy.sh [options]
#
# Options:
#   --skip-infra       Skip terraform apply (infra already provisioned)
#   --skip-ingest      Skip data ingestion and preprocessing
#   --skip-build       Skip Cloud Build (images + API deploy + ML training)
#   --skip-training    Skip KFP ML training pipeline submission
#   --skip-rag         Skip RAG ingestion
#   --skip-frontend    Skip frontend build and Firebase deploy
#
# Prerequisites:
#   gcloud auth application-default login
#   gcloud auth configure-docker us-central1-docker.pkg.dev
#   terraform >= 1.5.0
#   node >= 18, npm
#   firebase-tools (npm install -g firebase-tools && firebase login)

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-f1optimizer}"
REGION="${REGION:-us-central1}"
INGEST_IMAGE="us-central1-docker.pkg.dev/${PROJECT_ID}/f1-optimizer/ingest:latest"
INGEST_JOB="f1-ingest"

SKIP_INFRA=false
SKIP_INGEST=false
SKIP_BUILD=false
SKIP_TRAINING=false
SKIP_RAG=false
SKIP_FRONTEND=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-infra)     SKIP_INFRA=true;     shift ;;
    --skip-ingest)    SKIP_INGEST=true;    shift ;;
    --skip-build)     SKIP_BUILD=true;     shift ;;
    --skip-training)  SKIP_TRAINING=true;  shift ;;
    --skip-rag)       SKIP_RAG=true;       shift ;;
    --skip-frontend)  SKIP_FRONTEND=true;  shift ;;
    *) echo "Unknown flag: $1" >&2; exit 1 ;;
  esac
done

STEP=0
TOTAL=6
log() { echo ""; echo "=== [$(( ++STEP ))/$TOTAL] $* ==="; }

# -- 1. Infrastructure ---------------------------------------------------------
if [[ "$SKIP_INFRA" == "false" ]]; then
  log "Provisioning GCP infrastructure (Terraform)"
  terraform -chdir=infra/terraform init -input=false
  terraform -chdir=infra/terraform apply -var-file=dev.tfvars -auto-approve
else
  log "Skipping infrastructure (--skip-infra)"
fi

# -- 2. Data ingestion ---------------------------------------------------------
if [[ "$SKIP_INGEST" == "false" ]]; then
  log "Running data ingestion"

  # Build and push ingest image
  echo "Building ingest image..."
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

  # Create or update the Cloud Run Job (10 tasks: indices 0-8 = FastF1, 9 = Jolpica)
  echo "Deploying Cloud Run ingest job..."
  if gcloud run jobs describe "$INGEST_JOB" --region="$REGION" --project="$PROJECT_ID" &>/dev/null; then
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

  # Execute the job and wait for all tasks to complete
  echo "Executing ingest job (this may take 20-40 minutes)..."
  gcloud run jobs execute "$INGEST_JOB" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --wait

  # Preprocess raw GCS data into ml_features Parquet files
  echo "Running feature preprocessing..."
  PYTHONPATH=. python ml/preprocessing/preprocess_data.py

  # Build year-aware car performance table for the frontend
  echo "Building car performance table..."
  python pipeline/scripts/build_car_performance.py \
    --input gs://f1optimizer-data-lake/processed/race_results.parquet \
    --output frontend/public/data/car_performance.json
else
  log "Skipping data ingestion (--skip-ingest)"
fi

# -- 3. Cloud Build: images + API deploy + ML training ------------------------
if [[ "$SKIP_BUILD" == "false" ]]; then
  log "Building images and deploying API (Cloud Build)"
  COMMIT_SHA=$(git rev-parse HEAD 2>/dev/null || echo "manual")
  SHORT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "manual")
  gcloud builds submit --config cloudbuild.yaml . \
    --project="$PROJECT_ID" \
    --substitutions="COMMIT_SHA=${COMMIT_SHA},SHORT_SHA=${SHORT_SHA}"
else
  log "Skipping Cloud Build (--skip-build)"
fi

# -- 4. ML training pipeline (KFP) --------------------------------------------
if [[ "$SKIP_TRAINING" == "false" ]]; then
  log "Submitting KFP ML training pipeline to Vertex AI"
  RUN_ID="deploy-$(date +%Y%m%d-%H%M%S)"
  PROJECT_ID="$PROJECT_ID" \
  REGION="$REGION" \
  TRAINING_BUCKET="gs://f1optimizer-training" \
  MODELS_BUCKET="gs://f1optimizer-models" \
    python ml/dag/pipeline_runner.py --run-id "$RUN_ID"
  echo "Pipeline submitted. Monitor at:"
  echo "  https://console.cloud.google.com/vertex-ai/pipelines?project=$PROJECT_ID"
else
  log "Skipping ML training (--skip-training)"
fi

# -- 5. RAG ingestion ----------------------------------------------------------
if [[ "$SKIP_RAG" == "false" ]]; then
  log "Running RAG ingestion"
  GOOGLE_CLOUD_PROJECT="$PROJECT_ID" \
  VECTOR_SEARCH_DEPLOYED_INDEX_ID="${VECTOR_SEARCH_DEPLOYED_INDEX_ID:-f1_rag_deployed}" \
    python -m rag.ingestion_job
else
  log "Skipping RAG ingestion (--skip-rag)"
fi

# -- 6. Frontend ---------------------------------------------------------------
if [[ "$SKIP_FRONTEND" == "false" ]]; then
  log "Building and deploying frontend to Firebase Hosting"
  (
    cd frontend
    npm install
    npm run build
    firebase deploy --only hosting --project "$PROJECT_ID"
  )
else
  log "Skipping frontend (--skip-frontend)"
fi

# -- Health check --------------------------------------------------------------
echo ""
echo "=== Health check ==="
API_URL=$(gcloud run services describe f1-strategy-api-dev \
  --region="$REGION" --project="$PROJECT_ID" \
  --format="value(status.url)" 2>/dev/null || echo "")

if [[ -n "$API_URL" ]]; then
  echo "API URL: $API_URL"
  if curl -sf --max-time 10 "$API_URL/health" > /dev/null; then
    echo "API health check passed."
  else
    echo "WARNING: API health check failed. Check Cloud Run logs."
  fi
else
  echo "WARNING: Could not retrieve API URL from Cloud Run."
fi

echo ""
echo "Deploy complete."
