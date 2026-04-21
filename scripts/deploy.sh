#!/usr/bin/env bash
# scripts/deploy.sh
# Full DivergeX deployment:
#   1. Terraform    -- provision all GCP infrastructure
#   2. Cloud Build  -- build all images, deploy API, train ML models
#   3. Ingest       -- run Cloud Run ingest job (10 parallel tasks), preprocess, RAG
#   4. Frontend     -- build React app and deploy to Firebase Hosting
#
# Usage:
#   bash scripts/deploy.sh [options]
#
# Options:
#   --skip-infra      Skip terraform apply
#   --skip-build      Skip Cloud Build
#   --skip-ingest     Skip data ingestion and RAG
#   --skip-rag        Skip only RAG ingestion (still runs data ingest)
#   --skip-frontend   Skip frontend build and Firebase deploy
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

SKIP_INFRA=false
SKIP_BUILD=false
SKIP_INGEST=false
SKIP_RAG=false
SKIP_FRONTEND=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-infra)     SKIP_INFRA=true;     shift ;;
    --skip-build)     SKIP_BUILD=true;     shift ;;
    --skip-ingest)    SKIP_INGEST=true;    shift ;;
    --skip-rag)       SKIP_RAG=true;       shift ;;
    --skip-frontend)  SKIP_FRONTEND=true;  shift ;;
    *) echo "Unknown flag: $1" >&2; exit 1 ;;
  esac
done

STEP=0
TOTAL=4
log() { echo ""; echo "=== [$(( ++STEP ))/$TOTAL] $* ==="; }

# -- Pre-flight: seed SMTP secrets if missing ----------------------------------
# Reads a variable from a .env file, stripping inline comments and whitespace.
read_env_var() {
  local var="$1"
  local file="${2:-.env}"
  grep -E "^${var}=" "$file" 2>/dev/null | head -1 | cut -d= -f2- | sed 's/[[:space:]]*#.*//' | xargs
}

seed_secret() {
  local secret_id="$1"
  local value="$2"

  # Create the secret container if it doesn't exist yet (idempotent)
  if ! gcloud secrets describe "$secret_id" --project="$PROJECT_ID" &>/dev/null; then
    echo "Creating secret $secret_id ..."
    gcloud secrets create "$secret_id" \
      --project="$PROJECT_ID" \
      --replication-policy="automatic" \
      --quiet
  fi

  # Add a version only when none exists
  local existing
  existing=$(gcloud secrets versions list "$secret_id" \
    --project="$PROJECT_ID" \
    --filter="state=ENABLED" \
    --format="value(name)" 2>/dev/null | head -1)

  if [[ -z "$existing" ]]; then
    printf '%s' "$value" | gcloud secrets versions add "$secret_id" \
      --project="$PROJECT_ID" \
      --data-file=-
    echo "Secret $secret_id populated from .env."
  else
    echo "Secret $secret_id already has a version — skipping."
  fi
}

echo ""
echo "=== [pre-flight] Seeding SMTP secrets ==="
SMTP_USER_VAL=$(read_env_var "SMTP_USER")
SMTP_PASS_VAL=$(read_env_var "SMTP_PASS")

if [[ -z "$SMTP_USER_VAL" || -z "$SMTP_PASS_VAL" ]]; then
  echo "ERROR: SMTP_USER and SMTP_PASS must be set in .env" >&2
  exit 1
fi

seed_secret "smtp-user" "$SMTP_USER_VAL"
seed_secret "smtp-pass" "$SMTP_PASS_VAL"

# -- 1. Infrastructure ---------------------------------------------------------
if [[ "$SKIP_INFRA" == "false" ]]; then
  log "Provisioning GCP infrastructure (Terraform)"
  terraform -chdir=infra/terraform init -input=false
  terraform -chdir=infra/terraform apply -auto-approve
else
  log "Skipping infrastructure (--skip-infra)"
fi

# -- 2. Cloud Build: all images + API deploy + ML training --------------------
if [[ "$SKIP_BUILD" == "false" ]]; then
  log "Building images and deploying API (Cloud Build)"
  COMMIT_SHA=$(git rev-parse HEAD 2>/dev/null || echo "manual")
  SHORT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "manual")
  VS_INDEX_ID=$(terraform -chdir=infra/terraform output -raw rag_index_id 2>/dev/null || echo "")
  VS_ENDPOINT_ID=$(terraform -chdir=infra/terraform output -raw rag_endpoint_id 2>/dev/null || echo "")
  VS_DEPLOYED_ID=$(terraform -chdir=infra/terraform output -raw rag_deployed_index_id 2>/dev/null || echo "f1_rag_deployed")
  gcloud builds submit --config cloudbuild.yaml . \
    --project="$PROJECT_ID" \
    --substitutions="COMMIT_SHA=${COMMIT_SHA},SHORT_SHA=${SHORT_SHA},_VECTOR_SEARCH_INDEX_ID=${VS_INDEX_ID},_VECTOR_SEARCH_ENDPOINT_ID=${VS_ENDPOINT_ID},_VECTOR_SEARCH_DEPLOYED_INDEX_ID=${VS_DEPLOYED_ID}"
else
  log "Skipping Cloud Build (--skip-build)"
fi

# -- 3. Data ingestion + preprocessing + RAG ----------------------------------
if [[ "$SKIP_INGEST" == "false" ]]; then
  log "Running ingestion pipeline"

  echo "--- [3a] Executing Cloud Run ingest job (10 parallel tasks) ---"
  echo "Tasks 0-8: FastF1 telemetry 2018-2026 | Task 9: Jolpica historical 1950-2017"
  echo "Containers are deleted automatically on completion. ETA: 20-40 min."
  gcloud run jobs execute f1-ingest \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --wait

  echo ""
  echo "--- [3b] Verifying GCS uploads ---"
  python pipeline/scripts/verify_upload.py --bucket f1optimizer-data-lake

  echo ""
  echo "--- [3c] Preprocessing features ---"
  PYTHONPATH=. python ml/preprocessing/preprocess_data.py

  echo ""
  echo "--- [3d] Building car performance table ---"
  python pipeline/scripts/build_car_performance.py \
    --output gs://f1optimizer-data-lake/processed/car_performance.json \
    --local-output frontend/public/data/car_performance.json

  if [[ "$SKIP_RAG" == "false" ]]; then
    echo ""
    echo "--- [3e] RAG ingestion ---"
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

else
  log "Skipping ingestion (--skip-ingest)"
fi

# -- 4. Frontend ---------------------------------------------------------------
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
