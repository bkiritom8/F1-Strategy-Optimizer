/**
 * @file __tests__/store.test.ts
 * @description Unit tests for the Zustand global store.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useAppStore } from '../store/useAppStore';

describe('useAppStore', () => {
  beforeEach(() => {
    // Reset store to defaults
    useAppStore.setState({
      selectedDriverId: 'max_verstappen',
      activeRaceId: '2024_1',
      activeLap: 1,
      sidebarOpen: false,
    });
  });

  it('should have correct default state', () => {
    const state = useAppStore.getState();
    expect(state.selectedDriverId).toBe('max_verstappen');
    expect(state.activeRaceId).toBe('2024_1');
    expect(state.activeLap).toBe(1);
    expect(state.sidebarOpen).toBe(false);
  });

  it('should update selected driver', () => {
    useAppStore.getState().setSelectedDriverId('hamilton');
    expect(useAppStore.getState().selectedDriverId).toBe('hamilton');
  });

  it('should update active race', () => {
    useAppStore.getState().setActiveRace('2024_5', 10);
    const state = useAppStore.getState();
    expect(state.activeRaceId).toBe('2024_5');
    expect(state.activeLap).toBe(10);
  });

  it('should default lap to 1 when not provided', () => {
    useAppStore.getState().setActiveRace('2024_10');
    expect(useAppStore.getState().activeLap).toBe(1);
  });

  it('should toggle sidebar', () => {
    expect(useAppStore.getState().sidebarOpen).toBe(false);
    useAppStore.getState().toggleSidebar();
    expect(useAppStore.getState().sidebarOpen).toBe(true);
  });
});
