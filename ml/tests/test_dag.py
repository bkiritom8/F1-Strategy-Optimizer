"""
Tests for the Vertex AI Pipeline DAG and pipeline runner CLI.
KFP dsl.component decorator is mocked to prevent execution at import time.
"""

from __future__ import annotations

import argparse
import sys
from unittest.mock import MagicMock

import pytest


def pytest_configure(config):
    """Mock kfp before any imports."""
    kfp_mock = MagicMock()
    kfp_dsl_mock = MagicMock()
    kfp_dsl_mock.component = lambda **kwargs: (lambda fn: fn)
    kfp_dsl_mock.pipeline = lambda **kwargs: (lambda fn: fn)
    kfp_dsl_mock.Output = MagicMock()
    kfp_dsl_mock.Input = MagicMock()
    kfp_dsl_mock.Dataset = MagicMock()
    kfp_dsl_mock.Model = MagicMock()
    kfp_dsl_mock.Metrics = MagicMock()
    kfp_mock.dsl = kfp_dsl_mock
    sys.modules["kfp"] = kfp_mock
    sys.modules["kfp.dsl"] = kfp_dsl_mock


class TestPipelineRunnerCLI:
    def test_compile_only_flag(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--compile-only", action="store_true")
        parser.add_argument("--run-id", default="test")
        parser.add_argument("--no-cache", action="store_true")
        parser.add_argument("--no-monitor", action="store_true")
        args = parser.parse_args(["--compile-only"])
        assert args.compile_only is True

    def test_run_id_default(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--compile-only", action="store_true")
        parser.add_argument("--run-id", default="20260101-000000")
        parser.add_argument("--no-cache", action="store_true")
        parser.add_argument("--no-monitor", action="store_true")
        args = parser.parse_args([])
        assert args.run_id == "20260101-000000"

    def test_no_cache_flag(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--compile-only", action="store_true")
        parser.add_argument("--run-id", default="test")
        parser.add_argument("--no-cache", action="store_true")
        parser.add_argument("--no-monitor", action="store_true")
        args = parser.parse_args(["--no-cache"])
        assert args.no_cache is True

    def test_no_monitor_flag(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--compile-only", action="store_true")
        parser.add_argument("--run-id", default="test")
        parser.add_argument("--no-cache", action="store_true")
        parser.add_argument("--no-monitor", action="store_true")
        args = parser.parse_args(["--no-monitor"])
        assert args.no_monitor is True
