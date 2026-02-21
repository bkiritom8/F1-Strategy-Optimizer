"""
verify_upload.py — Verify GCS uploads for the F1 data lake.

Usage:
    python pipeline/scripts/verify_upload.py --bucket f1optimizer-data-lake

Reports file counts and sizes for both raw/ and processed/ prefixes.
"""

import argparse
import logging

from google.cloud import storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _human(n_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n_bytes < 1024:
            return f"{n_bytes:.1f} {unit}"
        n_bytes //= 1024
    return f"{n_bytes:.1f} TB"


def verify(bucket_name: str) -> None:
    client = storage.Client()
    bucket = client.bucket(bucket_name)

    for prefix in ("raw/", "processed/"):
        blobs = list(bucket.list_blobs(prefix=prefix))
        total_bytes = sum(b.size for b in blobs if b.size)
        print(f"\ngs://{bucket_name}/{prefix}")
        print(f"  Files : {len(blobs)}")
        print(f"  Total : {_human(total_bytes)}")
        print()
        for b in sorted(blobs, key=lambda x: x.name):
            size_str = _human(b.size) if b.size else "—"
            print(f"  {b.name:<60} {size_str:>10}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify GCS data lake uploads")
    parser.add_argument(
        "--bucket",
        required=True,
        help="GCS bucket name (e.g. f1optimizer-data-lake)",
    )
    args = parser.parse_args()
    verify(args.bucket)


if __name__ == "__main__":
    main()
