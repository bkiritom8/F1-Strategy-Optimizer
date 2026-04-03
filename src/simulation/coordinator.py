"""
SimulationCoordinator: hashes scenarios, checks Redis cache,
dispatches background simulation tasks.
"""

import hashlib
import json
import logging
import os
from typing import Any

import redis as redis_lib

logger = logging.getLogger(__name__)

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
CACHE_TTL = 3600  # 1 hour for standard scenarios
STRATEGY_CACHE_TTL = 900  # 15 min for custom strategy overrides
SIMULATION_ENDPOINT = os.environ.get(
    "SIMULATION_ENDPOINT", "http://simulation-worker/internal/simulate"
)


def scenario_hash(race_id: str, scenario: dict) -> str:
    payload = json.dumps({"race_id": race_id, "scenario": scenario}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def n_trials(queue_depth: int) -> int:
    if queue_depth < 100:
        return 50
    if queue_depth < 500:
        return 20
    return 10


def _make_redis() -> redis_lib.Redis:
    return redis_lib.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


class SimulationCoordinator:
    def __init__(self, redis_client: redis_lib.Redis | None = None) -> None:
        self._redis = redis_client or _make_redis()

    def check_cache(self, job_id: str) -> dict | None:
        """Return cached final result dict or None."""
        key = f"sim:result:{job_id}"
        if not self._redis.exists(key):
            return None
        raw = self._redis.get(key)
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    def cache_result(
        self, job_id: str, result: dict, has_strategy_overrides: bool = False
    ) -> None:
        ttl = STRATEGY_CACHE_TTL if has_strategy_overrides else CACHE_TTL
        self._redis.setex(f"sim:result:{job_id}", ttl, json.dumps(result))

    def push_frame(self, job_id: str, frame: dict) -> None:
        """Push one lap frame to the Redis list for this job."""
        self._redis.rpush(f"sim:frames:{job_id}", json.dumps(frame))
        self._redis.expire(f"sim:frames:{job_id}", CACHE_TTL)

    def set_status(self, job_id: str, status: str) -> None:
        self._redis.setex(f"sim:status:{job_id}", CACHE_TTL, status)

    def get_status(self, job_id: str) -> str:
        return self._redis.get(f"sim:status:{job_id}") or "unknown"

    def get_frames_from(self, job_id: str, offset: int) -> list[dict]:
        """Return frames starting at offset from the Redis list."""
        raw_frames = self._redis.lrange(f"sim:frames:{job_id}", offset, -1)
        result = []
        for raw in raw_frames:
            try:
                result.append(json.loads(raw))
            except json.JSONDecodeError:
                pass
        return result

    def get_queue_depth(self) -> int:
        """Approximate queue depth from Redis key count of pending jobs."""
        return len(self._redis.keys("sim:status:*"))

    def replay_from_cache(self, job_id: str) -> bool:
        """
        If cached frames exist for job_id, set status to complete so streamer
        can replay them. Returns True if replay is available.
        """
        frame_count = self._redis.llen(f"sim:frames:{job_id}")
        if frame_count > 0:
            self.set_status(job_id, "complete")
            return True
        return False

    def n_trials(self, queue_depth: int) -> int:
        """Wrapper so routes don't import the module-level function."""
        return n_trials(queue_depth)
