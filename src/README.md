# Shared Backend Logic

FastAPI and backend core modules for the F1 Strategy Optimizer.

## Contents

- **`api/`**: Main entrypoint for Cloud Run. Defines the FastAPI app and public/internal endpoints.
- **`ingestion/`**: Jolpica and FastF1 API connectors and ingestion managers.
- **`llm/`**: Connectors for Gemini Pro (Vertex AI). Includes prompt templates and structured output parsers for strategy recommendations.
- **`preprocessing/`**: shared Python classes for data cleaning and feature engineering in both real-time and training pipelines.
- **`common/`**: Logging, configuration, and environment variable loaders.
- **`security/`**: JWT authentication, Firestore-backed session management, and data sanitization.

## Usage

Running locally:
```bash
uvicorn src.api.main:app --reload
```

## Maintenance

Keep dependencies updated in `requirements-api.txt` and ensure new endpoints are added to the `endpoints.ts` registry in the frontend.
