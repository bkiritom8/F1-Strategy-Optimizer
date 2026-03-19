#!/bin/bash
# monitor_workers.sh — Check F1 workers every 60 min, restart any preempted.
# Run in background: nohup bash scripts/monitor_workers.sh > monitor.log 2>&1 &

PROJECT="f1optimizer"
ZONE="us-central1-a"
INTERVAL=3600  # 60 minutes

while true; do
    echo "[$(date -u +%FT%TZ)] Checking workers..."

    TERMINATED=$(gcloud compute instances list \
        --project="$PROJECT" \
        --zones="$ZONE" \
        --filter="name~'f1-lt-worker|f1-fastf1-backfill' AND status=TERMINATED" \
        --format="value(name)" 2>/dev/null)

    if [ -z "$TERMINATED" ]; then
        echo "  All workers still running."
    else
        echo "  Preempted/stopped: $TERMINATED"
        gcloud compute instances start $TERMINATED \
            --zone="$ZONE" --project="$PROJECT"
        echo "  Restarted: $TERMINATED"
    fi

    echo "  Next check in 60 min."
    sleep "$INTERVAL"
done
