import pytest
from unittest.mock import MagicMock, patch, call
from langchain.schema import Document


def _make_mock_model(dim: int = 768):
    """Create a mock TextEmbeddingModel that returns dim-dimensional vectors."""
    mock_result = MagicMock()
    mock_result.values = [0.1] * dim
    mock_model = MagicMock()
    mock_model.get_embeddings.return_value = [mock_result]
    return mock_model


@patch("rag.embedder.TextEmbeddingModel")
def test_get_embeddings_returns_correct_shape(mock_model_cls):
    """get_embeddings returns correct number of 768-dim vectors."""
    from rag.embedder import get_embeddings

    mock_model = _make_mock_model(768)
    mock_model.get_embeddings.side_effect = lambda batch: [
        MagicMock(values=[0.1] * 768) for _ in batch
    ]
    mock_model_cls.from_pretrained.return_value = mock_model

    result = get_embeddings(["text1", "text2"], batch_size=250, sleep_seconds=0)

    assert len(result) == 2
    assert len(result[0]) == 768
    assert len(result[1]) == 768


@patch("rag.embedder.time")
@patch("rag.embedder.TextEmbeddingModel")
def test_get_embeddings_batches_correctly(mock_model_cls, mock_time):
    """get_embeddings calls the model twice for 300 texts with batch_size=250."""
    from rag.embedder import get_embeddings

    mock_model = MagicMock()
    mock_model.get_embeddings.side_effect = lambda batch: [
        MagicMock(values=[0.1] * 768) for _ in batch
    ]
    mock_model_cls.from_pretrained.return_value = mock_model

    texts = [f"text{i}" for i in range(300)]
    result = get_embeddings(texts, batch_size=250, sleep_seconds=0.0)

    assert mock_model.get_embeddings.call_count == 2
    assert len(result) == 300


@patch("rag.embedder.TextEmbeddingModel")
def test_embed_documents_preserves_order(mock_model_cls):
    """embed_documents returns tuples in the same order as input documents."""
    from rag.embedder import embed_documents

    docs = [
        Document(page_content=f"doc{i}", metadata={"i": i})
        for i in range(3)
    ]
    mock_model = MagicMock()
    mock_model.get_embeddings.side_effect = lambda batch: [
        MagicMock(values=[float(i)] * 768) for i, _ in enumerate(batch)
    ]
    mock_model_cls.from_pretrained.return_value = mock_model

    pairs = embed_documents(docs, batch_size=250, sleep_seconds=0)

    assert len(pairs) == 3
    for i, (doc, vec) in enumerate(pairs):
        assert doc.metadata["i"] == i
        # Verify the vector is paired with the correct document (not scrambled)
        assert vec[0] == pytest.approx(float(i)), f"Vector for doc {i} has wrong first element: {vec[0]}"
