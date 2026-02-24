"""
Vertex AI cluster configurations for distributed F1 training jobs.

Usage:
    from ml.distributed.cluster_config import MULTI_NODE_DATA_PARALLEL
    job = aiplatform.CustomJob(worker_pool_specs=MULTI_NODE_DATA_PARALLEL.worker_pool_specs())
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ClusterConfig:
    """Describes a Vertex AI worker pool configuration."""

    name: str
    machine_type: str
    accelerator_type: str | None
    accelerator_count: int
    replica_count: int
    strategy: str
    # HP-search-only fields
    parallel_trial_count: int = 0
    max_trial_count: int = 0

    def worker_pool_specs(
        self,
        container_uri: str = "us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/ml:latest",
        args: list[str] | None = None,
        env_vars: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return Vertex AI worker_pool_specs list for CustomJob creation."""
        machine_spec: dict[str, Any] = {"machine_type": self.machine_type}
        if self.accelerator_type:
            machine_spec["accelerator_type"] = self.accelerator_type
            machine_spec["accelerator_count"] = self.accelerator_count

        container_spec: dict[str, Any] = {"image_uri": container_uri}
        if args:
            container_spec["args"] = args
        if env_vars:
            container_spec["env"] = [
                {"name": k, "value": v} for k, v in env_vars.items()
            ]

        return [
            {
                "machine_spec": machine_spec,
                "replica_count": self.replica_count,
                "container_spec": container_spec,
            }
        ]


# ── Named cluster configs ─────────────────────────────────────────────────────

SINGLE_NODE_MULTI_GPU = ClusterConfig(
    name="single-node-multi-gpu",
    machine_type="n1-standard-16",
    accelerator_type="NVIDIA_TESLA_T4",
    accelerator_count=4,
    replica_count=1,
    strategy="MirroredStrategy",
)

MULTI_NODE_DATA_PARALLEL = ClusterConfig(
    name="multi-node-data-parallel",
    machine_type="n1-standard-8",
    accelerator_type="NVIDIA_TESLA_T4",
    accelerator_count=1,
    replica_count=4,
    strategy="MultiWorkerMirroredStrategy",
)

HYPERPARAMETER_SEARCH = ClusterConfig(
    name="hyperparameter-search",
    machine_type="n1-standard-8",
    accelerator_type="NVIDIA_TESLA_T4",
    accelerator_count=1,
    replica_count=1,
    strategy="GRID_SEARCH",
    parallel_trial_count=5,
    max_trial_count=20,
)

CPU_DISTRIBUTED = ClusterConfig(
    name="cpu-distributed",
    machine_type="n1-highmem-16",
    accelerator_type=None,
    accelerator_count=0,
    replica_count=8,
    strategy="MultiWorkerMirroredStrategy",
)

VERTEX_T4 = ClusterConfig(
    name="vertex-t4",
    machine_type="n1-standard-4",
    accelerator_type="NVIDIA_TESLA_T4",
    accelerator_count=1,
    replica_count=1,
    strategy="MirroredStrategy",
)

ALL_CONFIGS: dict[str, ClusterConfig] = {
    "single_node_multi_gpu": SINGLE_NODE_MULTI_GPU,
    "multi_node_data_parallel": MULTI_NODE_DATA_PARALLEL,
    "hyperparameter_search": HYPERPARAMETER_SEARCH,
    "cpu_distributed": CPU_DISTRIBUTED,
    "vertex_t4": VERTEX_T4,
}
