"""data_sanitizer.py — Deduplication, whitespace stripping, null handling."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def sanitize_data(df: pd.DataFrame) -> pd.DataFrame:
    logger.info("Sanitizing data...")
    df_clean = df.copy()
    df_clean = df_clean.dropna(how="all")
    for col in df_clean.select_dtypes(include=["object"]).columns:
        df_clean[col] = df_clean[col].str.strip()
    df_clean = df_clean.replace(r"^\s*$", np.nan, regex=True)
    original_count = len(df_clean)
    df_clean = df_clean.drop_duplicates()
    logger.info("Sanitization complete: removed %d duplicates", original_count - len(df_clean))
    return df_clean
