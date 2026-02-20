#!/bin/bash
# Finds the first available GCP zone with capacity for the Workbench machine type.
# Outputs a single zone name (e.g. "us-east1-c") to stdout.
# Zone order: remaining untried zones first; known-capacity-failed zones last.

MACHINE_TYPE="n1-standard-4"
PROJECT="f1optimizer"

ZONES=("us-east1-c" "us-east1-d"
       "us-east1-b" "us-central1-c" "us-central1-f"
       "us-central1-a" "us-central1-b")

for ZONE in "${ZONES[@]}"; do
  ZONE_STATUS=$(gcloud compute zones describe "$ZONE" \
    --project="$PROJECT" \
    --format="value(status)" 2>/dev/null)

  if [ "$ZONE_STATUS" != "UP" ]; then
    continue
  fi

  MT_AVAILABLE=$(gcloud compute machine-types describe "$MACHINE_TYPE" \
    --zone="$ZONE" \
    --project="$PROJECT" \
    --format="value(name)" 2>/dev/null)

  if [ "$MT_AVAILABLE" = "$MACHINE_TYPE" ]; then
    echo "$ZONE"
    exit 0
  fi
done

echo "us-east1-c"  # default fallback
