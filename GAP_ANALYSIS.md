# Gap Analysis: Apex Intelligence vs. Original Infrastructure

This document provides a comprehensive audit of the differences between the **Apex Intelligence** dashboard and the original **F1-Strategy-Optimizer** infrastructure. It also highlights critical faults found in the original codebase.

## 1. Feature & API Gaps
The original repository is a "Heavy MLOps" backend, while the frontend is a "Premium Strategy Visualizer."

### Missing Models & Logic
The original `ml/models/` directory contains logic that is not yet visible in the UI:
- **Safety Car Forecast**: Predicts VSC/SC phases during a race.
- **Overtake Probability**: Corner-by-corner risk assessment.
- **Race Outcome Engine**: Predicts final standings based on simulated pit windows.
- **SHAP Explainability**: The repo generates `shap_bar.png` plots for model transparency. These are not yet rendered in the **Model Engineering** tab.

### Advanced Simulation
- **Original API**: `/v1/simulate/full` ranks strategies by **Win Probability** and **Risk Level**.
- **Apex Dashboard**: Currently focuses on manual "Sandbox" simulation. It lacks a "Best Strategy Ranking" engine that automatically proposes the top 3 tactical variants.

---

## 2. Identified Faults (Original Repo)
During the audit of the `ml-models` and `pipeline` branches, the following critical issues were found:

### 🔴 Code & Dependency Issues
1. **Broken Models**: The `predict()` methods in both the tire degradation and fuel consumption models raise `NotImplementedError`. This means the API is **stuck in "Rule-Based Fallback" mode** permanently until fixed.
2. **Missing DRS Features (DATA FAULT)**: The `FeaturePipeline` (in `ml/features/feature_pipeline.py`) currently drops the `DRS` column from telemetry during feature engineering.
   - **Impact**: The models cannot distinguish between raw speed and DRS-assisted speed, leading to biased race predictions for circuits like Albert Park (which has 4 zones).
3. **Missing Dependency**: `ml/training/distributed_trainer.py` imports `ray`, but `ray` is **not included** in `requirements-ml.txt`. Production builds will fail during training.
4. **Ingestion Bottleneck**: The Jolpica/Ergast worker is rate-limited to 450 requests/hour. A full historical backfill of all 1,300+ races would take over a week to complete on a single instance.

### 🟡 Documentation Inconsistencies
1. **2026 Regulation Gap**: No logic exists for "Active Aero" or "Manual Override Mode" (MOM) in the ingestion layer.
2. **Stale Secrets**: The README references `GITHUB_TOKEN` for CI gating but omits the `VERCEL_TOKEN` process required for frontend deployment.

### 🔴 Backend API Faults (`src/api/main.py`)
1. **The "Silent Fallback" Problem**:
   - The `/strategy/recommend` endpoint silently falls back to a hardcoded rule (`lap > 30 = PIT`) if the ML model fails to load. Users are misled into thinking they are seeing AI predictions when they are seeing a basic script.
2. **Hardcoded Grid**:
   - The `/data/drivers` endpoint is **hardcoded** to only return Max Verstappen and Lewis Hamilton. It completely ignores the actual race entry list from the database.
3. **Blocking Synchronous Loading**:
   - Endpoints like `/race/state` load FastF1 telemetry **on-demand**. This causes 20-30 second spikes in latency on the first request, leading to frontend timeouts.
4. **Placeholder Model Registry**:
   - The `/models/status` endpoint returns **fake accuracy metrics** (0.92 / 0.89) instead of querying a real model metadata store.
5. **CORS Security Risk**:
   - Middleware is configured with `allow_origins=["*"]`, which is unsuitable for a production deployment of Apex Intelligence.

---

## 3. Operational Gaps & Admin Expansion
The `infra/terraform` files provide resources that are completely hidden from the current dashboard. We can expose these in the **Admin Center**:

### New Proposed Admin Tabs:
1. **Cost Center**: Expose the `budget_amount` ($200) and track real-time GCP spending against the target (found in `variables.tf`).
2. **Database Terminal**: Monitor the **Cloud SQL** (`db-f1-micro`) instance status, storage usage, and latest ingestion timestamps.
3. **Ingestion Control**: A dashboard for starting/stopping **Cloud Run Jobs** (e.g., `fastf1_worker`, `lap_times_worker`) and monitoring their logs.
4. **Security & IAM**: List the permissions for the `f1-ingest-sa` service account and verify IAM policy compliance.

---

## 4. 2026 Transition Strategy: "The Aero Toggle"
For Albert Park and other tracks transitioning to the 2026 regulations, we propose:
- **Historical Data**: Re-integrate `DRS_Status (0-14)` into the feature set to ensure correct lap-time modeling for pre-2026 races.
- **2026+ Simulation**: Add a UI toggle in the **Strategy Simulator** for "Regulation Set" (2025 vs 2026). This would switch the physics engine from DRS logic to Active Aero logic (X-mode/Z-mode).

## 4. Proposed Roadmap for Apex Intelligence
1. **Phase 1 (Explainability)**: Integrate SHAP plots into the Model Registry to show *why* the AI recommends a strategy.
2. **Phase 2 (Strategy Ranking)**: Refactor the simulator to display the "Top 3 Ranked Strategies" from the `/simulate/full` endpoint.
3. **Phase 3 (Operational Health)**: Connect the **System Monitoring** tab to real worker logs and GCS progress markers.
