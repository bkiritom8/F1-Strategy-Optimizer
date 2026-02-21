# F1 Strategy Optimizer — ML Team Handoff

**Date**: 2026-02-20
**Status**: Infrastructure complete, data in GCS, models ready for training
**GCP Project**: `f1optimizer` | **Region**: `us-central1`

---

> **The authoritative ML handoff document is `ml/HANDOFF.md`.**
> This file provides a high-level overview; see `ml/HANDOFF.md` for
> full repo structure, GCP resources, training commands, and first-steps.

---

## Infrastructure State

All infrastructure is Terraform-managed (`infra/terraform/`, state in `gs://f1-optimizer-terraform-state/`).

| Resource | Name / ID | Status |
|---|---|---|
| GCS — data lake | `gs://f1optimizer-data-lake/` | Active — 51 raw, 10 processed files |
| GCS — model artifacts | `gs://f1optimizer-models/` | Active |
| GCS — training artifacts | `gs://f1optimizer-training/` | Active |
| GCS — pipeline runs | `gs://f1optimizer-pipeline-runs/` | Active |
| GCS — Terraform state | `gs://f1-optimizer-terraform-state/` | Active |
| Service Account | `f1-training-dev@f1optimizer.iam.gserviceaccount.com` | Active |
| Artifact Registry | `us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/` | Active |
| Cloud Run service | `f1-strategy-api-dev` | Active |
| Cloud Run Job | `f1-pipeline-trigger` | Active |
| Pub/Sub topics | `f1-race-events-dev`, `f1-telemetry-stream-dev`, `f1-predictions-dev`, `f1-alerts-dev` | Active |

---

## Data

All F1 data is stored in GCS — there is no database.

| Path | Files | Size | Contents |
|---|---|---|---|
| `gs://f1optimizer-data-lake/raw/` | 51 | 6.0 GB | Source CSVs (Jolpica + FastF1) |
| `gs://f1optimizer-data-lake/processed/` | 10 | 1.0 GB | Parquet files (ML-ready) |

### Processed Parquet files

| File | Rows | Description |
|---|---|---|
| `processed/laps_all.parquet` | 93,372 | Lap data 1996–2025 |
| `processed/telemetry_all.parquet` | 30,477,110 | FastF1 telemetry 2018–2025 |
| `processed/telemetry_laps_all.parquet` | 92,242 | FastF1 session laps |
| `processed/circuits.parquet` | 78 | Circuit master list |
| `processed/drivers.parquet` | 100 | Driver master list |
| `processed/pit_stops.parquet` | 11,077 | Pit stop records |
| `processed/race_results.parquet` | 7,600 | Race results 1950–2026 |
| `processed/lap_times.parquet` | 56,720 | Aggregated lap times |
| `processed/fastf1_laps.parquet` | 92,242 | FastF1 lap data 2018–2026 |
| `processed/fastf1_telemetry.parquet` | 90,302 | FastF1 telemetry summary |

```python
import pandas as pd

laps         = pd.read_parquet("gs://f1optimizer-data-lake/processed/laps_all.parquet")
telemetry    = pd.read_parquet("gs://f1optimizer-data-lake/processed/telemetry_all.parquet")
race_results = pd.read_parquet("gs://f1optimizer-data-lake/processed/race_results.parquet")
```

ADC credentials are all that is required — no proxy or VPN. See `DEV_SETUP.md` §2.

---

## GPU Training

The recommended way to run GPU training is via a Vertex AI Custom Job:

```bash
bash ml/scripts/submit_training_job.sh --display-name your-name-strategy-v1
```

This submits with: `n1-standard-4`, 1× NVIDIA T4, `ml:latest` image.

### Trigger full pipeline

```bash
# Cloud Run Job (scheduled / automated)
gcloud run jobs execute f1-pipeline-trigger \
  --region=us-central1 --project=f1optimizer

# Python SDK
python ml/dag/pipeline_runner.py --run-id $(date +%Y%m%d)
```

---

## API

**Endpoint**: `https://f1-strategy-api-dev-694267183904.us-central1.run.app`

Loads promoted models from `gs://f1optimizer-models/` at startup;
falls back to rule-based strategy if models are not yet promoted.

---

## Day 1 Quickstart

1. **Authenticate** — follow `DEV_SETUP.md` §1–2
2. **Verify data**:
   ```bash
   gsutil ls gs://f1optimizer-data-lake/processed/
   ```
3. **Run tests**:
   ```bash
   python ml/tests/run_tests_on_vertex.py
   ```
4. **Trigger first pipeline run**:
   ```bash
   python ml/dag/pipeline_runner.py --run-id first-run
   ```
5. **Check Experiments**:
   https://console.cloud.google.com/vertex-ai/experiments?project=f1optimizer

---

## Branch Strategy

| Branch | Purpose |
|---|---|
| `main` | Stable — infra + code, reviewed PRs only |
| `pipeline` | CI/CD trigger — Cloud Build builds all Docker images on push |
| `ml-dev` | ML team development branch |

**See `ml/HANDOFF.md` for complete documentation.**
