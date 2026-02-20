#!/usr/bin/env bash
# workbench_startup.sh
# Runs on Vertex AI Workbench (f1-ml-workbench) at every boot.
# Uploaded to: gs://f1optimizer-training/startup/workbench_startup.sh
#
# What it does:
#   1. Installs ML Python dependencies
#   2. Pulls secrets from Secret Manager
#   3. Sets GCP environment variables
#   4. Configures Application Default Credentials (ADC)
#   5. Prints a ready message with console links

set -euo pipefail

PROJECT_ID="f1optimizer"
REGION="us-central1"
INSTANCE_CONNECTION_NAME="${PROJECT_ID}:${REGION}:f1-optimizer-dev"
DB_NAME="f1_strategy"
DB_USER="f1_app"
REQUIREMENTS_PATH="/home/jupyter/requirements-ml.txt"

log() { echo "[workbench-startup] $*"; }

# ── 1. Install ML dependencies ────────────────────────────────────────────────
log "Installing ML dependencies..."

# Copy requirements from GCS if not already present locally
if [[ ! -f "${REQUIREMENTS_PATH}" ]]; then
  gsutil cp "gs://f1optimizer-training/startup/requirements-ml.txt" "${REQUIREMENTS_PATH}" || true
fi

if [[ -f "${REQUIREMENTS_PATH}" ]]; then
  pip install --quiet -r "${REQUIREMENTS_PATH}"
  log "ML dependencies installed."
else
  log "WARNING: requirements-ml.txt not found at ${REQUIREMENTS_PATH} — skipping pip install."
fi

# ── 2. Pull secrets from Secret Manager ──────────────────────────────────────
log "Fetching secrets from Secret Manager..."

DB_PASSWORD=$(gcloud secrets versions access latest \
  --secret="f1-db-password-dev" \
  --project="${PROJECT_ID}" 2>/dev/null || echo "")

if [[ -z "${DB_PASSWORD}" ]]; then
  log "WARNING: Could not fetch f1-db-password-dev — DB_PASSWORD will be unset."
fi

# ── 3. Write environment variables to shell profile ──────────────────────────
log "Writing environment variables to /etc/profile.d/f1_env.sh..."

cat > /etc/profile.d/f1_env.sh <<EOF
# F1 Strategy Optimizer — set by workbench_startup.sh
export PROJECT_ID="${PROJECT_ID}"
export REGION="${REGION}"
export INSTANCE_CONNECTION_NAME="${INSTANCE_CONNECTION_NAME}"
export DB_NAME="${DB_NAME}"
export DB_USER="${DB_USER}"
export DB_PASSWORD="${DB_PASSWORD}"
export TRAINING_BUCKET="gs://f1optimizer-training"
export MODELS_BUCKET="gs://f1optimizer-models"
export DATA_LAKE_BUCKET="gs://f1optimizer-data-lake"
export ARTIFACT_REGISTRY="us-central1-docker.pkg.dev/${PROJECT_ID}/f1-optimizer"
export PYTHONPATH="\${PYTHONPATH:-}:/home/jupyter"
EOF

chmod 644 /etc/profile.d/f1_env.sh
source /etc/profile.d/f1_env.sh
log "Environment variables written."

# ── 4. Configure ADC ─────────────────────────────────────────────────────────
log "Configuring Application Default Credentials..."

# On Workbench, the SA is attached to the VM — ADC works automatically.
# This just validates that credentials are reachable.
gcloud auth application-default print-access-token \
  --project="${PROJECT_ID}" > /dev/null 2>&1 \
  && log "ADC: OK (service account credentials active)" \
  || log "WARNING: ADC check failed — run 'gcloud auth application-default login' manually."

# ── 5. Ready message ──────────────────────────────────────────────────────────
log "============================================================"
log "  f1-ml-workbench is ready"
log "============================================================"
log "  Project        : ${PROJECT_ID}"
log "  Region         : ${REGION}"
log "  Training bucket: gs://f1optimizer-training/"
log "  Models bucket  : gs://f1optimizer-models/"
log ""
log "  Console links:"
log "  Workbench : https://console.cloud.google.com/vertex-ai/workbench/instances?project=${PROJECT_ID}"
log "  Pipelines : https://console.cloud.google.com/vertex-ai/pipelines?project=${PROJECT_ID}"
log "  Training  : https://console.cloud.google.com/vertex-ai/training/custom-jobs?project=${PROJECT_ID}"
log "  Experiments: https://console.cloud.google.com/vertex-ai/experiments?project=${PROJECT_ID}"
log "============================================================"
