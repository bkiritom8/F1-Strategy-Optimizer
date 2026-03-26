import re
import logging
import requests
from langchain_core.documents import Document
from google.cloud import storage

logger = logging.getLogger(__name__)

DOCUMENTS = {
    "fia_sporting_regs_2024": {
        "url": "https://www.fia.com/sites/default/files/2024_formula_1_sporting_regulations_-_issue_7_-_2024-07-31.pdf",
        "type": "pdf",
        "metadata": {
            "source": "FIA",
            "doc_type": "sporting_regulations",
            "season": 2024,
            "category": "regulations",
        },
    },
    "fia_technical_regs_2024": {
        "url": "https://www.fia.com/sites/default/files/2024_formula_1_technical_regulations_-_issue_7_-_2024-07-31.pdf",
        "type": "pdf",
        "metadata": {
            "source": "FIA",
            "doc_type": "technical_regulations",
            "season": 2024,
            "category": "regulations",
        },
    },
}

CIRCUIT_GUIDES = [
    {
        "name": "Bahrain Grand Prix",
        "url": "https://www.formula1.com/en/racing/2024/bahrain",
        "metadata": {"race": "Bahrain Grand Prix", "season": 2024, "category": "circuit_guide"},
    },
    {
        "name": "Saudi Arabian Grand Prix",
        "url": "https://www.formula1.com/en/racing/2024/saudi-arabia",
        "metadata": {"race": "Saudi Arabian Grand Prix", "season": 2024, "category": "circuit_guide"},
    },
    {
        "name": "Australian Grand Prix",
        "url": "https://www.formula1.com/en/racing/2024/australia",
        "metadata": {"race": "Australian Grand Prix", "season": 2024, "category": "circuit_guide"},
    },
    {
        "name": "Japanese Grand Prix",
        "url": "https://www.formula1.com/en/racing/2024/japan",
        "metadata": {"race": "Japanese Grand Prix", "season": 2024, "category": "circuit_guide"},
    },
    {
        "name": "Chinese Grand Prix",
        "url": "https://www.formula1.com/en/racing/2024/china",
        "metadata": {"race": "Chinese Grand Prix", "season": 2024, "category": "circuit_guide"},
    },
    {
        "name": "Miami Grand Prix",
        "url": "https://www.formula1.com/en/racing/2024/miami",
        "metadata": {"race": "Miami Grand Prix", "season": 2024, "category": "circuit_guide"},
    },
    {
        "name": "Emilia Romagna Grand Prix",
        "url": "https://www.formula1.com/en/racing/2024/emilia-romagna",
        "metadata": {"race": "Emilia Romagna Grand Prix", "season": 2024, "category": "circuit_guide"},
    },
    {
        "name": "Monaco Grand Prix",
        "url": "https://www.formula1.com/en/racing/2024/monaco",
        "metadata": {"race": "Monaco Grand Prix", "season": 2024, "category": "circuit_guide"},
    },
    {
        "name": "Canadian Grand Prix",
        "url": "https://www.formula1.com/en/racing/2024/canada",
        "metadata": {"race": "Canadian Grand Prix", "season": 2024, "category": "circuit_guide"},
    },
    {
        "name": "Spanish Grand Prix",
        "url": "https://www.formula1.com/en/racing/2024/spain",
        "metadata": {"race": "Spanish Grand Prix", "season": 2024, "category": "circuit_guide"},
    },
    {
        "name": "Austrian Grand Prix",
        "url": "https://www.formula1.com/en/racing/2024/austria",
        "metadata": {"race": "Austrian Grand Prix", "season": 2024, "category": "circuit_guide"},
    },
    {
        "name": "British Grand Prix",
        "url": "https://www.formula1.com/en/racing/2024/great-britain",
        "metadata": {"race": "British Grand Prix", "season": 2024, "category": "circuit_guide"},
    },
    {
        "name": "Hungarian Grand Prix",
        "url": "https://www.formula1.com/en/racing/2024/hungary",
        "metadata": {"race": "Hungarian Grand Prix", "season": 2024, "category": "circuit_guide"},
    },
    {
        "name": "Belgian Grand Prix",
        "url": "https://www.formula1.com/en/racing/2024/belgium",
        "metadata": {"race": "Belgian Grand Prix", "season": 2024, "category": "circuit_guide"},
    },
    {
        "name": "Dutch Grand Prix",
        "url": "https://www.formula1.com/en/racing/2024/netherlands",
        "metadata": {"race": "Dutch Grand Prix", "season": 2024, "category": "circuit_guide"},
    },
    {
        "name": "Italian Grand Prix",
        "url": "https://www.formula1.com/en/racing/2024/italy",
        "metadata": {"race": "Italian Grand Prix", "season": 2024, "category": "circuit_guide"},
    },
    {
        "name": "Azerbaijan Grand Prix",
        "url": "https://www.formula1.com/en/racing/2024/azerbaijan",
        "metadata": {"race": "Azerbaijan Grand Prix", "season": 2024, "category": "circuit_guide"},
    },
    {
        "name": "Singapore Grand Prix",
        "url": "https://www.formula1.com/en/racing/2024/singapore",
        "metadata": {"race": "Singapore Grand Prix", "season": 2024, "category": "circuit_guide"},
    },
    {
        "name": "United States Grand Prix",
        "url": "https://www.formula1.com/en/racing/2024/united-states",
        "metadata": {"race": "United States Grand Prix", "season": 2024, "category": "circuit_guide"},
    },
    {
        "name": "Mexico City Grand Prix",
        "url": "https://www.formula1.com/en/racing/2024/mexico",
        "metadata": {"race": "Mexico City Grand Prix", "season": 2024, "category": "circuit_guide"},
    },
    {
        "name": "São Paulo Grand Prix",
        "url": "https://www.formula1.com/en/racing/2024/brazil",
        "metadata": {"race": "São Paulo Grand Prix", "season": 2024, "category": "circuit_guide"},
    },
    {
        "name": "Las Vegas Grand Prix",
        "url": "https://www.formula1.com/en/racing/2024/las-vegas",
        "metadata": {"race": "Las Vegas Grand Prix", "season": 2024, "category": "circuit_guide"},
    },
    {
        "name": "Qatar Grand Prix",
        "url": "https://www.formula1.com/en/racing/2024/qatar",
        "metadata": {"race": "Qatar Grand Prix", "season": 2024, "category": "circuit_guide"},
    },
    {
        "name": "Abu Dhabi Grand Prix",
        "url": "https://www.formula1.com/en/racing/2024/abu-dhabi",
        "metadata": {"race": "Abu Dhabi Grand Prix", "season": 2024, "category": "circuit_guide"},
    },
]

_ARTICLE_RE = re.compile(r"(Article\s+\d+)", re.IGNORECASE)


def download_pdf(url: str) -> bytes:
    """Download a PDF from a URL.

    Sets a browser-like User-Agent header to avoid 403 errors.
    Raises requests.HTTPError on failure. Times out after 30 seconds.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.content


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pypdf.

    Returns extracted text as a single string.
    Returns empty string if extraction fails, logs warning.
    """
    try:
        import io
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_bytes))
        parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                parts.append(text)
        return "\n".join(parts)
    except Exception as e:
        logger.warning(f"PDF text extraction failed: {e}")
        return ""


def chunk_regulation_text(
    text: str,
    source_metadata: dict,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
) -> list[Document]:
    """Chunk regulation text into overlapping windows.

    Splits on Article boundaries first. Falls back to fixed-size windows
    for text without Articles or for articles longer than chunk_size.

    Each Document carries source_metadata fields plus:
      - article: str | None  (e.g. "Article 28" if detected)
      - chunk_index: int
    """
    if not text or not text.strip():
        return []

    # Split on Article boundaries
    parts = _ARTICLE_RE.split(text)
    # parts alternates: [pre-article text, "Article N", article body, "Article M", body, ...]

    segments: list[tuple[str | None, str]] = []  # (article_label, content)

    if len(parts) == 1:
        # No articles found — treat whole text as one segment
        segments.append((None, text))
    else:
        # parts[0] is preamble before first article
        if parts[0].strip():
            segments.append((None, parts[0]))
        # Remaining parts come in pairs: article label, article body
        for i in range(1, len(parts), 2):
            label = parts[i].strip()
            body = parts[i + 1] if i + 1 < len(parts) else ""
            segments.append((label, body))

    documents: list[Document] = []
    for article_label, content in segments:
        content = content.strip()
        if not content:
            continue

        if len(content) <= chunk_size:
            chunk_text = f"{article_label}\n{content}" if article_label else content
            documents.append(
                Document(
                    page_content=chunk_text,
                    metadata={
                        **source_metadata,
                        "article": article_label,
                        "chunk_index": len(documents),
                    },
                )
            )
        else:
            # Split long article into overlapping fixed-size windows
            start = 0
            while start < len(content):
                end = start + chunk_size
                window = content[start:end]
                prefix = f"{article_label}\n" if article_label else ""
                documents.append(
                    Document(
                        page_content=prefix + window,
                        metadata={
                            **source_metadata,
                            "article": article_label,
                            "chunk_index": len(documents),
                        },
                    )
                )
                if end >= len(content):
                    break
                start = end - chunk_overlap

    return documents


def scrape_circuit_guide(url: str, race_metadata: dict) -> list[Document]:
    """Scrape circuit guide text from F1 website.

    Uses requests + BeautifulSoup (no JavaScript needed).
    Returns [] if scraping fails, logs warning.
    """
    try:
        from bs4 import BeautifulSoup

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        text_parts = []

        # Circuit description paragraphs
        for p in soup.find_all("p"):
            txt = p.get_text(strip=True)
            if txt and len(txt) > 40:
                text_parts.append(txt)

        # Key stats from table-like elements
        for stat in soup.select("[class*='stat'], [class*='fact'], [class*='info']"):
            txt = stat.get_text(separator=" ", strip=True)
            if txt:
                text_parts.append(txt)

        if not text_parts:
            logger.warning(f"No usable text found at {url}")
            return []

        combined = "\n".join(text_parts)
        return [
            Document(
                page_content=combined,
                metadata={**race_metadata, "source_url": url},
            )
        ]
    except Exception as e:
        logger.warning(f"Circuit guide scrape failed for {url}: {e}")
        return []


def cache_document_to_gcs(content: bytes, bucket: str, gcs_path: str) -> None:
    """Upload raw document bytes to GCS for caching.

    Skips upload if file already exists in GCS (cache hit).
    """
    client = storage.Client()
    b = client.bucket(bucket)
    blob = b.blob(gcs_path)
    if blob.exists():
        return
    blob.upload_from_string(content)
    logger.info(f"Cached document to gs://{bucket}/{gcs_path}")


def load_cached_document_from_gcs(bucket: str, gcs_path: str) -> bytes | None:
    """Download cached document from GCS. Returns None if not found."""
    try:
        client = storage.Client()
        b = client.bucket(bucket)
        blob = b.blob(gcs_path)
        if not blob.exists():
            return None
        return blob.download_as_bytes()
    except Exception as e:
        logger.warning(f"Failed to load cached document gs://{bucket}/{gcs_path}: {e}")
        return None


def fetch_all_text_documents(
    bucket: str,
    force_refresh: bool = False,
) -> list[Document]:
    """Main entry point. Downloads and chunks all text documents.

    For each document in DOCUMENTS:
      1. Check GCS cache (rag/documents/) unless force_refresh=True
      2. If not cached: download, cache to GCS, extract text
      3. If cached: load from GCS
      4. Chunk into Documents

    For each circuit in CIRCUIT_GUIDES:
      1. Scrape circuit guide
      2. Add to documents list

    Logs progress for each document.
    Returns all Documents as flat list.
    Skips failed documents with a warning, does not raise.
    """
    all_docs: list[Document] = []

    for doc_key, doc_info in DOCUMENTS.items():
        url = doc_info["url"]
        doc_type = doc_info["type"]
        metadata = doc_info["metadata"]
        gcs_path = f"rag/documents/{doc_key}/{doc_key}.{doc_type}"

        logger.info(f"Processing document: {doc_key}")
        try:
            raw: bytes | None = None

            if not force_refresh:
                raw = load_cached_document_from_gcs(bucket, gcs_path)

            if raw is None:
                logger.info(f"Downloading {doc_key} from {url}")
                raw = download_pdf(url)
                cache_document_to_gcs(raw, bucket, gcs_path)

            text = extract_pdf_text(raw)
            if not text:
                logger.warning(f"No text extracted from {doc_key}")
                continue

            chunks = chunk_regulation_text(text, metadata)
            logger.info(f"Chunked {doc_key} into {len(chunks)} documents")
            all_docs.extend(chunks)

        except Exception as e:
            logger.warning(f"Skipping {doc_key}: {e}")
            continue

    for circuit in CIRCUIT_GUIDES:
        logger.info(f"Scraping circuit guide: {circuit['name']}")
        try:
            docs = scrape_circuit_guide(circuit["url"], circuit["metadata"])
            all_docs.extend(docs)
        except Exception as e:
            logger.warning(f"Skipping circuit guide {circuit['name']}: {e}")
            continue

    logger.info(f"fetch_all_text_documents: returning {len(all_docs)} total documents")
    return all_docs
