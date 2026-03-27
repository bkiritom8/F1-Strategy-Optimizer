#!/bin/bash
# airflow_startup.sh — GCE startup script (Container-Optimized OS)
#
# - Docker is pre-installed on COS; skip install if present.
# - Installs docker-compose v2 as a standalone binary.
# - Creates /opt/airflow/{dags,logs,plugins}.
# - Starts a background loop that syncs DAGs from GCS every 5 minutes.
# - Writes /opt/airflow/docker-compose.yml and starts Airflow.
#
# All GCS paths read from instance metadata (set via Terraform).

set -euo pipefail

# ── Swap (2 GB on stateful partition — survives reboots on COS) ───────────────
SWAP_FILE="/mnt/stateful_partition/swapfile"
if [ ! -f "$SWAP_FILE" ]; then
  fallocate -l 2G "$SWAP_FILE"
  chmod 600 "$SWAP_FILE"
  mkswap "$SWAP_FILE"
fi
swapon "$SWAP_FILE" 2>/dev/null || true  # no-op if already active

LOG_FILE="/var/log/airflow_startup.log"
exec >> "$LOG_FILE" 2>&1
echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] === Airflow VM startup BEGIN ==="

# ── Read instance metadata ────────────────────────────────────────────────────
METADATA_URL="http://metadata.google.internal/computeMetadata/v1/instance/attributes"
_meta() { curl -sf -H "Metadata-Flavor: Google" "${METADATA_URL}/${1}" 2>/dev/null || echo "${2:-}"; }

GCS_DAGS_BUCKET="$(_meta gcs-dags-bucket "gs://f1optimizer-training/dags")"
AIRFLOW_IMAGE="$(_meta airflow-image "us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/airflow:latest")"
GCS_PROCESSED="${GCS_PROCESSED:-gs://f1optimizer-data-lake/processed}"
GCS_RAW="${GCS_RAW:-gs://f1optimizer-data-lake/raw}"

echo "[INFO] GCS_DAGS_BUCKET=${GCS_DAGS_BUCKET}"
echo "[INFO] AIRFLOW_IMAGE=${AIRFLOW_IMAGE}"

# ── Docker (pre-installed on COS) ─────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo "[ERROR] Docker not found — this VM should use Container-Optimized OS."
    exit 1
fi
echo "[INFO] Docker version: $(docker --version)"

# ── docker-compose (install if missing) ───────────────────────────────────────
if ! command -v docker-compose &>/dev/null; then
    echo "[INFO] Installing docker-compose v2..."
    curl -SL \
        "https://github.com/docker/compose/releases/download/v2.24.5/docker-compose-linux-x86_64" \
        -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
fi
echo "[INFO] docker-compose version: $(docker-compose --version)"

# ── Directories ───────────────────────────────────────────────────────────────
mkdir -p /opt/airflow/{dags,logs,plugins}
chmod -R 777 /opt/airflow

# ── Authenticate Docker with Artifact Registry ────────────────────────────────
echo "[INFO] Configuring Docker credentials for Artifact Registry..."
docker-credential-gcr configure-docker --registries=us-central1-docker.pkg.dev || true

# ── Initial DAG sync from GCS ─────────────────────────────────────────────────
echo "[INFO] Syncing DAGs from ${GCS_DAGS_BUCKET}..."
if gsutil ls "${GCS_DAGS_BUCKET}" &>/dev/null; then
    gsutil -m rsync -r "${GCS_DAGS_BUCKET}/" /opt/airflow/dags/
    echo "[INFO] DAG sync complete — $(ls /opt/airflow/dags/ | wc -l) files"
else
    echo "[WARN] ${GCS_DAGS_BUCKET} not accessible. Starting with empty DAGs directory."
fi

# ── Background DAG sync every 5 minutes ───────────────────────────────────────
nohup bash -c "
while true; do
    gsutil -m rsync -r ${GCS_DAGS_BUCKET}/ /opt/airflow/dags/ \
        >> /var/log/dag_sync.log 2>&1
    sleep 300
done
" &
echo "[INFO] DAG sync daemon started (PID=$!)"

# ── Generate Fernet key for Airflow ───────────────────────────────────────────
FERNET_KEY=$(python3 -c \
    "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" \
    2>/dev/null || echo "")
if [[ -z "$FERNET_KEY" ]]; then
    # Fallback: base64-encode 32 random bytes
    FERNET_KEY=$(dd if=/dev/urandom bs=32 count=1 2>/dev/null | base64 | tr -d '\n')
fi

# ── Write docker-compose.yml ──────────────────────────────────────────────────
cat > /opt/airflow/docker-compose.yml <<COMPOSEEOF
version: '3.8'

x-airflow-common: &airflow-common
  image: ${AIRFLOW_IMAGE}
  environment:
    AIRFLOW__CORE__EXECUTOR: LocalExecutor
    AIRFLOW__CORE__FERNET_KEY: ${FERNET_KEY}
    AIRFLOW__CORE__LOAD_EXAMPLES: 'false'
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: sqlite:////opt/airflow/airflow.db
    AIRFLOW__WEBSERVER__EXPOSE_CONFIG: 'false'
    AIRFLOW__WEBSERVER__SECRET_KEY: ${FERNET_KEY}
    GCS_PROCESSED: ${GCS_PROCESSED}
    GCS_RAW: ${GCS_RAW}
    GCS_DAGS_BUCKET: ${GCS_DAGS_BUCKET}
    DATA_BUCKET: f1optimizer-data-lake
    MODELS_BUCKET: f1optimizer-models
    USE_LOCAL_DATA: 'false'
  volumes:
    - /opt/airflow/dags:/opt/airflow/dags
    - /opt/airflow/logs:/opt/airflow/logs
    - /opt/airflow/plugins:/opt/airflow/plugins
  restart: unless-stopped

services:
  airflow-init:
    <<: *airflow-common
    entrypoint: /bin/bash
    command: >-
      -c "airflow db init &&
          airflow users create
            --username admin --password admin
            --firstname Admin --lastname User
            --role Admin --email admin@f1optimizer.com || true"
    restart: 'no'

  airflow-webserver:
    <<: *airflow-common
    command: webserver
    ports:
      - "8080:8080"
    healthcheck:
      test: ["CMD", "curl", "--fail", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s
    depends_on:
      airflow-init:
        condition: service_completed_successfully

  airflow-scheduler:
    <<: *airflow-common
    command: scheduler
    depends_on:
      airflow-init:
        condition: service_completed_successfully
COMPOSEEOF

# ── Pull image and start Airflow ──────────────────────────────────────────────
echo "[INFO] Pulling Airflow image..."
docker pull "${AIRFLOW_IMAGE}"

echo "[INFO] Running airflow-init..."
docker-compose -f /opt/airflow/docker-compose.yml up -d airflow-init

# Wait for init to complete (up to 120 seconds)
for i in $(seq 1 24); do
    STATUS=$(docker-compose -f /opt/airflow/docker-compose.yml \
        ps --format json airflow-init 2>/dev/null | python3 -c \
        "import sys,json; d=json.load(sys.stdin); print(d.get('State',''))" \
        2>/dev/null || echo "unknown")
    if [[ "$STATUS" == "exited" ]] || [[ "$STATUS" == "exited (0)" ]]; then
        echo "[INFO] airflow-init complete"
        break
    fi
    echo "[INFO] Waiting for airflow-init... (${i}/24)"
    sleep 5
done

echo "[INFO] Starting airflow-webserver and airflow-scheduler..."
docker-compose -f /opt/airflow/docker-compose.yml up -d \
    airflow-webserver airflow-scheduler

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] === Airflow VM startup DONE ==="
echo "[INFO] Airflow UI will be available at http://$(curl -sf \
    http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip \
    -H 'Metadata-Flavor: Google' 2>/dev/null || echo 'VM_IP'):8080"
