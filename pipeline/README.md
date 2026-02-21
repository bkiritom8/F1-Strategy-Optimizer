# Pipeline — Data Scripts

Utility scripts for managing F1 data in GCS.

## Directory layout

```
pipeline/
└── scripts/
    ├── csv_to_parquet.py   Convert raw CSVs → Parquet and upload to GCS
    └── verify_upload.py    Verify GCS data lake contents (file counts + sizes)
```

## Usage

### Convert CSVs to Parquet

```bash
python pipeline/scripts/csv_to_parquet.py \
  --input-dir raw/ \
  --bucket f1optimizer-data-lake
```

Outputs 10 Parquet files to `gs://f1optimizer-data-lake/processed/`.

### Verify GCS upload

```bash
python pipeline/scripts/verify_upload.py --bucket f1optimizer-data-lake
```

Reports file counts and sizes for `raw/` and `processed/` prefixes.

## Data already uploaded

The full F1 dataset has been uploaded:
- `gs://f1optimizer-data-lake/raw/`: 51 files, 6.0 GB (source CSVs)
- `gs://f1optimizer-data-lake/processed/`: 10 files, 1.0 GB (Parquet)
