# Pipeline — Ingestion & Orchestration

Scripts that run as Cloud Run Jobs or are baked into the ingestion Docker image.

## Directory layout

```
pipeline/
└── scripts/
    ├── run_ingestion.sh       Schema → Ergast → FastF1 pipeline
    ├── monitor_ingestion.py   Triggers + polls f1-data-ingestion, emails on completion
    ├── init_db.py             Database schema initialisation
    ├── workbench_startup.sh   Vertex AI Workbench startup script
    └── run_local.sh           Local docker-compose stack (dev only)
```

## Running ingestion on GCP

```bash
# Direct job execution
gcloud run jobs execute f1-data-ingestion --region=us-central1 --project=f1optimizer

# With monitoring + email
gcloud run jobs execute f1-ingestion-monitor --region=us-central1 --project=f1optimizer
```

## Docker image

`docker/Dockerfile.ingestion` copies `pipeline/scripts/` into `/app/scripts/` and
runs `run_ingestion.sh` as the job entrypoint.
