# GCP Admin Handover Guide: DivergeX

This document provides the necessary steps to deploy and manage DivergeX in a production environment.

## 1. Production Secrets (GitHub Actions / Cloud Run)

To ensure the platform runs securely and "flawlessly," the following secrets must be configured in your **GitHub Actions Secrets** (and injected into the Cloud Run environment).

### Required New Secrets
| Name | Description | Value |
| :--- | :--- | :--- |
| `JWT_SECRET_KEY` | Used to sign sensitive auth tokens | Random 32+ character string |
| `SEED_SECRET` | Required for one-time admin seeding | Secure random string |
| `ENV` | Environment identifier | `production` |
| `ALLOWED_ORIGINS` | CORS protection | `https://f1optimizer.web.app` |

### Existing Secrets (Verified)
- `FIREBASE_SERVICE_ACCOUNT`: Used for Firebase Hosting deployment.
- `GCP_SA_KEY`: Used for GCP service interaction (Models/Storage).
- `VITE_API_URL`: Points to the Cloud Run backend.
- `VITE_CLOUD_RUN_URL`: The direct URL of the Cloud Run instance.

## 2. Infrastructure Deployment

1.  **Cloud Run Backend**: Ensure the service is configured to pull secrets from **GCP Secret Manager**.
2.  **Firebase Hosting**: Frontend is hosted at `https://f1optimizer.web.app`. Deploy using `firebase deploy`.

## 3. Post-Deployment: Admin Seeding

After the initial backend deployment, you must initialize the production administrator account. This can only be done **once**.

**Command**:
```bash
curl -X POST https://<YOUR_CLOUDRUN_URL>/api/v1/admin/seed \
     -H "Content-Type: application/json" \
     -d '{"secret": "<YOUR_SEED_SECRET>"}'
```

**Output**: Returns the `admin` credentials. **Save these immediately.** 
- **Default Email**: `ajithsri3103@gmail.com`
- **Default Username**: `admin`

## 4. Monitoring & Logs

- **Error Monitoring**: Check GCP Logging with filter `severity >= ERROR`.
- **Backend Admin Panel**: Log in as `admin` at `/admin` to see live CPU/Memory metrics and Gemini API quotas.

## 5. Maintenance Notes

- **Backend Dependencies**: `requirements-f1.txt` has been standardized to `requirements.txt` for automatic detection by GCP Cloud Build and Cloud Run.
- **Source of Truth**: The `pipeline` branch is the production source. All deployments should be triggered from this branch.

---
*Maintained by Antigravity AI*
