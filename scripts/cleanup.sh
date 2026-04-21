#!/usr/bin/env bash
# scripts/cleanup.sh
# Tear down the full DivergeX deployment completely.
#
# Usage:
#   bash scripts/cleanup.sh
#
# What this does:
#   - Disables Firebase Hosting
#   - Wipes all GCS bucket contents (raw data, models, training artifacts)
#   - Destroys all GCP resources via Terraform (Cloud Run, Vertex AI,
#     Pub/Sub, Artifact Registry, IAM, Cloud Build trigger, buckets, etc.)
#
# CANNOT BE UNDONE. All data will be lost.
#
# Prerequisites:
#   gcloud auth application-default login
#   terraform >= 1.5.0
#   firebase-tools (npm install -g firebase-tools && firebase login)

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-f1optimizer}"
REGION="${REGION:-us-central1}"

echo "DivergeX Cleanup"
echo "Project:  $PROJECT_ID"
echo "Region:   $REGION"
echo ""
echo "WARNING: This will permanently delete ALL cloud resources and data."
read -r -p "Continue? [y/N] " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi

# -- 1. Disable Firebase Hosting -----------------------------------------------
echo ""
echo "=== [1/3] Disabling Firebase Hosting ==="
(cd frontend && firebase hosting:disable --project "$PROJECT_ID" --force) || \
  echo "Firebase hosting disable skipped (may already be disabled or CLI not logged in)."

# -- 2. Wipe GCS bucket contents -----------------------------------------------
echo ""
echo "=== [2/3] Wiping GCS bucket contents ==="
for bucket in \
  "gs://f1optimizer-data-lake" \
  "gs://f1optimizer-models" \
  "gs://f1optimizer-training"; do
  echo "Deleting all objects in $bucket ..."
  gsutil -m rm -rf "${bucket}/**" 2>/dev/null || echo "  $bucket is already empty or does not exist."
done

# -- 3. Destroy GCP infrastructure via Terraform -------------------------------
echo ""
echo "=== [3/3] Destroying GCP infrastructure (Terraform) ==="
terraform -chdir=infra/terraform init -input=false
terraform -chdir=infra/terraform destroy -auto-approve

echo ""
echo "Cleanup complete."
