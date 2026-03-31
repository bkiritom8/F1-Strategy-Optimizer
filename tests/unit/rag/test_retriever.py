import pytest
from unittest.mock import MagicMock, patch

pytest.importorskip("langchain_core")
from langchain_core.documents import Document


def _make_retriever():
    """Create an F1Retriever with a mock config — bypasses Vertex AI init."""
    from rag.retriever import F1Retriever
    retriever = F1Retriever.__new__(F1Retriever)
    retriever._initialized = False
    retriever._gemini_client = MagicMock()

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
    mock_config.LLM_MODEL = "gemini-2.5-flash"
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


def test_init_sets_attributes():
    """F1Retriever.__init__ sets config, _initialized=False, and _gemini_client."""
    with patch("rag.retriever.RagConfig") as MockConfig, \
         patch("rag.retriever.GeminiClient") as MockGeminiClient:
        from rag.retriever import F1Retriever
        r = F1Retriever()
    assert r._initialized is False
    assert r._gemini_client is not None
    MockConfig.assert_called_once()


def test_ensure_initialized_already_initialized():
    """_ensure_initialized returns immediately when already initialized."""
    retriever = _make_retriever()
    retriever._initialized = True
    with patch("rag.retriever.vertexai") as mock_vertexai:
        retriever._ensure_initialized()
    mock_vertexai.init.assert_not_called()


def test_ensure_initialized_not_configured_raises():
    """_ensure_initialized raises RuntimeError when config.is_configured is False."""
    retriever = _make_retriever()
    retriever._initialized = False
    retriever.config.is_configured = False

    with pytest.raises(RuntimeError, match="RAG index not configured"):
        retriever._ensure_initialized()


def test_ensure_initialized_success():
    """_ensure_initialized calls vertexai.init and sets _initialized=True."""
    retriever = _make_retriever()
    retriever._initialized = False

    with patch("rag.retriever.vertexai") as mock_vertexai:
        retriever._ensure_initialized()

    mock_vertexai.init.assert_called_once_with(
        project="f1optimizer", location="us-central1"
    )
    assert retriever._initialized is True


def test_retrieve_calls_vector_store():
    """retrieve() embeds query and calls vector_store.query_index when configured."""
    retriever = _make_retriever()

    fake_docs = [Document(page_content="some content", metadata={})]
    fake_embedding = [0.1] * 768

    with patch("rag.retriever.embedder.get_embeddings", return_value=[fake_embedding]), \
         patch("rag.retriever.vector_store.query_index", return_value=fake_docs), \
         patch.object(retriever, "_ensure_initialized"):
        result = retriever.retrieve("fastest lap 2023", filters={"season": 2023})

    assert result == fake_docs


def test_retrieve_with_no_filters():
    """retrieve() passes None filters correctly."""
    retriever = _make_retriever()
    fake_embedding = [0.0] * 768

    with patch("rag.retriever.embedder.get_embeddings", return_value=[fake_embedding]), \
         patch("rag.retriever.vector_store.query_index", return_value=[]) as mock_query, \
         patch.object(retriever, "_ensure_initialized"):
        retriever.retrieve("any question")

    call_kwargs = mock_query.call_args[1]
    assert call_kwargs["filter_season"] is None
    assert call_kwargs["filter_race"] is None
    assert call_kwargs["filter_driver"] is None


def test_generate_with_context():
    """generate() delegates to _gemini_client.generate when context_docs provided."""
    retriever = _make_retriever()
    retriever._initialized = True

    docs = [
        Document(page_content="Hamilton dominated Monaco 2019", metadata={}),
    ]
    retriever._gemini_client.generate.return_value = "Hamilton won."

    with patch.object(retriever, "_ensure_initialized"):
        answer = retriever.generate("Who won Monaco 2019?", docs)

    assert answer == "Hamilton won."
    retriever._gemini_client.generate.assert_called_once_with(
        "Who won Monaco 2019?", context_docs=docs
    )
