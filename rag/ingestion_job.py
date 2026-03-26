import sys
import logging
import time
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


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

        # Step 3: Load all documents from GCS
        logger.info(f"[{datetime.utcnow().isoformat()}] Step 3: Loading documents from GCS")
        from rag.chunker import load_all_documents
        documents = load_all_documents(config.GCS_DATA_BUCKET)
        logger.info(f"Loaded {len(documents)} documents from GCS")

        # Step 4: Embed all documents
        logger.info(f"[{datetime.utcnow().isoformat()}] Step 4: Generating embeddings")
        from rag.embedder import embed_documents
        doc_embedding_pairs = embed_documents(
            documents,
            batch_size=config.EMBEDDING_BATCH_SIZE,
            sleep_seconds=config.EMBEDDING_BATCH_SLEEP_SECONDS,
            model_name=config.EMBEDDING_MODEL,
        )
        if doc_embedding_pairs and not (isinstance(doc_embedding_pairs[0], tuple) and len(doc_embedding_pairs[0]) == 2):
            raise RuntimeError(f"Unexpected embed_documents return shape: {type(doc_embedding_pairs[0])}")
        docs_embedded = [pair[0] for pair in doc_embedding_pairs]
        embeddings = [pair[1] for pair in doc_embedding_pairs]
        logger.info(f"Generated {len(embeddings)} embeddings")

        # Step 5: Check if index exists
        logger.info(f"[{datetime.utcnow().isoformat()}] Step 5: Checking Vector Search index")
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
            logger.info(f"Job completed in {elapsed:.1f}s (index created, manual steps required)")
            sys.exit(0)
        else:
            from rag import vector_store
            logger.info(f"Upserting {len(docs_embedded)} vectors to index {index_id}")
            vector_store.upsert_vectors(
                index_id=index_id,
                project=config.PROJECT_ID,
                region=config.REGION,
                documents=docs_embedded,
                embeddings=embeddings,
                metadata_bucket=config.GCS_MODELS_BUCKET,
                metadata_gcs_path=config.METADATA_GCS_PATH,
            )
            logger.info(f"Upserted {len(docs_embedded)} vectors to index {index_id}")

        elapsed = time.time() - job_start
        logger.info(f"[{datetime.utcnow().isoformat()}] Job completed successfully in {elapsed:.1f}s")
        sys.exit(0)

    except Exception as e:
        logger.exception(f"Ingestion job failed: {e}")
        sys.exit(1)
