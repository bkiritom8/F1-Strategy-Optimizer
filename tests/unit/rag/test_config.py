import os
import pytest
from rag.config import RagConfig


_DEFAULT_ENV_KEYS = [
    "PROJECT_ID", "REGION", "EMBEDDING_MODEL", "EMBEDDING_DIMENSION",
    "LLM_MODEL", "VECTOR_SEARCH_INDEX_ID", "VECTOR_SEARCH_ENDPOINT_ID",
    "VECTOR_SEARCH_DEPLOYED_INDEX_ID", "GCS_DATA_BUCKET", "GCS_MODELS_BUCKET",
    "METADATA_GCS_PATH", "CHUNK_SIZE", "CHUNK_OVERLAP", "TOP_K",
    "MAX_OUTPUT_TOKENS", "LLM_TEMPERATURE", "EMBEDDING_BATCH_SIZE",
    "EMBEDDING_BATCH_SLEEP_SECONDS",
]


def test_defaults(monkeypatch):
    """RagConfig instantiated with no env vars returns correct defaults."""
    for key in _DEFAULT_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    config = RagConfig()
    assert config.PROJECT_ID == "f1optimizer"
    assert config.REGION == "us-central1"
    assert config.EMBEDDING_MODEL == "text-embedding-004"
    assert config.EMBEDDING_DIMENSION == 768
    assert config.LLM_MODEL == "gemini-2.5-flash"
    assert config.VECTOR_SEARCH_INDEX_ID == ""
    assert config.VECTOR_SEARCH_ENDPOINT_ID == ""
    assert config.VECTOR_SEARCH_DEPLOYED_INDEX_ID == "f1_rag_deployed"
    assert config.GCS_DATA_BUCKET == "f1optimizer-data-lake"
    assert config.GCS_MODELS_BUCKET == "f1optimizer-models"
    assert config.METADATA_GCS_PATH == "rag/metadata.json"
    assert config.CHUNK_SIZE == 512
    assert config.CHUNK_OVERLAP == 50
    assert config.TOP_K == 5
    assert config.MAX_OUTPUT_TOKENS == 4096
    assert config.LLM_TEMPERATURE == 0.2
    assert config.EMBEDDING_BATCH_SIZE == 250
    assert config.EMBEDDING_BATCH_SLEEP_SECONDS == 1.0


def test_is_configured_false():
    """is_configured returns False when both IDs are empty."""
    config = RagConfig()
    assert config.is_configured is False


def test_is_configured_true(monkeypatch):
    """is_configured returns True when both IDs are set."""
    monkeypatch.setenv("VECTOR_SEARCH_INDEX_ID", "my-index-123")
    monkeypatch.setenv("VECTOR_SEARCH_ENDPOINT_ID", "my-endpoint-456")
    config = RagConfig()
    assert config.is_configured is True


def test_env_override(monkeypatch):
    """PROJECT_ID env var overrides default."""
    monkeypatch.setenv("PROJECT_ID", "my-project")
    config = RagConfig()
    assert config.PROJECT_ID == "my-project"
