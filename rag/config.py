"""RAG pipeline configuration using Pydantic Settings."""

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class RagConfig(BaseSettings):
    """Configuration for F1 RAG pipeline.

    All values are read from environment variables with sensible defaults.

    GCP project is resolved from the standard GOOGLE_CLOUD_PROJECT env var
    (set automatically by Cloud Run) before falling back to PROJECT_ID, then
    to the hardcoded default. This ensures the Vertex AI SDK picks up the
    correct project without manual configuration.
    """

    # GCP Configuration
    # Prefer GOOGLE_CLOUD_PROJECT (standard GCP env var, auto-set by Cloud Run)
    # over PROJECT_ID for compatibility with the Vertex AI SDK.
    PROJECT_ID: str = os.environ.get(
        "GOOGLE_CLOUD_PROJECT",
        os.environ.get("PROJECT_ID", "f1optimizer"),
    )
    REGION: str = os.environ.get(
        "GOOGLE_CLOUD_REGION",
        os.environ.get("REGION", "us-central1"),
    )

    # Embedding Configuration
    EMBEDDING_MODEL: str = "text-embedding-004"
    EMBEDDING_DIMENSION: int = 768

    # LLM Configuration
    LLM_MODEL: str = "gemini-2.5-flash"

    # Vector Search Configuration
    # VECTOR_SEARCH_DEPLOYED_INDEX_ID has a default because the deployed index name
    # is typically consistent; the index and endpoint IDs are the unique identifiers
    # that must be explicitly set after creating resources.
    VECTOR_SEARCH_INDEX_ID: str = ""
    VECTOR_SEARCH_ENDPOINT_ID: str = ""
    VECTOR_SEARCH_DEPLOYED_INDEX_ID: str = "f1_rag_deployed"

    # GCS Storage
    GCS_DATA_BUCKET: str = "f1optimizer-data-lake"
    GCS_MODELS_BUCKET: str = "f1optimizer-models"
    METADATA_GCS_PATH: str = "rag/metadata.json"

    # Chunking Configuration
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 50

    # Retrieval Configuration
    TOP_K: int = 5

    # Generation Configuration
    MAX_OUTPUT_TOKENS: int = 4096
    LLM_TEMPERATURE: float = 0.2

    # Embedding Batch Configuration
    EMBEDDING_BATCH_SIZE: int = 250
    EMBEDDING_BATCH_SLEEP_SECONDS: float = 1.0

    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=True, extra="ignore"
    )

    @property
    def is_configured(self) -> bool:
        """Check if vector search is fully configured.

        Returns True only if both VECTOR_SEARCH_INDEX_ID and
        VECTOR_SEARCH_ENDPOINT_ID are non-empty strings.

        Returns:
            bool: True if both required IDs are configured, False otherwise.
        """
        return bool(self.VECTOR_SEARCH_INDEX_ID) and bool(
            self.VECTOR_SEARCH_ENDPOINT_ID
        )
