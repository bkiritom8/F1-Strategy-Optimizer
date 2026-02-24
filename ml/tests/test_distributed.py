"""
Tests for distributed training infrastructure.

Verifies:
  - ClusterConfig.worker_pool_specs() produces valid Vertex AI spec dicts
  - DataSharding assigns disjoint race_id sets across workers
  - DataSharding handles uneven shards (non-divisible totals)
  - Aggregator.pick_best_checkpoint selects lowest val_loss
  - DistributionStrategy classes instantiate and describe correctly

All tests run on Vertex AI (n1-standard-4, no GPU).
No Cloud SQL or GCS calls — all external I/O is mocked.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

# ── ClusterConfig tests ───────────────────────────────────────────────────────


class TestClusterConfig:

    def test_all_configs_importable(self):
        from ml.distributed.cluster_config import (
            SINGLE_NODE_MULTI_GPU,
            MULTI_NODE_DATA_PARALLEL,
            HYPERPARAMETER_SEARCH,
            CPU_DISTRIBUTED,
        )

        for cfg in (
            SINGLE_NODE_MULTI_GPU,
            MULTI_NODE_DATA_PARALLEL,
            HYPERPARAMETER_SEARCH,
            CPU_DISTRIBUTED,
        ):
            assert cfg.name
            assert cfg.machine_type
            assert cfg.replica_count >= 1

    def test_worker_pool_specs_structure(self):
        from ml.distributed.cluster_config import MULTI_NODE_DATA_PARALLEL

        specs = MULTI_NODE_DATA_PARALLEL.worker_pool_specs()
        assert len(specs) == 1
        spec = specs[0]
        assert "machine_spec" in spec
        assert "replica_count" in spec
        assert "container_spec" in spec
        assert spec["replica_count"] == MULTI_NODE_DATA_PARALLEL.replica_count

    def test_worker_pool_specs_with_args(self):
        from ml.distributed.cluster_config import SINGLE_NODE_MULTI_GPU

        specs = SINGLE_NODE_MULTI_GPU.worker_pool_specs(
            args=["python", "-m", "ml.models.strategy_predictor"],
        )
        assert specs[0]["container_spec"]["args"] == [
            "python",
            "-m",
            "ml.models.strategy_predictor",
        ]

    def test_worker_pool_specs_with_env_vars(self):
        from ml.distributed.cluster_config import CPU_DISTRIBUTED

        specs = CPU_DISTRIBUTED.worker_pool_specs(
            env_vars={"PROJECT_ID": "f1optimizer", "REGION": "us-central1"}
        )
        env = specs[0]["container_spec"]["env"]
        names = {e["name"] for e in env}
        assert "PROJECT_ID" in names
        assert "REGION" in names

    def test_cpu_config_has_no_accelerator(self):
        from ml.distributed.cluster_config import CPU_DISTRIBUTED

        specs = CPU_DISTRIBUTED.worker_pool_specs()
        machine_spec = specs[0]["machine_spec"]
        assert "accelerator_type" not in machine_spec

    def test_gpu_config_has_accelerator(self):
        from ml.distributed.cluster_config import SINGLE_NODE_MULTI_GPU

        specs = SINGLE_NODE_MULTI_GPU.worker_pool_specs()
        machine_spec = specs[0]["machine_spec"]
        assert "accelerator_type" in machine_spec
        assert machine_spec["accelerator_count"] == 4

    def test_hp_search_config_has_trial_counts(self):
        from ml.distributed.cluster_config import HYPERPARAMETER_SEARCH

        assert HYPERPARAMETER_SEARCH.parallel_trial_count == 5
        assert HYPERPARAMETER_SEARCH.max_trial_count == 20


# ── DataSharding tests ────────────────────────────────────────────────────────


class TestDataSharding:

    def _make_sharding(self, num_workers: int, mock_race_ids: list[int]):
        from ml.distributed.data_sharding import DataSharding

        sharding = DataSharding(num_workers=num_workers)
        sharding._fetch_all_race_ids = MagicMock(return_value=mock_race_ids)  # type: ignore[method-assign]
        return sharding

    def test_shards_are_disjoint(self):
        race_ids = list(range(1, 41))  # 40 races, 4 workers → 10 each
        sharding = self._make_sharding(4, race_ids)

        assigned = [set(sharding.get_worker_race_ids(i)) for i in range(4)]

        # No overlap between any two workers
        for i in range(4):
            for j in range(i + 1, 4):
                overlap = assigned[i] & assigned[j]
                assert not overlap, f"Workers {i} and {j} share races: {overlap}"

    def test_shards_cover_all_races(self):
        race_ids = list(range(1, 41))
        sharding = self._make_sharding(4, race_ids)

        all_assigned = set()
        for i in range(4):
            all_assigned |= set(sharding.get_worker_race_ids(i))

        assert all_assigned == set(race_ids), "Not all races were assigned"

    def test_uneven_shards_handled(self):
        """41 races across 4 workers — remainder distributed to first workers."""
        race_ids = list(range(1, 42))  # 41 races
        sharding = self._make_sharding(4, race_ids)

        sizes = [len(sharding.get_worker_race_ids(i)) for i in range(4)]
        total = sum(sizes)
        assert total == 41, f"Expected 41 total races, got {total}"
        # First worker gets the extra race
        assert (
            sizes[0] == sizes[1] + 1 or sizes[0] == sizes[1]
        ), "Remainder not distributed to leading workers"

    def test_empty_race_list(self):
        sharding = self._make_sharding(4, [])
        result = sharding.get_worker_race_ids(0)
        assert result == []

    def test_more_workers_than_races(self):
        race_ids = [1, 2, 3]
        sharding = self._make_sharding(10, race_ids)

        all_assigned = []
        for i in range(10):
            all_assigned.extend(sharding.get_worker_race_ids(i))

        assert sorted(all_assigned) == sorted(race_ids)

    def test_single_worker_gets_all(self):
        race_ids = list(range(1, 21))
        sharding = self._make_sharding(1, race_ids)
        assert sorted(sharding.get_worker_race_ids(0)) == sorted(race_ids)


# ── Aggregator tests ──────────────────────────────────────────────────────────


class TestAggregator:

    @pytest.fixture(autouse=True)
    def _patch_gcp(self):
        with patch("ml.distributed.aggregator.storage.Client"), patch(
            "ml.distributed.aggregator.pubsub_v1.PublisherClient"
        ):
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

        mock_future = MagicMock()
        mock_future.result.return_value = "msg-id-123"
        aggregator._publisher.publish.return_value = mock_future

        best = CheckpointMeta("gs://b/c/w0", 0, 0.21, 5, {})
        # Should not raise
        aggregator.publish_completion(best, model_uri="gs://f1optimizer-models/latest/")

        aggregator._publisher.publish.assert_called_once()
        call_kwargs = aggregator._publisher.publish.call_args
        payload = json.loads(call_kwargs.kwargs["data"].decode())
        assert payload["event"] == "training_complete"
        assert payload["model_name"] == "strategy_predictor"


# ── DistributionStrategy tests ────────────────────────────────────────────────


class TestDistributionStrategy:

    def test_data_parallel_single_node_describe(self):
        from ml.distributed.distribution_strategy import DataParallelStrategy

        s = DataParallelStrategy(multi_worker=False)
        desc = s.describe()
        assert desc["type"] == "data_parallel"
        assert "MirroredStrategy" in desc["strategy"]

    def test_data_parallel_multi_node_describe(self):
        from ml.distributed.distribution_strategy import DataParallelStrategy

        s = DataParallelStrategy(multi_worker=True)
        desc = s.describe()
        assert "MultiWorker" in desc["strategy"]

    def test_hyperparameter_parallel_vizier_spec(self):
        from ml.distributed.distribution_strategy import HyperparameterParallelStrategy

        s = HyperparameterParallelStrategy(
            parallel_trial_count=3, max_trial_count=10, algorithm="GRID_SEARCH"
        )
        spec = s.vizier_study_spec(metric_id="val_loss")
        assert spec["parallel_trial_count"] == 3
        assert spec["max_trial_count"] == 10
        assert spec["metrics"][0]["metric_id"] == "val_loss"
        assert spec["metrics"][0]["goal"] == "MINIMIZE"
        assert len(spec["parameters"]) > 0

    def test_hyperparameter_parallel_describe(self):
        from ml.distributed.distribution_strategy import HyperparameterParallelStrategy

        s = HyperparameterParallelStrategy()
        desc = s.describe()
        assert desc["type"] == "hyperparameter_parallel"

    def test_model_parallel_describe(self):
        from ml.distributed.distribution_strategy import ModelParallelStrategy

        s = ModelParallelStrategy(num_gpus=4)
        desc = s.describe()
        assert desc["type"] == "model_parallel"
        assert "feature_extraction" in desc["stages"]
