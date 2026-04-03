from langchain_core.documents import Document
from google.cloud import storage
import pandas as pd
import io
import re
import logging

logger = logging.getLogger(__name__)


def _parse_gcs_uri(gcs_uri: str):
    """Parse gs://bucket/path into (bucket, blob_path)."""
    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"Invalid GCS URI: {gcs_uri}")
    parts = gcs_uri[5:].split("/", 1)
    return parts[0], parts[1] if len(parts) > 1 else ""


def _extract_season(path: str) -> int | None:
    """Extract 4-digit year from a GCS path."""
    match = re.search(r"/(\d{4})/", path)
    return int(match.group(1)) if match else None


def _extract_race(path: str) -> str | None:
    """Extract race name from a GCS path (directory segment after year)."""
    match = re.search(r"/\d{4}/([^/]+)/", path)
    return match.group(1) if match else None


def _extract_session(filename: str) -> str | None:
    """Extract session type (FP1/FP2/FP3/Q/R) from filename."""
    match = re.search(r"_(FP1|FP2|FP3|Q|R)[_\.]", filename)
    return match.group(1) if match else None


def _is_null(v) -> bool:
    """Return True if v is None or a scalar NA value."""
    if v is None:
        return True
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _read_gcs_bytes(gcs_uri: str, client: storage.Client | None = None) -> bytes | None:
    """Read raw bytes from GCS URI. Returns None on error."""
    try:
        bucket_name, blob_path = _parse_gcs_uri(gcs_uri)
        _client = client or storage.Client()
        bucket = _client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        return blob.download_as_bytes()
    except Exception as e:
        logger.warning(f"Failed to read {gcs_uri}: {e}")
        return None


def chunk_parquet(gcs_uri: str, client: storage.Client | None = None) -> list[Document]:
    """
    Read a parquet file from GCS and convert each row to a natural language Document.

    Column mapping (uses whichever columns are present):
      Telemetry/lap rows (Driver, LapNumber, LapTime present):
        "In the {Year} {EventName}, {Driver} completed lap {LapNumber}
         in {LapTime} on {Compound} tyres from position {Position}."

      Race result rows (positionOrder, constructorRef present):
        "In the {year} {raceName}, {driverRef} finished P{positionOrder}
         for {constructorRef}, starting P{grid}. Points: {points}."

      Pit stop rows (stop, duration, lap present):
        "{driverRef} pitted on lap {lap} of the {year} {raceName},
         taking {duration}s. Stop number {stop}."

    Returns [] if file cannot be read.
    """
    raw = _read_gcs_bytes(gcs_uri, client=client)
    if raw is None:
        return []

    try:
        df = pd.read_parquet(io.BytesIO(raw))
    except Exception as e:
        logger.warning(f"Failed to parse parquet {gcs_uri}: {e}")
        return []

    if df.empty:
        return []

    cols = set(df.columns)
    filename = gcs_uri.split("/")[-1]
    base_meta = {
        "source_file": gcs_uri,
        "source_type": "parquet",
        "season": _extract_season(gcs_uri),
        "race": _extract_race(gcs_uri),
        "session": _extract_session(filename),
    }

    def get(row, col, default=""):
        val = row.get(col, default)
        try:
            if pd.isna(val):
                return ""
        except (TypeError, ValueError):
            pass
        return str(val)

    documents = []
    for _, row in df.iterrows():
        row = row.to_dict()

        # Detect template
        if {"Driver", "LapNumber", "LapTime"}.intersection(cols):
            # Telemetry/lap template
            key_vals = [row.get("Driver"), row.get("LapNumber"), row.get("LapTime")]
            if all(_is_null(v) for v in key_vals):
                continue
            text = (
                f"In the {get(row, 'Year')} {get(row, 'EventName')}, "
                f"{get(row, 'Driver')} completed lap {get(row, 'LapNumber')} "
                f"in {get(row, 'LapTime')} on {get(row, 'Compound')} tyres "
                f"from position {get(row, 'Position')}."
            )
            driver = get(row, "Driver") or None
        elif {"positionOrder", "constructorRef"}.intersection(cols):
            # Race result template
            key_vals = [row.get("positionOrder"), row.get("driverRef")]
            if all(_is_null(v) for v in key_vals):
                continue
            year_val = get(row, "year") or str(base_meta.get("season") or "")
            race_val = get(row, "raceName") or str(base_meta.get("race") or "")
            driver_val = get(row, "driverRef") or get(row, "driver") or ""
            text = (
                f"In the {year_val} {race_val}, "
                f"{driver_val} finished P{get(row, 'positionOrder')} "
                f"for {get(row, 'constructorRef')}, starting P{get(row, 'grid')}. "
                f"Points: {get(row, 'points')}."
            )
            driver = driver_val or None
        elif {"stop", "duration"}.intersection(cols) and "lap" in cols:
            # Pit stop template
            key_vals = [row.get("driverRef"), row.get("lap")]
            if all(_is_null(v) for v in key_vals):
                continue
            year_val = get(row, "year") or str(base_meta.get("season") or "")
            race_val = get(row, "raceName") or str(base_meta.get("race") or "")
            driver_val = get(row, "driverRef") or get(row, "driver") or ""
            text = (
                f"{driver_val} pitted on lap {get(row, 'lap')} "
                f"of the {year_val} {race_val}, "
                f"taking {get(row, 'duration')}s. Stop number {get(row, 'stop')}."
            )
            driver = driver_val or None
        else:
            # Generic fallback: join non-null values
            non_null = {k: v for k, v in row.items() if not _is_null(v)}
            if not non_null:
                continue
            text = " | ".join(f"{k}: {v}" for k, v in list(non_null.items())[:10])
            driver = None

        meta = {**base_meta, "driver": driver or None}
        documents.append(Document(page_content=text, metadata=meta))

    return documents


def chunk_csv(gcs_uri: str, client: storage.Client | None = None) -> list[Document]:
    """
    Read a CSV from GCS and convert rows to natural language Documents.
    Template inferred from filename.
    Returns [] if file cannot be read.
    """
    raw = _read_gcs_bytes(gcs_uri, client=client)
    if raw is None:
        return []

    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as e:
        logger.warning(f"Failed to parse CSV {gcs_uri}: {e}")
        return []

    if df.empty:
        return []

    filename = gcs_uri.split("/")[-1].lower()
    base_meta = {
        "source_file": gcs_uri,
        "source_type": "csv",
        "season": _extract_season(gcs_uri),
        "race": _extract_race(gcs_uri),
        "session": _extract_session(filename),
    }

    def get(row, col, default=""):
        val = row.get(col, default)
        try:
            if pd.isna(val):
                return ""
        except (TypeError, ValueError):
            pass
        return str(val)

    documents = []
    for _, row in df.iterrows():
        row = row.to_dict()
        driver = None

        if filename.startswith("race_results"):
            year_val = get(row, "year") or str(base_meta.get("season") or "")
            race_val = get(row, "raceName") or str(base_meta.get("race") or "")
            driver_val = get(row, "driverRef") or get(row, "driver") or ""
            text = (
                f"{driver_val} finished P{get(row, 'positionOrder')} for "
                f"{get(row, 'constructorRef')} in the {year_val} {race_val}, "
                f"starting P{get(row, 'grid')}. Points: {get(row, 'points')}."
            )
            driver = driver_val or None
        elif filename.startswith("pit_stops"):
            year_val = get(row, "year") or str(base_meta.get("season") or "")
            race_val = get(row, "raceName") or str(base_meta.get("race") or "")
            driver_val = get(row, "driverRef") or get(row, "driver") or ""
            text = (
                f"{driver_val} pitted on lap {get(row, 'lap')} of the "
                f"{year_val} {race_val}, taking {get(row, 'duration')}s."
            )
            driver = driver_val or None
        elif filename.startswith("lap_times"):
            text = (
                f"{get(row, 'driverRef')} set a lap time of {get(row, 'milliseconds')}ms "
                f"on lap {get(row, 'lap')} of the {get(row, 'year')} {get(row, 'raceName')}."
            )
            driver = get(row, "driverRef") or None
        elif filename.startswith("drivers"):
            text = (
                f"{get(row, 'forename')} {get(row, 'surname')} ({get(row, 'code')}) represented "
                f"{get(row, 'nationality')}. dob: {get(row, 'dob')}."
            )
            driver = get(row, "driverRef") or None
        elif filename.startswith("circuits"):
            text = f"{get(row, 'name')} circuit in {get(row, 'location')}, {get(row, 'country')}."
        elif filename.startswith("constructor_standings"):
            text = (
                f"{get(row, 'constructorRef')} finished P{get(row, 'position')} "
                f"in the {get(row, 'year')} constructors championship "
                f"with {get(row, 'points')} points and {get(row, 'wins')} wins."
            )
        elif filename.startswith("qualifying"):
            text = (
                f"{get(row, 'driverRef')} qualified P{get(row, 'position')} "
                f"for the {get(row, 'year')} {get(row, 'raceName')} "
                f"with a best lap of {get(row, 'q3') or get(row, 'q2') or get(row, 'q1')}."
            )
            driver = get(row, "driverRef") or None
        elif filename.startswith("standings"):
            text = (
                f"{get(row, 'driverRef')} finished the {get(row, 'year')} season "
                f"P{get(row, 'position')} with {get(row, 'points')} points."
            )
            driver = get(row, "driverRef") or None
        else:
            # Generic fallback
            non_null = {k: v for k, v in row.items() if not _is_null(v)}
            if not non_null:
                continue
            text = " | ".join(f"{k}: {v}" for k, v in list(non_null.items())[:10])

        meta = {**base_meta, "driver": driver or None}
        documents.append(Document(page_content=text, metadata=meta))

    return documents


def chunk_driver_season_summary(
    df: pd.DataFrame, season: int, source_file: str
) -> list[Document]:
    """
    Generate per-driver season summary Documents from a laps DataFrame.
    Aggregates stats per driver across all laps in a season.
    """
    if df.empty:
        return []

    driver_col = "Driver" if "Driver" in df.columns else "driverRef"
    lap_time_col = "LapTime" if "LapTime" in df.columns else "time"

    if driver_col not in df.columns:
        return []

    documents = []
    for driver, group in df.groupby(driver_col):
        if _is_null(driver):
            continue
        total_laps = len(group)
        if lap_time_col in group.columns:
            lt = pd.to_numeric(group[lap_time_col], errors="coerce").dropna()
            mean_lt = round(float(lt.mean()), 3) if not lt.empty else None
            best_lt = round(float(lt.min()), 3) if not lt.empty else None
        else:
            mean_lt = best_lt = None

        text = f"In the {season} F1 season, {driver} completed {total_laps} laps"
        if mean_lt:
            text += f" with an average lap time of {mean_lt}s"
        if best_lt:
            text += f" and a best lap time of {best_lt}s"
        text += "."

        documents.append(
            Document(
                page_content=text,
                metadata={
                    "source_file": source_file,
                    "source_type": "season_summary",
                    "season": season,
                    "driver": str(driver),
                    "race": None,
                    "session": None,
                },
            )
        )
    return documents


def load_all_documents(bucket: str) -> list[Document]:
    """
    Walk entire GCS bucket, call appropriate chunker per file.
    Skips: *.ff1pkl, *.sqlite, rag/*, htmlcov/*, *.pyc
    Logs progress every 100 files. Returns flat list of all Documents.
    """
    skip_patterns = [".ff1pkl", ".sqlite", ".pyc"]
    skip_prefixes = ["rag/", "htmlcov/", "telemetry/", "ml_features/", "raw/telemetry/"]
    skip_exact = {
        "processed/fastf1_telemetry.parquet",
        "processed/fastf1_laps.parquet",
        "processed/telemetry_all.parquet",
        "processed/telemetry_laps_all.parquet",
        "processed/laps_all.parquet",
        "raw/fastf1_telemetry.csv",
        "raw/fastf1_laps.csv",
    }

    try:
        client = storage.Client()
        blobs = list(client.list_blobs(bucket))
    except Exception as e:
        logger.warning(f"Failed to list bucket {bucket}: {e}")
        return []

    all_docs: list[Document] = []
    processed = 0

    for blob in blobs:
        name = blob.name

        # Apply skip rules
        if any(name.endswith(pat) for pat in skip_patterns):
            continue
        if any(name.startswith(prefix) for prefix in skip_prefixes):
            continue
        if name in skip_exact:
            continue

        gcs_uri = f"gs://{bucket}/{name}"

        if name.endswith(".parquet"):
            docs = chunk_parquet(gcs_uri, client=client)
        elif name.endswith(".csv"):
            docs = chunk_csv(gcs_uri, client=client)
        else:
            continue

        all_docs.extend(docs)
        processed += 1

        if processed % 100 == 0:
            logger.info(
                f"Processed {processed} files, {len(all_docs)} documents so far..."
            )

    logger.info(f"Total documents loaded: {len(all_docs)} from {processed} files")
    return all_docs


def iter_gcs_uris(bucket: str):
    """
    Yield (gcs_uri, file_type) for every processable file in the bucket
    without downloading content. file_type is 'parquet' or 'csv'.

    Used by the batched ingestion path to avoid loading all files into memory.
    """
    skip_patterns = [".ff1pkl", ".sqlite", ".pyc"]
    # Skip RAG internals, coverage artifacts, raw telemetry (10Hz sensor data —
    # not useful as retrieval context), and ML feature tables (numerical, not factual).
    skip_prefixes = ["rag/", "htmlcov/", "telemetry/", "ml_features/", "raw/telemetry/"]
    skip_exact = {
        "processed/fastf1_telemetry.parquet",
        "processed/fastf1_laps.parquet",
        "processed/telemetry_all.parquet",
        "processed/telemetry_laps_all.parquet",
        "processed/laps_all.parquet",
        "raw/fastf1_telemetry.csv",
        "raw/fastf1_laps.csv",
    }

    try:
        client = storage.Client()
        blobs = client.list_blobs(bucket)
    except Exception as e:
        logger.warning(f"Failed to list bucket {bucket}: {e}")
        return

    for blob in blobs:
        name = blob.name
        if any(name.endswith(pat) for pat in skip_patterns):
            continue
        if any(name.startswith(prefix) for prefix in skip_prefixes):
            continue
        if name in skip_exact:
            continue
        if name.endswith(".parquet"):
            yield f"gs://{bucket}/{name}", "parquet"
        elif name.endswith(".csv"):
            yield f"gs://{bucket}/{name}", "csv"


def chunk_uri(gcs_uri: str, file_type: str, client=None) -> list[Document]:
    """Chunk a single GCS file by type. Returns [] on error."""
    if file_type == "parquet":
        return chunk_parquet(gcs_uri, client=client)
    if file_type == "csv":
        return chunk_csv(gcs_uri, client=client)
    return []
