#!/bin/bash
# Run this script to push the frontend to the F1-Strategy-Optimizer repo on a new 'frontend' branch.
# Usage: bash push_frontend.sh

set -e

REPO="/Users/skymaster/Library/CloudStorage/OneDrive-NortheasternUniversity/Projects/F1-Strategy-Optimizer"
FRONTEND_SRC="/Users/skymaster/Library/CloudStorage/OneDrive-NortheasternUniversity/Projects/Apex-Intelligence"

echo "==> Navigating to repo..."
cd "$REPO"

echo "==> Creating and switching to 'frontend' branch..."
git checkout -b frontend

echo "==> Copying Apex-Intelligence into frontend/..."
mkdir -p frontend
rsync -av --exclude='node_modules' --exclude='.DS_Store' --exclude='dist' "$FRONTEND_SRC/" frontend/

echo "==> Staging files..."
git add frontend/

echo "==> Committing..."
git commit -m "feat: add Apex Intelligence frontend with live FastAPI integration

- API client layer (api/client.ts) with JWT auto-auth against IAM simulator
- Typed endpoint wrappers (api/endpoints.ts) for all 10 backend routes
- React hooks (hooks/useApi.ts) with graceful mock fallback
- Vite proxy config routing /api/v1, /token, /health to localhost:8000
- DriverProfiles view linked to GET /api/v1/drivers (860+ drivers from GCS Parquet)
- SystemMonitoringHealth linked to GET /api/v1/health/system + /models/status
- RaceCommandCenter linked to GET /api/v1/race/state
- Live connection badge in sidebar (green=connected, yellow=mock mode)
- All pipeline/API code untouched"

echo "==> Pushing to origin/frontend..."
git push origin frontend

echo "==> Done! Frontend pushed to origin/frontend"
