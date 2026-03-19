# Pipeline — Data Management Utilities

Data management scripts, race simulator, and RL utilities.

## Directory Layout

```
pipeline/
├── scripts/
│   ├── csv_to_parquet.py   Convert raw CSVs → Parquet, upload to GCS
│   ├── verify_upload.py    Verify GCS data lake contents (file counts + sizes)
│   └── backfill_data.py    Fix known data gaps (race results, laps, FastF1 rounds)
├── simulator/
│   ├── race_simulator.py   Race strategy simulator
│   └── validator.py        Simulation result validator
└── rl/
    └── experience_builder.py  Build RL experience tuples from race data
```

For the full MLOps pipeline (DVC stages, Airflow DAG, validation, anomaly detection,
bias analysis), see [`Data-Pipeline/README.md`](../Data-Pipeline/README.md).

### Backfill known data gaps

```bash
# Dry run first to see what would change
python pipeline/scripts/backfill_data.py --bucket f1optimizer-data-lake --dry-run

# Run full backfill (race results + FastF1 missing rounds)
python pipeline/scripts/backfill_data.py --bucket f1optimizer-data-lake

# Skip FastF1 (race results only — much faster)
python pipeline/scripts/backfill_data.py --bucket f1optimizer-data-lake --skip-fastf1

# FastF1 only
python pipeline/scripts/backfill_data.py --bucket f1optimizer-data-lake --fastf1-only
```

The script pauses 90 seconds between each race when fetching FastF1 data to stay within
API rate limits.

## Usage

### Convert CSVs to Parquet

```bash
# GCP mode (uploads to GCS)
python pipeline/scripts/csv_to_parquet.py \
  --input-dir raw/ \
  --bucket f1optimizer-data-lake

# Local mode (writes to data/processed/)
USE_LOCAL_DATA=true python pipeline/scripts/csv_to_parquet.py \
  --input-dir raw/ \
  --bucket local
```

Outputs 10 Parquet files to `gs://f1optimizer-data-lake/processed/`.

### Verify GCS Upload

```bash
python pipeline/scripts/verify_upload.py --bucket f1optimizer-data-lake
```

Reports file counts and sizes for `raw/` and `processed/` prefixes.

## Data Already Uploaded

The full F1 dataset is in GCS:

| Path | Files | Size | Contents |
|---|---|---|---|
| `gs://f1optimizer-data-lake/raw/` | 51 | 6.0 GB | Source CSVs (Jolpica + FastF1) |
| `gs://f1optimizer-data-lake/processed/` | 10 | 1.0 GB | Parquet (ML-ready) |

To read directly in Python (ADC credentials required):

```python
import pandas as pd

laps = pd.read_parquet("gs://f1optimizer-data-lake/processed/laps_all.parquet")
```
