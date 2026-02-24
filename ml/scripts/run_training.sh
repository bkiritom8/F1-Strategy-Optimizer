#!/usr/bin/env bash
# ml/scripts/run_training.sh
# Compile and submit the full KFP training pipeline to Vertex AI Pipelines.
#
# Usage:
#   bash ml/scripts/run_training.sh [--run-id <id>] [--compile-only]
#
# Prerequisites:
#   - ADC credentials active (gcloud auth application-default login)
#   - GCS buckets gs://f1optimizer-models and gs://f1optimizer-training exist
#   - ML Docker image built and pushed to Artifact Registry
#
# Environment variables (all have defaults):
#   PROJECT_ID        GCP project          (default: f1optimizer)
#   REGION            GCP region           (default: us-central1)
#   TRAINING_BUCKET   GCS training bucket  (default: gs://f1optimizer-training)
#   MODELS_BUCKET     GCS models bucket    (default: gs://f1optimizer-models)

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-f1optimizer}"
REGION="${REGION:-us-central1}"
TRAINING_BUCKET="${TRAINING_BUCKET:-gs://f1optimizer-training}"
MODELS_BUCKET="${MODELS_BUCKET:-gs://f1optimizer-models}"
RUN_ID="${1:-$(date +%Y%m%d-%H%M%S)}"
COMPILE_ONLY="${COMPILE_ONLY:-false}"

echo "=== F1 Strategy Training Pipeline ==="
echo "Project:          $PROJECT_ID"
echo "Region:           $REGION"
echo "Training bucket:  $TRAINING_BUCKET"
echo "Models bucket:    $MODELS_BUCKET"
echo "Run ID:           $RUN_ID"
echo ""

# Compile and optionally submit via pipeline_runner.py
if [[ "$COMPILE_ONLY" == "true" ]]; then
    python ml/dag/pipeline_runner.py --compile-only
    echo "Pipeline compiled. YAML written to gs://f1optimizer-training/pipelines/."
else
    python ml/dag/pipeline_runner.py --run-id "$RUN_ID"
    echo ""
    echo "Pipeline submitted. Monitor at:"
    echo "  https://console.cloud.google.com/vertex-ai/pipelines?project=$PROJECT_ID"
fi
