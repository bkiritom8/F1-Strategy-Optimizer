"""telemetry_extractor.py — FastF1 per-lap telemetry extraction."""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

log = logging.getLogger(__name__)


def extract_telemetry(session) -> Optional[pd.DataFrame]:
    """
    Iterate every lap, call get_telemetry(), concatenate.
    Prepends Driver and LapNumber; all other columns are raw FastF1 output.
    """
    frames = []
    for _, lap in session.laps.iterlaps():
        try:
            tel = lap.get_telemetry()
            if tel is None or tel.empty:
                continue
            tel.insert(0, "LapNumber", lap["LapNumber"])
            tel.insert(0, "Driver", lap["Driver"])
            frames.append(tel)
        except Exception as exc:
            log.debug(
                "skipped lap %s/%s: %s",
                lap.get("Driver"), lap.get("LapNumber"), exc,
            )
    return pd.concat(frames, ignore_index=True) if frames else None
