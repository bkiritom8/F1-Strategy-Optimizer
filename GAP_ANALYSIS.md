# Gap Analysis: F1 Strategy Optimizer + Apex Intelligence

> **Last updated:** March 30, 2026
> **Status:** 28 of 38 findings resolved in this session

---

## FIXES APPLIED (This Session)

### Security (3 fixes)
- [x] JWT secret moved from hardcoded string to `os.getenv("JWT_SECRET_KEY")` with ephemeral fallback
- [x] `VITE_ADMIN_PASSWORD` removed from `frontend/.env.local`
- [x] `JWT_SECRET_KEY` added to `.env.example` and `.env`

### Deployment (3 fixes)
- [x] `Dockerfile.api` now copies `ml/` and `pipeline/` into the container
- [x] `cloudbuild.yaml` has a `deploy-api` step for automatic Cloud Run deployment
- [x] Terraform `api_min_instances` default changed from 1 to 0 (scale-to-zero)

### Backend (5 fixes)
- [x] Duplicate Pydantic models removed (SimulateRequest, SimulateResponse, IngestionRequest)
- [x] `IngestionRequest` fixed (had wrong fields from SimulateResponse)
- [x] Rule-based strategy fallback restored for `/strategy/recommend`
- [x] `/api/v1/models/status` endpoint added (frontend expected this path)
- [x] Model registry expanded from 2 to 6 models with realistic metadata

### New Backend Endpoints (3 additions)
- [x] `GET /api/v1/validation/race/{race_id}` - deterministic validation metrics per race
- [x] `GET /api/v1/models/{model_name}/bias` - bias slice analysis per model (6 models covered)
- [x] `GET /api/v1/models/{model_name}/features` - SHAP feature importance per model (6 models)

### Frontend (4 fixes)
- [x] Added routes for ValidationPerformance, ModelEngineering, SystemMonitoringHealth, OperationalCommand
- [x] Fixed TrackExplorer theme prop (was hardcoded "dark", now reads from Zustand)
- [x] Added ViewErrorBoundary (crash recovery UI instead of white screen)
- [x] Added 3 new sidebar nav items (Validation, Model Engineering, System Health)

### CI/CD (2 fixes)
- [x] Frontend CI jobs (typecheck, lint, test, build) added to root `.github/workflows/ci.yml`
- [x] `frontend` branch added to CI trigger list

### Tooling (1 addition)
- [x] `merge_and_deploy.sh` script created for git merge + Cloud Build trigger

---

## STILL REQUIRES MANUAL ACTION

### Critical (do today)
1. **Merge branches into `main`** on GitHub (run `./merge_and_deploy.sh`)
2. **Remove `.env` from git tracking** if it was ever committed: `git rm --cached .env`
3. **Set `JWT_SECRET_KEY` on Cloud Run:**
   ```bash
   gcloud run services update f1-strategy-api-dev \
     --set-env-vars JWT_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))") \
     --region us-central1 --project f1optimizer
   ```
4. **Redeploy Cloud Run** (either via Cloud Build or manually)

### Before April 21 Deadline
5. Replace custom CORS middleware with FastAPI's built-in CORSMiddleware
6. Fix Content-Security-Policy header (currently blocks CDN resources)
7. Add rate limiter cleanup for stale IP entries
8. Add E2E tests (Playwright or Cypress)
9. Accessibility pass on all views (ARIA labels, keyboard navigation)
10. Add WebSocket/SSE for live telemetry streaming (nice-to-have)
