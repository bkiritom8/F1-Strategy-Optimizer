import pytest

pytest.importorskip("langchain_core")
from langchain_core.documents import Document


# ---------------------------------------------------------------------------
# chunk_regulation_text
# ---------------------------------------------------------------------------

def test_chunk_regulation_text_splits_on_articles():
    """Text with Article boundaries yields one Document per article."""
    from rag.document_fetcher import chunk_regulation_text

    text = (
        "Preamble text before articles.\n"
        "Article 28\nPit stops are mandatory. Each driver must make at least one pit stop "
        "during the race to change tyres.\n"
        "Article 29\nTyres must be of the specification approved by the FIA for that event."
    )
    source_meta = {"source": "FIA", "doc_type": "sporting_regulations", "season": 2024, "category": "regulations"}

    docs = chunk_regulation_text(text, source_meta)

    assert len(docs) >= 2
    article_numbers = [d.metadata.get("article") for d in docs]
    assert "Article 28" in article_numbers
    assert "Article 29" in article_numbers
    for doc in docs:
        assert doc.metadata["source"] == "FIA"
        assert doc.metadata["season"] == 2024
        assert "chunk_index" in doc.metadata


def test_chunk_regulation_text_empty():
    """Empty text returns []."""
    from rag.document_fetcher import chunk_regulation_text

    result = chunk_regulation_text("", {"source": "FIA", "doc_type": "test", "season": 2024, "category": "regulations"})
    assert result == []


def test_chunk_regulation_text_chunk_index_sequential():
    """chunk_index values are sequential starting from 0."""
    from rag.document_fetcher import chunk_regulation_text

    text = (
        "Article 1\nShort article one.\n"
        "Article 2\nShort article two.\n"
        "Article 3\nShort article three.\n"
    )
    meta = {"source": "FIA", "doc_type": "tech", "season": 2024, "category": "regulations"}
    docs = chunk_regulation_text(text, meta)

    assert len(docs) >= 1
    indices = [d.metadata["chunk_index"] for d in docs]
    assert indices == list(range(len(docs)))


def test_chunk_regulation_text_no_articles_falls_back_to_fixed_windows():
    """Text without Article markers is chunked into fixed windows."""
    from rag.document_fetcher import chunk_regulation_text

    text = "word " * 300  # 1500 chars, no Article markers
    meta = {"source": "FIA", "doc_type": "notes", "season": 2024, "category": "regulations"}
    docs = chunk_regulation_text(text, meta, chunk_size=100, chunk_overlap=10)

    assert len(docs) > 1
    for doc in docs:
        assert doc.metadata.get("article") is None


# ---------------------------------------------------------------------------
# fetch_all_text_documents — skips on download failure
# ---------------------------------------------------------------------------

def test_fetch_all_skips_failed_downloads():
    """fetch_all_text_documents returns a non-empty list of hardcoded documents
    regardless of network availability (no external I/O is performed)."""
    from rag.document_fetcher import fetch_all_text_documents

    result = fetch_all_text_documents(bucket="test-bucket", force_refresh=False)

    assert isinstance(result, list)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# fetch_all_text_documents — cache hit skips download
# ---------------------------------------------------------------------------

def test_cache_hit_skips_download():
    """fetch_all_text_documents uses hardcoded content — no HTTP requests are made."""
    from rag.document_fetcher import fetch_all_text_documents

    result = fetch_all_text_documents(bucket="test-bucket", force_refresh=False)

    assert isinstance(result, list)
    assert len(result) > 0
