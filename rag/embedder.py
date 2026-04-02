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

    # text-embedding-004: max 20 000 tokens per batch, 2 048 tokens per input.
    # Truncate each text to 1 500 chars (~375 tokens) to stay well within limits.
    _MAX_CHARS = 1500
    texts = [t[:_MAX_CHARS] if len(t) > _MAX_CHARS else t for t in texts]

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        logger.debug(f"Embedding batch {i // batch_size + 1} ({len(batch)} texts)...")
        # Retry up to 3 times on rate limit errors
        max_retries = 3
        retry_delay = sleep_seconds
        for attempt in range(max_retries):
            try:
                results = model.get_embeddings(batch)
                embeddings.extend([r.values for r in results])
                break
            except Exception as e:
                if "429" in str(e) or "quota" in str(e).lower() or "rate" in str(e).lower():
                    if attempt < max_retries - 1:
                        wait = retry_delay * (2 ** attempt)
                        logger.warning(
                            f"Rate limit hit on batch {i // batch_size + 1}, "
                            f"retrying in {wait}s (attempt {attempt + 1}/{max_retries})..."
                        )
                        time.sleep(wait)
                    else:
                        logger.error(f"Rate limit exceeded after {max_retries} attempts")
                        raise
                else:
                    raise
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
