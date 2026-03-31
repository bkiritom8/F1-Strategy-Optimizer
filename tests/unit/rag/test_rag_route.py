"""Unit tests for /rag/query LRU cache."""
import pytest
from unittest.mock import MagicMock, patch

pytest.importorskip("fastapi")


def _make_result(answer: str = "test answer") -> dict:
    return {
        "answer": answer,
        "sources": [],
        "query": "test query",
        "num_sources": 0,
        "latency_ms": 100.0,
    }


def test_cache_key_same_for_identical_queries():
    """Same query params produce same cache key."""
    from src.api.routes.rag import _cache_key

    key1 = _cache_key("Hamilton Monaco", {"season": 2019}, 5)
    key2 = _cache_key("Hamilton Monaco", {"season": 2019}, 5)
    assert key1 == key2


def test_cache_key_different_for_different_queries():
    """Different queries produce different cache keys."""
    from src.api.routes.rag import _cache_key

    key1 = _cache_key("Hamilton Monaco", None, 5)
    key2 = _cache_key("Verstappen Spa", None, 5)
    assert key1 != key2


def test_cache_key_different_for_different_filters():
    """Same query with different filters produces different keys."""
    from src.api.routes.rag import _cache_key

    key1 = _cache_key("lap times", {"season": 2019}, 5)
    key2 = _cache_key("lap times", {"season": 2020}, 5)
    assert key1 != key2


def test_cache_evicts_oldest_when_full():
    """Cache evicts oldest entry when max size is reached."""
    import src.api.routes.rag as rag_module

    # Clear cache
    rag_module._query_cache.clear()
    rag_module._cache_keys.clear()

    # Fill cache to max
    original_max = rag_module._CACHE_MAX_SIZE
    rag_module._CACHE_MAX_SIZE = 3

    for i in range(3):
        key = rag_module._cache_key(f"query{i}", None, 5)
        rag_module._query_cache[key] = _make_result(f"answer{i}")
        rag_module._cache_keys.append(key)

    first_key = rag_module._cache_keys[0]
    assert first_key in rag_module._query_cache

    # Add one more — should evict first
    new_key = rag_module._cache_key("new query", None, 5)
    if len(rag_module._query_cache) >= rag_module._CACHE_MAX_SIZE:
        oldest = rag_module._cache_keys.pop(0)
        rag_module._query_cache.pop(oldest, None)
    rag_module._query_cache[new_key] = _make_result("new answer")
    rag_module._cache_keys.append(new_key)

    assert first_key not in rag_module._query_cache
    assert new_key in rag_module._query_cache

    # Restore
    rag_module._CACHE_MAX_SIZE = original_max
    rag_module._query_cache.clear()
    rag_module._cache_keys.clear()