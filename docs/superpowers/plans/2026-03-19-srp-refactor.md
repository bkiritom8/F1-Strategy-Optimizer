# SRP Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor all five layers of the codebase to enforce single responsibility principle per file, using extract-and-delegate so callers see no import breakage.

**Architecture:** Each original file is preserved as a thin orchestrator that imports from extracted siblings. New files own exactly one concern each. All five layers are committed independently.

**Tech Stack:** Python, FastAPI, GCS, KFP v2, XGBoost/LightGBM, Pydantic v2, bcrypt, python-jose

---

## Constraints (read before every task)

- **No tests changed** — tests are a follow-up layer
- **No import breakage** — original filenames remain, callers unchanged
- **One commit per layer**
- **No behavioral changes** — structural refactor only
- `upload_parquet` canonical signature: `(df, bucket, blob_path)` — fix any callers with wrong arg order in the same layer commit

---

## Layer 1: `ingest/`

**Files to create:**
- `ingest/http_utils.py` — rate-limited GET, backoff, retry_forever
- `ingest/jolpica_client.py` — Jolpica pagination + JSON fetch
- `ingest/telemetry_extractor.py` — FastF1 per-lap telemetry extraction

**Files to modify:**
- `ingest/gcs_utils.py` — add `blob_exists`
- `ingest/gap_worker.py` — remove duplicated helpers, fix `upload_parquet` arg order
- `ingest/fastf1_worker.py` — remove `_is_rate_limit`, `_backoff_wait`, `_extract_telemetry`
- `ingest/historical_worker.py` — remove `_get`, `_is_rate_limit`, `_backoff_wait`, `_fetch_json_retry`, `_paginate`
- `ingest/lap_times_worker.py` — remove HTTP + GCS helpers, fix `upload_parquet` arg order

---

### Task 1.1: Create `ingest/http_utils.py`

**Files:** Create `ingest/http_utils.py`

- [ ] **Step 1: Write the file**

```python
"""http_utils.py — Rate-limited HTTP helpers for ingest workers."""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

import requests

log = logging.getLogger(__name__)

_last_req: float = 0.0
BACKOFF_BASE = 60
BACKOFF_CAP = 3_600


def rate_limited_get(url: str, gap: float = 1.0, timeout: int = 30) -> requests.Response:
    """HTTP GET with rate limiting. *gap* = min seconds between calls."""
    global _last_req
    elapsed = time.monotonic() - _last_req
    if elapsed < gap:
        time.sleep(gap - elapsed)
    resp = requests.get(url, timeout=timeout)
    _last_req = time.monotonic()
    return resp


def is_rate_limit(exc: Exception) -> bool:
    s = f"{type(exc).__name__} {exc}".lower()
    return "rate limit" in s or "429" in s or "ratelimit" in s


def backoff_wait(attempt: int) -> float:
    wait = min(BACKOFF_BASE * (2 ** attempt), BACKOFF_CAP)
    log.warning("backoff: sleeping %.0fs (attempt %d)", wait, attempt + 1)
    time.sleep(wait)
    return wait


def retry_forever(fn: Callable, label: str, retry_sleep: int = 3600) -> Any:
    """Call *fn()* in a loop; on any exception sleep *retry_sleep* s and retry."""
    attempt = 0
    while True:
        try:
            return fn()
        except Exception as exc:
            attempt += 1
            log.error(
                "error — will retry after %ds  label=%s attempt=%d: %s: %s",
                retry_sleep, label, attempt, type(exc).__name__, exc,
            )
            time.sleep(retry_sleep)
```

- [ ] **Step 2: Verify import**

```bash
cd /Users/bhargav/Documents/F1-Strategy-Optimizer
python -c "from ingest.http_utils import rate_limited_get, backoff_wait, retry_forever; print('OK')"
```

Expected: `OK`

---

### Task 1.2: Create `ingest/jolpica_client.py`

**Files:** Create `ingest/jolpica_client.py`

- [ ] **Step 1: Write the file**

```python
"""jolpica_client.py — Jolpica/Ergast API pagination and JSON fetch."""
from __future__ import annotations

import logging
from typing import Any, Optional

from .http_utils import backoff_wait, is_rate_limit, rate_limited_get

log = logging.getLogger(__name__)


def fetch_json(url: str) -> Optional[dict[str, Any]]:
    """Fetch with infinite retry. Returns None on 404."""
    attempt = 0
    while True:
        try:
            resp = rate_limited_get(url)
            if resp.status_code == 404:
                return None
            if resp.status_code == 429:
                log.warning("rate limited 429  url=%s", url)
                backoff_wait(attempt)
                attempt += 1
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            if is_rate_limit(exc):
                log.warning("rate limit  url=%s: %s", url, exc)
            else:
                log.error(
                    "fetch error  url=%s attempt=%d: %s: %s",
                    url, attempt, type(exc).__name__, exc,
                )
            backoff_wait(attempt)
            attempt += 1


def paginate(base_url: str, limit: int = 100) -> list[dict[str, Any]]:
    """Page through a Jolpica endpoint, returning all records."""
    results: list[dict[str, Any]] = []
    offset = 0
    while True:
        data = fetch_json(f"{base_url}?limit={limit}&offset={offset}")
        if data is None:
            break
        mr = data.get("MRData", {})
        total = int(mr.get("total", 0))
        table = (
            mr.get("RaceTable")
            or mr.get("StandingsTable")
            or mr.get("SeasonTable")
            or {}
        )
        rows: list[dict[str, Any]] = []
        for val in table.values():
            if isinstance(val, list):
                rows = val
                break
        results.extend(rows)
        actual_limit = int(mr.get("limit", limit))
        offset += actual_limit
        if offset >= total or not rows:
            break
    return results
```

- [ ] **Step 2: Verify import**

```bash
python -c "from ingest.jolpica_client import fetch_json, paginate; print('OK')"
```

---

### Task 1.3: Create `ingest/telemetry_extractor.py`

**Files:** Create `ingest/telemetry_extractor.py`

- [ ] **Step 1: Write the file**

```python
"""telemetry_extractor.py — FastF1 per-lap telemetry extraction."""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

log = logging.getLogger(__name__)


def extract_telemetry(session) -> Optional[pd.DataFrame]:
    """
    Iterate every lap, call get_telemetry(), concatenate.
    Prepends Driver and LapNumber; all other columns are raw FastF1 output.
    """
    frames = []
    for _, lap in session.laps.iterlaps():
        try:
            tel = lap.get_telemetry()
            if tel is None or tel.empty:
                continue
            tel.insert(0, "LapNumber", lap["LapNumber"])
            tel.insert(0, "Driver", lap["Driver"])
            frames.append(tel)
        except Exception as exc:
            log.debug(
                "skipped lap %s/%s: %s",
                lap.get("Driver"), lap.get("LapNumber"), exc,
            )
    return pd.concat(frames, ignore_index=True) if frames else None
```

- [ ] **Step 2: Verify import**

```bash
python -c "from ingest.telemetry_extractor import extract_telemetry; print('OK')"
```

---

### Task 1.4: Add `blob_exists` to `ingest/gcs_utils.py`

**Files:** Modify `ingest/gcs_utils.py`

- [ ] **Step 1: Add `blob_exists` after the imports block**

Add to the end of `ingest/gcs_utils.py`:

```python
def blob_exists(bucket: storage.Bucket, path: str) -> bool:
    """Return True if *path* exists in *bucket*."""
    return bucket.blob(path).exists()
```

- [ ] **Step 2: Verify import**

```bash
python -c "from ingest.gcs_utils import blob_exists, upload_parquet, upload_done_marker; print('OK')"
```

---

### Task 1.5: Update `ingest/gap_worker.py`

**Files:** Modify `ingest/gap_worker.py`

gap_worker currently defines its own: `blob_exists`, `upload_parquet(bucket, path, df)` (wrong arg order), `upload_done_marker` (keep — different GCS path), `retry_forever`, `_extract_telemetry`, `_rate_get`, `_fetch_json`, `_paginate`.

- [ ] **Step 1: Add imports at the top of the file (after existing imports)**

Replace the existing imports block (lines 18-31) with:

```python
from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import requests
from google.cloud import storage

from .gcs_utils import blob_exists, upload_parquet
from .http_utils import retry_forever
from .jolpica_client import fetch_json, paginate
from .telemetry_extractor import extract_telemetry
```

- [ ] **Step 2: Remove the now-redundant local definitions**

Remove these functions from `gap_worker.py` (they are replaced by imports above):
- `def blob_exists(...)` (lines ~85-86)
- `def upload_parquet(bucket, path, df)` (lines ~89-94) — note arg order differs
- `def retry_forever(fn, label)` (lines ~108-118)
- `def _extract_telemetry(session)` (lines ~125-138)
- `def _rate_get(url)` (lines ~209-216)
- `def _fetch_json(url)` (lines ~219-238)
- `def _paginate(base_url, limit)` (lines ~241-262)

Keep: `upload_done_marker` (creates `status/job{N}.done`, different from gcs_utils), `_log/info/warn/error`, all config constants, `_download_session`, `run_fastf1_year`, `_fetch_race_results_year`, `_fetch_lap_times_round`, `run_historical`, `main`.

- [ ] **Step 3: Fix `upload_parquet` call arg order — wrong order in original**

In `_download_session` (was line ~164):
```python
# OLD: upload_parquet(bucket, blob_path, tel)
upload_parquet(tel, bucket, blob_path)
```

In `run_historical` (was line ~325):
```python
# OLD: upload_parquet(bucket, f"historical/race_results/{y}.parquet", df)
upload_parquet(df, bucket, f"historical/race_results/{y}.parquet")
```

In `run_historical` (was line ~339):
```python
# OLD: upload_parquet(bucket, abu_dhabi_path, df)
upload_parquet(df, bucket, abu_dhabi_path)
```

- [ ] **Step 4: Update `_download_session` to use `extract_telemetry` import**

In `_download_session`, replace the call `tel = _extract_telemetry(session)` with `tel = extract_telemetry(session)`.

- [ ] **Step 5: Update `_paginate`/`_fetch_json` call sites to use imported names**

In `run_historical`: replace `_paginate(...)` with `paginate(...)` and `_fetch_json(...)` with `fetch_json(...)`.

In `_fetch_race_results_year`: replace `_paginate(...)` with `paginate(...)`.

In `_fetch_lap_times_round`: replace `_paginate(...)` with `paginate(...)`.

- [ ] **Step 6: Verify import**

```bash
python -c "import ingest.gap_worker; print('OK')"
```

---

### Task 1.6: Update `ingest/fastf1_worker.py`

**Files:** Modify `ingest/fastf1_worker.py`

- [ ] **Step 1: Replace imports**

Change the imports section. Remove the local definitions of `_is_rate_limit`, `_backoff_wait`, `_extract_telemetry`. Add:

```python
from .http_utils import backoff_wait, is_rate_limit
from .telemetry_extractor import extract_telemetry
```

- [ ] **Step 2: Remove local definitions**

Delete functions: `_is_rate_limit`, `_backoff_wait`, `_extract_telemetry`.

- [ ] **Step 3: Update call sites**

In `_download_session`:
- `_is_rate_limit(exc)` → `is_rate_limit(exc)`
- `_backoff_wait(attempt)` → `backoff_wait(attempt)`
- `tel = _extract_telemetry(session)` → `tel = extract_telemetry(session)`

- [ ] **Step 4: Verify import**

```bash
python -c "import ingest.fastf1_worker; print('OK')"
```

---

### Task 1.7: Update `ingest/historical_worker.py`

**Files:** Modify `ingest/historical_worker.py`

- [ ] **Step 1: Replace imports**

Remove local definitions of `_get`, `_is_rate_limit`, `_backoff_wait`, `_fetch_json_retry`, `_paginate`. Add:

```python
from .http_utils import backoff_wait, is_rate_limit, rate_limited_get
from .jolpica_client import fetch_json as _fetch_json_retry, paginate as _paginate
```

Note: use `_fetch_json_retry` and `_paginate` as aliases so the remaining call sites inside fetcher functions need no change.

- [ ] **Step 2: Remove local definitions**

Delete: `_get`, `_is_rate_limit`, `_backoff_wait`, `_fetch_json_retry`, `_paginate`.

- [ ] **Step 3: Update `_get` call sites in `_ingest_year`**

`_ingest_year` uses `_backoff_wait(attempt)` directly → already covered by alias.

- [ ] **Step 4: Verify import**

```bash
python -c "import ingest.historical_worker; print('OK')"
```

---

### Task 1.8: Update `ingest/lap_times_worker.py`

**Files:** Modify `ingest/lap_times_worker.py`

lap_times_worker has its own JSON logging helpers, local `_get`, `_fetch_json`, `_paginate`, local `blob_exists`, and local `upload_parquet(bucket, path, df)` (wrong arg order).

- [ ] **Step 1: Add imports (after existing imports)**

```python
from .gcs_utils import blob_exists, upload_parquet
from .http_utils import backoff_wait, rate_limited_get
from .jolpica_client import fetch_json as _fetch_json, paginate as _paginate
```

- [ ] **Step 2: Remove local definitions**

Delete: `_get`, `_fetch_json`, `_paginate`, `blob_exists`, `upload_parquet`.

Keep: `_log/info/warn/error` (JSON logging helpers used in `main`).

- [ ] **Step 3: Fix `upload_parquet` arg order in `main`**

In `main`, the calls are `upload_parquet(bucket, blob_path, df)` → fix to `upload_parquet(df, bucket, blob_path)`.

- [ ] **Step 4: Fix `_get` call sites** — `_get` was used inside the old local `_fetch_json`. Since we now import `_fetch_json` from jolpica_client which uses `rate_limited_get` internally, no extra changes needed.

- [ ] **Step 5: Verify import**

```bash
python -c "import ingest.lap_times_worker; print('OK')"
```

---

### Task 1.9: Commit Layer 1

- [ ] **Step 1: Stage and commit**

```bash
cd /Users/bhargav/Documents/F1-Strategy-Optimizer
git add ingest/http_utils.py ingest/jolpica_client.py ingest/telemetry_extractor.py \
        ingest/gcs_utils.py ingest/gap_worker.py ingest/fastf1_worker.py \
        ingest/historical_worker.py ingest/lap_times_worker.py
git commit -m "$(cat <<'EOF'
refactor(ingest): Layer 1 — SRP extract-and-delegate

- http_utils.py: rate-limited GET, exponential backoff, retry_forever
- jolpica_client.py: Jolpica pagination + JSON fetch (unified from 3 workers)
- telemetry_extractor.py: FastF1 per-lap telemetry extraction
- gcs_utils.py: add blob_exists (consolidated from gap_worker, lap_times_worker)
- gap_worker, fastf1_worker, historical_worker, lap_times_worker: thin orchestrators
- Fix upload_parquet arg order in gap_worker and lap_times_worker callers

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Layer 2: `src/ingestion/` + `src/preprocessing/`

**Files to create:**
- `src/ingestion/http_client.py`
- `src/ingestion/ergast_client.py`
- `src/ingestion/fastf1_extractor.py`
- `src/preprocessing/schema_validator.py`
- `src/preprocessing/quality_metrics.py`
- `src/preprocessing/data_sanitizer.py`

**Files to modify:**
- `src/ingestion/ergast_ingestion.py` — thin orchestrator
- `src/ingestion/fastf1_ingestion.py` — thin orchestrator
- `src/preprocessing/validator.py` — aggregates the three preprocessing modules

---

### Task 2.1: Create `src/ingestion/http_client.py`

- [ ] **Step 1: Write the file**

```python
"""http_client.py — Rate-limited HTTP client for src/ingestion."""
from __future__ import annotations

import logging
import time

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

_MIN_REQUEST_INTERVAL = 1.0
_last_request_time: float = 0.0


def rate_limited_get(url: str, timeout: int = 30) -> requests.Response:
    """HTTP GET with 1 req/s rate limiting."""
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
    resp = requests.get(url, timeout=timeout)
    _last_request_time = time.monotonic()
    return resp


@retry(
    retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    stop=stop_after_attempt(5),
    reraise=True,
)
def fetch_json(url: str) -> dict:
    """Fetch URL, retry on connection errors, handle 429 with 60s backoff."""
    logger.debug("GET %s", url)
    resp = rate_limited_get(url)
    if resp.status_code == 429:
        logger.warning("Rate limited (429) — sleeping 60s before retry")
        time.sleep(60)
        resp = rate_limited_get(url)
    resp.raise_for_status()
    return resp.json()
```

- [ ] **Step 2: Verify**

```bash
python -c "from src.ingestion.http_client import rate_limited_get, fetch_json; print('OK')"
```

---

### Task 2.2: Create `src/ingestion/ergast_client.py`

- [ ] **Step 1: Write the file**

```python
"""ergast_client.py — Jolpica/Ergast endpoint pagination."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from .http_client import fetch_json

logger = logging.getLogger(__name__)

BASE_URL = "https://api.jolpi.ca/ergast/f1"


def paginate(base_url: str, limit: int = 1000) -> List[Dict[str, Any]]:
    """Fetch all pages from a Jolpica endpoint."""
    results: List[Dict[str, Any]] = []
    offset = 0
    while True:
        url = f"{base_url}?limit={limit}&offset={offset}"
        data = fetch_json(url)
        mr = data.get("MRData", {})
        total = int(mr.get("total", 0))
        table = (
            mr.get("RaceTable")
            or mr.get("SeasonTable")
            or mr.get("DriverTable")
            or mr.get("CircuitTable")
            or {}
        )
        rows: List[Dict[str, Any]] = []
        for val in table.values():
            if isinstance(val, list):
                rows = val
                break
        results.extend(rows)
        actual_limit = int(mr.get("limit", limit))
        offset += actual_limit
        if offset >= total or not rows:
            break
    logger.info("Fetched %d records from %s", len(results), base_url)
    return results
```

- [ ] **Step 2: Verify**

```bash
python -c "from src.ingestion.ergast_client import paginate; print('OK')"
```

---

### Task 2.3: Create `src/ingestion/fastf1_extractor.py`

- [ ] **Step 1: Write the file**

```python
"""fastf1_extractor.py — FastF1 session loading, telemetry, timedelta normalization."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

try:
    import fastf1  # type: ignore[import]
    _FASTF1_AVAILABLE = True
except ImportError:
    _FASTF1_AVAILABLE = False

SESSION_LABELS = {
    "FP1": "Practice 1", "FP2": "Practice 2", "FP3": "Practice 3",
    "Q": "Qualifying", "S": "Sprint", "R": "Race",
}


def enable_cache(cache_dir: str) -> None:
    if _FASTF1_AVAILABLE:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        fastf1.Cache.enable_cache(cache_dir)


def load_session(year: int, round_num: int, session_type: str) -> "fastf1.core.Session":
    if year < 2018:
        raise ValueError(f"FastF1 only supports 2018+. Got year={year}")
    label = SESSION_LABELS.get(session_type, session_type)
    logger.info("Loading session: %d Round %d %s (%s)", year, round_num, session_type, label)
    session = fastf1.get_session(year, round_num, session_type)
    session.load(telemetry=True, laps=True, weather=True)
    logger.info("Session loaded: %s %d — %d laps", session.event["EventName"], year, len(session.laps))
    return session


def normalize_timedeltas(df: pd.DataFrame) -> pd.DataFrame:
    """Convert timedelta64 columns to float seconds."""
    for col in df.select_dtypes(include=["timedelta64[ns]"]).columns:
        df[col] = df[col].dt.total_seconds()
    return df


def extract_laps(session, year: int, round_num: int, session_type: str) -> pd.DataFrame:
    laps = session.laps.copy()
    laps["season"] = year
    laps["round"] = round_num
    laps["session_type"] = session_type
    return normalize_timedeltas(laps)


def extract_telemetry(
    session, year: int, round_num: int, session_type: str,
    driver: Optional[str] = None,
) -> pd.DataFrame:
    laps = session.laps
    if driver is not None:
        laps = laps.pick_driver(driver)
    frames: List[pd.DataFrame] = []
    for _, lap in laps.iterlaps():
        try:
            tel = lap.get_telemetry()
            if tel is not None and not tel.empty:
                tel["Driver"] = lap["Driver"]
                tel["LapNumber"] = lap["LapNumber"]
                tel["season"] = year
                tel["round"] = round_num
                tel["session_type"] = session_type
                frames.append(tel)
        except Exception:
            logger.debug("Telemetry unavailable for %s lap %s", lap.get("Driver"), lap.get("LapNumber"))
    if not frames:
        return pd.DataFrame()
    return normalize_timedeltas(pd.concat(frames, ignore_index=True))


def extract_weather(session, year: int, round_num: int, session_type: str) -> pd.DataFrame:
    weather = session.weather_data.copy()
    weather["season"] = year
    weather["round"] = round_num
    weather["session_type"] = session_type
    return normalize_timedeltas(weather)
```

- [ ] **Step 2: Verify**

```bash
python -c "from src.ingestion.fastf1_extractor import load_session, extract_laps; print('OK')"
```

---

### Task 2.4: Create `src/preprocessing/schema_validator.py`

- [ ] **Step 1: Write the file**

```python
"""schema_validator.py — Pydantic schema definitions and per-record validation."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    pass


class RaceDataSchema(BaseModel):
    race_id: int = Field(..., gt=0)
    year: int = Field(..., ge=1950, le=2024)
    round: int = Field(..., ge=1, le=25)
    circuit_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    date: str
    time: Optional[str] = None
    url: Optional[str] = None

    @validator("date")
    def validate_date(cls, v):
        try:
            datetime.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError("Invalid date format, expected ISO format")


class DriverDataSchema(BaseModel):
    driver_id: str = Field(..., min_length=1)
    driver_number: Optional[int] = Field(None, ge=1, le=99)
    code: Optional[str] = Field(None, min_length=3, max_length=3)
    forename: str = Field(..., min_length=1)
    surname: str = Field(..., min_length=1)
    dob: str
    nationality: str
    url: Optional[str] = None

    @validator("dob")
    def validate_dob(cls, v):
        try:
            dob = datetime.fromisoformat(v)
            if dob.year < 1900 or dob.year > datetime.now().year - 16:
                raise ValueError("Invalid birth year")
            return v
        except ValueError as e:
            raise ValueError(f"Invalid date of birth: {e}")


class TelemetryDataSchema(BaseModel):
    race_id: str
    driver_id: str
    lap: int = Field(..., ge=1)
    timestamp: str
    speed: float = Field(..., ge=0, le=400)
    throttle: float = Field(..., ge=0, le=1)
    brake: bool
    gear: int = Field(..., ge=-1, le=8)
    rpm: int = Field(..., ge=0, le=20000)


def validate_dataframe(
    df: pd.DataFrame,
    schema_class: type[BaseModel],
    required_columns: Optional[List[str]] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    logger.info("Validating %d records against %s", len(df), schema_class.__name__)
    if required_columns:
        missing_cols = set(required_columns) - set(df.columns)
        if missing_cols:
            raise ValidationError(f"Missing required columns: {missing_cols}")

    valid_records, invalid_records, errors = [], [], []
    for idx, row in df.iterrows():
        try:
            validated = schema_class(**row.to_dict())
            valid_records.append(validated.dict())
        except Exception as e:
            invalid_records.append({"index": idx, "record": row.to_dict(), "error": str(e)})
            errors.append(str(e))

    valid_df = pd.DataFrame(valid_records) if valid_records else pd.DataFrame()
    report = {
        "total": len(df),
        "valid": len(valid_records),
        "invalid": len(invalid_records),
        "validation_rate": len(valid_records) / len(df) if len(df) > 0 else 0,
        "errors": errors[:10],
        "invalid_records": invalid_records[:10],
    }
    logger.info("Validation complete: %d/%d valid (%.2f%%)", len(valid_records), len(df), report["validation_rate"] * 100)
    return valid_df, report
```

- [ ] **Step 2: Verify**

```bash
python -c "from src.preprocessing.schema_validator import validate_dataframe, RaceDataSchema; print('OK')"
```

---

### Task 2.5: Create `src/preprocessing/quality_metrics.py`

- [ ] **Step 1: Write the file**

```python
"""quality_metrics.py — Completeness, validity, consistency scoring."""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


class DataQualityLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INVALID = "invalid"


def check_data_quality(
    df: pd.DataFrame,
    column_rules: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[DataQualityLevel, Dict[str, Any]]:
    logger.info("Assessing data quality for %d records", len(df))
    metrics: Dict[str, Dict[str, Any]] = {
        "completeness": {}, "validity": {}, "consistency": {}, "accuracy": {},
    }

    for col in df.columns:
        null_pct = df[col].isnull().sum() / len(df) * 100
        metrics["completeness"][col] = {
            "null_count": int(df[col].isnull().sum()),
            "null_percentage": round(null_pct, 2),
        }

    if column_rules:
        for col, rules in column_rules.items():
            if col not in df.columns:
                continue
            if "valid_range" in rules:
                min_val, max_val = rules["valid_range"]
                out_of_range = df[(df[col] < min_val) | (df[col] > max_val)].shape[0]
                metrics["validity"][col] = {
                    "out_of_range_count": out_of_range,
                    "out_of_range_percentage": round(out_of_range / len(df) * 100, 2),
                }

    dup_count = df.duplicated().sum()
    metrics["consistency"]["duplicates"] = {
        "count": int(dup_count),
        "percentage": round(dup_count / len(df) * 100, 2),
    }

    completeness_score = 100 - sum(
        m["null_percentage"] for m in metrics["completeness"].values()
    ) / max(len(df.columns), 1)
    validity_score = 100
    if metrics["validity"]:
        validity_score = 100 - sum(
            m["out_of_range_percentage"] for m in metrics["validity"].values()
        ) / max(len(metrics["validity"]), 1)
    consistency_score = 100 - metrics["consistency"]["duplicates"]["percentage"]
    overall = (completeness_score + validity_score + consistency_score) / 3

    if overall >= 90:
        level = DataQualityLevel.HIGH
    elif overall >= 70:
        level = DataQualityLevel.MEDIUM
    elif overall >= 50:
        level = DataQualityLevel.LOW
    else:
        level = DataQualityLevel.INVALID

    report = {
        "overall_score": round(overall, 2),
        "quality_level": level.value,
        "metrics": metrics,
        "scores": {
            "completeness": round(completeness_score, 2),
            "validity": round(validity_score, 2),
            "consistency": round(consistency_score, 2),
        },
    }
    logger.info("Data quality: %s (score: %.2f)", level.value.upper(), overall)
    return level, report
```

- [ ] **Step 2: Verify**

```bash
python -c "from src.preprocessing.quality_metrics import check_data_quality, DataQualityLevel; print('OK')"
```

---

### Task 2.6: Create `src/preprocessing/data_sanitizer.py`

- [ ] **Step 1: Write the file**

```python
"""data_sanitizer.py — Deduplication, whitespace stripping, null handling."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def sanitize_data(df: pd.DataFrame) -> pd.DataFrame:
    logger.info("Sanitizing data...")
    df_clean = df.copy()
    df_clean = df_clean.dropna(how="all")
    for col in df_clean.select_dtypes(include=["object"]).columns:
        df_clean[col] = df_clean[col].str.strip()
    df_clean = df_clean.replace(r"^\s*$", np.nan, regex=True)
    original_count = len(df_clean)
    df_clean = df_clean.drop_duplicates()
    logger.info("Sanitization complete: removed %d duplicates", original_count - len(df_clean))
    return df_clean
```

- [ ] **Step 2: Verify**

```bash
python -c "from src.preprocessing.data_sanitizer import sanitize_data; print('OK')"
```

---

### Task 2.7: Update `src/ingestion/ergast_ingestion.py`

Remove module-level `_rate_limited_get`, `_fetch_json`, `_paginate`. Import from new modules.

- [ ] **Step 1: Replace module-level imports/helpers**

At the top of the file, add:
```python
from .http_client import fetch_json as _fetch_json
from .ergast_client import paginate as _paginate
```

Remove the module-level functions `_rate_limited_get`, `_fetch_json`, `_paginate`.

The `ErgastIngestion` class itself, `_save`, and all `fetch_*`/`ingest_season` methods stay unchanged — they already call `_fetch_json` and `_paginate` which now resolve to the imports.

- [ ] **Step 2: Verify**

```bash
python -c "from src.ingestion.ergast_ingestion import ErgastIngestion; print('OK')"
```

---

### Task 2.8: Update `src/ingestion/fastf1_ingestion.py`

- [ ] **Step 1: Add imports and restructure**

Add to imports:
```python
from .fastf1_extractor import (
    enable_cache, load_session, extract_laps,
    extract_telemetry, extract_weather, normalize_timedeltas,
)
```

Remove from `FastF1Ingestion`:
- The `__init__` fastf1 import block (keep the `_FASTF1_AVAILABLE` guard but simplify)
- The inline timedelta loop (now done by `normalize_timedeltas` from extractor)
- The inline telemetry loop in `fetch_telemetry` (now done by `extract_telemetry`)

Update `FastF1Ingestion.__init__` to call `enable_cache(str(self.cache_dir))` instead of `fastf1.Cache.enable_cache(...)`.

Update `fetch_session` to call `load_session(year, round_num, session_type)`.

Update `fetch_laps` to call `extract_laps(session, year, round_num, session_type)`, then save CSV from the returned df.

Update `fetch_telemetry` to call `extract_telemetry(session, year, round_num, session_type, driver)`, then save CSV.

Update `fetch_weather` to call `extract_weather(session, year, round_num, session_type)`, then save CSV.

- [ ] **Step 2: Verify**

```bash
python -c "from src.ingestion.fastf1_ingestion import FastF1Ingestion; print('OK')"
```

---

### Task 2.9: Update `src/preprocessing/validator.py`

- [ ] **Step 1: Add imports**

Add at top of file:
```python
from .schema_validator import (
    ValidationError, RaceDataSchema, DriverDataSchema,
    TelemetryDataSchema, validate_dataframe,
)
from .quality_metrics import DataQualityLevel, check_data_quality
from .data_sanitizer import sanitize_data
```

- [ ] **Step 2: Delegate from DataValidator**

Replace `DataValidator.validate_dataframe` body:
```python
def validate_dataframe(self, df, schema_class, required_columns=None):
    valid_df, report = validate_dataframe(df, schema_class, required_columns)
    self.validation_stats["total_records"] += report["total"]
    self.validation_stats["valid_records"] += report["valid"]
    self.validation_stats["invalid_records"] += report["invalid"]
    return valid_df, report
```

Replace `DataValidator.check_data_quality` body:
```python
def check_data_quality(self, df, column_rules=None):
    return check_data_quality(df, column_rules)
```

Replace `DataValidator.sanitize_data` body:
```python
def sanitize_data(self, df):
    return sanitize_data(df)
```

Keep the schema classes re-exported from validator.py for backward compatibility (they are already imported above).

- [ ] **Step 3: Verify**

```bash
python -c "from src.preprocessing.validator import DataValidator, RaceDataSchema; print('OK')"
```

---

### Task 2.10: Commit Layer 2

- [ ] **Step 1: Stage and commit**

```bash
git add src/ingestion/http_client.py src/ingestion/ergast_client.py \
        src/ingestion/fastf1_extractor.py \
        src/preprocessing/schema_validator.py src/preprocessing/quality_metrics.py \
        src/preprocessing/data_sanitizer.py \
        src/ingestion/ergast_ingestion.py src/ingestion/fastf1_ingestion.py \
        src/preprocessing/validator.py
git commit -m "$(cat <<'EOF'
refactor(src/ingestion,preprocessing): Layer 2 — SRP extract-and-delegate

- http_client.py: rate-limited GET + tenacity retry
- ergast_client.py: Jolpica pagination
- fastf1_extractor.py: session loading, telemetry, timedelta normalization
- schema_validator.py: Pydantic schemas + per-record validation
- quality_metrics.py: completeness/validity/consistency scoring
- data_sanitizer.py: dedup, whitespace, null handling
- ergast_ingestion, fastf1_ingestion, validator: thin orchestrators

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Layer 3: `src/common/security/`

**Files to create:**
- `src/common/security/security_headers_middleware.py`
- `src/common/security/request_validation_middleware.py`
- `src/common/security/rate_limit_middleware.py`
- `src/common/security/cors_middleware.py`
- `src/common/security/auth_helper.py`
- `src/common/security/token_manager.py`
- `src/common/security/password_manager.py`
- `src/common/security/role_permissions.py`

**Files to modify:**
- `src/common/security/https_middleware.py` — keep only `HTTPSRedirectMiddleware`, import+re-export others
- `src/common/security/iam_simulator.py` — keep only `IAMSimulator` user CRUD + authorization

---

### Task 3.1: Create `src/common/security/role_permissions.py`

- [ ] **Step 1: Write the file**

```python
"""role_permissions.py — Role and Permission enums + role→permission mapping."""
from enum import Enum
from typing import Dict, Set


class Role(str, Enum):
    ADMIN = "roles/admin"
    DATA_ENGINEER = "roles/dataEngineer"
    ML_ENGINEER = "roles/mlEngineer"
    DATA_VIEWER = "roles/dataViewer"
    API_USER = "roles/apiUser"


class Permission(str, Enum):
    DATA_READ = "data.read"
    DATA_WRITE = "data.write"
    DATA_DELETE = "data.delete"
    CLOUDSQL_QUERY = "cloudsql.query"
    CLOUDSQL_TABLE_CREATE = "cloudsql.table.create"
    CLOUDSQL_TABLE_UPDATE = "cloudsql.table.update"
    PUBSUB_PUBLISH = "pubsub.publish"
    PUBSUB_SUBSCRIBE = "pubsub.subscribe"
    DATAFLOW_JOB_CREATE = "dataflow.job.create"
    DATAFLOW_JOB_CANCEL = "dataflow.job.cancel"
    ML_MODEL_READ = "ml.model.read"
    ML_MODEL_WRITE = "ml.model.write"
    ML_MODEL_DEPLOY = "ml.model.deploy"
    ADMIN_ALL = "admin.*"


ROLE_PERMISSIONS: Dict[Role, Set[Permission]] = {
    Role.ADMIN: {Permission.ADMIN_ALL},
    Role.DATA_ENGINEER: {
        Permission.DATA_READ, Permission.DATA_WRITE,
        Permission.CLOUDSQL_QUERY, Permission.CLOUDSQL_TABLE_CREATE,
        Permission.CLOUDSQL_TABLE_UPDATE,
        Permission.PUBSUB_PUBLISH, Permission.PUBSUB_SUBSCRIBE,
        Permission.DATAFLOW_JOB_CREATE,
    },
    Role.ML_ENGINEER: {
        Permission.DATA_READ, Permission.CLOUDSQL_QUERY,
        Permission.ML_MODEL_READ, Permission.ML_MODEL_WRITE, Permission.ML_MODEL_DEPLOY,
    },
    Role.DATA_VIEWER: {Permission.DATA_READ, Permission.CLOUDSQL_QUERY},
    Role.API_USER: {Permission.DATA_READ, Permission.ML_MODEL_READ},
}
```

- [ ] **Step 2: Verify**

```bash
python -c "from src.common.security.role_permissions import Role, Permission, ROLE_PERMISSIONS; print('OK')"
```

---

### Task 3.2: Create `src/common/security/token_manager.py`

- [ ] **Step 1: Write the file**

```python
"""token_manager.py — JWT creation and verification."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from jose import JWTError, jwt
from pydantic import BaseModel

SECRET_KEY = "f1-strategy-optimizer-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


class TokenData(BaseModel):
    username: Optional[str] = None
    roles: List[str] = []


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> Optional[TokenData]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        roles: List[str] = payload.get("roles", [])
        if username is None:
            return None
        return TokenData(username=username, roles=roles)
    except JWTError:
        return None
```

- [ ] **Step 2: Verify**

```bash
python -c "from src.common.security.token_manager import create_access_token, verify_token; print('OK')"
```

---

### Task 3.3: Create `src/common/security/password_manager.py`

- [ ] **Step 1: Write the file**

```python
"""password_manager.py — Password hashing and verification."""
import bcrypt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8")[:72],
        hashed_password.encode("utf-8"),
    )
```

- [ ] **Step 2: Verify**

```bash
python -c "from src.common.security.password_manager import hash_password, verify_password; print('OK')"
```

---

### Task 3.4: Create the four extracted middleware files

- [ ] **Step 1: Write `src/common/security/security_headers_middleware.py`**

```python
"""security_headers_middleware.py — SecurityHeadersMiddleware."""
from typing import Callable
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response
```

- [ ] **Step 2: Write `src/common/security/request_validation_middleware.py`**

```python
"""request_validation_middleware.py — RequestValidationMiddleware + attack detection."""
import logging
from typing import Callable
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

_SUSPICIOUS_PATTERNS = [
    "<script", "javascript:", "onerror=", "onclick=",
    "../", "..\\", "SELECT * FROM", "DROP TABLE", "UNION SELECT", "; DROP",
]


def _is_suspicious(value: str) -> bool:
    value_lower = value.lower()
    return any(p.lower() in value_lower for p in _SUSPICIOUS_PATTERNS)


class RequestValidationMiddleware(BaseHTTPMiddleware):
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024

    async def dispatch(self, request: Request, call_next: Callable):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.MAX_CONTENT_LENGTH:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={"detail": "Request body too large"},
            )
        allowed_methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
        if request.method not in allowed_methods:
            return JSONResponse(
                status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
                content={"detail": f"Method {request.method} not allowed"},
            )
        for key, value in request.query_params.items():
            if _is_suspicious(value):
                logger.warning("Suspicious query parameter detected: %s=%s", key, value)
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"detail": "Invalid request parameters"},
                )
        return await call_next(request)
```

- [ ] **Step 3: Write `src/common/security/rate_limit_middleware.py`**

```python
"""rate_limit_middleware.py — RateLimitMiddleware with per-IP tracking."""
import logging
import time
from typing import Callable, Dict, Tuple
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.request_counts: Dict[str, Tuple[int, float]] = {}

    async def dispatch(self, request: Request, call_next: Callable):
        client_ip = request.client.host if request.client else "unknown"
        if request.url.path in ["/health", "/metrics"]:
            return await call_next(request)
        current_time = time.time()
        if client_ip in self.request_counts:
            count, window_start = self.request_counts[client_ip]
            if current_time - window_start > self.window_seconds:
                self.request_counts[client_ip] = (1, current_time)
            else:
                if count >= self.max_requests:
                    logger.warning("Rate limit exceeded for %s", client_ip)
                    return JSONResponse(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        content={"detail": "Rate limit exceeded"},
                        headers={"Retry-After": str(self.window_seconds)},
                    )
                self.request_counts[client_ip] = (count + 1, window_start)
        else:
            self.request_counts[client_ip] = (1, current_time)
        response = await call_next(request)
        if client_ip in self.request_counts:
            count, _ = self.request_counts[client_ip]
            response.headers["X-RateLimit-Limit"] = str(self.max_requests)
            response.headers["X-RateLimit-Remaining"] = str(max(0, self.max_requests - count))
            response.headers["X-RateLimit-Reset"] = str(int(current_time + self.window_seconds))
        return response
```

- [ ] **Step 4: Write `src/common/security/cors_middleware.py`**

```python
"""cors_middleware.py — CORSMiddleware with configurable origins."""
from typing import Callable, List
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class CORSMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, allow_origins: List[str] = [], allow_credentials: bool = True):
        super().__init__(app)
        self.allow_origins = allow_origins or ["http://localhost:3000", "http://localhost:8080"]
        self.allow_credentials = allow_credentials

    async def dispatch(self, request: Request, call_next: Callable):
        if request.method == "OPTIONS":
            response = JSONResponse(content={}, status_code=200)
        else:
            response = await call_next(request)
        origin = request.headers.get("origin")
        if origin and (origin in self.allow_origins or "*" in self.allow_origins):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = str(self.allow_credentials).lower()
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            response.headers["Access-Control-Max-Age"] = "3600"
        return response
```

- [ ] **Step 5: Verify all four**

```bash
python -c "
from src.common.security.security_headers_middleware import SecurityHeadersMiddleware
from src.common.security.request_validation_middleware import RequestValidationMiddleware
from src.common.security.rate_limit_middleware import RateLimitMiddleware
from src.common.security.cors_middleware import CORSMiddleware
print('OK')
"
```

---

### Task 3.5: Create `src/common/security/auth_helper.py`

- [ ] **Step 1: Write the file**

```python
"""auth_helper.py — get_current_user FastAPI dependency."""
from fastapi import HTTPException, Request, status
from .iam_simulator import iam_simulator, User


async def get_current_user(request: Request) -> User:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth_header.split(" ")[1]
    token_data = iam_simulator.verify_token(token)
    if not token_data or not token_data.username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_data = iam_simulator.users.get(token_data.username)
    if not user_data or user_data.get("disabled"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled",
        )
    return User(**{k: v for k, v in user_data.items() if k != "hashed_password"})
```

- [ ] **Step 2: Verify**

```bash
python -c "from src.common.security.auth_helper import get_current_user; print('OK')"
```

---

### Task 3.6: Update `src/common/security/iam_simulator.py`

Replace `Role`, `Permission`, `ROLE_PERMISSIONS` with imports. Replace `_hash_password`/`_verify_password` with imports. Replace `create_access_token`/`verify_token` with imports.

- [ ] **Step 1: Add imports after existing imports**

```python
from .role_permissions import Role, Permission, ROLE_PERMISSIONS
from .token_manager import TokenData, create_access_token as _create_token, verify_token as _verify_token
from .password_manager import hash_password as _hash_pw, verify_password as _verify_pw
```

- [ ] **Step 2: Remove local definitions**

Delete from `iam_simulator.py`:
- `class Role(str, Enum)` — now imported
- `class Permission(str, Enum)` — now imported
- `ROLE_PERMISSIONS` dict — now imported
- `class TokenData(BaseModel)` — now imported from token_manager

- [ ] **Step 3: Update `IAMSimulator` methods to delegate**

Replace `_hash_password`: `return _hash_pw(password)`
Replace `_verify_password`: `return _verify_pw(plain_password, hashed_password)`
Replace `create_access_token`: `return _create_token(data, expires_delta)`
Replace `verify_token`: `return _verify_token(token)`

Keep: `User`, `Token` models, `IAMSimulator` class with user CRUD, `authenticate_user`, `get_user_permissions`, `check_permission`, `add_user`, `grant_role`, `revoke_role`, `iam_simulator` global.

- [ ] **Step 4: Verify**

```bash
python -c "from src.common.security.iam_simulator import IAMSimulator, Role, Permission, User; print('OK')"
```

---

### Task 3.7: Update `src/common/security/https_middleware.py`

- [ ] **Step 1: Add imports and re-exports**

Replace the contents of `https_middleware.py` with the thin version that keeps only `HTTPSRedirectMiddleware` and re-exports the four extracted classes:

```python
"""
https_middleware.py — HTTPS enforcement + re-exports for backward compatibility.
"""
import logging
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

# Re-export extracted classes so existing callers see no import breakage
from .security_headers_middleware import SecurityHeadersMiddleware
from .request_validation_middleware import RequestValidationMiddleware
from .rate_limit_middleware import RateLimitMiddleware
from .cors_middleware import CORSMiddleware
from .auth_helper import get_current_user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce HTTPS connections."""

    def __init__(self, app: ASGIApp, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next: Callable):
        if not self.enabled or request.url.path in ["/health", "/metrics"]:
            return await call_next(request)
        if request.url.scheme != "https":
            logger.warning(
                "Non-HTTPS request detected: %s %s", request.method, request.url.path
            )
        return await call_next(request)
```

- [ ] **Step 2: Verify all imports still work as before**

```bash
python -c "
from src.common.security.https_middleware import (
    HTTPSRedirectMiddleware, SecurityHeadersMiddleware,
    RequestValidationMiddleware, RateLimitMiddleware,
    CORSMiddleware, get_current_user,
)
print('OK')
"
```

---

### Task 3.8: Commit Layer 3

- [ ] **Step 1: Stage and commit**

```bash
git add src/common/security/role_permissions.py \
        src/common/security/token_manager.py \
        src/common/security/password_manager.py \
        src/common/security/security_headers_middleware.py \
        src/common/security/request_validation_middleware.py \
        src/common/security/rate_limit_middleware.py \
        src/common/security/cors_middleware.py \
        src/common/security/auth_helper.py \
        src/common/security/iam_simulator.py \
        src/common/security/https_middleware.py
git commit -m "$(cat <<'EOF'
refactor(src/common/security): Layer 3 — SRP extract-and-delegate

- role_permissions.py: Role/Permission enums + ROLE_PERMISSIONS mapping
- token_manager.py: JWT creation/verification
- password_manager.py: bcrypt hash/verify
- security_headers_middleware.py, request_validation_middleware.py,
  rate_limit_middleware.py, cors_middleware.py: one class each
- auth_helper.py: get_current_user FastAPI dependency
- https_middleware.py: HTTPSRedirectMiddleware only, re-exports others
- iam_simulator.py: user CRUD + authorization only

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Layer 4: `src/api/`

**Files to create:**
- `src/api/models.py`
- `src/api/auth.py`
- `src/api/metrics.py`
- `src/api/startup.py`
- `src/api/routes/__init__.py`
- `src/api/routes/strategy.py`
- `src/api/routes/data.py`
- `src/api/routes/simulation.py`
- `src/api/routes/health.py`

**Files to modify:**
- `src/api/main.py` — becomes ~60-line app factory

---

### Task 4.1: Create `src/api/models.py`

- [ ] **Step 1: Write the file**

```python
"""models.py — All Pydantic request/response schemas for the API."""
from typing import List, Optional
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str
    environment: str


class StrategyRequest(BaseModel):
    race_id: str
    driver_id: str
    current_lap: int
    current_compound: str
    fuel_level: float
    track_temp: float
    air_temp: float


class StrategyRecommendation(BaseModel):
    recommended_action: str
    pit_window_start: Optional[int] = None
    pit_window_end: Optional[int] = None
    target_compound: Optional[str] = None
    driving_mode: str
    brake_bias: float
    confidence: float
    model_source: str


class SimulateRequest(BaseModel):
    race_id: str
    driver_id: str
    strategy: List[List]


class SimulateResponse(BaseModel):
    driver_id: str
    race_id: str
    predicted_final_position: int
    predicted_total_time_s: float
    strategy: List[List]
    lap_times_s: List[float]
```

- [ ] **Step 2: Verify**

```bash
python -c "from src.api.models import StrategyRequest, StrategyRecommendation, SimulateRequest, SimulateResponse; print('OK')"
```

---

### Task 4.2: Create `src/api/auth.py`

- [ ] **Step 1: Write the file**

```python
"""auth.py — get_current_user FastAPI dependency for the API layer."""
# Delegates to auth_helper which was extracted in Layer 3.
from src.common.security.auth_helper import get_current_user

__all__ = ["get_current_user"]
```

- [ ] **Step 2: Verify**

```bash
python -c "from src.api.auth import get_current_user; print('OK')"
```

---

### Task 4.3: Create `src/api/metrics.py`

- [ ] **Step 1: Write the file**

```python
"""metrics.py — Prometheus counter/histogram definitions."""
from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "api_requests_total", "Total API requests", ["method", "endpoint", "status"]
)
REQUEST_DURATION = Histogram(
    "api_request_duration_seconds", "API request duration", ["method", "endpoint"]
)
PREDICTION_COUNT = Counter(
    "api_predictions_total", "Total predictions made", ["model"]
)
```

- [ ] **Step 2: Verify**

```bash
python -c "from src.api.metrics import REQUEST_COUNT, REQUEST_DURATION, PREDICTION_COUNT; print('OK')"
```

---

### Task 4.4: Create `src/api/startup.py`

- [ ] **Step 1: Write the file**

```python
"""startup.py — Startup handler: load ML models from GCS."""
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_strategy_model: Optional[Any] = None
_models_loaded_from_gcs: bool = False


def get_strategy_model() -> Optional[Any]:
    return _strategy_model


async def startup_event() -> None:
    global _strategy_model, _models_loaded_from_gcs
    import io
    import os
    import joblib
    from google.cloud import storage

    env = os.getenv("ENV", "local")
    enable_https = os.getenv("ENABLE_HTTPS", "false").lower() == "true"
    enable_iam = os.getenv("ENABLE_IAM", "true").lower() == "true"
    logger.info("F1 Strategy Optimizer API starting in %s environment", env)
    logger.info("HTTPS enabled: %s", enable_https)
    logger.info("IAM enabled: %s", enable_iam)

    try:
        gcs_client = storage.Client()
        bucket = gcs_client.bucket("f1optimizer-models")
        blob = bucket.blob("strategy_predictor/latest/model.pkl")
        if blob.exists():
            buf = io.BytesIO()
            blob.download_to_file(buf)
            buf.seek(0)
            _strategy_model = joblib.load(buf)
            _models_loaded_from_gcs = True
            logger.info("ML model loaded from GCS: strategy_predictor/latest/model.pkl")
        else:
            logger.warning(
                "No ML model found at strategy_predictor/latest/model.pkl — using rule-based fallback"
            )
    except Exception as e:
        logger.warning("Model load failed, using rule-based fallback: %s", e)
```

- [ ] **Step 2: Verify**

```bash
python -c "from src.api.startup import startup_event, get_strategy_model; print('OK')"
```

---

### Task 4.5: Create `src/api/routes/__init__.py`

- [ ] **Step 1: Write the file**

```python
"""src/api/routes — API route modules."""
```

---

### Task 4.6: Create `src/api/routes/health.py`

- [ ] **Step 1: Write the file**

```python
"""health.py — /health and /metrics endpoints."""
import os
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from src.api.models import HealthResponse

router = APIRouter()
ENV = os.getenv("ENV", "local")


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        version="1.0.0",
        environment=ENV,
    )


@router.get("/metrics")
async def metrics():
    return JSONResponse(
        content=generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST
    )
```

- [ ] **Step 2: Verify**

```bash
python -c "from src.api.routes.health import router; print('OK')"
```

---

### Task 4.7: Create `src/api/routes/strategy.py`

- [ ] **Step 1: Write the file**

```python
"""strategy.py — /strategy/recommend endpoint."""
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.auth import get_current_user
from src.api.metrics import PREDICTION_COUNT, REQUEST_COUNT, REQUEST_DURATION
from src.api.models import StrategyRecommendation, StrategyRequest
from src.api.startup import get_strategy_model
from src.common.security.iam_simulator import iam_simulator, Permission
from src.common.security.iam_simulator import User

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/strategy/recommend", response_model=StrategyRecommendation)
async def recommend_strategy(
    request: StrategyRequest, current_user: User = Depends(get_current_user)
):
    if not iam_simulator.check_permission(current_user, Permission.ML_MODEL_READ):
        REQUEST_COUNT.labels(method="POST", endpoint="/strategy/recommend", status="403").inc()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    start_time = time.time()
    try:
        _strategy_model = get_strategy_model()
        if _strategy_model is not None:
            import numpy as np
            features = np.array([[request.current_lap, request.fuel_level, request.track_temp, request.air_temp]])
            pred = _strategy_model.predict(features)[0]
            recommended_action = "PIT_SOON" if pred > 0.5 else "CONTINUE"
            recommendation = StrategyRecommendation(
                recommended_action=recommended_action,
                pit_window_start=request.current_lap + 1 if recommended_action == "PIT_SOON" else None,
                pit_window_end=request.current_lap + 5 if recommended_action == "PIT_SOON" else None,
                target_compound="HARD" if request.current_compound == "MEDIUM" else "SOFT",
                driving_mode="BALANCED", brake_bias=52.5,
                confidence=float(abs(pred - 0.5) * 2), model_source="ml_model",
            )
        else:
            recommendation = StrategyRecommendation(
                recommended_action="CONTINUE" if request.current_lap < 30 else "PIT_SOON",
                pit_window_start=30 if request.current_lap < 30 else None,
                pit_window_end=35 if request.current_lap < 30 else None,
                target_compound="HARD" if request.current_compound == "MEDIUM" else "SOFT",
                driving_mode="BALANCED", brake_bias=52.5,
                confidence=0.87, model_source="rule_based_fallback",
            )
        duration = time.time() - start_time
        REQUEST_DURATION.labels(method="POST", endpoint="/strategy/recommend").observe(duration)
        REQUEST_COUNT.labels(method="POST", endpoint="/strategy/recommend", status="200").inc()
        PREDICTION_COUNT.labels(model="strategy_v1").inc()
        logger.info("Strategy for %s lap %d: %s (%.2fms)", request.driver_id, request.current_lap, recommendation.recommended_action, duration * 1000)
        return recommendation
    except Exception as e:
        REQUEST_COUNT.labels(method="POST", endpoint="/strategy/recommend", status="500").inc()
        logger.error("Strategy recommendation error: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error generating recommendation")
```

- [ ] **Step 2: Verify**

```bash
python -c "from src.api.routes.strategy import router; print('OK')"
```

---

### Task 4.8: Create `src/api/routes/data.py`

- [ ] **Step 1: Write the file**

```python
"""data.py — /data/drivers, /models/status, /api/v1/drivers endpoints."""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.auth import get_current_user
from src.api.metrics import REQUEST_COUNT
from src.common.security.iam_simulator import iam_simulator, Permission, User

router = APIRouter()
logger = logging.getLogger(__name__)

_feature_pipeline: Any = None


def _get_pipeline():
    global _feature_pipeline
    if _feature_pipeline is None:
        from ml.features.feature_pipeline import FeaturePipeline
        _feature_pipeline = FeaturePipeline()
    return _feature_pipeline


@router.get("/data/drivers", response_model=List[Dict])
async def get_drivers(current_user: User = Depends(get_current_user), year: Optional[int] = 2024):
    if not iam_simulator.check_permission(current_user, Permission.DATA_READ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    drivers = [
        {"driver_id": "max_verstappen", "name": "Max Verstappen", "nationality": "Dutch"},
        {"driver_id": "lewis_hamilton", "name": "Lewis Hamilton", "nationality": "British"},
    ]
    REQUEST_COUNT.labels(method="GET", endpoint="/data/drivers", status="200").inc()
    return drivers


@router.get("/models/status")
async def get_models_status(current_user: User = Depends(get_current_user)):
    if not iam_simulator.check_permission(current_user, Permission.ML_MODEL_READ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    models = [
        {"name": "tire_degradation", "version": "1.2.0", "status": "active", "accuracy": 0.92, "last_updated": "2024-01-15T10:30:00Z"},
        {"name": "fuel_consumption", "version": "1.1.0", "status": "active", "accuracy": 0.89, "last_updated": "2024-01-10T14:20:00Z"},
    ]
    REQUEST_COUNT.labels(method="GET", endpoint="/models/status", status="200").inc()
    return {"models": models}


@router.get("/api/v1/drivers")
async def list_drivers(current_user=Depends(get_current_user)):
    if not iam_simulator.check_permission(current_user, Permission.DATA_READ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    try:
        pipeline = _get_pipeline()
        drv_df = pipeline._drivers()
        drivers_out = []
        for _, row in drv_df.iterrows():
            driver_id = str(row.get("driverId", ""))
            history = pipeline.get_driver_history(driver_id)
            drivers_out.append({"driver_id": driver_id, "given_name": str(row.get("givenName", "")), "family_name": str(row.get("familyName", "")), "nationality": str(row.get("nationality", "")), "code": str(row.get("code", "")), "permanent_number": str(row.get("permanentNumber", "")), **{k: v for k, v in history.items() if k != "driver_id"}})
        return {"count": len(drivers_out), "drivers": drivers_out}
    except Exception as exc:
        logger.error("list_drivers error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/v1/drivers/{driver_id}/history")
async def driver_history(driver_id: str, current_user=Depends(get_current_user)):
    if not iam_simulator.check_permission(current_user, Permission.DATA_READ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    try:
        pipeline = _get_pipeline()
        history = pipeline.get_driver_history(driver_id)
        if history.get("races", 0) == 0:
            raise HTTPException(status_code=404, detail=f"Driver not found: {driver_id}")
        return history
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("driver_history error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/v1/telemetry/{driver_id}/lap/{lap}")
async def driver_lap_telemetry(driver_id: str, lap: int, race_id: str = Query(...), current_user=Depends(get_current_user)):
    if not iam_simulator.check_permission(current_user, Permission.DATA_READ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    try:
        pipeline = _get_pipeline()
        df = pipeline.build_state_vector(race_id, driver_id)
        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data for {driver_id} in {race_id}")
        lap_row = df[df["lap_number"] == lap]
        if lap_row.empty:
            raise HTTPException(status_code=404, detail=f"Lap {lap} not found")
        row = lap_row.iloc[0].to_dict()
        return {k: (int(v) if hasattr(v, "item") else v) for k, v in row.items()}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("driver_lap_telemetry error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
```

- [ ] **Step 2: Verify**

```bash
python -c "from src.api.routes.data import router; print('OK')"
```

---

### Task 4.9: Create `src/api/routes/simulation.py`

- [ ] **Step 1: Write the file**

```python
"""simulation.py — /simulate endpoint + per-request simulator cache."""
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.auth import get_current_user
from src.api.models import SimulateRequest, SimulateResponse
from src.common.security.iam_simulator import iam_simulator, Permission

router = APIRouter()
logger = logging.getLogger(__name__)

_simulators: Dict[str, Any] = {}


def _get_simulator(race_id: str):
    if race_id not in _simulators:
        from pipeline.simulator.race_simulator import RaceSimulator
        _simulators[race_id] = RaceSimulator(race_id)
    return _simulators[race_id]


@router.get("/api/v1/race/state")
async def race_state(race_id: str = Query(...), lap: int = Query(..., ge=1), current_user=Depends(get_current_user)):
    if not iam_simulator.check_permission(current_user, Permission.DATA_READ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    try:
        sim = _get_simulator(race_id)
        race_state_obj = sim.step(lap)
        return {
            "race_id": race_state_obj.race_id, "lap_number": race_state_obj.lap_number,
            "total_laps": race_state_obj.total_laps, "weather": race_state_obj.weather,
            "track_temp": race_state_obj.track_temp, "air_temp": race_state_obj.air_temp,
            "safety_car": race_state_obj.safety_car,
            "drivers": [{"driver_id": d.driver_id, "position": d.position, "gap_to_leader": d.gap_to_leader, "gap_to_ahead": d.gap_to_ahead, "lap_time_ms": d.lap_time_ms, "tire_compound": d.tire_compound, "tire_age_laps": d.tire_age_laps, "pit_stops_count": d.pit_stops_count, "fuel_remaining_kg": d.fuel_remaining_kg} for d in race_state_obj.drivers],
        }
    except Exception as exc:
        logger.error("race_state error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/v1/race/standings")
async def race_standings(race_id: str = Query(...), lap: int = Query(..., ge=1), current_user=Depends(get_current_user)):
    if not iam_simulator.check_permission(current_user, Permission.DATA_READ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    try:
        sim = _get_simulator(race_id)
        return {"race_id": race_id, "lap": lap, "standings": sim.get_standings(lap)}
    except Exception as exc:
        logger.error("race_standings error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/v1/strategy/simulate", response_model=SimulateResponse)
async def simulate_strategy(request: SimulateRequest, current_user=Depends(get_current_user)):
    if not iam_simulator.check_permission(current_user, Permission.ML_MODEL_READ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    try:
        strategy_tuples = [(int(s[0]), str(s[1])) for s in request.strategy]
        sim = _get_simulator(request.race_id)
        result = sim.simulate_strategy(request.driver_id, strategy_tuples)
        return SimulateResponse(
            driver_id=result.driver_id, race_id=result.race_id,
            predicted_final_position=result.predicted_final_position,
            predicted_total_time_s=result.predicted_total_time_s,
            strategy=[[p, c] for p, c in result.strategy],
            lap_times_s=result.lap_times_s,
        )
    except Exception as exc:
        logger.error("simulate_strategy error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
```

- [ ] **Step 2: Verify**

```bash
python -c "from src.api.routes.simulation import router; print('OK')"
```

---

### Task 4.10: Rewrite `src/api/main.py` as thin app factory

- [ ] **Step 1: Replace main.py contents**

```python
"""
F1 Strategy Optimizer API
App factory: creates FastAPI instance, registers middleware, includes routers.
"""
import logging
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi import Depends, status
from datetime import timedelta

from src.common.security.https_middleware import (
    HTTPSRedirectMiddleware, SecurityHeadersMiddleware,
    RequestValidationMiddleware, RateLimitMiddleware, CORSMiddleware,
)
from src.common.security.iam_simulator import iam_simulator, Token
from src.api.metrics import REQUEST_COUNT
from src.api.startup import startup_event
from src.api.routes import health, strategy, data, simulation

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

ENABLE_HTTPS = os.getenv("ENABLE_HTTPS", "false").lower() == "true"
ENV = os.getenv("ENV", "local")

app = FastAPI(
    title="F1 Strategy Optimizer API",
    description="Real-time race strategy recommendations with <500ms P99 latency",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Middleware
if ENABLE_HTTPS:
    app.add_middleware(HTTPSRedirectMiddleware, enabled=True)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestValidationMiddleware)
app.add_middleware(RateLimitMiddleware, max_requests=100, window_seconds=60)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://localhost:8080", "*"], allow_credentials=True)

# Startup
app.on_event("startup")(startup_event)

# Routers
app.include_router(health.router)
app.include_router(strategy.router)
app.include_router(data.router)
app.include_router(simulation.router)

# OAuth2 + token endpoint (stays in main as app-level concern)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


@app.get("/", response_model=dict)
async def root():
    return {"service": "F1 Strategy Optimizer API", "version": "1.0.0", "status": "running", "docs": "/docs"}


@app.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = iam_simulator.authenticate_user(form_data.username, form_data.password)
    if not user:
        REQUEST_COUNT.labels(method="POST", endpoint="/token", status="401").inc()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password", headers={"WWW-Authenticate": "Bearer"})
    access_token = iam_simulator.create_access_token(data={"sub": user.username, "roles": [r.value for r in user.roles]}, expires_delta=timedelta(minutes=30))
    REQUEST_COUNT.labels(method="POST", endpoint="/token", status="200").inc()
    logger.info("User %s logged in successfully", user.username)
    return Token(access_token=access_token, token_type="bearer")


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path, status=exc.status_code).inc()
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path, status="500").inc()
    logger.error("Unhandled exception: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

- [ ] **Step 2: Verify**

```bash
python -c "from src.api.main import app; print('OK')"
```

---

### Task 4.11: Commit Layer 4

- [ ] **Step 1: Stage and commit**

```bash
git add src/api/models.py src/api/auth.py src/api/metrics.py src/api/startup.py \
        src/api/routes/__init__.py src/api/routes/health.py \
        src/api/routes/strategy.py src/api/routes/data.py \
        src/api/routes/simulation.py src/api/main.py
git commit -m "$(cat <<'EOF'
refactor(src/api): Layer 4 — SRP extract-and-delegate

- models.py: all Pydantic request/response schemas
- auth.py: get_current_user dependency (re-exports from auth_helper)
- metrics.py: Prometheus counter/histogram definitions
- startup.py: lifespan handler, GCS model loading
- routes/health.py: /health, /metrics endpoints
- routes/strategy.py: /strategy/recommend endpoint
- routes/data.py: /data/drivers, /models/status, telemetry endpoints
- routes/simulation.py: /simulate endpoints + _simulators cache
- main.py: ~60-line app factory

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Layer 5: `ml/`

**Files to create:**
- `ml/features/gcs_loader.py`
- `ml/features/parsers.py`
- `ml/features/cache_layer.py`
- `ml/distributed/checkpoint_selector.py`
- `ml/distributed/model_promoter.py`
- `ml/distributed/shard_partitioner.py`
- `ml/dag/components/feature_calculators/__init__.py`
- `ml/dag/components/feature_calculators/gcs_writer.py`
- `ml/dag/components/feature_calculators/tire_degradation.py`
- `ml/dag/components/feature_calculators/gap_evolution.py`
- `ml/dag/components/feature_calculators/undercut_analyzer.py`

**Files to modify:**
- `ml/features/feature_pipeline.py` — state vector assembly only
- `ml/features/feature_store.py` — public API, imports from cache_layer
- `ml/distributed/aggregator.py` — pure coordinator
- `ml/distributed/data_sharding.py` — GCS shard I/O only
- `ml/dag/components/feature_engineering.py` — thin KFP wrapper

---

### Task 5.1: Create `ml/features/parsers.py`

- [ ] **Step 1: Write the file**

```python
"""parsers.py — Lap time parsing, race ID parsing, driver code mapping."""
from __future__ import annotations

import re
from typing import Any, Optional

import numpy as np


def parse_race_id(race_id: str) -> tuple[int, int]:
    """Parse "2024_1" → (2024, 1)."""
    parts = str(race_id).split("_")
    if len(parts) != 2:
        raise ValueError(f"race_id must be '{{season}}_{{round}}', got: {race_id!r}")
    return int(parts[0]), int(parts[1])


def parse_lap_time_ms(time_val: Any) -> float:
    """Convert lap time string '1:37.284' or float seconds to milliseconds."""
    if time_val is None or (isinstance(time_val, float) and np.isnan(time_val)):
        return np.nan
    s = str(time_val).strip()
    if not s or s in ("nan", "None", ""):
        return np.nan
    try:
        return float(s) * 1000.0
    except ValueError:
        pass
    match = re.match(r"^(\d+):(\d+\.?\d*)$", s)
    if match:
        return (int(match.group(1)) * 60 + float(match.group(2))) * 1000.0
    return np.nan


def map_driver_code(drivers_df: "pd.DataFrame", driver_id: str) -> Optional[str]:
    """Map Ergast driverRef (e.g. 'max_verstappen') → FastF1 3-letter code ('VER')."""
    import pandas as pd
    if "driverId" not in drivers_df.columns or "code" not in drivers_df.columns:
        return None
    row = drivers_df[drivers_df["driverId"] == driver_id]
    if row.empty:
        return None
    code = row.iloc[0]["code"]
    return str(code) if pd.notna(code) else None
```

- [ ] **Step 2: Verify**

```bash
python -c "from ml.features.parsers import parse_race_id, parse_lap_time_ms, map_driver_code; print('OK')"
```

---

### Task 5.2: Create `ml/features/gcs_loader.py`

- [ ] **Step 1: Write the file**

```python
"""gcs_loader.py — GCS Parquet reading with in-memory caching."""
from __future__ import annotations

import io
import logging
from typing import Dict, Optional

import pandas as pd
from google.cloud import storage

logger = logging.getLogger(__name__)

DATA_BUCKET = "f1optimizer-data-lake"
PROCESSED_PREFIX = "processed"
PROJECT_ID = "f1optimizer"


class GCSLoader:
    """Loads Parquet files from GCS and caches them in memory."""

    def __init__(self, project: str = PROJECT_ID, bucket: str = DATA_BUCKET) -> None:
        self._client = storage.Client(project=project)
        self._bucket_name = bucket
        self._cache: Dict[str, pd.DataFrame] = {}

    def load(self, blob_path: str, force: bool = False) -> pd.DataFrame:
        """Load *blob_path* from GCS, using in-memory cache on subsequent calls."""
        if not force and blob_path in self._cache:
            return self._cache[blob_path]
        bucket = self._client.bucket(self._bucket_name)
        blob = bucket.blob(blob_path)
        if not blob.exists():
            logger.warning("GCSLoader: blob not found gs://%s/%s", self._bucket_name, blob_path)
            return pd.DataFrame()
        buf = io.BytesIO()
        blob.download_to_file(buf)
        buf.seek(0)
        df = pd.read_parquet(buf)
        self._cache[blob_path] = df
        logger.info("GCSLoader: loaded gs://%s/%s (%d rows)", self._bucket_name, blob_path, len(df))
        return df

    def load_processed(self, filename: str) -> pd.DataFrame:
        return self.load(f"{PROCESSED_PREFIX}/{filename}")
```

- [ ] **Step 2: Verify**

```bash
python -c "from ml.features.gcs_loader import GCSLoader; print('OK')"
```

---

### Task 5.3: Create `ml/features/cache_layer.py`

- [ ] **Step 1: Write the file**

```python
"""cache_layer.py — Local disk + GCS cache read/write for computed feature vectors."""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Optional

import pandas as pd
from google.cloud import storage

logger = logging.getLogger(__name__)

GCS_CACHE_PREFIX = "cache"


class CacheLayer:
    def __init__(
        self,
        training_bucket_name: str,
        local_cache_dir: str,
        gcs_client: storage.Client,
    ) -> None:
        self._bucket_name = training_bucket_name
        self._local_dir = Path(local_cache_dir)
        self._local_dir.mkdir(parents=True, exist_ok=True)
        self._gcs = gcs_client

    def _local_path(self, race_id: str) -> Path:
        return self._local_dir / f"race_{race_id.replace('/', '_')}.parquet"

    def _blob_path(self, race_id: str) -> str:
        return f"{GCS_CACHE_PREFIX}/race_{race_id.replace('/', '_')}.parquet"

    def read(self, race_id: str) -> Optional[pd.DataFrame]:
        """Try local cache first, then GCS. Returns None on miss."""
        local = self._local_path(race_id)
        if local.exists():
            logger.info("CacheLayer: local hit race_id=%s", race_id)
            return pd.read_parquet(local)
        blob = self._gcs.bucket(self._bucket_name).blob(self._blob_path(race_id))
        try:
            if blob.exists():
                buf = io.BytesIO()
                blob.download_to_file(buf)
                buf.seek(0)
                df = pd.read_parquet(buf)
                logger.info("CacheLayer: GCS hit race_id=%s", race_id)
                try:
                    df.to_parquet(local, index=False)
                except Exception:
                    pass
                return df
        except Exception as exc:
            logger.debug("CacheLayer: GCS read failed for %s: %s", race_id, exc)
        return None

    def write(self, race_id: str, df: pd.DataFrame) -> None:
        """Write to local cache and GCS."""
        local = self._local_path(race_id)
        try:
            df.to_parquet(local, index=False)
        except Exception as exc:
            logger.debug("CacheLayer: local write failed: %s", exc)
        try:
            buf = io.BytesIO()
            df.to_parquet(buf, index=False)
            buf.seek(0)
            self._gcs.bucket(self._bucket_name).blob(
                self._blob_path(race_id)
            ).upload_from_file(buf, content_type="application/octet-stream")
        except Exception as exc:
            logger.debug("CacheLayer: GCS write failed: %s", exc)
```

- [ ] **Step 2: Verify**

```bash
python -c "from ml.features.cache_layer import CacheLayer; print('OK')"
```

---

### Task 5.4: Create `ml/distributed/checkpoint_selector.py`

- [ ] **Step 1: Write the file**

```python
"""checkpoint_selector.py — GCS checkpoint scanning and best selection by val_loss."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

from google.cloud import storage

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("PROJECT_ID", "f1optimizer")
TRAINING_BUCKET = os.environ.get("TRAINING_BUCKET", "gs://f1optimizer-training").lstrip("gs://")


@dataclass
class CheckpointMeta:
    gcs_uri: str
    worker_index: int
    val_loss: float
    epoch: int
    metrics: dict


def list_checkpoints(run_id: str) -> list[CheckpointMeta]:
    """Scan gs://f1optimizer-training/checkpoints/<run_id>/ for manifests."""
    client = storage.Client(project=PROJECT_ID)
    bucket = client.bucket(TRAINING_BUCKET)
    prefix = f"checkpoints/{run_id}/"
    blobs = list(bucket.list_blobs(prefix=prefix, match_glob="**/manifest.json"))
    checkpoints = []
    for blob in blobs:
        data = json.loads(blob.download_as_text())
        checkpoints.append(CheckpointMeta(
            gcs_uri=data["checkpoint_uri"],
            worker_index=data.get("worker_index", 0),
            val_loss=data["val_loss"],
            epoch=data.get("epoch", 0),
            metrics=data.get("metrics", {}),
        ))
    logger.info("Found %d checkpoints for run %s", len(checkpoints), run_id)
    return checkpoints


def select_best(run_id: str) -> CheckpointMeta:
    """Return the checkpoint with the lowest validation loss."""
    checkpoints = list_checkpoints(run_id)
    if not checkpoints:
        raise RuntimeError(f"No checkpoints found for run {run_id}")
    best = min(checkpoints, key=lambda c: c.val_loss)
    logger.info("Best checkpoint: worker=%d val_loss=%.6f epoch=%d uri=%s",
                best.worker_index, best.val_loss, best.epoch, best.gcs_uri)
    return best
```

- [ ] **Step 2: Verify**

```bash
python -c "from ml.distributed.checkpoint_selector import select_best, CheckpointMeta; print('OK')"
```

---

### Task 5.5: Create `ml/distributed/model_promoter.py`

- [ ] **Step 1: Write the file**

```python
"""model_promoter.py — Copy checkpoint to latest/ + versioned path, write model card."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from google.cloud import storage

from .checkpoint_selector import CheckpointMeta

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("PROJECT_ID", "f1optimizer")
MODELS_BUCKET = os.environ.get("MODELS_BUCKET", "gs://f1optimizer-models").lstrip("gs://")


def promote_model(model_name: str, run_id: str, checkpoint: CheckpointMeta) -> str:
    """
    Copy checkpoint to gs://f1optimizer-models/<model_name>/latest/ and
    a timestamped path. Returns the versioned GCS URI.
    """
    client = storage.Client(project=PROJECT_ID)
    source_bucket_name, *parts = checkpoint.gcs_uri.lstrip("gs://").split("/")
    source_prefix = "/".join(parts)
    source_bucket = client.bucket(source_bucket_name)
    dest_bucket = client.bucket(MODELS_BUCKET)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest_versioned = f"{model_name}/{timestamp}/"
    dest_latest = f"{model_name}/latest/"

    for blob in source_bucket.list_blobs(prefix=source_prefix):
        relative = blob.name[len(source_prefix):].lstrip("/")
        for dest_prefix in (dest_versioned, dest_latest):
            dest_blob = dest_bucket.blob(f"{dest_prefix}{relative}")
            token, _, _ = dest_blob.rewrite(blob)
            while token is not None:
                token, _, _ = dest_blob.rewrite(blob, rewrite_token=token)

    final_uri = f"gs://{MODELS_BUCKET}/{dest_versioned}"
    logger.info("Model promoted to %s (also at latest/)", final_uri)

    card: dict[str, Any] = {
        "model_name": model_name, "run_id": run_id,
        "promoted_at": timestamp, "val_loss": checkpoint.val_loss,
        "epoch": checkpoint.epoch, "metrics": checkpoint.metrics,
        "source_checkpoint": checkpoint.gcs_uri, "gcs_uri": final_uri,
    }
    card_json = json.dumps(card, indent=2)
    dest_bucket.blob(f"{dest_versioned}model_card.json").upload_from_string(card_json, content_type="application/json")
    dest_bucket.blob(f"{dest_latest}model_card.json").upload_from_string(card_json, content_type="application/json")
    return final_uri
```

- [ ] **Step 2: Verify**

```bash
python -c "from ml.distributed.model_promoter import promote_model; print('OK')"
```

---

### Task 5.6: Create `ml/distributed/shard_partitioner.py`

- [ ] **Step 1: Write the file**

```python
"""shard_partitioner.py — Race ID fetching from Cloud SQL + division across workers."""
from __future__ import annotations

import logging
import os

from google.cloud.sql.connector import Connector

logger = logging.getLogger(__name__)

INSTANCE_CONNECTION_NAME = os.environ.get("INSTANCE_CONNECTION_NAME", "f1optimizer:us-central1:f1-optimizer-dev")
DB_NAME = os.environ.get("DB_NAME", "f1_strategy")
DB_USER = os.environ.get("DB_USER", "f1_app")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")


def fetch_all_race_ids(connector: Connector) -> list[int]:
    """Return all race_ids from Cloud SQL ordered by year and round."""
    conn = connector.connect(INSTANCE_CONNECTION_NAME, "pg8000", user=DB_USER, password=DB_PASSWORD, db=DB_NAME)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT race_id FROM races ORDER BY year ASC, round ASC")
        return [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()


def get_worker_slice(all_ids: list[int], worker_index: int, num_workers: int) -> list[int]:
    """Return the disjoint slice of race_ids for *worker_index*."""
    total = len(all_ids)
    base_size = total // num_workers
    remainder = total % num_workers
    start = worker_index * base_size + min(worker_index, remainder)
    end = start + base_size + (1 if worker_index < remainder else 0)
    assigned = all_ids[start:end]
    logger.info("Worker %d/%d assigned %d races", worker_index, num_workers, len(assigned))
    return assigned
```

- [ ] **Step 2: Verify**

```bash
python -c "from ml.distributed.shard_partitioner import fetch_all_race_ids, get_worker_slice; print('OK')"
```

---

### Task 5.7: Create `ml/dag/components/feature_calculators/` package and files

- [ ] **Step 1: Write `__init__.py`**

```python
"""feature_calculators — extracted single-purpose feature calculation modules."""
```

- [ ] **Step 2: Write `gcs_writer.py`**

```python
"""gcs_writer.py — DataFrame serialization + GCS upload helper."""
from __future__ import annotations

import logging

import pandas as pd
from google.cloud import storage

logger = logging.getLogger(__name__)


def upload_df(
    df: pd.DataFrame,
    bucket: storage.Bucket,
    blob_path: str,
) -> str:
    """Serialize *df* to Parquet and upload to *bucket*/*blob_path*. Returns gs:// URI."""
    bucket.blob(blob_path).upload_from_string(
        df.to_parquet(index=False), content_type="application/octet-stream"
    )
    uri = f"gs://{bucket.name}/{blob_path}"
    logger.info("gcs_writer: wrote %d rows to %s", len(df), uri)
    return uri
```

- [ ] **Step 3: Write `tire_degradation.py`**

```python
"""tire_degradation.py — Tire degradation curve calculation."""
from __future__ import annotations

import pandas as pd


def compute_tire_degradation(laps: pd.DataFrame) -> pd.DataFrame:
    """
    Given a laps DataFrame with columns [race_id, driver_id, lap_number,
    lap_time_ms, tire_compound, tire_age_laps], compute degradation curves.

    Returns a DataFrame with columns [tire_compound, tire_age_laps,
    deg_mean_ms, deg_std_ms, sample_count].
    """
    laps = laps.sort_values(["race_id", "driver_id", "lap_number"])
    laps = laps.copy()
    laps["lap_time_delta"] = laps.groupby(["race_id", "driver_id"])["lap_time_ms"].diff()
    return (
        laps.groupby(["tire_compound", "tire_age_laps"])["lap_time_delta"]
        .agg(["mean", "std", "count"])
        .reset_index()
        .rename(columns={"mean": "deg_mean_ms", "std": "deg_std_ms", "count": "sample_count"})
    )
```

- [ ] **Step 4: Write `gap_evolution.py`**

```python
"""gap_evolution.py — Gap tracking feature computation."""
from __future__ import annotations

import pandas as pd


def compute_gap_evolution(laps: pd.DataFrame) -> pd.DataFrame:
    """
    Add gap_delta column = per-lap change in gap_to_car_ahead_ms.
    Returns the input DataFrame with gap_delta appended.
    """
    laps = laps.copy()
    laps["gap_delta"] = laps.groupby(["race_id", "driver_id"])["gap_to_car_ahead_ms"].diff()
    return laps
```

- [ ] **Step 5: Write `undercut_analyzer.py`**

```python
"""undercut_analyzer.py — Undercut/overcut window analysis."""
from __future__ import annotations

import pandas as pd


def compute_undercut_windows(laps: pd.DataFrame) -> pd.DataFrame:
    """
    Compute position gain for pit-stop laps.

    Input laps needs: [race_id, driver_id, lap_number, position, pit_stop_flag].
    Returns DataFrame with [race_id, driver_id, lap_number, position,
    position_after, position_gain].
    """
    pit_laps = laps[laps["pit_stop_flag"] == 1].copy()
    if pit_laps.empty:
        return pd.DataFrame(columns=["race_id", "driver_id", "lap_number", "position", "position_after", "position_gain"])
    pit_laps["position_after"] = laps.groupby(["race_id", "driver_id"])["position"].shift(-2)
    pit_laps["position_gain"] = pit_laps["position"] - pit_laps["position_after"]
    return pit_laps[["race_id", "driver_id", "lap_number", "position", "position_after", "position_gain"]]
```

- [ ] **Step 6: Verify all**

```bash
python -c "
from ml.dag.components.feature_calculators.gcs_writer import upload_df
from ml.dag.components.feature_calculators.tire_degradation import compute_tire_degradation
from ml.dag.components.feature_calculators.gap_evolution import compute_gap_evolution
from ml.dag.components.feature_calculators.undercut_analyzer import compute_undercut_windows
print('OK')
"
```

---

### Task 5.8: Update `ml/features/feature_pipeline.py`

- [ ] **Step 1: Add imports**

```python
from .parsers import parse_race_id, parse_lap_time_ms, map_driver_code
from .gcs_loader import GCSLoader
```

- [ ] **Step 2: Remove local definitions**

Delete `_parse_race_id` and `_parse_lap_time_ms` module-level functions.

Remove the `_driver_code` method from `FeaturePipeline` (lines 126-135). Replace its call sites inside `FeaturePipeline` with `map_driver_code(self._drivers(), driver_id)`.

- [ ] **Step 3: Update `FeaturePipeline` to use `GCSLoader`**

In `FeaturePipeline.__init__`, add:
```python
self._loader = GCSLoader(project=PROJECT_ID, bucket=DATA_BUCKET)
```

Replace any `io.BytesIO` + `bucket.blob(...).download_to_file(...)` + `pd.read_parquet(...)` patterns in `FeaturePipeline` with calls to `self._loader.load_processed(filename)`.

Replace all calls to `_parse_race_id(...)` with `parse_race_id(...)` and `_parse_lap_time_ms(...)` with `parse_lap_time_ms(...)`.

- [ ] **Step 4: Verify**

```bash
python -c "from ml.features.feature_pipeline import FeaturePipeline; print('OK')"
```

---

### Task 5.9: Update `ml/features/feature_store.py`

- [ ] **Step 1: Add imports**

```python
from .cache_layer import CacheLayer
```

- [ ] **Step 2: Update `FeatureStore.__init__`**

Add:
```python
self._cache_layer = CacheLayer(
    training_bucket_name=self._training_bucket_name,
    local_cache_dir=local_cache_dir,
    gcs_client=self._gcs_client,
)
```

- [ ] **Step 3: Delegate cache methods**

Replace `_local_path`, `_gcs_blob_path`, `_read_gcs_cache`, `_write_caches` methods with delegation to `self._cache_layer`:

In `load_race_features`:
- Replace `local = self._local_path(race_id)` + subsequent local read with `cached = self._cache_layer.read(race_id)`
- Replace `self._write_caches(race_id, df)` with `self._cache_layer.write(race_id, df)`

Remove the four helper methods (`_local_path`, `_gcs_blob_path`, `_read_gcs_cache`, `_write_caches`) — they now live in `CacheLayer`.

- [ ] **Step 4: Verify**

```bash
python -c "from ml.features.feature_store import FeatureStore; print('OK')"
```

---

### Task 5.10: Update `ml/distributed/aggregator.py`

- [ ] **Step 1: Add imports**

```python
from .checkpoint_selector import CheckpointMeta, select_best as _select_best
from .model_promoter import promote_model as _promote_model
```

- [ ] **Step 2: Remove extracted methods from `Aggregator`**

Delete `list_checkpoints` and `save_final_model` from `Aggregator`.

- [ ] **Step 3: Update `Aggregator` methods to delegate**

Replace `pick_best_checkpoint`:
```python
def pick_best_checkpoint(self) -> CheckpointMeta:
    return _select_best(self.run_id)
```

Replace `save_final_model`:
```python
def save_final_model(self, checkpoint: CheckpointMeta) -> str:
    return _promote_model(self.model_name, self.run_id, checkpoint)
```

Keep `publish_completion` in `Aggregator` — it's the Pub/Sub notification, correctly scoped here.

Also remove `CheckpointMeta` dataclass definition (now imported from `checkpoint_selector`).

- [ ] **Step 4: Verify**

```bash
python -c "from ml.distributed.aggregator import Aggregator; print('OK')"
```

---

### Task 5.11: Update `ml/distributed/data_sharding.py`

- [ ] **Step 1: Add import**

```python
from .shard_partitioner import fetch_all_race_ids, get_worker_slice
```

- [ ] **Step 2: Remove extracted methods from `DataSharding`**

Delete `_get_connection` and `_fetch_all_race_ids` from `DataSharding`.

- [ ] **Step 3: Update `get_worker_race_ids`**

Replace `DataSharding.get_worker_race_ids` body:
```python
def get_worker_race_ids(self, worker_index: int) -> list[int]:
    from google.cloud.sql.connector import Connector
    connector = Connector()
    try:
        all_ids = fetch_all_race_ids(connector)
    finally:
        connector.close()
    return get_worker_slice(all_ids, worker_index, self.num_workers)
```

Remove `_get_connection` and `_connector` attribute from `DataSharding.__init__` and `close()`.

Also remove `_fetch_all_race_ids` from `DataSharding`.

- [ ] **Step 4: Verify**

```bash
python -c "from ml.distributed.data_sharding import DataSharding; print('OK')"
```

---

### Task 5.12: Update `ml/dag/components/feature_engineering.py`

- [ ] **Step 1: Import from feature_calculators inside the KFP component function**

Inside `feature_engineering_op` function body (after the existing imports section), add:
```python
from ml.dag.components.feature_calculators.tire_degradation import compute_tire_degradation
from ml.dag.components.feature_calculators.gap_evolution import compute_gap_evolution
from ml.dag.components.feature_calculators.undercut_analyzer import compute_undercut_windows
from ml.dag.components.feature_calculators.gcs_writer import upload_df as _upload_df
```

Note: These imports are inside the function because KFP components serialize the function body — top-level imports outside the decorated function are not available inside the container.

- [ ] **Step 2: Replace inline calculation blocks with calls to extractors**

Replace the tire degradation inline block:
```python
deg_curve = compute_tire_degradation(laps)
```

Replace the gap evolution inline block:
```python
laps = compute_gap_evolution(laps)
```

Replace the undercut/overcut inline block:
```python
undercut_windows = compute_undercut_windows(laps)
```

Replace the inline `upload_df` definition + calls:
```python
def upload_df(df, name):
    uri = f"gs://{bucket_name}/{base_prefix}/{name}.parquet"
    _upload_df(df, bucket, f"{base_prefix}/{name}.parquet")
    logger.info("feature_engineering: wrote %s (%d rows) to %s", name, len(df), uri)
    return uri
```

- [ ] **Step 3: Verify KFP component still loads**

```bash
python -c "from ml.dag.components.feature_engineering import feature_engineering_op; print('OK')"
```

---

### Task 5.13: Commit Layer 5

- [ ] **Step 1: Stage and commit**

```bash
git add ml/features/parsers.py ml/features/gcs_loader.py ml/features/cache_layer.py \
        ml/distributed/checkpoint_selector.py ml/distributed/model_promoter.py \
        ml/distributed/shard_partitioner.py \
        ml/dag/components/feature_calculators/__init__.py \
        ml/dag/components/feature_calculators/gcs_writer.py \
        ml/dag/components/feature_calculators/tire_degradation.py \
        ml/dag/components/feature_calculators/gap_evolution.py \
        ml/dag/components/feature_calculators/undercut_analyzer.py \
        ml/features/feature_pipeline.py ml/features/feature_store.py \
        ml/distributed/aggregator.py ml/distributed/data_sharding.py \
        ml/dag/components/feature_engineering.py
git commit -m "$(cat <<'EOF'
refactor(ml): Layer 5 — SRP extract-and-delegate

- features/parsers.py: parse_race_id, parse_lap_time_ms, map_driver_code
- features/gcs_loader.py: GCS Parquet loading with in-memory cache
- features/cache_layer.py: local disk + GCS cache read/write
- distributed/checkpoint_selector.py: GCS checkpoint scan + best selection
- distributed/model_promoter.py: GCS copy to latest/ + model card
- distributed/shard_partitioner.py: Cloud SQL race_id fetch + worker slice
- feature_calculators/gcs_writer.py: upload_df helper
- feature_calculators/tire_degradation.py: degradation curve calculation
- feature_calculators/gap_evolution.py: gap delta computation
- feature_calculators/undercut_analyzer.py: undercut/overcut window analysis
- feature_pipeline, feature_store, aggregator, data_sharding,
  feature_engineering: thin orchestrators

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Post-Refactor Verification

After all five layers are committed, run the full import check:

```bash
cd /Users/bhargav/Documents/F1-Strategy-Optimizer
python -c "
from ingest.http_utils import rate_limited_get, retry_forever
from ingest.jolpica_client import paginate, fetch_json
from ingest.telemetry_extractor import extract_telemetry
from ingest.gcs_utils import blob_exists, upload_parquet
from src.ingestion.http_client import fetch_json
from src.ingestion.ergast_client import paginate
from src.preprocessing.schema_validator import validate_dataframe
from src.preprocessing.quality_metrics import check_data_quality
from src.preprocessing.data_sanitizer import sanitize_data
from src.common.security.role_permissions import Role, Permission
from src.common.security.token_manager import create_access_token
from src.common.security.password_manager import hash_password
from src.common.security.https_middleware import HTTPSRedirectMiddleware, SecurityHeadersMiddleware, CORSMiddleware, get_current_user
from src.common.security.iam_simulator import IAMSimulator, Role, Permission
from src.api.models import StrategyRequest, SimulateRequest
from src.api.metrics import REQUEST_COUNT
from src.api.startup import startup_event
from ml.features.parsers import parse_race_id, parse_lap_time_ms
from ml.features.gcs_loader import GCSLoader
from ml.features.cache_layer import CacheLayer
from ml.distributed.checkpoint_selector import select_best, CheckpointMeta
from ml.distributed.model_promoter import promote_model
from ml.distributed.shard_partitioner import get_worker_slice
print('All imports OK')
"
```
