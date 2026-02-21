#!/usr/bin/env bash
# ml/scripts/submit_training_job.sh
# Submit a Vertex AI Custom Training Job using the ml:latest image with 1x T4 GPU.
#
# Usage:
#   bash ml/scripts/submit_training_job.sh --display-name <name> [--args <arg1,arg2,...>]
#
# Examples:
#   bash ml/scripts/submit_training_job.sh --display-name alice-strategy-v1
#   bash ml/scripts/submit_training_job.sh --display-name bob-pit-v2 \
#       --args "--mode=train,--model=pit_stop_optimizer"
#
# Prerequisites:
#   - ADC credentials active (gcloud auth application-default login)
#   - ml:latest image built and pushed to Artifact Registry
#   - SA f1-training-dev has roles/aiplatform.user

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-f1optimizer}"
REGION="${REGION:-us-central1}"
IMAGE_URI="us-central1-docker.pkg.dev/${PROJECT_ID}/f1-optimizer/ml:latest"
SERVICE_ACCOUNT="f1-training-dev@${PROJECT_ID}.iam.gserviceaccount.com"
MACHINE_TYPE="n1-standard-4"
ACCELERATOR_TYPE="NVIDIA_TESLA_T4"
ACCELERATOR_COUNT=1

DISPLAY_NAME=""
JOB_ARGS=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --display-name)
      DISPLAY_NAME="$2"
      shift 2
      ;;
    --args)
      JOB_ARGS="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 --display-name <name> [--args <arg1,arg2,...>]" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$DISPLAY_NAME" ]]; then
  echo "Error: --display-name is required" >&2
  echo "Usage: $0 --display-name <name> [--args <arg1,arg2,...>]" >&2
  exit 1
fi

echo "=== Vertex AI Custom Training Job ==="
echo "Project:          $PROJECT_ID"
echo "Region:           $REGION"
echo "Display name:     $DISPLAY_NAME"
echo "Image:            $IMAGE_URI"
echo "Machine:          $MACHINE_TYPE + ${ACCELERATOR_COUNT}x ${ACCELERATOR_TYPE}"
echo ""

# Build worker pool spec JSON
WORKER_POOL_SPEC="machine-type=${MACHINE_TYPE}"
WORKER_POOL_SPEC+=",accelerator-type=${ACCELERATOR_TYPE}"
WORKER_POOL_SPEC+=",accelerator-count=${ACCELERATOR_COUNT}"
WORKER_POOL_SPEC+=",replica-count=1"
WORKER_POOL_SPEC+=",container-image-uri=${IMAGE_URI}"

if [[ -n "$JOB_ARGS" ]]; then
  WORKER_POOL_SPEC+=",local-package-path=.,executor-image-uri=${IMAGE_URI}"
fi

gcloud ai custom-jobs create \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --display-name="${DISPLAY_NAME}" \
  --worker-pool-spec="${WORKER_POOL_SPEC}" \
  --service-account="${SERVICE_ACCOUNT}"

echo ""
echo "Job submitted. Monitor at:"
echo "  https://console.cloud.google.com/vertex-ai/training/custom-jobs?project=${PROJECT_ID}"
