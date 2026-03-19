"""schema_validator.py — Pydantic schema definitions and per-record validation."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    pass


class RaceDataSchema(BaseModel):
    race_id: int = Field(..., gt=0)
    year: int = Field(..., ge=1950, le=2024)
    round: int = Field(..., ge=1, le=25)
    circuit_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    date: str
    time: Optional[str] = None
    url: Optional[str] = None

    @validator("date")
    def validate_date(cls, v):
        try:
            datetime.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError("Invalid date format, expected ISO format")


class DriverDataSchema(BaseModel):
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
        try:
            dob = datetime.fromisoformat(v)
            if dob.year < 1900 or dob.year > datetime.now().year - 16:
                raise ValueError("Invalid birth year")
            return v
        except ValueError as e:
            raise ValueError(f"Invalid date of birth: {e}")


class TelemetryDataSchema(BaseModel):
    race_id: str
    driver_id: str
    lap: int = Field(..., ge=1)
    timestamp: str
    speed: float = Field(..., ge=0, le=400)
    throttle: float = Field(..., ge=0, le=1)
    brake: bool
    gear: int = Field(..., ge=-1, le=8)
    rpm: int = Field(..., ge=0, le=20000)


def validate_dataframe(
    df: pd.DataFrame,
    schema_class: type[BaseModel],
    required_columns: Optional[List[str]] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    logger.info("Validating %d records against %s", len(df), schema_class.__name__)
    if required_columns:
        missing_cols = set(required_columns) - set(df.columns)
        if missing_cols:
            raise ValidationError(f"Missing required columns: {missing_cols}")

    valid_records, invalid_records, errors = [], [], []
    for idx, row in df.iterrows():
        try:
            validated = schema_class(**row.to_dict())
            valid_records.append(validated.dict())
        except Exception as e:
            invalid_records.append({"index": idx, "record": row.to_dict(), "error": str(e)})
            errors.append(str(e))

    valid_df = pd.DataFrame(valid_records) if valid_records else pd.DataFrame()
    report = {
        "total": len(df),
        "valid": len(valid_records),
        "invalid": len(invalid_records),
        "validation_rate": len(valid_records) / len(df) if len(df) > 0 else 0,
        "errors": errors[:10],
        "invalid_records": invalid_records[:10],
    }
    logger.info("Validation complete: %d/%d valid (%.2f%%)", len(valid_records), len(df), report["validation_rate"] * 100)
    return valid_df, report
