#!/bin/bash
# ───────────────────────────────────────────────────────────────────────────
# merge_and_deploy.sh
# Merges all local changes into main, pushes to GitHub, and triggers
# a Cloud Build deployment.
#
# Usage:
#   cd /path/to/F1-Strategy-Optimizer
#   chmod +x merge_and_deploy.sh
#   ./merge_and_deploy.sh
# ───────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_DIR="/Users/skymaster/Library/CloudStorage/OneDrive-NortheasternUniversity/Projects/F1-Strategy-Optimizer"
PROJECT_ID="f1optimizer"
REGION="us-central1"

echo "=== F1 Strategy Optimizer: Merge & Deploy ==="
echo ""

cd "$REPO_DIR"

# ── Step 1: Ensure .env is not tracked ────────────────────────────────────
echo "[1/6] Ensuring .env is not tracked by git..."
git rm --cached .env 2>/dev/null || true
git rm --cached frontend/.env.local 2>/dev/null || true

# ── Step 2: Stage all changes ─────────────────────────────────────────────
echo "[2/6] Staging all changes..."
git add -A

# ── Step 3: Commit ────────────────────────────────────────────────────────
echo "[3/6] Committing..."
git commit -m "fix: security hardening, missing endpoints, deployment pipeline

- JWT secret now loaded from JWT_SECRET_KEY env var (not hardcoded)
- Removed VITE_ADMIN_PASSWORD from frontend .env.local
- Added ml/ and pipeline/ to Dockerfile.api
- Added Cloud Run deploy step to cloudbuild.yaml
- Fixed duplicate Pydantic models in main.py
- Restored rule-based strategy fallback when ML model unavailable
- Added /api/v1/models/status endpoint (fixes frontend 404)
- Added /api/v1/validation/race/{id} endpoint
- Added /api/v1/models/{name}/bias endpoint
- Added /api/v1/models/{name}/features endpoint
- Added missing routes in App.tsx (Validation, Models, Monitoring)
- Added React Error Boundary for view crash recovery
- Fixed TrackExplorer theme prop (was hardcoded 'dark')
- Merged frontend CI into root GitHub Actions workflow
- Fixed Terraform min_instances default to 0 (cost savings)" || echo "Nothing to commit (clean tree)"

# ── Step 4: Push to current branch ────────────────────────────────────────
CURRENT_BRANCH=$(git branch --show-current)
echo "[4/6] Pushing to origin/$CURRENT_BRANCH..."
git push origin "$CURRENT_BRANCH"

# ── Step 5: Merge into main ──────────────────────────────────────────────
echo "[5/6] Merging $CURRENT_BRANCH into main..."
git checkout main 2>/dev/null || git checkout -b main
git merge "$CURRENT_BRANCH" --no-edit || {
    echo "⚠️  Merge conflict detected. Resolve manually, then run:"
    echo "    git add -A && git commit && git push origin main"
    exit 1
}
git push origin main
git checkout "$CURRENT_BRANCH"

echo ""
echo "✅ Code pushed to origin/main successfully!"
echo ""

# ── Step 6: Trigger Cloud Build (optional) ────────────────────────────────
echo "[6/6] Trigger Cloud Build deployment? (y/N)"
read -r DEPLOY_ANSWER
if [[ "$DEPLOY_ANSWER" =~ ^[Yy]$ ]]; then
    echo "Submitting Cloud Build..."
    gcloud builds submit \
        --config=cloudbuild.yaml \
        --project="$PROJECT_ID" \
        --region="$REGION" \
        --async
    echo ""
    echo "✅ Cloud Build triggered! Monitor at:"
    echo "   https://console.cloud.google.com/cloud-build/builds?project=$PROJECT_ID"
else
    echo ""
    echo "Skipped Cloud Build. To deploy manually later:"
    echo "  gcloud builds submit --config=cloudbuild.yaml --project=$PROJECT_ID"
    echo ""
    echo "Or deploy the API image directly:"
    echo "  gcloud run deploy f1-strategy-api-dev \\"
    echo "    --image us-central1-docker.pkg.dev/$PROJECT_ID/f1-optimizer/api:latest \\"
    echo "    --region $REGION --project $PROJECT_ID --allow-unauthenticated"
fi

echo ""
echo "=== Done! ==="
