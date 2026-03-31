# Antigravity Prompt: Build, Deploy & Push Apex Intelligence Frontend

## Context

You are working on the **Apex Intelligence** F1 Race Strategy Dashboard.

There are TWO local project folders involved:

1. **Development source** (where all code lives):
   `/Users/skymaster/Library/CloudStorage/OneDrive-NortheasternUniversity/Projects/apex-intelligence`

2. **Deployment repo** (Bhargav's team repo, connected to Vercel):
   `/Users/skymaster/Library/CloudStorage/OneDrive-NortheasternUniversity/Projects/F1-Strategy-Optimizer`
   - GitHub: `https://github.com/bkiritom8/F1-Strategy-Optimizer`
   - Branch: `main`
   - Vercel reads from the `frontend/` subfolder in this repo

The Vercel deployment URL is: `https://apexintelligence.vercel.app/`

**How deployment works:**
The `apex-intelligence/` folder is NOT connected to Vercel directly. Instead, after building locally, the `dist/` output is copied into `F1-Strategy-Optimizer/frontend/dist/`, committed, and pushed to Bhargav's repo. Vercel auto-deploys from that push.

---

## What Changed (Summary of Updates)

These changes have already been made to the source code in `apex-intelligence/`. Nothing needs to be coded. This prompt is ONLY for building and deploying.

### New Features
- **Race Command Center**: Safety Car probability gauge, Overtake probability gauge, DRS status card with per-circuit zone count, Sector timing breakdown with S1/S2/S3 bars
- **Pit Strategy Simulator**: Full rewrite with driver/race selectors, "Run Simulation" button wired to `POST /api/v1/strategy/simulate`, custom stint builder (add/remove pit stops), simulated lap time trace chart, Live/Local indicator
- **Driver Profiles**: Complete rewrite. Removed fake Trait Correlation Matrix and Radar charts (those used fabricated behavioral scores). Replaced with verified 2024 season roster showing real FIA race data: points, wins, podiums, avg grid, avg finish, DNFs, finish rate, positions gained per race. All computed from `races-2024.json`

### Bug Fixes
- Removed `/data` Vite proxy that was intercepting `public/data/*.json` static files (breaking the second-tier fallback chain)
- Fixed `vite-env.d.ts` (removed stale `VITE_ADMIN_PASSWORD`, `VITE_NVIDIA_API_KEY`)
- All numbers across the entire UI now use 2 decimal places (`.toFixed(2)`)
- Fixed Race Command scrolling (removed `flex-1 min-h-0` constraints that squished content)
- Zustand store sync added to RaceCommandCenter and PitStrategySimulator (driver/race selection persists across views)

### Cleanup
- Removed Validation, Model Engineering, System Health from public sidebar (they stay inside AdminPage behind password gate only)
- Removed unused `@google/genai` dependency from package.json
- Removed `refactor_tracks.js` (one-off utility)
- Removed stale lazy imports (`ValidationPerformance`, `ModelEngineering`, `SystemMonitoringHealth` from App.tsx routes)

### Files NOT modified (left as-is)
- `components/RacingBackground.tsx` (kept intentionally)
- `services/client.ts`, `services/logger.ts` (unchanged)
- `hooks/useApi.ts` (unchanged)
- `__tests__/*` (unchanged)
- `components/tracks/*` (unchanged)
- `public/data/*.json` (unchanged)

---

## Task: Build and Deploy

Execute these steps in order. Stop and report if any step fails.

### Step 1: Build the frontend

```bash
cd /Users/skymaster/Library/CloudStorage/OneDrive-NortheasternUniversity/Projects/apex-intelligence
npm run build
```

This runs `vite build` which TypeScript-checks and bundles everything into `dist/`.

**If this fails:** Read the error. It will be a TypeScript or import error. Fix it in the source file, then re-run `npm run build`.

**Expected output:** A `dist/` folder containing `index.html`, `assets/`, and `favicon.svg`.

### Step 2: Copy build output to deployment repo

```bash
# Remove old build
rm -rf /Users/skymaster/Library/CloudStorage/OneDrive-NortheasternUniversity/Projects/F1-Strategy-Optimizer/frontend/dist

# Copy new build
cp -r /Users/skymaster/Library/CloudStorage/OneDrive-NortheasternUniversity/Projects/apex-intelligence/dist /Users/skymaster/Library/CloudStorage/OneDrive-NortheasternUniversity/Projects/F1-Strategy-Optimizer/frontend/dist

# Copy static data files (real pipeline data served by Vercel as static assets)
cp -r /Users/skymaster/Library/CloudStorage/OneDrive-NortheasternUniversity/Projects/apex-intelligence/public/data /Users/skymaster/Library/CloudStorage/OneDrive-NortheasternUniversity/Projects/F1-Strategy-Optimizer/frontend/dist/data

# Also copy vercel.json for SPA rewrites
cp /Users/skymaster/Library/CloudStorage/OneDrive-NortheasternUniversity/Projects/apex-intelligence/vercel.json /Users/skymaster/Library/CloudStorage/OneDrive-NortheasternUniversity/Projects/F1-Strategy-Optimizer/frontend/vercel.json
```

### Step 3: Verify the copied output

```bash
ls -la /Users/skymaster/Library/CloudStorage/OneDrive-NortheasternUniversity/Projects/F1-Strategy-Optimizer/frontend/dist/
ls -la /Users/skymaster/Library/CloudStorage/OneDrive-NortheasternUniversity/Projects/F1-Strategy-Optimizer/frontend/dist/data/
ls -la /Users/skymaster/Library/CloudStorage/OneDrive-NortheasternUniversity/Projects/F1-Strategy-Optimizer/frontend/dist/assets/
```

You should see:
- `dist/index.html`
- `dist/favicon.svg`
- `dist/assets/` (JS and CSS bundles)
- `dist/data/drivers.json`, `circuits.json`, `races-2024.json`, `seasons.json`, `pipeline-reports.json`

### Step 4: Commit and push to Bhargav's repo

```bash
cd /Users/skymaster/Library/CloudStorage/OneDrive-NortheasternUniversity/Projects/F1-Strategy-Optimizer

# Check current branch (should be main)
git branch

# See what changed
git status

# Stage only the frontend folder
git add frontend/

# Commit
git commit -m "feat(frontend): SC/overtake gauges, DRS card, sector timing, strategy sim rewrite, verified driver roster, scroll fix, 2-decimal formatting, admin route cleanup"

# Push
git push origin main
```

**If push is rejected** (because remote has newer commits):
```bash
git pull --rebase origin main
git push origin main
```

**If there are merge conflicts in frontend/dist:** Since dist is a build artifact, always take our version:
```bash
git checkout --ours frontend/dist
git add frontend/dist
git rebase --continue
```

### Step 5: Verify Vercel deployment

After pushing, Vercel auto-deploys within 2 minutes. Check:
- `https://apexintelligence.vercel.app/`

Verify these pages work:
1. **Race Command** (`/`): Should show SC gauge, Overtake gauge, DRS card, Sector timing row
2. **Driver Profiles** (`/drivers`): Should show ranked 2024 roster with real points, wins, podiums (NO scatter plot, NO radar chart)
3. **Strategy Sim** (`/strategy`): Should have driver/race dropdowns and "Run Simulation" button
4. **Sidebar**: Should show 7 items (Race Command, Driver Profiles, Strategy Sim, AI Strategist, Circuit Directory, Post-Race, Admin Control). Should NOT show Validation, Model Engineering, or System Health

---

## Important Notes

- The `F1-Strategy-Optimizer` repo is owned by Bhargav (`bkiritom8`). Make sure you have push access. If not, create a PR instead of pushing directly.
- Do NOT modify any source code in `F1-Strategy-Optimizer/src/`, `ml/`, `pipeline/`, or `Data-Pipeline/`. Only touch `frontend/`.
- The `.env.local` in `frontend/` is gitignored. It contains `VITE_GEMINI_API_KEY` and `VITE_API_URL`. Do not commit it.
- Vercel is configured with Root Directory = `frontend` and Output Directory = `dist`.
