from google.cloud import aiplatform
from google.cloud import storage
from google.cloud.exceptions import NotFound
from google.cloud.aiplatform.compat.types import matching_engine_index as gca_index
from langchain_core.documents import Document
import uuid
import json
import logging

logger = logging.getLogger(__name__)


def create_index(
    project: str,
    region: str,
    display_name: str = "f1-rag-index",
    dimensions: int = 768,
) -> str:
    """
    Create a Vertex AI Vector Search index.
    Settings:
      dimensions = dimensions param
      distance_measure_type = DOT_PRODUCT_DISTANCE
      shard_size = SHARD_SIZE_SMALL
      index_update_method = STREAM_UPDATE
    Waits for the operation to complete.
    Prints: "Index created: {resource_name}"
    Prints: "Set env var: VECTOR_SEARCH_INDEX_ID={index_id}"
    Returns the index_id string.
    """
    aiplatform.init(project=project, location=region)

    index = aiplatform.MatchingEngineIndex.create_tree_ah_index(
        display_name=display_name,
        dimensions=dimensions,
        distance_measure_type="DOT_PRODUCT_DISTANCE",
        shard_size="SHARD_SIZE_SMALL",
        index_update_method="STREAM_UPDATE",
        sync=True,
    )

    resource_name = index.resource_name
    # Extract the numeric index ID from the resource name
    # Format: projects/{project}/locations/{region}/indexes/{index_id}
    index_id = resource_name.split("/")[-1]

    print(f"Index created: {resource_name}")
    print(f"Set env var: VECTOR_SEARCH_INDEX_ID={index_id}")

    return index_id


def save_metadata(
    documents: list[Document],
    doc_ids: list[str],
    bucket: str,
    gcs_path: str,
) -> None:
    """
    Save document metadata to GCS as JSON.
    Format: { "doc_id": {"page_content": "...", "metadata": {...}}, ... }
    Merges with existing metadata to preserve prior ingestion runs.
    Writes to gs://{bucket}/{gcs_path}.
    """
    # Load existing metadata to preserve prior ingestion runs
    existing = load_metadata(bucket, gcs_path)

    new_entries = {
        doc_id: {
            "page_content": doc.page_content,
            "metadata": doc.metadata,
        }
        for doc_id, doc in zip(doc_ids, documents)
    }
    existing.update(new_entries)

    client = storage.Client()
    bucket_obj = client.bucket(bucket)
    blob = bucket_obj.blob(gcs_path)
    blob.upload_from_string(
        json.dumps(existing),
        content_type="application/json",
    )
    logger.info(f"Saved metadata for {len(documents)} new documents (total: {len(existing)}) to gs://{bucket}/{gcs_path}")


def load_metadata(bucket: str, gcs_path: str) -> dict:
    """
    Load metadata JSON from GCS.
    Returns empty dict if file does not exist (first run).
    Raises on any other GCS error.
    """
    client = storage.Client()
    bucket_obj = client.bucket(bucket)
    blob = bucket_obj.blob(gcs_path)

    try:
        data = blob.download_as_text()
        return json.loads(data)
    except NotFound:
        logger.info(f"No metadata found at gs://{bucket}/{gcs_path} (first run)")
        return {}


def upsert_vectors(
    index_id: str,
    project: str,
    region: str,
    documents: list[Document],
    embeddings: list[list[float]],
    metadata_bucket: str,
    metadata_gcs_path: str,
    batch_size: int = 100,
) -> None:
    """
    Upsert document vectors to Vertex AI Vector Search index.
    Generates a UUID for each document.
    Saves metadata to GCS before upserting.
    Upserts in batches of batch_size.
    """
    if not documents:
        logger.warning("upsert_vectors called with empty documents list; skipping")
        return

    aiplatform.init(project=project, location=region)

    doc_ids = [str(uuid.uuid4()) for _ in documents]

    # Save metadata first so IDs are resolvable before vectors are queryable
    save_metadata(documents, doc_ids, metadata_bucket, metadata_gcs_path)

    index = aiplatform.MatchingEngineIndex(index_name=index_id)

    for i in range(0, len(documents), batch_size):
        batch_ids = doc_ids[i : i + batch_size]
        batch_embeddings = embeddings[i : i + batch_size]

        datapoints = [
            gca_index.IndexDatapoint(
                datapoint_id=doc_id,
                feature_vector=embedding,
            )
            for doc_id, embedding in zip(batch_ids, batch_embeddings)
        ]

        index.upsert_datapoints(datapoints=datapoints)
        logger.info(
            f"Upserted batch {i // batch_size + 1} "
            f"({len(batch_ids)} vectors, total so far: {i + len(batch_ids)})"
        )

    logger.info(f"Upserted {len(documents)} vectors to index {index_id}")


def query_index(
    index_endpoint_id: str,
    deployed_index_id: str,
    project: str,
    region: str,
    query_embedding: list[float],
    top_k: int,
    metadata_bucket: str,
    metadata_gcs_path: str,
    filter_season: int | None = None,
    filter_race: str | None = None,
    filter_driver: str | None = None,
) -> list[Document]:
    """
    Query the deployed Vertex AI Vector Search endpoint.
    Loads metadata from GCS to resolve IDs back to Documents.
    Applies post-retrieval metadata filters if provided.
    Returns top_k most relevant Documents after filtering.
    Returns [] if no results found.
    """
    aiplatform.init(project=project, location=region)

    metadata = load_metadata(metadata_bucket, metadata_gcs_path)
    if not metadata:
        logger.warning("No metadata loaded; cannot resolve query results to documents")
        return []

    endpoint = aiplatform.MatchingEngineIndexEndpoint(
        index_endpoint_name=index_endpoint_id
    )

    # Over-fetch 3x when filtering to account for post-filter drop rate
    fetch_k = top_k * 3 if any([filter_season, filter_race, filter_driver]) else top_k

    response = endpoint.find_neighbors(
        deployed_index_id=deployed_index_id,
        queries=[query_embedding],
        num_neighbors=fetch_k,
    )

    if not response or not response[0]:
        return []

    neighbors = response[0]
    documents: list[Document] = []

    for neighbor in neighbors:
        doc_id = neighbor.id
        entry = metadata.get(doc_id)
        if not entry:
            continue

        doc = Document(
            page_content=entry["page_content"],
            metadata=entry.get("metadata", {}),
        )

        # Post-retrieval metadata filters
        meta = doc.metadata
        if filter_season is not None and meta.get("season") != filter_season:
            continue
        if filter_race is not None and meta.get("race") != filter_race:
            continue
        if filter_driver is not None and meta.get("driver") != filter_driver:
            continue

        documents.append(doc)

        if len(documents) >= top_k:
            break

    return documents
