# Operational Scripts

Utility scripts for maintenance, data backfills, GCP operations, and deployment.

## Contents

| Script | Purpose |
|---|---|
| `backfill_jolpica.py` | Manual backfill for historical race results (1950–2023) from Jolpica |
| `deploy_all.sh` | Build and push all service containers (`api`, `ml`, `ingest`, `rag`) |
| `gcp_cleanup.py` | Delete temporary Cloud Run revisions and old GCS staging artifacts |
| `generate_track_paths.py` | Convert SVG circuit paths into the JSON track registry for the frontend |
| `monitor_workers.sh` | Monitor active Cloud Run ingest worker status |
| `run_rag_ingestion.sh` | Orchestrate a full RAG re-indexing run |

## Usage

### Data Backfill

```bash
# Backfill a specific season
python scripts/backfill_jolpica.py --season 2024

# Backfill a range
python scripts/backfill_jolpica.py --season-start 2019 --season-end 2023
```

### Deploy All Services

```bash
bash scripts/deploy_all.sh
```

### GCP Cleanup

```bash
# Dry run first — see what would be deleted
python scripts/gcp_cleanup.py --dry-run

# Execute cleanup
python scripts/gcp_cleanup.py
```

> [!WARNING]
> Always run `--dry-run` first. Ensure no active production deployments are targeted before executing.

### Track Path Generation

Run after adding or updating circuit SVG files:

```bash
python scripts/generate_track_paths.py \
  --input frontend/public/tracks/ \
  --output frontend/public/data/track_registry.json
```

### Monitor Workers

```bash
bash scripts/monitor_workers.sh
```

### RAG Re-indexing

```bash
bash scripts/run_rag_ingestion.sh
```

---

**Prerequisites**: `gcloud auth application-default login` and `gcloud config set project f1optimizer`
