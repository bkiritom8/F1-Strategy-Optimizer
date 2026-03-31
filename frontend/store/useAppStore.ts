/**
 * @file store/useAppStore.ts
 * @description Global application state via Zustand.
 * Shares selected driver, race context, and theme across all views
 * so navigating from Command Center to Driver Profiles preserves selection.
 */

import { create } from 'zustand';

interface AppState {
  // Selected driver (shared across Command Center, Profiles, Strategy Sim)
  selectedDriverId: string;
  setSelectedDriverId: (id: string) => void;

  // Active race context
  activeRaceId: string;
  activeRaceRound: number;
  activeLap: number;
  setActiveRace: (raceId: string, round?: number, lap?: number) => void;
  setActiveRaceRound: (round: number) => void;
  setActiveLap: (lap: number) => void;

  // Theme
  theme: 'dark' | 'light';
  toggleTheme: () => void;

  // Sidebar state (mobile & desktop collapse)
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;
  sidebarCollapsed: boolean;
  toggleSidebarCollapsed: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  selectedDriverId: 'max_verstappen',
  setSelectedDriverId: (id) => set({ selectedDriverId: id }),

  activeRaceId: '2024_1',
  activeRaceRound: 1,
  activeLap: 1,
  setActiveRace: (raceId, round, lap) =>
    set({ activeRaceId: raceId, activeRaceRound: round ?? 1, activeLap: lap ?? 1 }),
  setActiveRaceRound: (round) =>
    set({ activeRaceRound: round, activeRaceId: `2024_${round}` }),
  setActiveLap: (lap) => set({ activeLap: lap }),

  theme: 'dark',
  toggleTheme: () =>
    set((s) => ({ theme: s.theme === 'dark' ? 'light' : 'dark' })),

  sidebarOpen: false,
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),

  sidebarCollapsed: false,
  toggleSidebarCollapsed: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
}));
