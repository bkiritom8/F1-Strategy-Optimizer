#!/usr/bin/env bash
# scripts/cleanup.sh
# Tear down the full DivergeX deployment.
#
# Usage:
#   bash scripts/cleanup.sh [--wipe-data]
#
# Options:
#   --wipe-data    Also delete all GCS bucket contents (raw data, models,
#                  training artifacts). CANNOT BE UNDONE.
#
# What this does (without --wipe-data):
#   - Disables Firebase Hosting
#   - Destroys all GCP resources via Terraform (Cloud Run, Vertex AI,
#     Pub/Sub, Artifact Registry, IAM, Cloud Build trigger, etc.)
#   - GCS bucket contents are preserved (Terraform does not force-destroy them)
#
# Prerequisites:
#   gcloud auth application-default login
#   terraform >= 1.5.0
#   firebase-tools (npm install -g firebase-tools && firebase login)

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-f1optimizer}"
REGION="${REGION:-us-central1}"
TFVARS="infra/terraform/dev.tfvars"
WIPE_DATA=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --wipe-data) WIPE_DATA=true; shift ;;
    *) echo "Unknown flag: $1" >&2; exit 1 ;;
  esac
done

echo "DivergeX Cleanup"
echo "Project:  $PROJECT_ID"
echo "Region:   $REGION"
if [[ "$WIPE_DATA" == "true" ]]; then
  echo "WARNING: --wipe-data is set. All GCS bucket contents will be deleted."
fi
echo ""
read -r -p "Continue? This will destroy all cloud resources. [y/N] " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi

# -- 1. Disable Firebase Hosting -----------------------------------------------
echo ""
echo "=== [1/3] Disabling Firebase Hosting ==="
(cd frontend && firebase hosting:disable --project "$PROJECT_ID" --force) || \
  echo "Firebase hosting disable skipped (may already be disabled or CLI not logged in)."

# -- 2. Wipe GCS data (optional) -----------------------------------------------
if [[ "$WIPE_DATA" == "true" ]]; then
  echo ""
  echo "=== [2/3] Wiping GCS bucket contents ==="
  for bucket in \
    "gs://f1optimizer-data-lake" \
    "gs://f1optimizer-models" \
    "gs://f1optimizer-training"; do
    echo "Deleting all objects in $bucket ..."
    gsutil -m rm -rf "${bucket}/**" 2>/dev/null || echo "  $bucket is already empty or does not exist."
  done
else
  echo ""
  echo "=== [2/3] Skipping GCS data wipe (pass --wipe-data to delete bucket contents) ==="
fi

# -- 3. Destroy GCP infrastructure via Terraform -------------------------------
echo ""
echo "=== [3/3] Destroying GCP infrastructure (Terraform) ==="
terraform -chdir=infra/terraform init -input=false
terraform -chdir=infra/terraform destroy -var-file=dev.tfvars -auto-approve

echo ""
echo "Cleanup complete."
