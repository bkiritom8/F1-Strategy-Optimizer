# Project Progress Log

**Purpose**: Append-only session log tracking all major decisions, implementations, and milestones.

**Format**: Each session appends a new entry with date, summary, decisions, and next steps.

**Instructions**:
- At the end of each session (after /compact), append a new entry
- Keep entries concise (200-300 words max)
- Focus on: code changes, architecture decisions, model behavior, blockers

---

## Session 2026-02-14 - Initial Setup

**Date**: 2026-02-14
**Duration**: Initial setup
**Participants**: Claude Code

**Summary**:
Initialized F1 Complete Race Strategy Optimizer project with comprehensive documentation structure. Created persistent project memory system following modular context approach.

**Completed**:
- [OK] Created CLAUDE.md as single source of truth (≤5000 tokens)
- [OK] Established docs/ directory with modular documentation:
  - docs/data.md: Data sources, splits, management (comprehensive)
  - docs/models.md: ML architectures, training, validation
  - docs/architecture.md: System design, deployment, infrastructure
  - docs/metrics.md: KPIs, targets, validation criteria
  - docs/monitoring.md: Operational monitoring, alerting, runbooks
  - docs/roadmap.md: 13-week timeline, phases, milestones
- [OK] Initialized docs/progress.md (this file) and session_summary.md
- [OK] Set up branch: claude/f1-strategy-optimizer-lh9No

**Key Decisions**:
1. **Modular Documentation**: Large content separated into specialized docs/ files rather than bloating CLAUDE.md
2. **Tech Stack Confirmed**: GCP (BigQuery, Dataflow, Cloud Run, Vertex AI) for integrated ecosystem
3. **4-Model Architecture**: Tire degradation (XGBoost), Fuel consumption (LSTM), Brake bias (LinReg), Driving style (DecisionTree)
4. **Temporal Split Strategy**: 1950-2022 train, 2023 Q1-Q2 val, 2023 Q3-Q4 + 2024 test (prevents data leakage)
5. **Success Metrics**: Podium ≥70%, Winner ≥65%, API P99 <500ms, Cost <$0.001/prediction

**Architecture Highlights**:
- Data Layer: Ergast API (1950-2024) + FastF1 (2018-2024, 10Hz telemetry)
- Feature Store: BigQuery partitioned by race_date
- ML Layer: 4 specialized models + Monte Carlo simulator (10K scenarios)
- Serving: FastAPI on Cloud Run with <500ms P99 latency target
- Monitoring: Cloud Monitoring with 6 alert policies

**Known Bottlenecks Identified**:
- [CRITICAL] Monte Carlo simulation (10K scenarios) → Mitigation: GPU acceleration, reduce to 5K live
- [CRITICAL] Real-time inference latency → Mitigation: Model caching, quantization (FP32→INT8)
- [CRITICAL] API response time target → Mitigation: Cloud Run autoscaling, load testing
- [HIGH] Model training compute → Mitigation: Vertex AI distributed training

**Hard Constraints**:
- Telemetry only 2018+ (earlier races have partial data)
- Budget: ~$200-250/month GCP spend
- P99 latency must be <500ms (pit wall requirement)
- Uptime 99.5% during race weekends

**Next Steps**:
1. Commit and push documentation structure to branch
2. Run setup.sh to configure GCP project
3. Begin data ingestion (Ergast + FastF1 download)
4. Create BigQuery schema and raw tables
5. Start driver profile extraction (Week 3-4)

**Blockers**: None

**Notes**:
- Repository structure aligns with specification
- All documentation cross-referenced for easy navigation
- Session hygiene protocol established (append to progress.md after /compact)
- Compaction discipline: Every ~40 messages, run /compact

---

## Session 2026-02-17 - Terraform: BigQuery → Cloud SQL Migration

**Date**: 2026-02-17
**Duration**: ~3 hours
**Participants**: Claude Code

**Summary**:
Migrated entire GCP infrastructure from BigQuery to Cloud SQL (PostgreSQL 15). Applied Terraform to provision Cloud SQL instance with private IP on VPC.

**Completed**:
- [x] Removed `google_bigquery_dataset` and `bigquery.googleapis.com` API from Terraform
- [x] Added `google_sql_database_instance` (`f1-optimizer-dev`, `db-f1-micro`, private IP)
- [x] Added `google_sql_database` (`f1_data`) and `google_sql_user` (`f1_api`)
- [x] Auto-generated 32-char PostgreSQL password stored in Secret Manager
- [x] Added VPC private IP peering (`google_compute_global_address`, `/16` CIDR)
- [x] Updated IAM: `bigquery.dataViewer` → `roles/cloudsql.client` for `api_sa`
- [x] Updated Cloud Run env vars: `BIGQUERY_DATASET` → `DB_HOST`, `DB_NAME`, `DB_PORT`
- [x] Created `dev.tfvars` and `prod.tfvars` (project: f1optimizer, budget: $70)
- [x] Added `hashicorp/random ~> 3.0` and `hashicorp/null ~> 3.0` providers
- [x] `terraform apply -var-file=dev.tfvars` applied successfully

**Key Decisions**:
1. **Cloud SQL over BigQuery**: Lower latency for transactional queries; better fit for operational store; lower cost at this scale
2. **Private IP only**: No public Cloud SQL endpoint; access only from VPC; reduces attack surface
3. **Password auto-generated**: No manual secret management; Terraform-generated and stored in Secret Manager

**Next Steps**: Add Cloud SQL write step to data ingestion DAG

---

## Session 2026-02-18 - Cloud Build, Auto Ingestion, Formatting, Docs

**Date**: 2026-02-18
**Duration**: ~2 hours
**Participants**: Claude Code

**Summary**:
Added Cloud Build CI/CD trigger, auto data ingestion null_resource, formatting cleanup, and full documentation update.

**Completed**:
- [x] Added `cloudbuild.googleapis.com` API to Terraform
- [x] Created `cloudbuild.yaml` (builds `docker/Dockerfile.api`, pushes to Artifact Registry)
- [x] Added `google_cloudbuild_trigger` (GitHub: `bkiritom8/F1-Strategy-Optimizer`, branch: `^pipeline$`)
- [x] Added `data "google_project" "project"` for dynamic Cloud Build SA email
- [x] Added `google_project_iam_member.cloudbuild_ar_writer` (`roles/artifactregistry.writer`)
- [x] Added `null_resource.trigger_data_ingestion` (fires `gcloud run jobs execute f1-data-ingestion` after apply)
- [x] Added `google_cloud_run_service_iam_member.api_sa_run_invoker` (`roles/run.invoker`)
- [x] Pinned numpy to 1.24.4 in `docker/Dockerfile.airflow` (apache-beam==2.53.0 constraint)
- [x] Removed unused `import numpy as np` from `src/ingestion/fastf1_ingestion.py`
- [x] Applied `black` formatting to common/security and ingestion modules
- [x] Removed all emojis from Python, shell, markdown, YAML files
- [x] Updated README: Cloud SQL storage section, ASCII architecture diagram
- [x] Created `mkdocs.yml` for CI documentation build
- [x] Updated all docs/ files: replaced BigQuery references with Cloud SQL, updated budget to $70/month
- [x] Committed and pushed: `bbcb087 Add Cloud Build trigger and auto data ingestion null_resource`

**Key Decisions**:
1. **Cloud Build over manual Docker builds**: Git-triggered CI; image versioning via Artifact Registry; no local Docker required
2. **null_resource trigger strategy**: Uses `db_instance_name` as trigger key — fires once on first `apply`, only re-fires if Cloud SQL is replaced
3. **Async job execution**: `gcloud run jobs execute` is async by default; no `--wait` needed for Terraform apply flow

**Known Gap Remaining**:
- Data ingestion DAG (`f1_data_ingestion.py`) fetches from Ergast/FastF1 but does not write to Cloud SQL — Cloud SQL will remain empty until this is implemented

**Next Steps**:
1. Add Cloud SQL write step to `airflow/dags/f1_data_ingestion.py`
2. Connect GitHub repo to Cloud Build via GitHub App (one-time manual step in GCP Console)
3. Begin data ingestion (Ergast + FastF1 download → Cloud SQL)

---

## Session 2026-02-18 - Jolpica Migration, Vertex AI Infra, Season Range Extension

**Date**: 2026-02-18
**Duration**: ~1.5 hours
**Participants**: Claude Code

**Summary**:
Migrated data ingestion from the deprecated Ergast API to Jolpica, extended season coverage to 2026, added Vertex AI training infrastructure to Terraform, and set Cloud Run Job resource limits.

**Completed**:
- [x] Migrated `src/ingestion/ergast_ingestion.py`: base URL → `https://api.jolpi.ca/ergast/f1`; trailing `/` added to all 10 endpoint URLs (Jolpica requirement); `ingest_races` wrapped in try/except to skip incomplete/future seasons; `--end-season` default → 2026
- [x] Extended `src/ingestion/fastf1_ingestion.py` to 2026: `--end-year` default → 2026; seasons >= 2025 wrapped in explicit try/except logging missing rounds at INFO level (not WARNING)
- [x] Added Vertex AI training infra to `terraform/main.tf`:
  - `google_storage_bucket.training` (`f1optimizer-training`, versioned)
  - `google_service_account.training_sa` (`f1-training-dev`)
  - `google_project_iam_member.training_sa_custom_code` (`roles/aiplatform.customCodeServiceAgent`)
  - `google_project_iam_member.training_sa_storage_admin` (`roles/storage.objectAdmin`)
  - `google_project_iam_member.api_sa_aiplatform_user` (`roles/aiplatform.user` on `api_sa`)
  - `service_accounts` output updated to include `training` key
- [x] Added resource limits to `google_cloud_run_v2_job.f1_data_ingestion`: `memory = "4Gi"`, `cpu = "2"`
- [x] Updated CLAUDE.md: Jolpica references, 1950-2026 data range, Vertex AI infra details, component status, known gaps, next steps
- [x] Committed `3377641` and pushed to `origin/main`

**Key Decisions**:
1. **Jolpica over Ergast**: Ergast API is deprecated; Jolpica is the maintained community mirror with identical response schema but requires trailing slashes on all endpoints
2. **Vertex AI infra only, no job resource**: Training jobs will be submitted programmatically by teammates; Terraform provisions the SA, bucket, and IAM only — no `google_vertex_ai_custom_job` resource to avoid hardcoding model config
3. **Season >= 2025 logged at INFO**: Missing rounds in 2025/2026 are expected (race hasn't happened), not errors — INFO avoids false alarm noise in Cloud Logging

**Known Gap Remaining**:
- Data ingestion DAG (`f1_data_ingestion.py`) still does not write to Cloud SQL — remains the top priority

**Next Steps**:
1. Add Cloud SQL write step to `airflow/dags/f1_data_ingestion.py`
2. Write training container code and Vertex AI job submission scripts using `f1-training-dev` SA
3. Begin driver profile extraction and feature engineering

---

## Session 2026-02-18 - ML Handoff: Repo Restructure + Distributed Pipeline

**Date**: 2026-02-18
**Duration**: ~3 hours
**Participants**: Claude Code

**Summary**:
Full ML team handoff — repo restructured into clean domain separation, distributed Vertex AI training pipeline built end-to-end, ML models implemented, Docker image created, tests written for Vertex AI execution.

**Completed**:
- [x] Repo restructured: `scripts/` → `pipeline/scripts/`, `terraform/` → `infra/terraform/`, new `ml/`, `api/`, `monitoring/` directories
- [x] Updated Dockerfiles (`COPY pipeline/scripts/`), CI (`cd infra/terraform`), cloudbuild.yaml (added `build-ml` step + `ml:latest` image)
- [x] `infra/terraform/vertex_workbench.tf`: `f1-ml-workbench` (n1-standard-8, T4, 60-min auto-shutdown)
- [x] `infra/terraform/vertex_ml.tf`: notebooks/workbench APIs, Pipelines IAM, `f1-pipeline-trigger` Cloud Run Job, `f1optimizer-pipeline-runs` GCS bucket
- [x] `pipeline/scripts/workbench_startup.sh`: installs deps, pulls secrets, sets env vars, ADC
- [x] `ml/distributed/`: `cluster_config.py` (4 configs), `distribution_strategy.py` (Data/Model/HP parallel), `data_sharding.py` (Cloud SQL → GCS shards), `aggregator.py` (best checkpoint → GCS + Pub/Sub)
- [x] `ml/dag/f1_pipeline.py`: full 5-step KFP pipeline (validate → features → [train×2 parallel] → [eval×2 parallel] → deploy)
- [x] `ml/dag/components/`: 6 `@dsl.component` files — each with Cloud Logging, GCS artifacts, Pub/Sub status, `retries=2`
- [x] `ml/dag/pipeline_runner.py`: compile → GCS upload → Vertex AI submit → monitor
- [x] `ml/models/base_model.py`: abstract base with GCS save/load, Vertex AI Experiments, Pub/Sub
- [x] `ml/models/strategy_predictor.py`: XGBoost + LightGBM ensemble, Vertex AI entry point
- [x] `ml/models/pit_stop_optimizer.py`: LSTM, MirroredStrategy, Vertex AI entry point
- [x] `ml/features/feature_store.py`: Cloud SQL → DataFrame (ADC only)
- [x] `ml/features/feature_pipeline.py`: 7 derived feature sets
- [x] `docker/Dockerfile.ml`: nvidia/cuda:11.8 + Python 3.10, NVIDIA env vars, no CMD
- [x] `docker/requirements-ml.txt`: PyTorch/CUDA, TF, XGBoost, LightGBM, KFP SDK, GCP libs
- [x] `ml/tests/`: 4 test files + `run_tests_on_vertex.py` (Vertex AI Custom Job, n1-standard-4)
- [x] `ml/HANDOFF.md`: complete handoff document for ML team

**Key Decisions**:
1. **No local testing**: all tests run on Vertex AI Custom Jobs only
2. **No terraform apply**: only file changes — team applies when ready
3. **No git clone in Workbench startup**: ML team handles their own repo access
4. **KFP v2 as DAG**: existing Airflow DAG kept in place; Vertex AI Pipelines is the new orchestration layer

**Next Steps for ML Team**:
1. Access `f1-ml-workbench`, run `python ml/tests/run_tests_on_vertex.py`
2. Trigger first pipeline run: `python ml/dag/pipeline_runner.py --run-id first-run`
3. Wire `src/api/main.py` to promoted models in `gs://f1optimizer-models/*/latest/`
4. Populate `driver_profiles` table

**Blockers**: None — infrastructure complete

---

## Session Template (Future Entries)

**Date**: YYYY-MM-DD
**Duration**: X hours
**Participants**: Team members

**Summary**:
[Brief overview of session work]

**Completed**:
- [ ] Task 1
- [ ] Task 2

**Key Decisions**:
1. Decision 1 with rationale
2. Decision 2 with rationale

**Code Changes**:
- File: path/to/file.py - Description

**Model Behavior**:
- Model X: Accuracy Y on test set

**Next Steps**:
1. Next action 1
2. Next action 2

**Blockers**: [Any issues]

**Notes**: [Additional context]

---

## Session 2026-02-19 — GPU Training Infra, Dev Setup, Image Builds, Workbench Fix

**Date**: 2026-02-19
**Participants**: Claude Code

**Completed**:
- Built and pushed all 3 Docker images (api:latest, ingestion:latest, ml:latest) via Cloud Build (build `2e867ccb`, SUCCESS)
- Fixed Workbench: hardcoded zone to `us-central1-a`, kept 150 GB SSD boot disk (minimum for Workbench image), switched data disk to PD_STANDARD to avoid SSD_TOTAL_GB quota (limit 250 GB in us-central1)
- Full `terraform apply`: 11 added, 1 changed, 5 destroyed. All Cloud Run jobs + service deployed. API live at `https://f1-strategy-api-dev-lu32hl5eqa-uc.a.run.app`
- Added `VERTEX_T4` profile to `ml/distributed/cluster_config.py` (n1-standard-4 + 1× T4)
- Created `ml/scripts/submit_training_job.sh` — submit Vertex AI Custom Job with T4 GPU; accepts `--display-name` per teammate
- Created `DEV_SETUP.md` — full dev onboarding guide (auth, Cloud SQL proxy, GCS, Docker, Vertex training, Colab Enterprise, env vars)
- Updated `ML_HANDOFF.md` §12 GPU Training section; added VERTEX_T4 to compute profiles table; updated repo structure
- Enabled `notebooks.googleapis.com` for Colab Enterprise
- Triggered ingestion job `f1-data-ingestion-snx26` to repopulate Cloud SQL
- Pushed all commits to `main` (commit `6dc0327`)

**Decisions**:
- Use PD_STANDARD for Workbench data disk (not PD_SSD) to stay within 250 GB SSD quota
- Hardcode Workbench zone to `us-central1-a` instead of dynamic script to avoid zone availability race conditions
- VERTEX_T4 profile is the default for individual ML experiments; SINGLE_NODE_MULTI_GPU for full production runs

**Next Steps**:
- Implement `predict()` in strategy_predictor.py and pit_stop_optimizer.py (raises NotImplementedError, API uses rule-based fallback)
- Add `ray[default]==2.9.1` to `docker/requirements-ml.txt` or replace Ray usage with TF MirroredStrategy
- Verify ingestion job completes successfully (`f1-data-ingestion-snx26`)
- Run first ML training pipeline: `bash ml/scripts/run_training.sh`

**End of Progress Log**

---

---

## Session 2026-02-20 — GCS Migration, Data Upload, Doc Overhaul

**Date**: 2026-02-20
**Participants**: Claude Code

**Summary**:
Removed Cloud SQL and Workbench from the project entirely, uploaded all F1 data to GCS, converted CSVs to Parquet, and overhauled all documentation to reflect the current GCS-only architecture.

**Completed**:
- [x] Removed `src/database/`, `airflow/`, `pipeline/scripts/init_db.py`, `run_local.sh`, `workbench_startup.sh`, `scripts/find_workbench_zone.sh`
- [x] Removed `infra/terraform/vertex_workbench.tf`, `workbench_zone.tf` (previous session)
- [x] Cleaned `cloudbuild.yaml`: removed Workbench deployment steps
- [x] Rewrote `pipeline/scripts/csv_to_parquet.py`: combines yearly CSVs, handles telemetry/ subdir
- [x] Created `pipeline/scripts/verify_upload.py`: reports file counts + sizes
- [x] Uploaded 51 raw CSV files (6.0 GB) to `gs://f1optimizer-data-lake/raw/`
- [x] Converted to 10 Parquet files (1.0 GB) in `gs://f1optimizer-data-lake/processed/`
- [x] Added `raw/` to `.gitignore` (6.5 GB must not go to git)
- [x] Updated `DEV_SETUP.md` with GCS paths and row counts
- [x] Updated `ml/HANDOFF.md` with GCS paths and row counts
- [x] Updated all 14 documentation files to remove Cloud SQL / Workbench / Airflow references:
  README.md, SETUP.md, ML_HANDOFF.md, CLAUDE.md, api/README.md, monitoring/README.md,
  pipeline/README.md, ml/README.md, docs/architecture.md, docs/data.md, docs/roadmap.md,
  docs/training-pipeline.md, docs/progress.md

**Key Decisions**:
1. **GCS replaces Cloud SQL**: All data stored as Parquet in GCS — simpler, cheaper, no VPC proxy needed
2. **No Workbench**: GPU training via Vertex AI Custom Jobs (`ml/scripts/submit_training_job.sh`)
3. **Data never in git**: `raw/` directory in `.gitignore`; GCS is the single source of truth

**Data Summary**:
- laps_all: 93,372 rows | telemetry_all: 30,477,110 rows | race_results: 7,600 rows
- circuits: 78 | drivers: 100 | pit_stops: 11,077 | lap_times: 56,720

**Next Steps**:
1. Run ML tests: `python ml/tests/run_tests_on_vertex.py`
2. Trigger first training pipeline: `python ml/dag/pipeline_runner.py --run-id first-run`
3. Implement `predict()` in both models (currently raises `NotImplementedError`)
4. Check Vertex AI Experiments after pipeline completes

**Blockers**: None

---

**Instructions for Future Sessions**:
1. After running `/compact`, append a new session entry above this line
2. Include date, summary, completed tasks, decisions, next steps
3. Keep entries focused on high-signal information (code, architecture, model behavior)
4. Avoid repeating information already in CLAUDE.md or docs/ files
5. Reference files instead of restating content
