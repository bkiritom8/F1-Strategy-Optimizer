# Operational Scripts

Utility scripts for maintenance, data backfills, and GCP operations.

## Contents

- **`backfill_jolpica.py`**: Manual backfill for historical race results (1950-2023).
- **`deploy_all.sh`**: Convenience wrapper for building and pushing all service containers.
- **`gcp_cleanup.py`**: Deletes temporary Cloud Run revisions and old GCS staging artifacts.
- **`generate_track_paths.py`**: Helper to convert SVG circuit paths into JSON registry for the frontend.

## Usage

Example: Backfill 2024 season:
```bash
python scripts/backfill_jolpica.py --season 2024
```

> [!WARNING]
> Use `gcp_cleanup.py` with caution; ensure no active production deployments are targeted.
