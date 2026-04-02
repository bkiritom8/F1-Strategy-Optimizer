# Apex Intelligence | F1 Strategy Frontend

Modernized, high-performance Vite + React frontend for the F1 Strategy Optimizer. Visualizes real-time telemetry, historical trends, and ML-powered strategy recommendations.

## 2024 UI Modernization (Glass-Dark)

The 2.0 release introduces a premium **Pro-Racing** aesthetic:
- **Design System**: Glassmorphism core (`--glass-bg`, `--glass-border`, `--glass-blur`) with high-contrast racing accents.
- **Typography**: Google Fonts integration:
  - **Outfit**: Bold, kinetic headings for racing urgency.
  - **Inter**: Clean, functional body text for telemetric data readability.
- **Animations**: Accelerated, circuit-accurate SVG background simulations with smooth entrance transitions.

## Key Components

- **`LandingPage.tsx`**: High-impact entry point with glassmorphic stats and animations.
- **`RaceCommandCenter.tsx`**: Real-time strategy dashboard.
- **`DynamicSimulationBackground.tsx`**: Circuit-aware SVG animation engine.

## Development

### Prerequisites
- Node.js 18+
- NPM

### Commands
```bash
npm install     # Install dependencies
npm run dev     # Start development server at http://localhost:3000
npm run build   # Production bundle to dist/
```

## Deployment
Automated via **Vercel** on the `frontend` branch. Ensure `VITE_API_URL` is set in the environment for production backend connectivity.

---
**Status**: Visual Modernization Complete | **Build**: Vite + Tailwind + Glassmorphism
