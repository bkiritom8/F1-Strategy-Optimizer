import json
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from pipeline.scripts.build_car_performance import compute_offsets, normalise_to_ms

def test_compute_offsets_returns_constructor_year_dict():
    df = pd.DataFrame({
        "constructorId": ["mclaren", "mclaren", "red_bull", "red_bull"],
        "year": [2024, 2024, 2024, 2024],
        "positionOrder": [1, 3, 2, 4],
    })
    result = compute_offsets(df)
    assert "mclaren" in result
    assert "red_bull" in result
    assert "2024" in result["mclaren"]
    assert isinstance(result["mclaren"]["2024"], float)

def test_normalise_to_ms_faster_team_negative():
    # mclaren avg finish 2.0, field median 10.0 → should be negative (faster)
    offsets_pos = {"mclaren": {"2024": -8.0}}  # delta already negative
    result = normalise_to_ms(offsets_pos, avg_lap_time_s=90.0)
    assert result["mclaren"]["2024"] < 0
