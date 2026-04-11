# Antigravity IDE: Push + Deploy F1 Strategy Optimizer Backend

## Context
- Repo: `/Users/skymaster/Library/CloudStorage/OneDrive-NortheasternUniversity/Projects/F1-Strategy-Optimizer`
- Remote: `https://github.com/bkiritom8/F1-Strategy-Optimizer.git`
- Branch: `pipeline`
- GCP project: `f1optimizer`
- Cloud Run service: `f1-strategy-api-dev`
- Region: `us-central1`
- Dockerfile: `docker/Dockerfile.api`
- Artifact Registry: `us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/api`

## Task: Push pending commit and redeploy Cloud Run

There is already a committed (but unpushed) change on branch `pipeline`. The git push keeps timing out because this repo lives on a OneDrive-synced path. The Cloud Run service also needs redeployment with the latest code.

### Step 1: Push the pending commit

Run the following. If `git push` times out, increase the HTTP buffer and retry:

```bash
cd /Users/skymaster/Library/CloudStorage/OneDrive-NortheasternUniversity/Projects/F1-Strategy-Optimizer
git config http.postBuffer 524288000
git push origin pipeline
```

If that still times out, copy to a temp dir and push from there:

```bash
cp -R /Users/skymaster/Library/CloudStorage/OneDrive-NortheasternUniversity/Projects/F1-Strategy-Optimizer /tmp/f1-deploy
cd /tmp/f1-deploy
git push origin pipeline
```

Verify the push succeeded by checking `git log --oneline -1` matches the remote.

### Step 2: Build the Docker image via Cloud Build

Do NOT use `gcloud run deploy --source .` (it times out uploading from this machine). Instead, use Cloud Build with the existing Dockerfile:

```bash
gcloud builds submit \
  --project f1optimizer \
  --region us-central1 \
  --timeout=1800 \
  --dockerfile=docker/Dockerfile.api \
  --tag us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/api:latest
```

Wait for "SUCCESS" in the output. If it fails with auth issues, run `gcloud auth login` first.

### Step 3: Deploy the built image to Cloud Run

```bash
gcloud run deploy f1-strategy-api-dev \
  --image us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/api:latest \
  --region us-central1 \
  --project f1optimizer \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 3 \
  --port 8000 \
  --set-env-vars "ENV=production,ENABLE_HTTPS=true,ENABLE_IAM=true,ALLOWED_ORIGINS=http://localhost:3000,https://f1optimizer.web.app"
```

### Step 4: Verify deployment

```bash
# Health check
curl -s https://f1-strategy-api-dev-694267183904.us-central1.run.app/health | python3 -m json.tool

# Check CORS headers
curl -s -I -X OPTIONS \
  -H "Origin: https://f1optimizer.web.app" \
  -H "Access-Control-Request-Method: GET" \
  https://f1-strategy-api-dev-694267183904.us-central1.run.app/health
```

The health check should return `{"status": "healthy", ...}`. The OPTIONS request should include `Access-Control-Allow-Origin: https://f1optimizer.web.app`.

### What this deployment fixes
- CORS block: `f1optimizer.web.app` is now in the allowed origins
- All `/users/*` routes (login, register, OTP, verify-email, me)
- All `/api/v1/*` routes (race state, drivers, strategy simulate)
- `/llm/chat` endpoint for the AI Strategist
- Upgraded email templates (OTP + verification) with Apex Intelligence dark branding
- Pydantic v2 migration in schema_validator.py

### Troubleshooting
- If `gcloud builds submit` fails with "Dockerfile required": make sure you're in the repo root directory
- If Cloud Run deploy says "image not found": the Cloud Build step didn't finish; rerun Step 2
- If you get 403 on the deployed URL: the `--allow-unauthenticated` flag may not have applied; run: `gcloud run services add-iam-policy-binding f1-strategy-api-dev --region=us-central1 --member="allUsers" --role="roles/run.invoker" --project=f1optimizer`
