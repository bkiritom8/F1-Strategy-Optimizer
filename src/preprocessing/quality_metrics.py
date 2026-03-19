"""quality_metrics.py — Completeness, validity, consistency scoring."""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


class DataQualityLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INVALID = "invalid"


def check_data_quality(
    df: pd.DataFrame,
    column_rules: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[DataQualityLevel, Dict[str, Any]]:
    logger.info("Assessing data quality for %d records", len(df))
    metrics: Dict[str, Dict[str, Any]] = {
        "completeness": {}, "validity": {}, "consistency": {}, "accuracy": {},
    }

    for col in df.columns:
        null_pct = df[col].isnull().sum() / len(df) * 100
        metrics["completeness"][col] = {
            "null_count": int(df[col].isnull().sum()),
            "null_percentage": round(null_pct, 2),
        }

    if column_rules:
        for col, rules in column_rules.items():
            if col not in df.columns:
                continue
            if "valid_range" in rules:
                min_val, max_val = rules["valid_range"]
                out_of_range = df[(df[col] < min_val) | (df[col] > max_val)].shape[0]
                metrics["validity"][col] = {
                    "out_of_range_count": out_of_range,
                    "out_of_range_percentage": round(out_of_range / len(df) * 100, 2),
                }

    dup_count = df.duplicated().sum()
    metrics["consistency"]["duplicates"] = {
        "count": int(dup_count),
        "percentage": round(dup_count / len(df) * 100, 2),
    }

    completeness_score = 100 - sum(
        m["null_percentage"] for m in metrics["completeness"].values()
    ) / max(len(df.columns), 1)
    validity_score = 100
    if metrics["validity"]:
        validity_score = 100 - sum(
            m["out_of_range_percentage"] for m in metrics["validity"].values()
        ) / max(len(metrics["validity"]), 1)
    consistency_score = 100 - metrics["consistency"]["duplicates"]["percentage"]
    overall = (completeness_score + validity_score + consistency_score) / 3

    if overall >= 90:
        level = DataQualityLevel.HIGH
    elif overall >= 70:
        level = DataQualityLevel.MEDIUM
    elif overall >= 50:
        level = DataQualityLevel.LOW
    else:
        level = DataQualityLevel.INVALID

    report = {
        "overall_score": round(overall, 2),
        "quality_level": level.value,
        "metrics": metrics,
        "scores": {
            "completeness": round(completeness_score, 2),
            "validity": round(validity_score, 2),
            "consistency": round(consistency_score, 2),
        },
    }
    logger.info("Data quality: %s (score: %.2f)", level.value.upper(), overall)
    return level, report
