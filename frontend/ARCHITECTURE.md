# Apex Intelligence Architecture

This document outlines the technical architecture, design principles, and API integration
for the Apex Intelligence platform.

## 1. Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend Core | React 19 (TypeScript) | Component framework |
| Build Tool | Vite 6 | Dev server, proxy, bundler |
| Styling | Tailwind CSS (CDN) + CSS variables | Theming (dark/light) |
| Animations | Framer Motion v11 | View transitions, micro-interactions |
| Icons | Lucide React | UI iconography |
| Charts | Recharts v2.15 | Area, scatter, radar, bar charts |
| AI Integration | NVIDIA NIM API (kimi-k2.5) | AI Strategist chat |
| Backend | FastAPI (Python 3.10) | REST API with JWT auth |
| Cloud | GCP (Cloud Run, GCS, Vertex AI) | Hosting, storage, ML serving |

## 2. Project Structure

```
├── services/                    # Backend communication layer
│   ├── client.ts                #   JWT auth, token lifecycle, apiFetch()
│   ├── endpoints.ts             #   Typed endpoint wrappers + transforms
│   ├── index.ts                 #   Barrel exports
│   └── logger.ts                #   Client-side logging utility
├── hooks/                       # React data hooks
│   └── useApi.ts                #   useDrivers, useRaceState, useBackendStatus, etc.
├── components/                  # Reusable UI components

│   ├── ConnectionBadge.tsx      #   Live API / Mock Data indicator
│   ├── ConceptTooltip.tsx       #   F1 glossary hover definitions
│   ├── DriverCard.tsx           #   Telemetry card for selected driver
│   ├── PositionTower.tsx        #   Race position standings sidebar
│   ├── RacingBackground.tsx     #   Ambient animated background
│   └── tracks/                  #   Circuit SVG maps and detail views
├── views/                       # Full-page view components
│   ├── RaceCommandCenter.tsx    #   Primary race monitoring dashboard
│   ├── DriverProfiles.tsx       #   Driver explorer with scatter/radar charts
│   ├── PitStrategySimulator.tsx #   Monte Carlo strategy simulation
│   ├── AIChatbot.tsx            #   Conversational AI strategist
│   ├── TrackExplorer.tsx        #   Circuit directory and detail browser
│   ├── LapByLapAnalysis.tsx     #   Post-race sector analysis
│   ├── ValidationPerformance.tsx#   Model prediction accuracy dashboard
│   └── SystemMonitoringHealth.tsx#  MLOps health and pipeline monitor
├── App.tsx                      # Root layout, sidebar, theme management
├── index.tsx                    # React DOM entry
├── types.ts                     # TypeScript interfaces and enums
├── constants.ts                 # Theme tokens, team colors, mock fallback data
└── vite.config.ts               # Dev server proxy + build configuration
```

## 3. API Integration Architecture

```
View Component
  │
  ├── useDrivers()  ──────── hooks/useApi.ts
  │                              │
  │                              ├── fetchDrivers()  ── api/endpoints.ts
  │                              │                         │
  │                              │                         ├── apiFetch('/api/v1/drivers')
  │                              │                         │       │
  │                              │                         │       └── api/client.ts
  │                              │                         │           ├── getToken()
  │                              │                         │           ├── POST /token (auto-auth)
  │                              │                         │           └── Bearer <jwt> header
  │                              │                         │
  │                              │                         └── Transform backend → frontend types
  │                              │
  │                              └── Fallback: MOCK_DRIVERS (constants.ts)
  │
  └── Renders with { data, loading, error, isLive }
```

### Request Flow

1. **View** calls a hook (e.g., `useDrivers()`)
2. **Hook** calls an endpoint function (e.g., `fetchDrivers()`)
3. **Endpoint** calls `apiFetch(path)` which auto-injects JWT
4. **Client** checks `sessionStorage` for cached token; if expired, POSTs to `/token`
5. **Response** is transformed from backend schema to frontend `types.ts` interfaces
6. **Hook** returns `{ data, loading, error, isLive }` to the view
7. If any step fails, the hook falls back to mock data from `constants.ts`

### Environment Routing

| Context | API_BASE | Routing |
|---------|----------|---------|
| `npm run dev` | `""` (empty) | Vite proxy to `localhost:8000` |
| `npm run build` | Cloud Run URL | Direct HTTPS to GCP |

## 4. Design System

### Color Palette

| Token | Dark | Light | Usage |
|-------|------|-------|-------|
| `--bg-primary` | `#0F0F0F` | `#FCFBF7` | Page background |
| `--bg-secondary` | `#1A1A1A` | `#F0EFE9` | Card backgrounds |
| `--text-primary` | `#FFFFFF` | `#1A1A1A` | Body text |
| `--border-color` | `rgba(255,255,255,0.05)` | `rgba(0,0,0,0.05)` | Dividers |
| Accent Red | `#E10600` | `#E10600` | Active nav, CTAs |
| Accent Green | `#00D2BE` | `#00D2BE` | Positive values |

### Team Colors (from `constants.ts`)

Used for scatter plot dots, radar chart fills, and driver card accents.
Maps: Red Bull (#3671C6), Mercedes (#27F4D2), Ferrari (#E8002D), McLaren (#FF8000), etc.

### UI Principles

- **Glassmorphism**: `backdrop-blur` with low-opacity backgrounds for overlays
- **Data Density**: Compact telemetry readouts inspired by F1 pit wall displays
- **Graceful Degradation**: Every view renders with mock data; live API enhances, never blocks
- **Connection Awareness**: Sidebar shows green (Connected) or yellow (Mock Mode) in real time

## 5. Data Flow

| Source | Type | Update Pattern |
|--------|------|---------------|
| `GET /api/v1/drivers` | 860+ driver profiles | On mount (cached) |
| `GET /api/v1/race/state` | Race state at a lap | On mount + user interaction |
| `GET /api/v1/health/system` | Pipeline status | On mount |
| `GET /models/status` | Model registry | On mount |
| `GET /health` | Connectivity check | Polled every 10 seconds |
| `POST /strategy/recommend` | Strategy recommendation | On demand |
| `POST /api/v1/strategy/simulate` | Monte Carlo results | On demand |
| `constants.ts` | Mock fallback data | Always available |

## 6. Development Guidelines

- Always use hooks from `hooks/useApi.ts` instead of calling endpoints directly in views
- Check `isLive` to show the `ConnectionBadge` so users know if data is real or mock
- New endpoints: add raw types + fetcher in `endpoints.ts`, add hook in `useApi.ts`
- Keep components focused; extract chart configs and transformations into utilities
- Test with backend both online and offline to verify fallback behavior
