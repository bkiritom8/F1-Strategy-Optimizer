from __future__ import annotations

import logging
import time

from langchain_core.documents import Document
from rag.config import RagConfig
from rag import embedder, vector_store
from src.llm.gemini_client import GeminiClient
import vertexai

logger = logging.getLogger(__name__)


class F1Retriever:
    """
    Main RAG interface. Handles retrieval from Vector Search
    and generation via GeminiClient.

    Lazily initialized — safe to import before Vertex AI is configured.
    """

    def __init__(self) -> None:
        self.config = RagConfig()
        self._initialized = False
        self._gemini_client = GeminiClient(self.config)
        self._embedding_cache: dict[str, list[float]] = {}

    def _ensure_initialized(self) -> None:
        """
        Initialize Vertex AI on first use (needed for embedder calls).
        Raises RuntimeError if config.is_configured is False.
        """
        if self._initialized:
            return
        if not self.config.is_configured:
            raise RuntimeError(
                "RAG index not configured. Set VECTOR_SEARCH_INDEX_ID and "
                "VECTOR_SEARCH_ENDPOINT_ID environment variables."
            )
        vertexai.init(project=self.config.PROJECT_ID, location=self.config.REGION)
        self._initialized = True

    def retrieve(
        self,
        query: str,
        filters: dict | None = None,
        top_k: int | None = None,
    ) -> list[Document]:
        """
        Embed the query and retrieve top_k relevant documents from Vector Search.

        filters dict can contain:
          season: int
          race: str
          driver: str

        Returns list of Documents. Returns [] if index not configured.
        """
        if not self.config.is_configured:
            return []

        self._ensure_initialized()

        if query in self._embedding_cache:
            logger.debug("Embedding cache hit for query: %s", query[:50])
            query_embedding = self._embedding_cache[query]
        else:
            query_embedding = embedder.get_embeddings(
                [query],
                model_name=self.config.EMBEDDING_MODEL,
            )[0]
            self._embedding_cache[query] = query_embedding

        filter_season = filters.get("season") if filters else None
        filter_race = filters.get("race") if filters else None
        filter_driver = filters.get("driver") if filters else None

        return vector_store.query_index(
            index_endpoint_id=self.config.VECTOR_SEARCH_ENDPOINT_ID,
            deployed_index_id=self.config.VECTOR_SEARCH_DEPLOYED_INDEX_ID,
            project=self.config.PROJECT_ID,
            region=self.config.REGION,
            query_embedding=query_embedding,
            top_k=top_k if top_k is not None else self.config.TOP_K,
            metadata_bucket=self.config.GCS_MODELS_BUCKET,
            metadata_gcs_path=self.config.METADATA_GCS_PATH,
            filter_season=filter_season,
            filter_race=filter_race,
            filter_driver=filter_driver,
        )

    def generate(
        self,
        query: str,
        context_docs: list[Document],
    ) -> str:
        """
        Generate an answer from context docs via GeminiClient.
        Returns the no-data fallback string if context_docs is empty.
        """
        if not context_docs:
            return "I don't have enough data to answer that."

        self._ensure_initialized()
        return self._gemini_client.generate(query, context_docs=context_docs)

    def query(
        self,
        query: str,
        filters: dict | None = None,
        top_k: int | None = None,
    ) -> dict:
        """
        Full RAG pipeline: retrieve then generate.

        Returns:
        {
          "answer": str,
          "sources": [{"content": str, "metadata": dict}],
          "query": str,
          "num_sources": int,
          "latency_ms": float
        }
        """
        start = time.time()

        docs = self.retrieve(query, filters=filters, top_k=top_k)
        answer = self.generate(query, docs)

        latency_ms = (time.time() - start) * 1000

        return {
            "answer": answer,
            "sources": [
                {
                    "content": doc.page_content[:200],
                    "metadata": doc.metadata,
                }
                for doc in docs
            ],
            "query": query,
            "num_sources": len(docs),
            "latency_ms": round(latency_ms, 2),
        }
