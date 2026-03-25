"""
Data validation pipeline for F1 Strategy Optimizer
Implements schema validation, data quality checks, and error handling
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

from .schema_validator import (
    ValidationError,
    RaceDataSchema,
    DriverDataSchema,
    TelemetryDataSchema,
    validate_dataframe as _validate_dataframe,
)
from .quality_metrics import DataQualityLevel, check_data_quality as _check_data_quality
from .data_sanitizer import sanitize_data as _sanitize_data


class DataValidator:
    """Comprehensive data validation pipeline"""

    def __init__(self):
        self.validation_stats = {
            "total_records": 0,
            "valid_records": 0,
            "invalid_records": 0,
            "warnings": [],
        }

    def validate_dataframe(
        self,
        df: pd.DataFrame,
        schema_class: type[BaseModel],
        required_columns: Optional[List[str]] = None,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Validate DataFrame against Pydantic schema

        Returns:
            Tuple of (valid_df, validation_report)
        """
        valid_df, report = _validate_dataframe(df, schema_class, required_columns)
        self.validation_stats["total_records"] += report["total"]
        self.validation_stats["valid_records"] += report["valid"]
        self.validation_stats["invalid_records"] += report["invalid"]
        return valid_df, report

    def check_data_quality(
        self, df: pd.DataFrame, column_rules: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> Tuple[DataQualityLevel, Dict[str, Any]]:
        """
        Assess data quality based on various metrics

        Args:
            df: DataFrame to assess
            column_rules: Quality rules per column (e.g., max_nulls, valid_range)

        Returns:
            Tuple of (quality_level, quality_report)
        """
        return _check_data_quality(df, column_rules)

    def sanitize_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Sanitize data by removing/fixing common issues"""
        return _sanitize_data(df)

    def get_validation_summary(self) -> Dict[str, Any]:
        """Get cumulative validation statistics"""
        return {
            **self.validation_stats,
            "validation_rate": (
                self.validation_stats["valid_records"]
                / max(self.validation_stats["total_records"], 1)
            ),
        }


if __name__ == "__main__":
    # Example usage
    data_validator = DataValidator()

    # Sample race data
    race_data = pd.DataFrame(
        [
            {
                "race_id": 1,
                "year": 2024,
                "round": 1,
                "circuit_id": "bahrain",
                "name": "Bahrain Grand Prix",
                "date": "2024-03-02",
                "time": "15:00:00",
                "url": "http://example.com",
            }
        ]
    )

    # Validate
    valid_df, report = data_validator.validate_dataframe(race_data, RaceDataSchema)

    print(f"Validation report: {report}")

    # Check quality
    quality_level, quality_report = data_validator.check_data_quality(race_data)

    print(f"Quality level: {quality_level.value}")
    print(f"Quality score: {quality_report['overall_score']}")
