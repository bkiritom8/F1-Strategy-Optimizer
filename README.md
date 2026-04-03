# F1 Strategy Optimizer

Production-grade real-time F1 race strategy system: pit strategy, tyre compound selection,
driving mode, and overtake decisions. Driver-aware recommendations using 76 years of F1 data (1950–2026). Target: <500ms P99 latency.

## Project Architecture Index

This root directory serves as the nexus for our specialized modules. For detailed architecture specifics, refer to the individual module directories:

- [**`/frontend`**](./frontend/README.md) - Apex Intelligence UI (React + Vite, Tailwind, Vercel)
- [**`/src`**](./src/README.md) - Core backend Python libs (FastAPI, LLM connectors, Security)
- [**`/ml`**](./ml/README.md) - ML codebase (preprocessing, RL training, predictions)
- [**`/pipeline`**](./pipeline/README.md) - Data pipelines, transformation utilities, simulators
- [**`/ingest`**](./ingest/README.md) - Ingest workers for Jolpica & FastF1 data
- [**`/rag`**](./rag/README.md) - Q&A pipelines over F1 history with Gemini & Vertex AI
- [**`/infra`**](./infra/README.md) - Terraform Infrastructure-as-code (GCP)
- [**`/tests`**](./tests/README.md) - Integration and Unit test suites
- [**`/scripts`**](./scripts/README.md) - Operational and maintenance scripts
- [**`/docs`**](./docs/README.md) - Technical documentation and integration guides
- **`/Data-Pipeline`** - Legacy / Protected pipeline artifacts (DO NOT DELETE)

## 2024 UI Modernization

The platform has undergone a major visual overhaul focusing on:
- **Premium Landing Page**: Glassmorphism aesthetic with `Outfit` headers and `Inter` body text.
- **Dynamic Background**: Circuit-accurate SVG track paths with kinetic F1 car animations.
- **Race Command Center**: Real-time telemetry visualization and ML-powered risk analysis.

## Features

- **Data**: Jolpica API (1950–2026) + FastF1 telemetry (2018–2026, 10Hz)
- **Serving**: FastAPI on Cloud Run (<500ms P99 latency)
- **AI**: Standalone strategy chat and parse-strategy endpoints (`/llm/chat`)
- **Status**: UI Modernization complete. ML pipeline complete. User auth live.

## Quick Start

```bash
# Setup GCP context
gcloud auth application-default login
gcloud config set project f1optimizer

# Run Frontend
cd frontend && npm install && npm run dev
```

---
**Status**: Stable Production | **UI Architecture**: Modern Glass-Dark