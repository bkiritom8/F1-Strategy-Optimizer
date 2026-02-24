"""
Data validation pipeline for F1 Strategy Optimizer
Implements schema validation, data quality checks, and error handling
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import numpy as np
from pydantic import BaseModel, Field, validator
from enum import Enum

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Custom validation error"""

    pass


class DataQualityLevel(str, Enum):
    """Data quality assessment levels"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INVALID = "invalid"


class RaceDataSchema(BaseModel):
    """Schema for race data validation"""

    race_id: int = Field(..., gt=0)
    year: int = Field(..., ge=1950, le=2024)
    round: int = Field(..., ge=1, le=25)
    circuit_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    date: str  # ISO format
    time: Optional[str] = None
    url: Optional[str] = None

    @validator("date")
    def validate_date(cls, v):
        """Validate date format"""
        try:
            datetime.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError("Invalid date format, expected ISO format")


class DriverDataSchema(BaseModel):
    """Schema for driver data validation"""

    driver_id: str = Field(..., min_length=1)
    driver_number: Optional[int] = Field(None, ge=1, le=99)
    code: Optional[str] = Field(None, min_length=3, max_length=3)
    forename: str = Field(..., min_length=1)
    surname: str = Field(..., min_length=1)
    dob: str
    nationality: str
    url: Optional[str] = None

    @validator("dob")
    def validate_dob(cls, v):
        """Validate date of birth"""
        try:
            dob = datetime.fromisoformat(v)
            if dob.year < 1900 or dob.year > datetime.now().year - 16:
                raise ValueError("Invalid birth year")
            return v
        except ValueError as e:
            raise ValueError(f"Invalid date of birth: {e}")


class TelemetryDataSchema(BaseModel):
    """Schema for telemetry data validation"""

    race_id: str
    driver_id: str
    lap: int = Field(..., ge=1)
    timestamp: str
    speed: float = Field(..., ge=0, le=400)  # km/h
    throttle: float = Field(..., ge=0, le=1)
    brake: bool
    gear: int = Field(..., ge=-1, le=8)  # -1 = reverse, 0 = neutral
    rpm: int = Field(..., ge=0, le=20000)


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
        logger.info(f"Validating {len(df)} records against {schema_class.__name__}")

        # Check required columns
        if required_columns:
            missing_cols = set(required_columns) - set(df.columns)
            if missing_cols:
                raise ValidationError(f"Missing required columns: {missing_cols}")

        valid_records = []
        invalid_records = []
        errors = []

        # Validate each record
        for idx, row in df.iterrows():
            try:
                # Convert to dict and validate with Pydantic
                record_dict = row.to_dict()
                validated = schema_class(**record_dict)
                valid_records.append(validated.dict())

            except Exception as e:
                invalid_records.append(
                    {"index": idx, "record": row.to_dict(), "error": str(e)}
                )
                errors.append(str(e))

        # Create validated DataFrame
        valid_df = pd.DataFrame(valid_records) if valid_records else pd.DataFrame()

        # Update stats
        self.validation_stats["total_records"] += len(df)
        self.validation_stats["valid_records"] += len(valid_records)
        self.validation_stats["invalid_records"] += len(invalid_records)

        validation_report = {
            "total": len(df),
            "valid": len(valid_records),
            "invalid": len(invalid_records),
            "validation_rate": len(valid_records) / len(df) if len(df) > 0 else 0,
            "errors": errors[:10],  # First 10 errors
            "invalid_records": invalid_records[:10],  # First 10 invalid records
        }

        logger.info(
            f"Validation complete: {len(valid_records)}/{len(df)} valid "
            f"({validation_report['validation_rate']*100:.2f}%)"
        )

        return valid_df, validation_report

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
        logger.info(f"Assessing data quality for {len(df)} records")

        quality_metrics: Dict[str, Dict[str, Any]] = {
            "completeness": {},
            "validity": {},
            "consistency": {},
            "accuracy": {},
        }

        # Completeness: Check missing values
        for col in df.columns:
            null_pct = df[col].isnull().sum() / len(df) * 100
            quality_metrics["completeness"][col] = {
                "null_count": int(df[col].isnull().sum()),
                "null_percentage": round(null_pct, 2),
            }

        # Validity: Check data ranges
        if column_rules:
            for col, rules in column_rules.items():
                if col not in df.columns:
                    continue

                if "valid_range" in rules:
                    min_val, max_val = rules["valid_range"]
                    out_of_range = df[(df[col] < min_val) | (df[col] > max_val)].shape[
                        0
                    ]
                    quality_metrics["validity"][col] = {
                        "out_of_range_count": out_of_range,
                        "out_of_range_percentage": round(
                            out_of_range / len(df) * 100, 2
                        ),
                    }

        # Consistency: Check duplicates
        duplicate_count = df.duplicated().sum()
        quality_metrics["consistency"]["duplicates"] = {
            "count": int(duplicate_count),
            "percentage": round(duplicate_count / len(df) * 100, 2),
        }

        # Calculate overall quality score (0-100)
        completeness_score = 100 - sum(
            m["null_percentage"] for m in quality_metrics["completeness"].values()
        ) / max(len(df.columns), 1)

        validity_score = 100
        if quality_metrics["validity"]:
            validity_score = 100 - sum(
                m["out_of_range_percentage"]
                for m in quality_metrics["validity"].values()
            ) / max(len(quality_metrics["validity"]), 1)

        consistency_score = (
            100 - quality_metrics["consistency"]["duplicates"]["percentage"]
        )

        overall_score = (completeness_score + validity_score + consistency_score) / 3

        # Determine quality level
        if overall_score >= 90:
            quality_level = DataQualityLevel.HIGH
        elif overall_score >= 70:
            quality_level = DataQualityLevel.MEDIUM
        elif overall_score >= 50:
            quality_level = DataQualityLevel.LOW
        else:
            quality_level = DataQualityLevel.INVALID

        quality_report = {
            "overall_score": round(overall_score, 2),
            "quality_level": quality_level.value,
            "metrics": quality_metrics,
            "scores": {
                "completeness": round(completeness_score, 2),
                "validity": round(validity_score, 2),
                "consistency": round(consistency_score, 2),
            },
        }

        logger.info(
            f"Data quality: {quality_level.value.upper()} "
            f"(score: {overall_score:.2f})"
        )

        return quality_level, quality_report

    def sanitize_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Sanitize data by removing/fixing common issues"""
        logger.info("Sanitizing data...")

        df_clean = df.copy()

        # Remove fully null rows
        df_clean = df_clean.dropna(how="all")

        # Strip whitespace from string columns
        string_cols = df_clean.select_dtypes(include=["object"]).columns
        for col in string_cols:
            df_clean[col] = df_clean[col].str.strip()

        # Replace empty strings with NaN
        df_clean = df_clean.replace(r"^\s*$", np.nan, regex=True)

        # Remove exact duplicates
        original_count = len(df_clean)
        df_clean = df_clean.drop_duplicates()
        duplicates_removed = original_count - len(df_clean)

        logger.info(f"Sanitization complete: removed {duplicates_removed} duplicates")

        return df_clean

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
