"""Unit tests for ml.monitoring — all GCS interactions mocked."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_df(n: int = 500, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "TyreLife": rng.integers(1, 40, n).astype(float),
            "fuel_load_pct": rng.uniform(0.4, 1.0, n),
            "mean_speed": rng.uniform(180, 320, n),
        }
    )


# ── feature_stats tests ───────────────────────────────────────────────────────

class TestExtractFeatureStats:
    def test_returns_all_features(self):
        from ml.monitoring.feature_stats import extract_feature_stats

        df = _make_df()
        stats = extract_feature_stats(df, ["TyreLife", "fuel_load_pct"])
        assert set(stats.keys()) == {"TyreLife", "fuel_load_pct"}

    def test_histogram_keys_present(self):
        from ml.monitoring.feature_stats import extract_feature_stats

        stats = extract_feature_stats(_make_df(), ["TyreLife"])
        s = stats["TyreLife"]
        assert "bin_edges" in s
        assert "expected_pcts" in s
        assert "n_bins" in s
        assert len(s["bin_edges"]) == s["n_bins"] + 1
        assert abs(sum(s["expected_pcts"]) - 1.0) < 1e-6

    def test_skips_non_numeric(self):
        from ml.monitoring.feature_stats import extract_feature_stats

        df = _make_df()
        df["cat_col"] = "A"
        # cat_col is not in the requested list, so no error
        stats = extract_feature_stats(df, ["TyreLife"])
        assert "TyreLife" in stats

    def test_handles_constant_column(self):
        from ml.monitoring.feature_stats import extract_feature_stats

        df = _make_df()
        df["constant"] = 5.0
        # Should not raise, should produce a degenerate histogram
        stats = extract_feature_stats(df, ["constant"])
        assert "constant" in stats


class TestSaveLoadFeatureStats:
    def test_roundtrip_via_mock_gcs(self):
        from ml.monitoring.feature_stats import extract_feature_stats, save_to_gcs, load_from_gcs

        df = _make_df()
        stats = extract_feature_stats(df, ["TyreLife", "fuel_load_pct"])

        stored: dict = {}

        def fake_upload(data, content_type=None):
            stored["data"] = data

        mock_blob = MagicMock()
        mock_blob.upload_from_string.side_effect = fake_upload
        mock_blob.download_as_text.side_effect = lambda: stored["data"]

        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        with patch("ml.monitoring.feature_stats.storage.Client", return_value=mock_client):
            save_to_gcs(stats, "tire_degradation")
            loaded = load_from_gcs("tire_degradation")

        assert loaded is not None
        assert set(loaded.keys()) == set(stats.keys())
        assert loaded["TyreLife"]["n_bins"] == stats["TyreLife"]["n_bins"]

    def test_load_returns_none_on_missing(self):
        from ml.monitoring.feature_stats import load_from_gcs

        mock_blob = MagicMock()
        mock_blob.download_as_text.side_effect = Exception("not found")
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        with patch("ml.monitoring.feature_stats.storage.Client", return_value=mock_client):
            result = load_from_gcs("nonexistent_model")

        assert result is None


# ── drift_detector tests ──────────────────────────────────────────────────────

class TestComputePsi:
    def test_identical_distribution_near_zero(self):
        from ml.monitoring.feature_stats import extract_feature_stats
        from ml.monitoring.drift_detector import compute_psi

        df = _make_df(n=1000)
        stats = extract_feature_stats(df, ["TyreLife"])
        psi = compute_psi(stats["TyreLife"], df["TyreLife"])
        assert psi < 0.05  # same data → near-zero PSI

    def test_very_different_distribution_high_psi(self):
        from ml.monitoring.feature_stats import extract_feature_stats
        from ml.monitoring.drift_detector import compute_psi

        rng = np.random.default_rng(0)
        train_df = pd.DataFrame({"TyreLife": rng.integers(1, 10, 500).astype(float)})
        prod_series = pd.Series(rng.integers(30, 40, 500).astype(float))
        stats = extract_feature_stats(train_df, ["TyreLife"])
        psi = compute_psi(stats["TyreLife"], prod_series)
        assert psi > 0.25  # completely different range → critical drift

    def test_psi_non_negative(self):
        from ml.monitoring.feature_stats import extract_feature_stats
        from ml.monitoring.drift_detector import compute_psi

        df = _make_df()
        stats = extract_feature_stats(df, ["mean_speed"])
        psi = compute_psi(stats["mean_speed"], df["mean_speed"] * 1.05)
        assert psi >= 0


class TestDriftDetector:
    def _make_stats(self):
        from ml.monitoring.feature_stats import extract_feature_stats
        df = _make_df(n=1000)
        return extract_feature_stats(df, ["TyreLife", "fuel_load_pct", "mean_speed"])

    def test_detect_returns_report(self):
        from ml.monitoring.drift_detector import DriftDetector

        stats = self._make_stats()
        detector = DriftDetector(baseline_stats=stats)
        report = detector.detect(_make_df(n=200), race_id="2025_1", model_name="tire_degradation")
        assert report.model_name == "tire_degradation"
        assert report.race_id == "2025_1"
        assert set(report.feature_psi.keys()) == {"TyreLife", "fuel_load_pct", "mean_speed"}
        assert report.overall_status in ("ok", "warn", "critical")

    def test_stable_data_ok_status(self):
        from ml.monitoring.drift_detector import DriftDetector

        rng = np.random.default_rng(99)
        df_train = pd.DataFrame({"TyreLife": rng.integers(1, 40, 1000).astype(float)})
        df_prod  = pd.DataFrame({"TyreLife": rng.integers(1, 40, 200).astype(float)})

        from ml.monitoring.feature_stats import extract_feature_stats
        stats = extract_feature_stats(df_train, ["TyreLife"])
        detector = DriftDetector(baseline_stats=stats)
        report = detector.detect(df_prod, race_id="2025_1", model_name="tire_degradation")
        assert report.overall_status == "ok"

    def test_drifted_data_non_ok_status(self):
        from ml.monitoring.drift_detector import DriftDetector
        from ml.monitoring.feature_stats import extract_feature_stats

        rng = np.random.default_rng(0)
        df_train = pd.DataFrame({"TyreLife": rng.integers(1, 5, 1000).astype(float)})
        df_prod  = pd.DataFrame({"TyreLife": rng.integers(35, 40, 200).astype(float)})
        stats = extract_feature_stats(df_train, ["TyreLife"])
        detector = DriftDetector(baseline_stats=stats)
        report = detector.detect(df_prod, race_id="2025_1", model_name="tire_degradation")
        assert report.overall_status != "ok"

    def test_missing_column_skipped(self):
        from ml.monitoring.drift_detector import DriftDetector

        stats = self._make_stats()
        detector = DriftDetector(baseline_stats=stats)
        df = _make_df()
        df = df.drop(columns=["mean_speed"])
        # Should not raise — missing column is skipped
        report = detector.detect(df, race_id="2025_1", model_name="tire_degradation")
        assert "mean_speed" not in report.feature_psi
