from vertexai.generative_models import GenerativeModel
from langchain_core.documents import Document
from rag.config import RagConfig
from rag import embedder, vector_store
import vertexai
import logging
import time

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert F1 race strategy analyst.
You have deep knowledge of Formula 1 racing, tire strategies,
pit stops, lap times, and race outcomes.
Answer questions based ONLY on the context provided.
If the answer is not in the context, say exactly:
"I don't have enough data to answer that."
Be concise and specific. Include relevant numbers and statistics
from the context when available."""


class F1Retriever:
    """
    Main RAG interface. Handles retrieval from Vector Search
    and generation via Gemini.

    Lazily initialized — safe to import before Vertex AI is configured.
    """

    def __init__(self):
        """Load config. Do not initialize Vertex AI here."""
        self.config = RagConfig()
        self._initialized = False
        self._model = None

    def _ensure_initialized(self) -> None:
        """
        Initialize Vertex AI and Gemini model on first use.
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
        self._model = GenerativeModel(self.config.LLM_MODEL)
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

        query_embedding = embedder.get_embeddings(
            [query],
            model_name=self.config.EMBEDDING_MODEL,
        )[0]

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
        Build a prompt from query + context docs and call Gemini.
        Returns "I don't have enough data to answer that." if context_docs is empty.
        Raises RuntimeError if called directly on an unconfigured retriever with non-empty docs.
        For normal usage, prefer query() which calls retrieve() + generate() together.
        """
        if not context_docs:
            return "I don't have enough data to answer that."

        self._ensure_initialized()

        context_parts = []
        for doc in context_docs:
            context_parts.append("---")
            context_parts.append(doc.page_content)
        context_parts.append("---")
        context_str = "\n".join(context_parts)

        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"Context:\n{context_str}\n\n"
            f"Question: {query}\n\n"
            f"Answer:"
        )

        response = self._model.generate_content(
            prompt,
            generation_config={
                "temperature": self.config.LLM_TEMPERATURE,
                "max_output_tokens": self.config.MAX_OUTPUT_TOKENS,
            },
        )
        return response.text

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
