<div align="center">

# Apex Intelligence

**F1 Race Strategy Dashboard**

Real-time telemetry · AI-driven strategy recommendations · Driver behavioural analytics

[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.8-3178C6?logo=typescript)](https://typescriptlang.org)
[![Vite](https://img.shields.io/badge/Vite-6-646CFF?logo=vite)](https://vite.dev)
[![Tailwind](https://img.shields.io/badge/Tailwind-3.4-06B6D4?logo=tailwindcss)](https://tailwindcss.com)
[![Vitest](https://img.shields.io/badge/Vitest-3-6E9F18?logo=vitest)](https://vitest.dev)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![GCP](https://img.shields.io/badge/Cloud-GCP-4285F4?logo=googlecloud)](https://cloud.google.com)

</div>

---

## What This Repository Is

**Apex Intelligence** is the React/TypeScript front-end for an F1 Race Strategy MLOps platform. It connects to a FastAPI backend (deployed on Google Cloud Run) that was trained on 74 years of Formula 1 race data (1950–2024).

The dashboard provides:
- **Live race telemetry** — driver positions, gap analysis, tyre compounds, fuel loads.
- **AI strategy engine** — Monte Carlo pit-stop simulations, sector consistency scoring.
- **Driver behaviour profiling** — aggression, consistency, wet-weather skill radar charts.
- **NVIDIA NIM AI Chatbot** — natural-language F1 strategy assistant (`/ai` route).
- **Circuit Directory** — animated SVG track maps for all 26 active circuits.
- **MLOps admin panel** — model accuracy metrics, pipeline health, anomaly/bias reports (password-protected at `/admin`).

If the Cloud Run backend is unreachable, every hook falls back to static pipeline data (`public/data/*.json`) and finally to hardcoded mock constants, so the UI is always functional.

---

## Routes

| Route | View | Description | Backend |
|---|---|---|---|
| `/` | Race Command Center | Position tower, telemetry, strategy alerts | `GET /api/v1/race/state`, `GET /api/v1/drivers` |
| `/drivers` | Driver Profiles | 860+ drivers, scatter + radar charts | `GET /api/v1/drivers` |
| `/strategy` | Strategy Simulator | Monte Carlo pit-stop simulations | `POST /api/v1/strategy/simulate` |
| `/ai` | AI Strategist | NVIDIA NIM language model chatbot | NVIDIA NIM API |
| `/circuits` | Circuit Directory | CSS motion-path animated SVG track maps | Static |
| `/analysis` | Post-Race | Lap-by-lap sector breakdowns | `GET /api/v1/telemetry/{driver}/lap/{lap}` |
| `/admin` | Admin (🔒) | MLOps models + system health | `GET /api/v1/health/system` |

> **Admin password:** `f1race@mlops`

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | React 19 + TypeScript 5.8 |
| Build | Vite 6 |
| Styling | Tailwind CSS 3.4 (PostCSS, class-based dark mode) |
| Routing | React Router DOM 7 |
| State | Zustand 5 (global) + React hooks (local) |
| Charts | Recharts 2.15 |
| Animations | Framer Motion 12 + CSS `offset-path` |
| Icons | Lucide React |
| Testing | Vitest 3 + Testing Library |
| Linting | ESLint 9 (flat config) + Prettier |
| CI/CD | GitHub Actions |
| Backend | FastAPI on GCP Cloud Run |
| Auth | JWT (OAuth2 password grant via IAM simulator) |
| AI | NVIDIA NIM API (configured via `VITE_NVIDIA_API_KEY`) |

---

## Project Structure

```
├── .github/workflows/
│   └── ci.yml                # Lint → typecheck → test → build pipeline
├── __tests__/
│   ├── setup.ts              # Vitest global setup
│   ├── api-client.test.ts    # API auth + endpoint tests
│   └── store.test.ts         # Zustand store tests
├── services/
│   ├── client.ts             # JWT auth (auto-login, token cache, 401 retry)
│   ├── endpoints.ts          # Typed API wrappers + 3-tier fallback
│   ├── logger.ts             # Structured logger (dev-only debug/info, always warn/error)
│   └── index.ts              # Barrel exports
├── hooks/
│   └── useApi.ts             # React hooks: loading / error / fallback / isLive
├── store/
│   └── useAppStore.ts        # Zustand: selectedDriver, race, theme, sidebar
├── components/
│   ├── ConnectionBadge.tsx   # Live/Mock data indicator badge
│   ├── DriverCard.tsx        # Single driver telemetry card
│   ├── PositionTower.tsx     # Animated race standings column
│   ├── DynamicSimulationBackground.tsx  # F1 racing circuit ambient background
│   ├── ConceptTooltip.tsx    # F1 glossary hover tooltips
│   └── tracks/               # SVG circuit map components (26 tracks)
├── views/
│   ├── RaceCommandCenter.tsx
│   ├── DriverProfiles.tsx
│   ├── PitStrategySimulator.tsx
│   ├── AIChatbot.tsx
│   ├── TrackExplorer.tsx
│   ├── LapByLapAnalysis.tsx
│   ├── AdminPage.tsx         # Password-protected MLOps admin panel
│   ├── ValidationPerformance.tsx
│   └── SystemMonitoringHealth.tsx
├── App.tsx                   # Root layout: sidebar, routing, theme toggle
├── index.tsx                 # Entry point: BrowserRouter + React.StrictMode
├── index.css                 # Tailwind directives + CSS variables (light/dark)
├── types.ts                  # TypeScript interfaces
├── constants.ts              # Team colours, mock fallbacks
├── tailwind.config.js        # Tailwind theme + dark mode config
├── vite.config.ts            # Build config, dev proxy, code splitting
├── vitest.config.ts          # Test config
├── vercel.json               # SPA rewrites for client-side routing
└── tsconfig.json             # TypeScript strict mode
```

---

## Getting Started

### Prerequisites

- Node.js 20+
- npm 10+

### Install & Run

```bash
git clone <repo-url>
cd apex-intelligence
npm install
npm run dev           # → http://localhost:3001
```

### Environment Variables

Create `.env.local` at the project root:

```env
# Required for the AI Chatbot (/ai route)
VITE_NVIDIA_API_KEY=nvapi-...

# Optional: point dev server directly at Cloud Run instead of local backend
# VITE_API_URL=https://f1-strategy-api-dev-...run.app
```

### Run with Local Backend

```bash
# Terminal 1: Start the FastAPI backend
cd F1-Strategy-Optimizer
pip install -r requirements-api.txt
python -m src.api.main    # → http://localhost:8000

# Terminal 2: Start the dashboard (proxies /api to :8000)
cd apex-intelligence
npm run dev               # → http://localhost:3001
```

### Scripts

| Command | Description |
|---|---|
| `npm run dev` | Start dev server |
| `npm run build` | TypeScript check + production build |
| `npm run preview` | Preview production build |
| `npm run test` | Run all tests |
| `npm run test:watch` | Tests in watch mode |
| `npm run lint` | ESLint check |
| `npm run lint:fix` | ESLint auto-fix |
| `npm run format` | Prettier format |
| `npm run typecheck` | TypeScript type check |

---

## API Integration

Three-layer fallback architecture — the UI always renders something useful:

```
Views (React)
  └── hooks/useApi.ts          { data, loading, error, isLive, refetch }
       └── services/endpoints.ts   typed wrappers + response transforms
            ├── Tier 1: Cloud Run FastAPI backend (live, authenticated)
            ├── Tier 2: /data/*.json static files (real pipeline data)
            └── Tier 3: constants.ts hardcoded mocks (always available)
```

All HTTP traffic is logged by `services/logger.ts` in the browser DevTools console during development (suppressed in production builds).

---

## Deployment

- **Frontend:** Vercel — pushes to `main` trigger the CI pipeline, then Vercel auto-deploys.
- **Backend:** Google Cloud Run — containerised FastAPI application.
- `vercel.json` includes SPA rewrites so routes like `/drivers` work on hard refresh.
- In production, API calls resolve directly to the Cloud Run URL defined in `services/client.ts`.

---

## License

Academic coursework project — MLOps curriculum, Northeastern University.
