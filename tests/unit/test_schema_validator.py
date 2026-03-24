"""Tests for src/preprocessing/schema_validator.py"""
import pandas as pd
import pytest

from src.preprocessing.schema_validator import (
    RaceDataSchema,
    DriverDataSchema,
    TelemetryDataSchema,
    ValidationError,
    validate_dataframe,
)


def _race_row(**overrides):
    base = {
        "race_id": 1,
        "year": 2024,
        "round": 1,
        "circuit_id": "bahrain",
        "name": "Bahrain Grand Prix",
        "date": "2024-03-02",
    }
    base.update(overrides)
    return base


def _driver_row(**overrides):
    base = {
        "driver_id": "max_verstappen",
        "forename": "Max",
        "surname": "Verstappen",
        "dob": "1997-09-30",
        "nationality": "Dutch",
    }
    base.update(overrides)
    return base


def _telemetry_row(**overrides):
    base = {
        "race_id": "2024_1",
        "driver_id": "max_verstappen",
        "lap": 1,
        "timestamp": "2024-03-02T15:01:00",
        "speed": 280.0,
        "throttle": 0.9,
        "brake": False,
        "gear": 6,
        "rpm": 11000,
    }
    base.update(overrides)
    return base


class TestRaceDataSchema:
    def test_valid_record(self):
        schema = RaceDataSchema(**_race_row())
        assert schema.race_id == 1
        assert schema.year == 2024

    def test_invalid_race_id_zero(self):
        with pytest.raises(Exception):
            RaceDataSchema(**_race_row(race_id=0))

    def test_invalid_year_too_early(self):
        with pytest.raises(Exception):
            RaceDataSchema(**_race_row(year=1949))

    def test_invalid_year_future(self):
        with pytest.raises(Exception):
            RaceDataSchema(**_race_row(year=2025))

    def test_invalid_round_zero(self):
        with pytest.raises(Exception):
            RaceDataSchema(**_race_row(round=0))

    def test_invalid_round_too_high(self):
        with pytest.raises(Exception):
            RaceDataSchema(**_race_row(round=26))

    def test_invalid_date_format(self):
        with pytest.raises(Exception):
            RaceDataSchema(**_race_row(date="02-03-2024"))

    def test_optional_fields_default_none(self):
        schema = RaceDataSchema(**_race_row())
        assert schema.time is None
        assert schema.url is None


class TestDriverDataSchema:
    def test_valid_record(self):
        schema = DriverDataSchema(**_driver_row())
        assert schema.driver_id == "max_verstappen"

    def test_invalid_dob_too_old(self):
        with pytest.raises(Exception):
            DriverDataSchema(**_driver_row(dob="1890-01-01"))

    def test_invalid_dob_too_young(self):
        with pytest.raises(Exception):
            DriverDataSchema(**_driver_row(dob="2015-01-01"))

    def test_invalid_dob_format(self):
        with pytest.raises(Exception):
            DriverDataSchema(**_driver_row(dob="30-09-1997"))

    def test_code_must_be_3_chars(self):
        with pytest.raises(Exception):
            DriverDataSchema(**_driver_row(code="VE"))

    def test_valid_code(self):
        schema = DriverDataSchema(**_driver_row(code="VER"))
        assert schema.code == "VER"

    def test_driver_number_range(self):
        with pytest.raises(Exception):
            DriverDataSchema(**_driver_row(driver_number=0))
        with pytest.raises(Exception):
            DriverDataSchema(**_driver_row(driver_number=100))


class TestTelemetryDataSchema:
    def test_valid_record(self):
        schema = TelemetryDataSchema(**_telemetry_row())
        assert schema.speed == 280.0

    def test_invalid_speed_negative(self):
        with pytest.raises(Exception):
            TelemetryDataSchema(**_telemetry_row(speed=-1.0))

    def test_invalid_speed_too_high(self):
        with pytest.raises(Exception):
            TelemetryDataSchema(**_telemetry_row(speed=401.0))

    def test_invalid_throttle_out_of_range(self):
        with pytest.raises(Exception):
            TelemetryDataSchema(**_telemetry_row(throttle=1.1))

    def test_invalid_gear(self):
        with pytest.raises(Exception):
            TelemetryDataSchema(**_telemetry_row(gear=9))

    def test_invalid_rpm_negative(self):
        with pytest.raises(Exception):
            TelemetryDataSchema(**_telemetry_row(rpm=-1))

    def test_invalid_lap_zero(self):
        with pytest.raises(Exception):
            TelemetryDataSchema(**_telemetry_row(lap=0))


class TestValidateDataframe:
    def test_all_valid_records(self):
        df = pd.DataFrame([_race_row(), _race_row(race_id=2, round=2)])
        valid_df, report = validate_dataframe(df, RaceDataSchema)
        assert report["valid"] == 2
        assert report["invalid"] == 0
        assert report["validation_rate"] == 1.0

    def test_some_invalid_records(self):
        df = pd.DataFrame([_race_row(), _race_row(race_id=0)])
        valid_df, report = validate_dataframe(df, RaceDataSchema)
        assert report["valid"] == 1
        assert report["invalid"] == 1

    def test_all_invalid_returns_empty_df(self):
        df = pd.DataFrame([_race_row(race_id=0), _race_row(year=1900)])
        valid_df, report = validate_dataframe(df, RaceDataSchema)
        assert valid_df.empty
        assert report["valid"] == 0

    def test_report_keys_present(self):
        df = pd.DataFrame([_race_row()])
        _, report = validate_dataframe(df, RaceDataSchema)
        for key in ("total", "valid", "invalid", "validation_rate", "errors", "invalid_records"):
            assert key in report

    def test_missing_required_column_raises(self):
        df = pd.DataFrame([{"race_id": 1, "year": 2024}])
        with pytest.raises(ValidationError):
            validate_dataframe(df, RaceDataSchema, required_columns=["circuit_id"])

    def test_empty_dataframe_returns_zero_validation_rate(self):
        df = pd.DataFrame(columns=["race_id", "year", "round", "circuit_id", "name", "date"])
        valid_df, report = validate_dataframe(df, RaceDataSchema)
        assert report["validation_rate"] == 0

    def test_errors_capped_at_ten(self):
        rows = [_race_row(race_id=0)] * 15
        df = pd.DataFrame(rows)
        _, report = validate_dataframe(df, RaceDataSchema)
        assert len(report["errors"]) <= 10
        assert len(report["invalid_records"]) <= 10
