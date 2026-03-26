import vertexai  # noqa: F401 — callers must call vertexai.init(project, location) before use
from vertexai.language_models import TextEmbeddingModel
from langchain_core.documents import Document
import time
import logging

logger = logging.getLogger(__name__)


def get_embeddings(
    texts: list[str],
    batch_size: int = 250,
    sleep_seconds: float = 1.0,
    model_name: str = "text-embedding-004",
) -> list[list[float]]:
    """
    Embed a list of texts using Vertex AI text-embedding-004.
    Processes in batches of batch_size (API limit is 250).
    Sleeps sleep_seconds between batches to avoid rate limits.
    Returns a flat list of embedding vectors in the same order as input.
    Raises ValueError if texts is empty.
    """
    if not texts:
        raise ValueError("texts must not be empty")
    if batch_size <= 0:
        raise ValueError(f"batch_size must be positive, got {batch_size}")

    model = TextEmbeddingModel.from_pretrained(model_name)
    embeddings: list[list[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        logger.debug(f"Embedding batch {i // batch_size + 1} ({len(batch)} texts)...")
        results = model.get_embeddings(batch)
        embeddings.extend([r.values for r in results])
        if i + batch_size < len(texts):
            time.sleep(sleep_seconds)

    return embeddings


def embed_documents(
    documents: list[Document],
    batch_size: int = 250,
    sleep_seconds: float = 1.0,
    model_name: str = "text-embedding-004",
) -> list[tuple[Document, list[float]]]:
    """
    Embed a list of LangChain Documents.
    Calls get_embeddings on doc.page_content for all docs.
    Returns list of (document, embedding_vector) tuples.
    Preserves original document order.
    """
    if not documents:
        return []

    texts = [doc.page_content for doc in documents]
    vectors = get_embeddings(texts, batch_size=batch_size, sleep_seconds=sleep_seconds, model_name=model_name)
    return list(zip(documents, vectors))
