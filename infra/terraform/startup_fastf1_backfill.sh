#!/bin/bash
# startup_fastf1_backfill.sh — runs on a one-shot GCE VM to backfill
# missing FastF1 lap data for 2022 (R4-22), 2024 (R2-24), 2025 (R17-24).
# Self-terminates when done so the VM stops billing.

set -euo pipefail
exec > >(tee /var/log/fastf1_backfill.log | logger -t fastf1-backfill) 2>&1

echo "[$(date -u +%FT%TZ)] startup: FastF1 backfill VM"

# ------- system packages -------
apt-get update -qq
apt-get install -y --no-install-recommends python3-pip python3-venv curl

# ------- Python venv -------
python3 -m venv /opt/ff1env
source /opt/ff1env/bin/activate

pip install --quiet --no-cache-dir \
    "fastf1>=3.3.0" \
    "google-cloud-storage>=2.14.0" \
    "pandas>=2.1.0" \
    "pyarrow>=14.0.0" \
    "requests>=2.31.0"

# ------- fetch backfill script from GCS -------
gsutil cp gs://f1optimizer-data-lake/scripts/backfill_data.py /opt/backfill_data.py

# ------- run -------
echo "[$(date -u +%FT%TZ)] starting FastF1 backfill (2022 R4-22, 2024 R2-24, 2025 R17-24)"
python /opt/backfill_data.py --fastf1-only --bucket f1optimizer-data-lake
echo "[$(date -u +%FT%TZ)] FastF1 backfill complete — stopping instance"

# Self-terminate
ZONE=$(curl -sf -H "Metadata-Flavor: Google" \
    "http://metadata.google.internal/computeMetadata/v1/instance/zone" | awk -F/ '{print $NF}')
NAME=$(curl -sf -H "Metadata-Flavor: Google" \
    "http://metadata.google.internal/computeMetadata/v1/instance/name")
gcloud compute instances stop "$NAME" --zone="$ZONE" --quiet
