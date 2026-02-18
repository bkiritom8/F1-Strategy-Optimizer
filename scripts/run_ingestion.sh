#!/usr/bin/env bash
# Run the full F1 data ingestion pipeline: schema → Ergast → FastF1
set -euo pipefail

LOG_DIR="${LOG_DIR:-/tmp/ingestion_logs}"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/ingestion_$(date +%Y%m%d_%H%M%S).log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "=== F1 Data Ingestion Pipeline ==="
log "Log file: $LOG_FILE"

# ---- 1. Apply schema -------------------------------------------------------
log "Step 1/3: Applying database schema..."
python - <<'PYEOF' 2>&1 | tee -a "$LOG_FILE"
import os, pg8000.native

conn = pg8000.native.Connection(
    host=os.environ["DB_HOST"],
    port=int(os.environ.get("DB_PORT", 5432)),
    database=os.environ["DB_NAME"],
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    ssl_context=True,
)
schema_path = os.path.join(os.path.dirname(__file__), "..", "src", "database", "schema.sql")
with open(schema_path) as f:
    conn.run(f.read())
conn.close()
print("Schema applied successfully.")
PYEOF
log "Step 1/3: Schema applied."

# ---- 2. Ergast historical ingestion ----------------------------------------
log "Step 2/3: Starting Ergast ingestion..."
python -m src.ingestion.ergast_ingestion 2>&1 | tee -a "$LOG_FILE"
log "Step 2/3: Ergast ingestion complete."

# ---- 3. FastF1 ingestion ---------------------------------------------------
log "Step 3/3: Starting FastF1 ingestion..."
python -m src.ingestion.fastf1_ingestion 2>&1 | tee -a "$LOG_FILE"
log "Step 3/3: FastF1 ingestion complete."

log "=== Ingestion pipeline finished ==="
