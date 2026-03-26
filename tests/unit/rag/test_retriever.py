import pytest
from unittest.mock import MagicMock, patch

pytest.importorskip("langchain_core")
from langchain_core.documents import Document


def _make_retriever():
    """Create an F1Retriever with a mock unconfigured config."""
    from rag.retriever import F1Retriever
    retriever = F1Retriever.__new__(F1Retriever)
    retriever._initialized = False
    retriever._model = None

    mock_config = MagicMock()
    mock_config.is_configured = True
    mock_config.PROJECT_ID = "f1optimizer"
    mock_config.REGION = "us-central1"
    mock_config.EMBEDDING_MODEL = "text-embedding-004"
    mock_config.TOP_K = 5
    mock_config.VECTOR_SEARCH_ENDPOINT_ID = "ep-123"
    mock_config.VECTOR_SEARCH_DEPLOYED_INDEX_ID = "dep-123"
    mock_config.GCS_MODELS_BUCKET = "f1optimizer-models"
    mock_config.METADATA_GCS_PATH = "rag/metadata.json"
    mock_config.LLM_MODEL = "gemini-1.5-flash"
    mock_config.LLM_TEMPERATURE = 0.2
    mock_config.MAX_OUTPUT_TOKENS = 1024
    retriever.config = mock_config
    return retriever


def test_query_returns_correct_shape():
    """query() returns dict with all required keys."""
    retriever = _make_retriever()

    fake_docs = [
        Document(page_content="Hamilton won Monaco", metadata={"season": 2019}),
        Document(page_content="Verstappen fastest lap", metadata={"season": 2022}),
    ]

    with patch.object(retriever, "retrieve", return_value=fake_docs), \
         patch.object(retriever, "generate", return_value="Test answer"):
        result = retriever.query("Who won Monaco 2019?")

    assert "answer" in result
    assert "sources" in result
    assert "query" in result
    assert "num_sources" in result
    assert "latency_ms" in result
    assert result["answer"] == "Test answer"
    assert result["num_sources"] == 2
    assert result["query"] == "Who won Monaco 2019?"


def test_query_not_configured_returns_empty():
    """query() returns no-data answer when not configured."""
    retriever = _make_retriever()
    retriever.config.is_configured = False

    result = retriever.query("test question")

    assert result["answer"] == "I don't have enough data to answer that."
    assert result["sources"] == []
    assert result["num_sources"] == 0


def test_generate_empty_context():
    """generate() returns no-data string when context_docs is empty."""
    retriever = _make_retriever()

    answer = retriever.generate("any question", [])

    assert answer == "I don't have enough data to answer that."
