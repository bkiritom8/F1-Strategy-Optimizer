# Apex Intelligence: Frontend API Requirements for Backend

**Author:** Ajith Srikanth (Frontend / PM)
**For:** Bhargav Pamidighantam (Backend / Infra)
**Date:** March 30, 2026

## Quick Reference

| Method | Path | Status |
|--------|------|--------|
| POST | `/token` | Working |
| GET | `/health` | Working |
| GET | `/api/v1/health/system` | Working |
| GET | `/api/v1/drivers` | Working |
| GET | `/api/v1/drivers/{id}/history` | Working |
| GET | `/api/v1/race/state` | Needs redeploy |
| GET | `/api/v1/race/standings` | Needs redeploy |
| GET | `/api/v1/telemetry/{id}/lap/{n}` | Needs redeploy + DRS fix |
| POST | `/strategy/recommend` | Working (rule-based) |
| POST | `/api/v1/strategy/simulate` | Needs redeploy |
| GET | `/api/v1/race/predict/overtake` | Placeholder (random) |
| GET | `/api/v1/race/predict/safety_car` | Placeholder (random) |
| GET | `/api/v1/models/status` | Hardcoded metadata |
| GET | `/api/v1/models/{name}/bias` | Hardcoded slices |
| GET | `/api/v1/models/{name}/features` | Hardcoded SHAP |
| GET | `/api/v1/validation/race/{id}` | Seeded mock values |
| POST | `/api/v1/jobs/ingestion` | Working |

Full details with request/response schemas in `apex-intelligence/API_REQUIREMENTS.md`
