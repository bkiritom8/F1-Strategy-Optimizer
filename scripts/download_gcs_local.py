"""
Download all GCS artifacts needed for local RL training and simulation.

Run from repo root:
    python scripts/download_gcs_local.py
"""
from __future__ import annotations

import os
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

from pathlib import Path
from google.cloud import storage

PROJECT = "f1optimizer"
REPO_ROOT = Path(__file__).parent.parent

# ── Destination dirs ──────────────────────────────────────────────────────────
MODELS_DIR = REPO_ROOT / "models"
RL_STRATEGY_DIR = MODELS_DIR / "rl_strategy"
TRAINING_CACHE_DIR = Path(os.environ.get("F1_LOCAL_CACHE", "/tmp/f1_cache"))
ML_FEATURES_DIR = REPO_ROOT / "data" / "ml_features"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

for d in [MODELS_DIR, RL_STRATEGY_DIR, TRAINING_CACHE_DIR, ML_FEATURES_DIR, PROCESSED_DIR]:
    d.mkdir(parents=True, exist_ok=True)

client = storage.Client(project=PROJECT)

def download(bucket_name: str, blob_path: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        print(f"  SKIP  {dest.relative_to(REPO_ROOT) if dest.is_relative_to(REPO_ROOT) else dest}")
        return
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.download_to_filename(str(dest))
    print(f"  OK    {dest.relative_to(REPO_ROOT) if dest.is_relative_to(REPO_ROOT) else dest}")

def download_prefix(bucket_name: str, prefix: str, dest_dir: Path) -> None:
    bucket = client.bucket(bucket_name)
    blobs = list(bucket.list_blobs(prefix=prefix))
    for blob in blobs:
        rel = blob.name[len(prefix):]
        if not rel or rel.endswith("/"):
            continue
        dest = dest_dir / rel
        download(bucket_name, blob.name, dest)


# ── 1. ML model PKLs (flat layout expected by load_local_adapters) ────────────
print("\n[1/5] ML model PKLs → models/")
for local_name, gcs_blob in {
    "tire_degradation.pkl": "tire_degradation/model.pkl",
    "driving_style.pkl":    "driving_style/model.pkl",
    "safety_car.pkl":       "safety_car/model.pkl",
    "pit_window.pkl":       "pit_window/model.pkl",
    "race_outcome.pkl":     "race_outcome/model.pkl",
    "overtake_prob.pkl":    "overtake_prob/model.pkl",
}.items():
    download("f1optimizer-models", gcs_blob, MODELS_DIR / local_name)

# Extra tire_degradation native format files (used by some training paths)
download("f1optimizer-models", "tire_degradation/lgb_model.txt",  MODELS_DIR / "tire_degradation_native" / "lgb_model.txt")
download("f1optimizer-models", "tire_degradation/xgb_model.json", MODELS_DIR / "tire_degradation_native" / "xgb_model.json")
download("f1optimizer-models", "tire_degradation/config.json",    MODELS_DIR / "tire_degradation_native" / "config.json")

download("f1optimizer-models", "champion_metrics.json", MODELS_DIR / "champion_metrics.json")

# ── 2. RL strategy checkpoints ────────────────────────────────────────────────
print("\n[2/5] RL strategy checkpoints → models/rl_strategy/")
for version in ("v2", "v3"):
    for fname in ("policy.zip", "vec_normalize.pkl"):
        download("f1optimizer-models", f"rl_strategy/{version}/{fname}", RL_STRATEGY_DIR / version / fname)

# ── 3. RL training cache (race parquet files) ─────────────────────────────────
print(f"\n[3/5] RL training cache → {TRAINING_CACHE_DIR}")
download_prefix("f1optimizer-training", "cache/", TRAINING_CACHE_DIR)

# ── 4. ML features ────────────────────────────────────────────────────────────
print(f"\n[4/5] ML features → data/ml_features/")
download_prefix("f1optimizer-data-lake", "ml_features/", ML_FEATURES_DIR)

# ── 5. Processed data ─────────────────────────────────────────────────────────
print(f"\n[5/5] Processed data → data/processed/")
download_prefix("f1optimizer-data-lake", "processed/", PROCESSED_DIR)

print("\nAll done.")
