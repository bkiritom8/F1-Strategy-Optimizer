# Pipeline & Simulator Utilities

Infrastructure-adjacent data management: CSV→Parquet conversion, data backfilling, GCS validation, offline RL simulation, and car performance table generation.

## Directory Structure

```
pipeline/
├── scripts/
│   ├── csv_to_parquet.py          # Bulk CSV → Parquet converter, uploads to GCS
│   ├── backfill_data.py           # Targeted data extraction for missed windows
│   ├── verify_upload.py           # Checksum validation against GCS data lake
│   └── build_car_performance.py   # GCS parquet → year-aware car offsets JSON
├── simulator/                     # Offline race simulator for RL agent evaluation
├── rl/                            # PPO experience building + caching layers
└── logs/                          # Pipeline execution logs
```

## Scripts

### `csv_to_parquet.py`

Converts raw CSVs from GCS into columnar Apache Parquet files for efficient downstream ML reads.

```bash
python pipeline/scripts/csv_to_parquet.py \
  --input gs://f1optimizer-data-lake/raw/ \
  --output gs://f1optimizer-data-lake/processed/
```

### `backfill_data.py`

Targeted extraction for specific seasons or circuits where gaps exist in the data lake.

```bash
python pipeline/scripts/backfill_data.py --season 2023 --circuit monza
```

### `verify_upload.py`

Validates GCS data lake contents by checksumming and counting expected files.

```bash
python pipeline/scripts/verify_upload.py
# Expected: 51 raw files (6.0 GB), 10+ Parquet + ml_features files
```

### `build_car_performance.py`

One-time script that reads `race_results.parquet` from GCS and generates `frontend/public/data/car_performance.json` — year-aware constructor performance offsets (2018–2025) consumed by the frontend `RaceSimulator`.

Run after new season data lands:

```bash
python pipeline/scripts/build_car_performance.py \
  --input gs://f1optimizer-data-lake/processed/race_results.parquet \
  --output frontend/public/data/car_performance.json
```

## Simulator (`simulator/`)

Offline race simulation for evaluating the PPO RL agent without Cloud infrastructure. Mirrors the full race environment including pit stop timing, tyre degradation, safety car probability, and gap dynamics.

## RL Layer (`rl/`)

Experience building and caching for PPO optimization:

- Converts simulator outputs into replay buffer format compatible with Stable-Baselines3
- GCS-backed caching so training jobs can resume from a checkpoint

---

**Data Lake**: `gs://f1optimizer-data-lake/` — raw CSV → processed Parquet → ml_features Parquet
