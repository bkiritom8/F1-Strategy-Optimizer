/**
 * @file store/useAppStore.ts
 * @description Global application state via Zustand.
 *
 * Auth model:
 *   - loginAsync(username, password) → calls backend /users/login → stores JWT
 *   - loginWithOtpAsync(email, otp)  → calls backend /users/login-otp → stores JWT
 *   - logout()  → clears JWT from sessionStorage + all auth state
 *
 * No credentials are stored in this module.  All auth logic lives in
 * authService.ts; the store only holds the resulting auth state.
 */

import { create } from 'zustand';
import {
  signIn,
  signInWithOtp,
  clearStoredToken,
  getStoredToken,
  type AuthUser,
} from '../services/authService';

const STORAGE_KEY = 'apex_auth';

// ─── Auth state persisted to localStorage ────────────────────────────────────
// We persist only non-sensitive state: isLoggedIn, isAdmin, username.
// The JWT itself lives in sessionStorage (cleared on browser close).

interface PersistedAuth {
  isLoggedIn: boolean;
  isAdmin:    boolean;
  username:   string;
  email:      string;
}

function loadPersistedAuth(): PersistedAuth {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as PersistedAuth;
      // If the JWT is gone (browser closed), clear the persisted logged-in state
      if (parsed.isLoggedIn && !getStoredToken()) {
        return { isLoggedIn: false, isAdmin: false, username: '', email: '' };
      }
      return parsed;
    }
  } catch { /* corrupted storage */ }
  return { isLoggedIn: false, isAdmin: false, username: '', email: '' };
}

function savePersistedAuth(state: PersistedAuth): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch { /* quota error */ }
}

// ─── Store interface ─────────────────────────────────────────────────────────

interface AppState {
  // ── Auth ────────────────────────────────────────────────────────────────────
  isLoggedIn:   boolean;
  isAdmin:      boolean;
  username:     string;
  email:        string;
  /** True while an async login call is in flight. */
  authLoading:  boolean;

  /**
   * Sign in with username + password.
   * Returns { ok, errorMsg?, needsVerification? } from authService.
   */
  loginAsync: (
    username: string,
    password: string,
  ) => Promise<{ ok: boolean; errorMsg?: string; needsVerification?: boolean }>;

  /**
   * Sign in with an emailed 6-digit OTP.
   * Returns { ok, errorMsg? } from authService.
   */
  loginWithOtpAsync: (
    email: string,
    otp:   string,
  ) => Promise<{ ok: boolean; errorMsg?: string }>;

  /** Clears all auth state and the stored JWT. */
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
}

// ─── Store creation ──────────────────────────────────────────────────────────

const initialAuth = loadPersistedAuth();

export const useAppStore = create<AppState>((set) => ({
  // ── Auth ──────────────────────────────────────────────────────────────────
  isLoggedIn:  initialAuth.isLoggedIn,
  isAdmin:     initialAuth.isAdmin,
  username:    initialAuth.username,
  email:       initialAuth.email,
  authLoading: false,

  loginAsync: async (username, password) => {
    set({ authLoading: true });
    const result = await signIn(username, password);
    set({ authLoading: false });

    if (result.ok && result.user) {
      _applyUser(set, result.user);
    }
    return { ok: result.ok, errorMsg: result.errorMsg, needsVerification: result.needsVerification };
  },

  loginWithOtpAsync: async (email, otp) => {
    set({ authLoading: true });
    const result = await signInWithOtp(email, otp);
    set({ authLoading: false });

    if (result.ok && result.user) {
      _applyUser(set, result.user);
    }
    return { ok: result.ok, errorMsg: result.errorMsg };
  },

  logout: () => {
    clearStoredToken();
    const authState: PersistedAuth = { isLoggedIn: false, isAdmin: false, username: '', email: '' };
    savePersistedAuth(authState);
    set({ isLoggedIn: false, isAdmin: false, username: '', email: '' });
  },

  // ── Driver selection ───────────────────────────────────────────────────────
  selectedDriverId:    'max_verstappen',
  setSelectedDriverId: (id) => set({ selectedDriverId: id }),

  // ── Season selection ───────────────────────────────────────────────────────
  selectedSeason: 2026,
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
  isReturningUser: document.cookie.includes('apex_returning_user=true'),
  setHasVisited: () => {
    document.cookie = 'apex_returning_user=true; path=/; max-age=31536000; SameSite=Lax';
    set({ isReturningUser: true });
  },
}));

// ─── Internal helpers ────────────────────────────────────────────────────────

/** Apply a successful auth result to the store and persist it. */
function _applyUser(set: any, user: AuthUser): void {
  const isAdmin = user.is_admin || user.role === 'roles/admin';
  const authState: PersistedAuth = {
    isLoggedIn: true,
    isAdmin,
    username:   user.username,
    email:      user.email,
  };
  savePersistedAuth(authState);
  set({ isLoggedIn: true, isAdmin, username: user.username, email: user.email });
}
