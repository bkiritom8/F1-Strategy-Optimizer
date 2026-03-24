"""
Tests for distributed training infrastructure.
DataSharding._fetch_all_race_ids mocked to avoid Cloud SQL.
Connector import is mocked at module level to avoid install requirement.
"""
from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

# mock google.cloud.sql before any import touches it
sys.modules.setdefault("google.cloud.sql", MagicMock())
sys.modules.setdefault("google.cloud.sql.connector", MagicMock())
sys.modules["google.cloud.sql.connector"].Connector = MagicMock

# mock tensorflow before any import touches it
sys.modules.setdefault("tensorflow", MagicMock())
sys.modules.setdefault("tensorflow.distribute", MagicMock())

# mock google cloud modules not available in CI
sys.modules.setdefault("google", MagicMock())
sys.modules.setdefault("google.cloud", MagicMock())
sys.modules.setdefault("google.cloud.storage", MagicMock())
sys.modules.setdefault("google.cloud.pubsub_v1", MagicMock())
sys.modules.setdefault("google.cloud.aiplatform", MagicMock())

class TestClusterConfig:
    def test_all_configs_importable(self):
        from ml.distributed.cluster_config import (
            SINGLE_NODE_MULTI_GPU, MULTI_NODE_DATA_PARALLEL,
            HYPERPARAMETER_SEARCH, CPU_DISTRIBUTED,
        )
        for cfg in (SINGLE_NODE_MULTI_GPU, MULTI_NODE_DATA_PARALLEL,
                    HYPERPARAMETER_SEARCH, CPU_DISTRIBUTED):
            assert cfg.name
            assert cfg.machine_type
            assert cfg.replica_count >= 1

    def test_worker_pool_specs_structure(self):
        from ml.distributed.cluster_config import MULTI_NODE_DATA_PARALLEL
        specs = MULTI_NODE_DATA_PARALLEL.worker_pool_specs()
        spec  = specs[0]
        assert "machine_spec" in spec
        assert "replica_count" in spec
        assert "container_spec" in spec

    def test_worker_pool_specs_with_args(self):
        from ml.distributed.cluster_config import SINGLE_NODE_MULTI_GPU
        specs = SINGLE_NODE_MULTI_GPU.worker_pool_specs(
            args=["python", "-m", "ml.training.train_tire_degradation"]
        )
        assert specs[0]["container_spec"]["args"] == [
            "python", "-m", "ml.training.train_tire_degradation"
        ]

    def test_worker_pool_specs_with_env_vars(self):
        from ml.distributed.cluster_config import CPU_DISTRIBUTED
        specs = CPU_DISTRIBUTED.worker_pool_specs(
            env_vars={"PROJECT_ID": "f1optimizer", "REGION": "us-central1"}
        )
        names = {e["name"] for e in specs[0]["container_spec"]["env"]}
        assert "PROJECT_ID" in names
        assert "REGION" in names

    def test_cpu_config_has_no_accelerator(self):
        from ml.distributed.cluster_config import CPU_DISTRIBUTED
        machine_spec = CPU_DISTRIBUTED.worker_pool_specs()[0]["machine_spec"]
        assert "accelerator_type" not in machine_spec

    def test_gpu_config_has_accelerator(self):
        from ml.distributed.cluster_config import SINGLE_NODE_MULTI_GPU
        machine_spec = SINGLE_NODE_MULTI_GPU.worker_pool_specs()[0]["machine_spec"]
        assert "accelerator_type" in machine_spec

    def test_hp_search_trial_counts(self):
        from ml.distributed.cluster_config import HYPERPARAMETER_SEARCH
        assert HYPERPARAMETER_SEARCH.parallel_trial_count == 5
        assert HYPERPARAMETER_SEARCH.max_trial_count == 20


class TestDataSharding:
    def _make(self, num_workers, race_ids):
        from ml.distributed.data_sharding import DataSharding
        s = DataSharding(num_workers=num_workers)
        s._fetch_all_race_ids = MagicMock(return_value=race_ids)
        return s

    def test_shards_are_disjoint(self):
        s        = self._make(4, list(range(1, 41)))
        assigned = [set(s.get_worker_race_ids(i)) for i in range(4)]
        for i in range(4):
            for j in range(i + 1, 4):
                assert not assigned[i] & assigned[j]

    def test_shards_cover_all_races(self):
        race_ids = list(range(1, 41))
        s        = self._make(4, race_ids)
        covered  = set()
        for i in range(4):
            covered |= set(s.get_worker_race_ids(i))
        assert covered == set(race_ids)

    def test_uneven_shards_total_correct(self):
        s     = self._make(4, list(range(1, 42)))
        total = sum(len(s.get_worker_race_ids(i)) for i in range(4))
        assert total == 41

    def test_empty_race_list(self):
        assert self._make(4, []).get_worker_race_ids(0) == []

    def test_more_workers_than_races(self):
        race_ids = [1, 2, 3]
        s        = self._make(10, race_ids)
        assigned = []
        for i in range(10):
            assigned.extend(s.get_worker_race_ids(i))
        assert sorted(assigned) == sorted(race_ids)

    def test_single_worker_gets_all(self):
        race_ids = list(range(1, 21))
        s        = self._make(1, race_ids)
        assert sorted(s.get_worker_race_ids(0)) == sorted(race_ids)


class TestAggregator:
    @pytest.fixture(autouse=True)
    def _patch_gcp(self):
        with patch("ml.distributed.aggregator.storage.Client"), \
             patch("ml.distributed.aggregator.pubsub_v1.PublisherClient"):
            yield

    @pytest.fixture
    def aggregator(self):
        from ml.distributed.aggregator import Aggregator
        return Aggregator(model_name="strategy_predictor", run_id="test-001")

    def test_pick_best_checkpoint_lowest_loss(self, aggregator):
        from ml.distributed.aggregator import CheckpointMeta
        checkpoints = [
            CheckpointMeta("gs://b/c/w0", 0, 0.35, 10, {"val_loss": 0.35}),
            CheckpointMeta("gs://b/c/w1", 1, 0.21, 10, {"val_loss": 0.21}),
            CheckpointMeta("gs://b/c/w2", 2, 0.48, 10, {"val_loss": 0.48}),
        ]
        aggregator.list_checkpoints = MagicMock(return_value=checkpoints)
        best = aggregator.pick_best_checkpoint()
        assert best.val_loss == 0.21
        assert best.worker_index == 1

    def test_pick_best_raises_when_no_checkpoints(self, aggregator):
        aggregator.list_checkpoints = MagicMock(return_value=[])
        with pytest.raises(RuntimeError, match="No checkpoints found"):
            aggregator.pick_best_checkpoint()

    def test_publish_completion(self, aggregator):
        from ml.distributed.aggregator import CheckpointMeta
        mock_future        = MagicMock()
        mock_future.result.return_value = "msg-id-123"
        aggregator._publisher.publish.return_value = mock_future
        best = CheckpointMeta("gs://b/c/w0", 0, 0.21, 5, {})
        aggregator.publish_completion(best, model_uri="gs://f1optimizer-models/latest/")
        aggregator._publisher.publish.assert_called_once()
        payload = json.loads(
            aggregator._publisher.publish.call_args.kwargs["data"].decode()
        )
        assert payload["event"] == "training_complete"
        assert payload["model_name"] == "strategy_predictor"


class TestDistributionStrategy:
    def test_data_parallel_single_node(self):
        from ml.distributed.distribution_strategy import DataParallelStrategy
        desc = DataParallelStrategy(multi_worker=False).describe()
        assert desc["type"] == "data_parallel"
        assert "MirroredStrategy" in desc["strategy"]

    def test_data_parallel_multi_node(self):
        from ml.distributed.distribution_strategy import DataParallelStrategy
        desc = DataParallelStrategy(multi_worker=True).describe()
        assert "MultiWorker" in desc["strategy"]

    def test_hp_parallel_vizier_spec(self):
        from ml.distributed.distribution_strategy import HyperparameterParallelStrategy
        spec = HyperparameterParallelStrategy(
            parallel_trial_count=3, max_trial_count=10, algorithm="GRID_SEARCH"
        ).vizier_study_spec(metric_id="val_loss")
        assert spec["parallel_trial_count"] == 3
        assert spec["max_trial_count"] == 10
        assert spec["metrics"][0]["metric_id"] == "val_loss"
        assert spec["metrics"][0]["goal"] == "MINIMIZE"

    def test_hp_parallel_describe(self):
        from ml.distributed.distribution_strategy import HyperparameterParallelStrategy
        desc = HyperparameterParallelStrategy().describe()
        assert desc["type"] == "hyperparameter_parallel"

    def test_model_parallel_describe(self):
        from ml.distributed.distribution_strategy import ModelParallelStrategy
        desc = ModelParallelStrategy(num_gpus=4).describe()
        assert desc["type"] == "model_parallel"