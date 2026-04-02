import vertexai  # noqa: F401 — callers must call vertexai.init(project, location) before use
from vertexai.language_models import TextEmbeddingModel
from langchain_core.documents import Document
import time
import logging

logger = logging.getLogger(__name__)

# text-embedding-004: max 2 048 tokens per input, 20 000 tokens per batch.
# 1 500 chars ≈ 375 tokens — first-pass per-text guard before sending to the API.
_MAX_CHARS = 1500


def _is_token_limit_error(e: Exception) -> bool:
    err = str(e).lower()
    return "token count" in err or "input token" in err


def _embed_batch_with_split(
    model: "TextEmbeddingModel",
    batch: list[str],
    sleep_seconds: float,
    depth: int = 0,
) -> list[list[float]]:
    """
    Embed a batch of texts. If the batch exceeds the model's token limit
    (400 InvalidArgument), split it in half and retry each half recursively.
    Single-text batches that still exceed the limit are hard-truncated to
    _MAX_CHARS // (2 ** depth) characters before re-embedding.
    """
    if not batch:
        return []
    try:
        results = model.get_embeddings(batch)
        return [r.values for r in results]
    except Exception as e:
        if _is_token_limit_error(e):
            if len(batch) > 1:
                mid = len(batch) // 2
                logger.warning(
                    f"Token limit exceeded for batch of {len(batch)} texts — "
                    f"splitting into {mid} + {len(batch) - mid} and retrying"
                )
                left = _embed_batch_with_split(model, batch[:mid], sleep_seconds, depth)
                right = _embed_batch_with_split(model, batch[mid:], sleep_seconds, depth)
                return left + right
            else:
                # Single text still too long — truncate harder and retry once
                truncated = batch[0][: _MAX_CHARS // max(1, 2**depth)]
                if not truncated:
                    logger.error("Text reduced to empty after truncation, skipping")
                    raise
                logger.warning(
                    f"Single text too long at depth {depth} — truncating to "
                    f"{len(truncated)} chars and retrying"
                )
                return _embed_batch_with_split(
                    model, [truncated], sleep_seconds, depth + 1
                )
        raise


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

    # First-pass per-text truncation. _embed_batch_with_split handles any
    # batches that still exceed the 20K token limit by splitting recursively.
    texts = [t[:_MAX_CHARS] if len(t) > _MAX_CHARS else t for t in texts]

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        logger.debug(f"Embedding batch {i // batch_size + 1} ({len(batch)} texts)...")
        # Retry up to 3 times on rate limit errors
        max_retries = 3
        retry_delay = sleep_seconds
        for attempt in range(max_retries):
            try:
                embeddings.extend(_embed_batch_with_split(model, batch, sleep_seconds))
                break
            except Exception as e:
                if (
                    "429" in str(e)
                    or "quota" in str(e).lower()
                    or "rate" in str(e).lower()
                ):
                    if attempt < max_retries - 1:
                        wait = retry_delay * (2**attempt)
                        logger.warning(
                            f"Rate limit hit on batch {i // batch_size + 1}, "
                            f"retrying in {wait}s (attempt {attempt + 1}/{max_retries})..."
                        )
                        time.sleep(wait)
                    else:
                        logger.error(
                            f"Rate limit exceeded after {max_retries} attempts"
                        )
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
    vectors = get_embeddings(
        texts, batch_size=batch_size, sleep_seconds=sleep_seconds, model_name=model_name
    )
    return list(zip(documents, vectors))
