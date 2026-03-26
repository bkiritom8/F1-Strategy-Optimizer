import json
import pytest
from unittest.mock import MagicMock, patch, call

pytest.importorskip("langchain_core")
from langchain_core.documents import Document
from google.cloud.exceptions import NotFound


def _make_doc(content: str, meta: dict | None = None) -> Document:
    return Document(page_content=content, metadata=meta or {})


# ---------------------------------------------------------------------------
# load_metadata
# ---------------------------------------------------------------------------

def test_load_metadata_returns_dict():
    """load_metadata returns parsed JSON dict from GCS blob."""
    payload = {"abc": {"page_content": "hello", "metadata": {"season": 2023}}}

    mock_blob = MagicMock()
    mock_blob.download_as_text.return_value = json.dumps(payload)
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket

    with patch("rag.vector_store.storage.Client", return_value=mock_client):
        from rag.vector_store import load_metadata
        result = load_metadata("my-bucket", "rag/meta.json")

    assert result == payload
    mock_bucket.blob.assert_called_once_with("rag/meta.json")


def test_load_metadata_returns_empty_on_not_found():
    """load_metadata returns {} when the GCS object does not exist."""
    mock_blob = MagicMock()
    mock_blob.download_as_text.side_effect = NotFound("not found")
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket

    with patch("rag.vector_store.storage.Client", return_value=mock_client):
        from rag.vector_store import load_metadata
        result = load_metadata("my-bucket", "rag/meta.json")

    assert result == {}


# ---------------------------------------------------------------------------
# save_metadata
# ---------------------------------------------------------------------------

def test_save_metadata_writes_merged_json():
    """save_metadata merges new entries with existing and uploads JSON."""
    existing = {"old-id": {"page_content": "old content", "metadata": {}}}
    docs = [_make_doc("new content", {"season": 2024})]
    doc_ids = ["new-id-123"]

    mock_blob = MagicMock()
    # First call (load_metadata inside save_metadata) returns existing data
    mock_blob.download_as_text.return_value = json.dumps(existing)
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket

    with patch("rag.vector_store.storage.Client", return_value=mock_client):
        from rag.vector_store import save_metadata
        save_metadata(docs, doc_ids, "my-bucket", "rag/meta.json")

    uploaded = json.loads(mock_blob.upload_from_string.call_args[0][0])
    assert "old-id" in uploaded
    assert "new-id-123" in uploaded
    assert uploaded["new-id-123"]["page_content"] == "new content"
    assert uploaded["new-id-123"]["metadata"] == {"season": 2024}


def test_save_metadata_first_run_no_existing():
    """save_metadata handles empty existing metadata (first run)."""
    docs = [_make_doc("first doc")]
    doc_ids = ["first-id"]

    mock_blob = MagicMock()
    mock_blob.download_as_text.side_effect = NotFound("not found")
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket

    with patch("rag.vector_store.storage.Client", return_value=mock_client):
        from rag.vector_store import save_metadata
        save_metadata(docs, doc_ids, "my-bucket", "rag/meta.json")

    uploaded = json.loads(mock_blob.upload_from_string.call_args[0][0])
    assert uploaded == {"first-id": {"page_content": "first doc", "metadata": {}}}
