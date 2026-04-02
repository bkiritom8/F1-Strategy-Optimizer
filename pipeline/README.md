# Pipeline & Simulator Utilities

This module handles infrastructure-adjacent data management steps such as transforming datasets, backfilling operations, validating Cloud Storage payloads, and deploying simulators.

## Structure

- **scripts/**: Quick runner scripts intended for data transformations.
  - `csv_to_parquet.py`: Bulk converter turning CSV ingest jobs into performant Apache Parquet files.
  - `backfill_data.py`: Targeted extraction.
  - `verify_upload.py`: Checksum validations against `gs://f1optimizer-data-lake`.
- **simulator/**: Internal race simulation tests to evaluate the RL agent offline.
- **rl/**: RL experience building and caching layers for PPO optimization.
