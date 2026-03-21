# Apex Intelligence: API Integration Guide

## Overview

The Apex Intelligence frontend is now linked to the F1 Strategy Optimizer FastAPI backend.
The integration uses a layered architecture:

```
Views (React components)
  └── hooks/useApi.ts (React hooks with loading/error/fallback)
       └── api/endpoints.ts (typed wrappers, response transformation)
            └── api/client.ts (JWT auth, token caching, auto-retry)
                 └── Vite proxy → http://localhost:8000 (FastAPI)
```

## Quick Start

### 1. Start the FastAPI Backend

```bash
cd /path/to/F1-Strategy-Optimizer
pip install -r requirements-api.txt
cd src && python -m api.main
# Backend runs at http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

### 2. Start the Frontend

```bash
cd /path/to/Apex-Intelligence
npm install
npm run dev
# Frontend runs at http://localhost:3000
```

### 3. Verify Connection

Open http://localhost:3000. Look at the sidebar footer:
- **Green "Connected"**: Backend is running, real data flows
- **Yellow "Mock Mode"**: Backend unreachable, mock data used as fallback

## Endpoint Mapping

| Frontend View | Hook | Backend Endpoint | Fallback |
|---|---|---|---|
| Driver Profiles | `useDrivers()` | `GET /api/v1/drivers` | `MOCK_DRIVERS` (5 drivers) |
| Command Center | `useDrivers()` + `fetchRaceState()` | `GET /api/v1/race/state` | `MOCK_RACE_STATE` |
| MLOps Health | `useSystemHealth()` | `GET /api/v1/health/system` | Static mock |
| MLOps Health | `useModelStatus()` | `GET /models/status` | 2 model entries |
| All Views | `useBackendStatus()` | `GET /health` (polled 10s) | `online: false` |
| Strategy | `fetchStrategyRecommendation()` | `POST /strategy/recommend` | `getMockStrategy()` |
| Simulation | `simulateStrategy()` | `POST /api/v1/strategy/simulate` | N/A |

## Authentication

The backend uses JWT tokens via an IAM simulator. The API client (`api/client.ts`)
auto-authenticates with:
- Username: `admin`
- Password: `admin`

Tokens are cached in `sessionStorage` for 25 minutes and auto-refresh.

Available accounts: `admin/admin`, `data_engineer/password`, `ml_engineer/password`, `viewer/password`.

## Vite Proxy Configuration

All backend routes are proxied in `vite.config.ts`:

| Path | Target |
|---|---|
| `/api/v1/*` | `http://localhost:8000` |
| `/token` | `http://localhost:8000` |
| `/health` | `http://localhost:8000` |
| `/strategy/*` | `http://localhost:8000` |
| `/models/*` | `http://localhost:8000` |
| `/data/*` | `http://localhost:8000` |
| `/api/nvidia/*` | `https://integrate.api.nvidia.com` (AI chat) |

## Graceful Degradation

Every hook follows the pattern:

```typescript
const { data, loading, error, isLive } = useDrivers();
// data: always has a value (real or mock)
// loading: true during fetch
// error: error message if API failed
// isLive: true if data came from real API
```

Views render immediately with mock data, then swap to real data when available.
The `ConnectionBadge` component shows "Live API" or "Mock Data" per section.

## File Structure

```
api/
  client.ts      # JWT auth, token lifecycle, apiFetch wrapper
  endpoints.ts   # Typed endpoint functions, response transformation
  index.ts       # Barrel exports
hooks/
  useApi.ts      # React hooks: useDrivers, useSystemHealth, etc.
components/
  ConnectionBadge.tsx  # Live/Mock status indicator
```

## Adding New Endpoints

1. Add the raw response interface in `api/endpoints.ts`
2. Add the fetcher function that calls `apiFetch()` and transforms the response
3. Add a hook in `hooks/useApi.ts` that wraps the fetcher with `useApiCall()`
4. Use the hook in your view: `const { data, isLive } = useMyNewEndpoint()`
