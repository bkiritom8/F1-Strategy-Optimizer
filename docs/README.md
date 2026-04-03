# Documentation

Technical architecture, setup guides, ML handoffs, and operational references for the F1 Strategy Optimizer.

## Index

| File | Contents |
|---|---|
| `DEV_SETUP.md` | Local development onboarding — GCP auth, environment setup, first run |
| `SETUP.md` | Initial infrastructure setup guide |
| `architecture.md` | System architecture overview — data flow, component interactions |
| `training-pipeline.md` | ML training pipeline walkthrough — KFP DAG, Vertex AI jobs, artifact promotion |
| `models.md` | Model specifications — features, hyperparameters, evaluation metrics |
| `ml_handoff.md` | Full ML handoff document — training reproducibility, deployment checklist |
| `data.md` | Data sources, schemas, and GCS bucket layout |
| `rag.md` | RAG deployment details — vector index setup, re-indexing instructions |
| `bias.md` | Bias analysis methodology and mitigation strategies |
| `metrics.md` | Performance metrics and monitoring targets |
| `monitoring.md` | System monitoring setup (planned — not yet configured) |
| `progress.md` | Session-by-session progress log |
| `roadmap.md` | Future roadmap and known gaps |
| `team_overview.md` | Team structure and module ownership |

## Quick Links

- **New to the project**: Start with `DEV_SETUP.md`
- **ML pipeline**: `training-pipeline.md` → `models.md` → `ml_handoff.md`
- **Infrastructure**: `SETUP.md` → `../infra/README.md`
- **RAG system**: `rag.md` → `../rag/README.md`

*(For the project-wide architecture index, see the root `README.md`.)*
