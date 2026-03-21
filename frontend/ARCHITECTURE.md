# Apex Intelligence Architecture

This document outlines the technical architecture, design principles, and development standards for the Apex Intelligence platform. Refer to this document when making changes to ensure consistency and maintain the high-end aesthetic and functional standards.

## 1. Technology Stack

- **Frontend Core**: React 19 (TypeScript)
- **Build Tool**: Vite 6
- **Styling**: Vanilla CSS (via CSS modules or global styles) with Tailwind-like utility classes in JSX where appropriate.
- **Animations**: Framer Motion (v11+)
- **Icons**: Lucide React
- **Charts**: Recharts (v2.15+)
- **AI Integration**: Google Generative AI SDK (`@google/genai`)

## 2. Project Structure

```text
/
├── components/          # Reusable UI components
│   ├── DriverCard.tsx   # Individual driver display
│   ├── PositionTower.tsx # Real-time race standings
│   └── RacingBackground.tsx # Global background animations
├── views/               # Page-level components (Routes)
│   ├── RaceCommandCenter.tsx
│   ├── DriverProfiles.tsx
│   ├── PitStrategySimulator.tsx
│   ├── LapByLapAnalysis.tsx
│   ├── SystemMonitoringHealth.tsx
│   ├── ValidationPerformance.tsx
│   └── AIChatbot.tsx
├── constants.ts         # Global theme tokens and mock data
├── types.ts             # TypeScript interfaces and enums
├── App.tsx              # Main entry point and navigation logic
└── index.tsx            # React DOM mounting
```

## 3. Design System & Aesthetics

### Color Palette (from `constants.ts`)
- **Primary Background**: `#0F0F0F` (Deep Dark)
- **Secondary Background**: `#1A1A1A` (Elevation)
- **Accent Red**: `#E10600` (F1 Brand Red)
- **Accent Green**: `#00D2BE` (Mercedes-style Teal)
- **Typography**: Display fonts should be bold, uppercase, and italicized for a racing feel.

### UI Principles
- **Glassmorphism**: Use `backdrop-blur` and low-opacity backgrounds (`/90`, `/40`) for overlays and sidebars.
- **Visual Feedback**: Buttons and interactive elements should have hover transitions and subtle glow effects (`box-shadow`).
- **Dynamic Content**: Use `Framer Motion` for all view transitions and data updates.

## 4. Data Flow & State

- **Telemetry**: Defined in `types.ts` as `DriverTelemetry`.
- **Strategy**: AI-driven recommendations are typed as `StrategyRecommendation`.
- **Mock Data**: Centralized in `constants.ts` for consistent testing and development.
- **State Management**: Uses React `useState` and `useEffect` at the view level. Global session state is managed via `RaceState`.

## 5. Development Guidelines

- **Component Best Practices**: Keep components focused. Extract complex logic into hooks or utility functions.
- **Styling Rules**: Prefer `className` strings with utility-like properties. Ensure responsive design using flexbox and grid.
- **AI Features**: When implementing AI-related features, use the `AIChatbot.tsx` patterns. Ensure the Gemini API key is managed via `.env.local`.

## 6. Verification Checklist
- [ ] UI maintains "Premium" look (no default browser styles).
- [ ] Transitions between views are smooth (Framer Motion).
- [ ] Telemetry data binds correctly to `DriverCard` and `PositionTower`.
- [ ] Charts (Recharts) are responsive and use the project color palette.
