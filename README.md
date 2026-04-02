# F1 Strategy Optimizer

Production-grade real-time F1 race strategy system: pit strategy, tyre compound selection,
driving mode, and overtake decisions. Driver-aware recommendations using 76 years of F1 data (1950–2026). Target: <500ms P99 latency.

## Project Architecture Index

This root directory serves as the nexus for our specialized modules. For detailed architecture specifics, refer to the individual module directories:

- [**`/frontend`**](./frontend/README.md) - Apex Intelligence UI (React + Vite, Tailwind, Vercel)
- [**`/ingest`**](./ingest/README.md) - Cloud Run ingest workers for Jolpica & FastF1 data
- [**`/ml`**](./ml/README.md) - ML codebase encompassing preprocessing, RL training, predictions, and distributed configurations
- [**`/pipeline`**](./pipeline/README.md) - Data pipelines, transformation utilities, simulators, and bucket validators
- [**`/rag`**](./rag/README.md) - Q&A pipelines over F1 historical logic with Gemini & Vertex AI Vector Search
- [**`/docs`**](./docs/README.md) - Dedicated technical documentation, setup steps, and integrations
- **`/Data-Pipeline`** - Legacy / Protected pipeline artifacts (DO NOT DELETE)
- **`/infra`** - Terraform Infrastructure-as-code
- **`/src`** - Shared backend Python libraries (FastAPI setup, LLM connectors, Security checks)
- **`/tests`** - Integration and Unit test suites
- **`/docker`** - Containerization scripts for ingestion, ML, backend and RAG operations.

## Features

- **Data**: Jolpica API (1950–2026) + FastF1 telemetry (2018–2026, 10Hz)
- **Storage**: GCS — 51 raw files (6.0 GB CSV) + processed Parquet files (1.0 GB)
- **LLM**: Standalone strategy chat endpoint — API POST (`/llm/chat`)
- **Serving**: FastAPI on Cloud Run (<500ms P99 latency)
- **Auth**: User registration/login with PBKDF2-HMAC-SHA256, JWT bearer tokens, GDPR compliance (Firestore-backed)
- **CI/CD**: GitHub Actions (lint, test, dockers, terraform) + Cloud Build (`pipeline` branch). Frontend through Vercel.

## Quick Start

### Prerequisites
- `gcloud` CLI (latest)
- Python 3.10
- Terraform 1.5+
- Node.js 18+ (for frontend)
- Docker Desktop (for local development)

### Setup

```bash
git clone https://github.com/bkiritom8/F1-Strategy-Optimizer.git
cd F1-Strategy-Optimizer

# Authenticate with GCP
gcloud auth login
gcloud auth application-default login
gcloud config set project f1optimizer
```

For Backend Initialization, please see [`docs/DEV_SETUP.md`](./docs/DEV_SETUP.md).

For Frontend Initialization:
```bash
cd frontend
npm install
npm run dev
```

---
**Status**: ML pipeline complete. User auth live. Semantic caching live. CI/CD verified. UI Modernization ongoing.
**Branch Targets**: `main` (stable) | `pipeline` (backend CI) | `frontend` (UI deployments) 