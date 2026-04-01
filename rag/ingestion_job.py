import os
import sys
import logging
import time
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Files per embed+upsert cycle. Override via FILE_BATCH_SIZE env var.
# Start low (5) for the large FastF1 Parquet telemetry files.
_FILE_BATCH_SIZE = int(os.environ.get("FILE_BATCH_SIZE", "5"))


def _process_in_batches(config, index_id):
    """
    Stream GCS files in batches of _FILE_BATCH_SIZE.
    Each batch is chunked → embedded → upserted, then released from memory.
    Returns total vectors upserted.
    """
    from google.cloud import storage as gcs
    from rag.chunker import iter_gcs_uris, chunk_uri
    from rag.embedder import embed_documents
    from rag import vector_store

    gcs_client = gcs.Client()
    total_vectors = 0
    batch_uris = []
    file_count = 0

    def _flush(uris):
        nonlocal total_vectors
        if not uris:
            return
        docs = []
        for uri, ftype in uris:
            docs.extend(chunk_uri(uri, ftype, client=gcs_client))
        if not docs:
            return
        pairs = embed_documents(
            docs,
            batch_size=config.EMBEDDING_BATCH_SIZE,
            sleep_seconds=config.EMBEDDING_BATCH_SLEEP_SECONDS,
            model_name=config.EMBEDDING_MODEL,
        )
        embedded_docs = [p[0] for p in pairs]
        embeddings = [p[1] for p in pairs]
        vector_store.upsert_vectors(
            index_id=index_id,
            project=config.PROJECT_ID,
            region=config.REGION,
            documents=embedded_docs,
            embeddings=embeddings,
            metadata_bucket=config.GCS_MODELS_BUCKET,
            metadata_gcs_path=config.METADATA_GCS_PATH,
        )
        total_vectors += len(embeddings)
        logger.info(
            f"  Flushed {len(embeddings)} vectors (total so far: {total_vectors})"
        )

    for uri, ftype in iter_gcs_uris(config.GCS_DATA_BUCKET):
        batch_uris.append((uri, ftype))
        file_count += 1
        if len(batch_uris) >= _FILE_BATCH_SIZE:
            logger.info(
                f"  Processing file batch {file_count - _FILE_BATCH_SIZE + 1}–{file_count}"
            )
            _flush(batch_uris)
            batch_uris = []

    # Flush remaining
    if batch_uris:
        logger.info(f"  Processing final batch of {len(batch_uris)} files")
        _flush(batch_uris)

    return total_vectors


if __name__ == "__main__":
    job_start = time.time()
    logger.info(f"[{datetime.utcnow().isoformat()}] Starting F1 RAG ingestion job")

    try:
        # Step 1: Load config
        logger.info(f"[{datetime.utcnow().isoformat()}] Step 1: Loading config")
        from rag.config import RagConfig

        config = RagConfig()
        logger.info(f"Project: {config.PROJECT_ID}, Region: {config.REGION}")

        # Step 2: Initialize Vertex AI
        logger.info(f"[{datetime.utcnow().isoformat()}] Step 2: Initializing Vertex AI")
        import vertexai

        vertexai.init(project=config.PROJECT_ID, location=config.REGION)

        # Step 3: Validate index
        logger.info(
            f"[{datetime.utcnow().isoformat()}] Step 3: Checking Vector Search index"
        )
        index_id = config.VECTOR_SEARCH_INDEX_ID

        if not index_id:
            from rag import vector_store

            logger.info("No index ID set — creating new Vector Search index...")
            index_id = vector_store.create_index(
                project=config.PROJECT_ID,
                region=config.REGION,
                display_name="f1-rag-index",
                dimensions=config.EMBEDDING_DIMENSION,
            )
            print("INDEX CREATED:", index_id)
            print("Next steps:")
            print("  1. Deploy the index to an endpoint in GCP Console")
            print(f"  2. Set VECTOR_SEARCH_INDEX_ID={index_id}")
            print("  3. Set VECTOR_SEARCH_ENDPOINT_ID=<endpoint_id>")
            print("  4. Set VECTOR_SEARCH_DEPLOYED_INDEX_ID=<deployed_id>")
            print("  5. Re-run this job to upsert vectors")
            elapsed = time.time() - job_start
            logger.info(
                f"Job completed in {elapsed:.1f}s (index created, manual steps required)"
            )
            sys.exit(0)

        # Step 4: Stream GCS data lake in batches → embed → upsert
        logger.info(
            f"[{datetime.utcnow().isoformat()}] Step 4: Streaming GCS files "
            f"in batches of {_FILE_BATCH_SIZE} → embed → upsert"
        )
        total_gcs = _process_in_batches(config, index_id)
        logger.info(f"GCS data lake: {total_gcs} vectors upserted")

        # Step 5: Text documents (FIA regulations, circuit guides) — small, load all at once
        logger.info(
            f"[{datetime.utcnow().isoformat()}] Step 5: Ingesting text documents"
        )
        from rag.document_fetcher import fetch_all_text_documents
        from rag.embedder import embed_documents
        from rag import vector_store

        text_docs = fetch_all_text_documents(
            bucket=config.GCS_DATA_BUCKET,
            force_refresh=False,
        )
        logger.info(f"Loaded {len(text_docs)} text documents")

        if text_docs:
            text_pairs = embed_documents(
                text_docs,
                batch_size=config.EMBEDDING_BATCH_SIZE,
                sleep_seconds=config.EMBEDDING_BATCH_SLEEP_SECONDS,
                model_name=config.EMBEDDING_MODEL,
            )
            vector_store.upsert_vectors(
                index_id=index_id,
                project=config.PROJECT_ID,
                region=config.REGION,
                documents=[p[0] for p in text_pairs],
                embeddings=[p[1] for p in text_pairs],
                metadata_bucket=config.GCS_MODELS_BUCKET,
                metadata_gcs_path=config.METADATA_GCS_PATH,
            )
            logger.info(f"Text documents: {len(text_pairs)} vectors upserted")

        elapsed = time.time() - job_start
        logger.info(
            f"[{datetime.utcnow().isoformat()}] Job completed successfully in {elapsed:.1f}s "
            f"— total vectors: {total_gcs + len(text_pairs if text_docs else [])}"
        )
        sys.exit(0)

    except Exception as e:
        logger.exception(f"Ingestion job failed: {e}")
        sys.exit(1)
