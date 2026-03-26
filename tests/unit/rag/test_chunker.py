import io
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch

pytest.importorskip("langchain_core")
from langchain_core.documents import Document


def _make_gcs_client(df: pd.DataFrame, format: str = "parquet"):
    """Create a mock storage.Client that returns df bytes."""
    buf = io.BytesIO()
    if format == "parquet":
        df.to_parquet(buf, index=False)
    else:
        df.to_csv(buf, index=False)
    buf.seek(0)
    mock_blob = MagicMock()
    mock_blob.download_as_bytes.return_value = buf.read()
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    return mock_client


@patch("rag.chunker.storage.Client")
def test_chunk_parquet_telemetry(mock_client_cls):
    """chunk_parquet creates Documents from telemetry columns."""
    from rag.chunker import chunk_parquet

    df = pd.DataFrame({
        "Year": [2023],
        "EventName": ["British Grand Prix"],
        "Driver": ["HAM"],
        "LapNumber": [10],
        "LapTime": ["1:30.123"],
        "Compound": ["MEDIUM"],
        "Position": [3],
    })
    mock_client_cls.return_value = _make_gcs_client(df, "parquet")

    docs = chunk_parquet("gs://bucket/2023/silverstone/R_laps.parquet")

    assert len(docs) == 1
    assert "HAM" in docs[0].page_content
    assert docs[0].metadata["source_type"] == "parquet"
    assert docs[0].metadata["season"] == 2023


@patch("rag.chunker.storage.Client")
def test_chunk_csv_race_results(mock_client_cls):
    """chunk_csv creates Documents from race_results CSV."""
    from rag.chunker import chunk_csv

    df = pd.DataFrame({
        "year": [2023],
        "raceName": ["British Grand Prix"],
        "driverRef": ["hamilton"],
        "positionOrder": [1],
        "constructorRef": ["mercedes"],
        "grid": [1],
        "points": [25],
    })
    mock_client_cls.return_value = _make_gcs_client(df, "csv")

    docs = chunk_csv("gs://bucket/2023/british/race_results.csv")

    assert len(docs) == 1
    assert "1" in docs[0].page_content  # positionOrder
    assert docs[0].metadata["source_type"] == "csv"


@patch("rag.chunker.storage.Client")
def test_chunk_parquet_empty_file(mock_client_cls):
    """chunk_parquet returns [] for empty DataFrame."""
    from rag.chunker import chunk_parquet

    df = pd.DataFrame()
    mock_client_cls.return_value = _make_gcs_client(df, "parquet")

    docs = chunk_parquet("gs://bucket/empty.parquet")
    assert docs == []


@patch("rag.chunker.storage.Client")
def test_load_all_documents_skips_ff1pkl(mock_client_cls):
    """load_all_documents skips .ff1pkl files."""
    from rag.chunker import load_all_documents

    # Mock blob list: parquet, csv, and ff1pkl
    blobs = []
    for name in ["data/2023/race_results.csv", "data/2023/laps.parquet", "cache/session.ff1pkl"]:
        b = MagicMock()
        b.name = name
        blobs.append(b)

    # Mock client for listing
    mock_list_client = MagicMock()
    mock_list_client.list_blobs.return_value = blobs

    # chunk_parquet/chunk_csv will be called — mock them to return empty
    with patch("rag.chunker.chunk_parquet", return_value=[]) as mock_parquet, \
         patch("rag.chunker.chunk_csv", return_value=[]) as mock_csv:
        mock_client_cls.return_value = mock_list_client
        result = load_all_documents("my-bucket")

    # ff1pkl should be skipped; parquet and csv should be called
    assert mock_parquet.call_count == 1
    assert mock_csv.call_count == 1
    assert result == []
