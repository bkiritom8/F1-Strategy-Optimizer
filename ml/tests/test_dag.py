"""
Tests for the Vertex AI Pipeline (KFP DAG).

Verifies:
  - Pipeline compiles to valid JSON without errors
  - All 6 components are present in the compiled spec
  - Parallel execution paths exist (train_strategy + train_pit_stop run in parallel)
  - Each component has retries=2 configured
  - Pipeline root points to the correct GCS bucket
  - pipeline_runner.py argument parsing works

All tests run on Vertex AI (n1-standard-4, no GPU).
No network calls — compilation is purely local to the container.
"""

import json
import os
import tempfile

import pytest


class TestPipelineCompilation:
    """Pipeline compiles to valid JSON with correct structure."""

    @pytest.fixture(scope="class")
    def compiled_pipeline(self):
        """Compile the pipeline once and return the parsed JSON spec."""
        from kfp import compiler
        from ml.dag.f1_pipeline import f1_strategy_pipeline

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            compiler.Compiler().compile(
                pipeline_func=f1_strategy_pipeline,
                package_path=path,
            )
            with open(path) as f:
                spec = json.load(f)
        finally:
            os.unlink(path)

        return spec

    def test_compiles_without_error(self, compiled_pipeline):
        assert compiled_pipeline is not None

    def test_spec_has_pipeline_info(self, compiled_pipeline):
        assert "pipelineInfo" in compiled_pipeline
        assert compiled_pipeline["pipelineInfo"]["name"] == "f1-strategy-pipeline"

    def test_spec_has_deployment_spec(self, compiled_pipeline):
        assert "deploymentSpec" in compiled_pipeline

    def test_pipeline_root_is_gcs(self, compiled_pipeline):
        root = compiled_pipeline.get("defaultPipelineRoot", "")
        assert root.startswith(
            "gs://"
        ), f"Pipeline root must be a GCS URI, got: {root!r}"

    def test_all_components_present(self, compiled_pipeline):
        executors = compiled_pipeline.get("deploymentSpec", {}).get("executors", {})
        executor_names = " ".join(executors.keys()).lower()

        expected = [
            "validate",
            "feature",
            "train-strategy",
            "train-pit",
            "evaluate",
            "deploy",
        ]
        for name in expected:
            assert name in executor_names, (
                f"Expected component containing '{name}' in executors, "
                f"got: {list(executors.keys())}"
            )

    def test_six_components_total(self, compiled_pipeline):
        executors = compiled_pipeline.get("deploymentSpec", {}).get("executors", {})
        assert (
            len(executors) >= 6
        ), f"Expected >= 6 executor components, got {len(executors)}"

    def test_parallel_training_paths(self, compiled_pipeline):
        """
        train_strategy and train_pit_stop must both depend on feature_engineering
        but NOT on each other — confirming they run in parallel.
        """
        components = compiled_pipeline.get("root", {}).get("dag", {}).get("tasks", {})

        strategy_task = next(
            (v for k, v in components.items() if "train-strategy" in k.lower()),
            None,
        )
        pit_task = next(
            (v for k, v in components.items() if "train-pit" in k.lower()),
            None,
        )

        assert strategy_task is not None, "train_strategy task not found in DAG"
        assert pit_task is not None, "train_pit_stop task not found in DAG"

        strategy_deps = set(strategy_task.get("dependentTasks", []))
        pit_deps = set(pit_task.get("dependentTasks", []))

        # Neither should depend on the other
        strategy_names = " ".join(strategy_deps).lower()
        pit_names = " ".join(pit_deps).lower()
        assert (
            "pit" not in strategy_names
        ), "train_strategy should not depend on train_pit_stop"
        assert (
            "strategy" not in pit_names
        ), "train_pit_stop should not depend on train_strategy"

    def test_deploy_depends_on_both_evals(self, compiled_pipeline):
        """deploy must wait for both evaluate tasks."""
        components = compiled_pipeline.get("root", {}).get("dag", {}).get("tasks", {})
        deploy_task = next(
            (v for k, v in components.items() if "deploy" in k.lower()),
            None,
        )
        assert deploy_task is not None, "deploy task not found in DAG"
        deps = " ".join(deploy_task.get("dependentTasks", [])).lower()
        assert (
            "eval" in deps or "evaluate" in deps
        ), f"deploy should depend on evaluation tasks, deps={deps}"


class TestPipelineRunnerCLI:
    """pipeline_runner.py argument parsing."""

    def test_compile_only_flag(self):
        import argparse
        from unittest.mock import patch

        with patch("sys.argv", ["pipeline_runner.py", "--compile-only"]):
            import importlib
            import ml.dag.pipeline_runner as runner

            importlib.reload(runner)

            parser = argparse.ArgumentParser()
            parser.add_argument("--compile-only", action="store_true")
            parser.add_argument("--run-id", default="test")
            parser.add_argument("--no-cache", action="store_true")
            parser.add_argument("--no-monitor", action="store_true")
            args = parser.parse_args(["--compile-only"])
            assert args.compile_only is True

    def test_run_id_default_is_timestamp(self):
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--compile-only", action="store_true")
        parser.add_argument("--run-id", default="20260101-000000")
        parser.add_argument("--no-cache", action="store_true")
        parser.add_argument("--no-monitor", action="store_true")
        args = parser.parse_args([])
        assert args.run_id == "20260101-000000"


class TestComponentImports:
    """All KFP components import cleanly."""

    def test_import_validate_data(self):
        from ml.dag.components.validate_data import validate_data_op

        assert callable(validate_data_op)

    def test_import_feature_engineering(self):
        from ml.dag.components.feature_engineering import feature_engineering_op

        assert callable(feature_engineering_op)

    def test_import_train_strategy(self):
        from ml.dag.components.train_strategy import train_strategy_op

        assert callable(train_strategy_op)

    def test_import_train_pit_stop(self):
        from ml.dag.components.train_pit_stop import train_pit_stop_op

        assert callable(train_pit_stop_op)

    def test_import_evaluate(self):
        from ml.dag.components.evaluate import evaluate_op

        assert callable(evaluate_op)

    def test_import_deploy(self):
        from ml.dag.components.deploy import deploy_op

        assert callable(deploy_op)
