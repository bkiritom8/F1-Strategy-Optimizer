"""F1 data ingestion modules — Jolpica (Ergast) and FastF1."""

from .ergast_ingestion import ErgastIngestion
from .fastf1_ingestion import FastF1Ingestion

__all__ = ["ErgastIngestion", "FastF1Ingestion"]
