# SRP Refactor Design
**Date:** 2026-03-19
**Status:** Approved

## Overview

Refactor the F1 Strategy Optimizer codebase layer by layer to enforce single responsibility principle (SRP) per file. Each layer is committed independently to preserve git history and enable safe rollback. Tests are excluded from this refactor and addressed in a follow-up.

## Approach: Extract-and-Delegate

Keep original filenames as public entry points. Extract distinct concerns into sibling files. Original files import from extracted files and delegate — callers see no import breakage.

## Layer Order

1. `ingest/` — Cloud Run workers (highest priority)
2. `src/ingestion/` + `src/preprocessing/`
3. `src/common/security/`
4. `src/api/`
5. `ml/features/`, `ml/distributed/`, `ml/dag/components/`

---

## Layer 1: `ingest/`

**Problem:** `gap_worker.py` (376 lines) handles 8+ concerns. `fastf1_worker.py`, `historical_worker.py`, and `lap_times_worker.py` each mix HTTP transport, API interaction, data extraction, and orchestration.

**Extractions:**

| New file | Responsibility | Extracted from |
|---|---|---|
| `ingest/http_utils.py` | Rate-limited GET, exponential backoff, retry-forever wrapper | gap_worker, historical_worker, fastf1_worker |
| `ingest/jolpica_client.py` | Jolpica API pagination + response parsing (seasons, results, laps, pit stops) | gap_worker, historical_worker |
| `ingest/telemetry_extractor.py` | FastF1 telemetry extraction per lap, column normalization | gap_worker, fastf1_worker |
| `ingest/gcs_utils.py` | Absorbs `blob_exists` from gap_worker and lap_times_worker (deduplication); `upload_parquet` and `upload_done_marker` already exist here | gap_worker, lap_times_worker |

**`gcs_utils.py` merge rules:**
- Canonical `upload_parquet` signature: `(df, bucket, blob_path)` — matching the existing file. Callers in `gap_worker` and `lap_times_worker` that pass arguments in a different order must be updated in the same commit.
- Add `blob_exists(bucket: storage.Bucket, path: str) -> bool` consolidated from both `gap_worker` and `lap_times_worker`.

**Files not touched in this layer:** `ingest/progress.py` (GCS-backed progress tracker, already correctly scoped) and `ingest/task.py` (Cloud Run entry point, already thin) are left as-is.

**Result:** `gap_worker.py`, `fastf1_worker.py`, `historical_worker.py`, `lap_times_worker.py` become thin orchestrators containing only job routing and high-level loop logic.

---

## Layer 2: `src/ingestion/` + `src/preprocessing/`

**Problem:** `ergast_ingestion.py` (335 lines) and `fastf1_ingestion.py` (321 lines) mix HTTP transport, API client logic, and orchestration. `validator.py` (337 lines) mixes schema validation, quality metrics, and data cleaning.

**Extractions:**

| New file | Responsibility | Extracted from |
|---|---|---|
| `src/ingestion/http_client.py` | Rate-limited GET, retry logic, shared request session | ergast_ingestion, fastf1_ingestion |
| `src/ingestion/ergast_client.py` | Jolpica/Ergast pagination + endpoint mapping | ergast_ingestion |
| `src/ingestion/fastf1_extractor.py` | FastF1 session loading, timedelta conversion, column normalization | fastf1_ingestion |
| `src/preprocessing/schema_validator.py` | Pydantic schema definitions + per-record validation | validator |
| `src/preprocessing/quality_metrics.py` | Completeness, validity, consistency, accuracy scoring | validator |
| `src/preprocessing/data_sanitizer.py` | Deduplication, whitespace stripping, null handling | validator |

**Result:**
- `ergast_ingestion.py` — season-level fetch orchestration only
- `fastf1_ingestion.py` — season loop + file write orchestration only
- `validator.py` — aggregates results from the three preprocessing modules, returns combined report

---

## Layer 3: `src/common/security/`

**Problem:** `https_middleware.py` (260 lines) contains 5 unrelated middleware classes. `iam_simulator.py` (333 lines) mixes password hashing, JWT management, user storage, and authorization.

**Extractions:**

| New file | Responsibility | Extracted from |
|---|---|---|
| `src/common/security/security_headers_middleware.py` | `SecurityHeadersMiddleware` class only | https_middleware |
| `src/common/security/request_validation_middleware.py` | `RequestValidationMiddleware` + `_is_suspicious` attack detection | https_middleware |
| `src/common/security/rate_limit_middleware.py` | `RateLimitMiddleware` + per-IP request tracking | https_middleware |
| `src/common/security/cors_middleware.py` | `CORSMiddleware` class only | https_middleware |
| `src/common/security/token_manager.py` | JWT creation + verification only | iam_simulator |
| `src/common/security/password_manager.py` | Password hashing + verification only | iam_simulator |
| `src/common/security/role_permissions.py` | `Role`, `Permission` enums + role→permission mapping | iam_simulator |

**Result:**
- `https_middleware.py` — keeps only `HTTPSRedirectMiddleware`, imports + re-exports the 4 extracted classes for backward compatibility. `get_current_user` (auth logic, not middleware) is moved to `src/common/security/auth_helper.py` in this layer so it is not left stranded until Layer 4.
- `iam_simulator.py` — keeps only `IAMSimulator` user CRUD + authorization logic

**Additional extraction:**

| New file | Responsibility | Extracted from |
|---|---|---|
| `src/common/security/auth_helper.py` | `get_current_user` FastAPI dependency — token validation + user lookup | https_middleware |

**Naming note:** The custom `CORSMiddleware` in `cors_middleware.py` does not conflict with Starlette's own `CORSMiddleware` since the app registers it by direct class reference; no aliasing needed.

---

## Layer 4: `src/api/`

**Problem:** `main.py` (660 lines) handles 7+ concerns: routing, authentication, ML model loading, Prometheus metrics, Pydantic models, middleware registration, and business logic per endpoint.

**Extractions:**

| New file | Responsibility | Extracted from |
|---|---|---|
| `src/api/models.py` | All Pydantic request/response schemas | main.py |
| `src/api/auth.py` | `get_current_user` dependency, token validation, user extraction | auth_helper.py (moved there in Layer 3) |
| `src/api/metrics.py` | Prometheus counter/histogram definitions + tracking helpers | main.py |
| `src/api/startup.py` | `lifespan` handler — ML model loading from GCS, lazy pipeline init | main.py |
| `src/api/routes/strategy.py` | `/strategy/recommend` endpoint logic | main.py |
| `src/api/routes/data.py` | `/drivers`, `/models/status`, `/telemetry` endpoints | main.py |
| `src/api/routes/simulation.py` | `/simulate` endpoint + race state logic | main.py |
| `src/api/routes/health.py` | `/health`, `/metrics` endpoints | main.py |

**Scope clarification:**
- `startup.py` owns only the `lifespan` handler and GCS-loaded model state (`_strategy_model`, `_pit_model`). It does NOT own the per-request simulator cache.
- `_simulators: Dict[str, Any]` and `_get_simulator()` belong in `routes/simulation.py` alongside the `/simulate` endpoint — they are per-request lazy state, not startup state.
- `get_current_user` moves from `https_middleware.py` (Layer 3) to `auth.py` in this layer.

**Result:** `main.py` becomes a ~60-line app factory: creates `FastAPI` instance, registers middleware, includes routers, wires `startup.py` lifespan.

---

## Layer 5: `ml/`

**Problem:** `feature_pipeline.py` (474 lines) mixes GCS loading, parsing, ID mapping, and feature engineering. `feature_store.py` (228 lines) mixes two-level caching with multi-granularity feature loading. `aggregator.py` mixes checkpoint discovery, selection, model promotion, and event publishing. `data_sharding.py` mixes DB connectivity with shard logic. `feature_engineering.py` KFP component contains 10+ inline calculations.

**Extractions:**

| New file | Responsibility | Extracted from |
|---|---|---|
| `ml/features/gcs_loader.py` | GCS Parquet reading + local caching for raw data files | feature_pipeline |
| `ml/features/parsers.py` | `_parse_lap_time_ms`, `_parse_race_id`, driver code mapping | feature_pipeline |
| `ml/features/cache_layer.py` | Local disk + GCS cache read/write for computed feature vectors | feature_store |
| `ml/distributed/checkpoint_selector.py` | GCS checkpoint scanning (`list_checkpoints`) + best selection by val_loss | aggregator |
| `ml/distributed/model_promoter.py` | GCS copy to `latest/` + versioned path, model card writing | aggregator |
| `ml/dag/components/feature_calculators/gcs_writer.py` | `upload_df` helper — DataFrame serialization + GCS upload | feature_engineering |
| `ml/distributed/shard_partitioner.py` | Race ID fetching from Cloud SQL + division across workers | data_sharding |
| `ml/dag/components/feature_calculators/tire_degradation.py` | Tire degradation curve calculation | feature_engineering |
| `ml/dag/components/feature_calculators/gap_evolution.py` | Gap tracking feature computation | feature_engineering |
| `ml/dag/components/feature_calculators/undercut_analyzer.py` | Undercut/overcut window analysis | feature_engineering |

**`checkpoint_selector.py` design:** takes no external input — it calls `list_checkpoints` internally (scanning GCS) and returns the best `CheckpointMeta`. `list_checkpoints` moves entirely into `checkpoint_selector.py`. This avoids any circular import with `aggregator.py`.

**`feature_engineering.py` KFP wrapper scope:** DB connection setup (`Connector`, `get_conn`), Pub/Sub client init, and the `publish()` helper remain in the KFP component wrapper as KFP-specific infrastructure plumbing — acknowledged as out-of-scope for this pass. Only the three calculation blocks and the GCS upload helper are extracted.

**Result:**
- `feature_pipeline.py` — state vector assembly only, imports from `gcs_loader`, `parsers`
- `feature_store.py` — public API coordinating `cache_layer` + `feature_pipeline`
- `aggregator.py` — pure coordinator: calls `checkpoint_selector`, `model_promoter`, and `publish_completion`; `publish_completion` stays here as Pub/Sub notification
- `data_sharding.py` — GCS shard I/O only, imports from `shard_partitioner`
- `feature_engineering.py` — thin KFP wrapper: DB/Pub/Sub init + calls `feature_calculators/`

---

## Constraints

- **No test changes** — tests are a follow-up layer
- **No import breakage** — all original filenames preserved as re-export points
- **Commit after each layer** — one commit per layer for safe rollback
- **No behavioral changes** — pure structural refactor, no logic modifications
