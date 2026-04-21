#!/usr/bin/env bash
# scripts/deploy.sh
# Full DivergeX deployment: infra -> images -> API -> ML training -> RAG -> frontend
#
# Usage:
#   bash scripts/deploy.sh [options]
#
# Options:
#   --skip-infra       Skip terraform apply (infra already provisioned)
#   --skip-build       Skip Cloud Build (images + API deploy + ML training)
#   --skip-data        Skip data pipeline (csv_to_parquet + verify)
#   --skip-rag         Skip RAG ingestion
#   --skip-frontend    Skip frontend build and Firebase deploy
#   --skip-training    Skip KFP ML training pipeline submission
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
TFVARS="infra/terraform/dev.tfvars"

SKIP_INFRA=false
SKIP_BUILD=false
SKIP_DATA=false
SKIP_RAG=false
SKIP_FRONTEND=false
SKIP_TRAINING=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-infra)     SKIP_INFRA=true;     shift ;;
    --skip-build)     SKIP_BUILD=true;     shift ;;
    --skip-data)      SKIP_DATA=true;      shift ;;
    --skip-rag)       SKIP_RAG=true;       shift ;;
    --skip-frontend)  SKIP_FRONTEND=true;  shift ;;
    --skip-training)  SKIP_TRAINING=true;  shift ;;
    *) echo "Unknown flag: $1" >&2; exit 1 ;;
  esac
done

STEP=0
total_steps=6

log() { echo ""; echo "=== [$(( ++STEP ))/$total_steps] $* ==="; }

# -- 1. Infrastructure ---------------------------------------------------------
if [[ "$SKIP_INFRA" == "false" ]]; then
  log "Provisioning GCP infrastructure (Terraform)"
  terraform -chdir=infra/terraform init -input=false
  terraform -chdir=infra/terraform apply -var-file=dev.tfvars -auto-approve
else
  log "Skipping infrastructure (--skip-infra)"
fi

# -- 2. Docker images + API deploy via Cloud Build -----------------------------
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

# -- 3. Data pipeline ----------------------------------------------------------
if [[ "$SKIP_DATA" == "false" ]]; then
  log "Running data pipeline (csv_to_parquet + verify)"
  python pipeline/scripts/csv_to_parquet.py
  python pipeline/scripts/verify_upload.py
  python pipeline/scripts/build_car_performance.py \
    --input gs://f1optimizer-data-lake/processed/race_results.parquet \
    --output frontend/public/data/car_performance.json
else
  log "Skipping data pipeline (--skip-data)"
fi

# -- 4. ML training pipeline ---------------------------------------------------
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
