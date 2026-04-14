/**
 * @file store/useAppStore.ts
 * @description Global application state via Zustand.
 *
 * Current model:
 *   - Open-access by default (isLoggedIn: true).
 *   - Administrative features gated by a simple password (adminLogin).
 *   - Persists admin status to localStorage.
 */

import { create } from 'zustand';

const STORAGE_KEY = 'divergex_admin_auth';
const ADMIN_PASSWORD = import.meta.env.VITE_ADMIN_PASSWORD ?? '';

function timingSafeEqual(a: string, b: string): boolean {
  if (!a || !b || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

// ─── Simple Admin Persistence ────────────────────────────────────────────────
// We only persist the admin status for convenience.
interface AdminState {
  isAdmin: boolean;
  username: string;
}

function loadAdminState(): AdminState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch { /* ignore */ }
  return { isAdmin: false, username: 'Race Control' };
}

function saveAdminState(state: AdminState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch { /* ignore */ }
}

// ─── Store interface ─────────────────────────────────────────────────────────

interface AppState {
  // ── Auth & Admin ───────────────────────────────────────────────────────────
  isLoggedIn: boolean;
  isAdmin:    boolean;
  username:   string;
  
  /**
    * Simple password-gated access for administrative features.
    * Password is injected via VITE_ADMIN_PASSWORD.
   */
  adminLogin: (password: string) => boolean;

  /** Reverts to standard user mode. */
  logout: () => void;

  // ── Selected driver (shared across Command Center / Profiles / Strategy) ───
  selectedDriverId: string;
  setSelectedDriverId: (id: string) => void;

  // ── Season selection ────────────────────────────────────────────────────────
  selectedSeason: 2024 | 2025 | 2026;
  setSelectedSeason: (season: 2024 | 2025 | 2026) => void;

  // ── Active race context ───────────────────────────────────────────────────
  activeRaceId:      string;
  activeRaceRound:   number;
  activeLap:         number;
  backgroundCircuitId: string | null;
  setActiveRace:        (raceId: string, round?: number, lap?: number) => void;
  setActiveRaceRound:   (round: number) => void;
  setActiveLap:         (lap: number) => void;
  setBackgroundCircuitId: (id: string | null) => void;

  // ── Sidebar state ─────────────────────────────────────────────────────────
  sidebarOpen:      boolean;
  setSidebarOpen:   (open: boolean) => void;
  toggleSidebar:    () => void;
  sidebarCollapsed: boolean;
  toggleSidebarCollapsed: () => void;

  // ── Greeting Logic ────────────────────────────────────────────────────────
  isReturningUser: boolean;
  setHasVisited: () => void;

  // ── Global Modals ─────────────────────────────────────────────────────────
  isAdminModalOpen: boolean;
  setAdminModalOpen: (open: boolean) => void;
}

// ─── Store creation ──────────────────────────────────────────────────────────

const initialAdmin = loadAdminState();

export const useAppStore = create<AppState>((set) => ({
  // ── Auth & Admin ──────────────────────────────────────────────────────────
  // The platform is now open-access by default.
  isLoggedIn: true,
  isAdmin:    initialAdmin.isAdmin,
  username:   initialAdmin.username,

  adminLogin: (password: string) => {
    if (timingSafeEqual(password, ADMIN_PASSWORD)) {
      const state = { isAdmin: true, username: 'F1 Admin' };
      set(state);
      saveAdminState(state);
      return true;
    }
    return false;
  },

  logout: () => {
    const state = { isAdmin: false, username: 'Race Control' };
    set(state);
    saveAdminState(state);
  },

  // ── Driver selection ───────────────────────────────────────────────────────
  selectedDriverId:    'max_verstappen',
  setSelectedDriverId: (id) => set({ selectedDriverId: id }),

  // ── Season selection ───────────────────────────────────────────────────────
  selectedSeason: 2024,
  setSelectedSeason: (season) => set({ selectedSeason: season }),

  // ── Race context ───────────────────────────────────────────────────────────
  activeRaceId:     '2024_1',
  activeRaceRound:  1,
  activeLap:        1,
  backgroundCircuitId: null,
  setActiveRace: (raceId, round, lap) =>
    set({ activeRaceId: raceId, activeRaceRound: round ?? 1, activeLap: lap ?? 1 }),
  setActiveRaceRound: (round) =>
    set((s) => ({ activeRaceRound: round, activeRaceId: `${s.selectedSeason}_${round}` })),
  setActiveLap: (lap) => set({ activeLap: lap }),
  setBackgroundCircuitId: (id) => set({ backgroundCircuitId: id }),

  // ── Sidebar ────────────────────────────────────────────────────────────────
  sidebarOpen:     false,
  setSidebarOpen:  (open) => set({ sidebarOpen: open }),
  toggleSidebar:   () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  sidebarCollapsed: false,
  toggleSidebarCollapsed: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),

  // ── Greeting Logic ────────────────────────────────────────────────────────
  isReturningUser: document.cookie.includes('divergex_returning_user=true'),
  setHasVisited: () => {
    document.cookie = 'divergex_returning_user=true; path=/; max-age=31536000; SameSite=Lax';
    set({ isReturningUser: true });
  },

  // ── Global Modals ─────────────────────────────────────────────────────────
  isAdminModalOpen:  false,
  setAdminModalOpen: (open) => set({ isAdminModalOpen: open }),
}));
