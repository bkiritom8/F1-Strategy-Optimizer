/**
 * @file __tests__/track-registry.test.ts
 * @description Unit tests for the TRACK_REGISTRY, TrackInfo metadata, and
 * helper functions exported from components/tracks/TrackMaps.tsx.
 *
 * These tests ensure:
 *  - Every circuit has required, non-empty metadata fields.
 *  - The hasLiveData flag correctly partitions circuits into live/speculative sets.
 *  - All 26 circuits are present and uniquely identified.
 *  - Helper functions (getTrackById, getLiveDataTracks, getSpeculativeTracks) behave correctly.
 *  - Speculative tracks declare a statusNote explaining the approximation.
 */

import { describe, it, expect } from 'vitest';
import {
  TRACK_REGISTRY,
  getTrackById,
  getLiveDataTracks,
  getSpeculativeTracks,
} from '../components/tracks/TrackMaps';

// ─── Registry integrity ────────────────────────────────────────────────────────

describe('TRACK_REGISTRY', () => {
  it('contains exactly 26 circuits', () => {
    expect(TRACK_REGISTRY).toHaveLength(26);
  });

  it('has no duplicate IDs', () => {
    const ids = TRACK_REGISTRY.map((t) => t.id);
    const unique = new Set(ids);
    expect(unique.size).toBe(ids.length);
  });

  it('every circuit has a non-empty id, name, and country', () => {
    for (const track of TRACK_REGISTRY) {
      expect(track.id.trim()).not.toBe('');
      expect(track.name.trim()).not.toBe('');
      expect(track.country.trim()).not.toBe('');
    }
  });

  it('every circuit has positive numeric metadata', () => {
    for (const track of TRACK_REGISTRY) {
      expect(track.lengthKm).toBeGreaterThan(0);
      expect(track.corners).toBeGreaterThan(0);
      expect(track.drsZones).toBeGreaterThanOrEqual(0);
      expect(track.laps).toBeGreaterThan(0);
    }
  });

  it('every circuit has a hasLiveData boolean', () => {
    for (const track of TRACK_REGISTRY) {
      expect(typeof track.hasLiveData).toBe('boolean');
    }
  });

  it('every circuit has a React component function', () => {
    for (const track of TRACK_REGISTRY) {
      expect(typeof track.component).toBe('function');
    }
  });
});

// ─── Live vs speculative partitioning ─────────────────────────────────────────

describe('hasLiveData partitioning', () => {
  it('23 circuits have live FastF1 telemetry data', () => {
    const live = TRACK_REGISTRY.filter((t) => t.hasLiveData);
    expect(live).toHaveLength(23);
  });

  it('3 circuits are flagged as speculative / no live data', () => {
    const speculative = TRACK_REGISTRY.filter((t) => !t.hasLiveData);
    expect(speculative).toHaveLength(3);
  });

  it('speculative circuits are madrid, bhuj, argentina', () => {
    const ids = TRACK_REGISTRY.filter((t) => !t.hasLiveData).map((t) => t.id).sort();
    expect(ids).toEqual(['argentina', 'bhuj', 'madrid']);
  });

  it('speculative circuits each have a statusNote explaining the approximation', () => {
    const spec = TRACK_REGISTRY.filter((t) => !t.hasLiveData);
    for (const track of spec) {
      expect(track.statusNote).toBeDefined();
      expect((track.statusNote ?? '').trim().length).toBeGreaterThan(10);
    }
  });

  it('2024 F1 calendar circuits are all flagged hasLiveData=true', () => {
    const expectedLiveIds = [
      'bahrain', 'jeddah', 'melbourne', 'suzuka', 'shanghai',
      'miami', 'imola', 'monaco', 'montreal', 'barcelona',
      'spielberg', 'silverstone', 'budapest', 'spa', 'zandvoort',
      'monza', 'singapore', 'cota', 'mexico', 'interlagos',
      'vegas', 'lusail', 'yas_marina',
    ];
    for (const id of expectedLiveIds) {
      const track = TRACK_REGISTRY.find((t) => t.id === id);
      expect(track, `Track "${id}" not found`).toBeDefined();
      expect(track?.hasLiveData, `Track "${id}" should have hasLiveData=true`).toBe(true);
    }
  });
});

// ─── getTrackById ─────────────────────────────────────────────────────────────

describe('getTrackById', () => {
  it('returns the correct track for a known id', () => {
    const track = getTrackById('monaco');
    expect(track).toBeDefined();
    expect(track?.name).toBe('Circuit de Monaco');
    expect(track?.corners).toBe(19);
    expect(track?.drsZones).toBe(0);
  });

  it('returns the correct track for a speculative circuit', () => {
    const track = getTrackById('madrid');
    expect(track).toBeDefined();
    expect(track?.country).toBe('Spain');
    expect(track?.hasLiveData).toBe(false);
  });

  it('returns undefined for an unknown id', () => {
    expect(getTrackById('unknown_circuit_xyz')).toBeUndefined();
  });

  it('returns undefined for an empty string', () => {
    expect(getTrackById('')).toBeUndefined();
  });

  it('is case-sensitive (IDs are lowercase)', () => {
    expect(getTrackById('MONACO')).toBeUndefined();
    expect(getTrackById('Monaco')).toBeUndefined();
    expect(getTrackById('monaco')).toBeDefined();
  });
});

// ─── getLiveDataTracks ────────────────────────────────────────────────────────

describe('getLiveDataTracks', () => {
  it('returns 23 tracks', () => {
    expect(getLiveDataTracks()).toHaveLength(23);
  });

  it('all returned tracks have hasLiveData=true', () => {
    for (const track of getLiveDataTracks()) {
      expect(track.hasLiveData).toBe(true);
    }
  });

  it('does not include speculative tracks', () => {
    const ids = getLiveDataTracks().map((t) => t.id);
    expect(ids).not.toContain('madrid');
    expect(ids).not.toContain('bhuj');
    expect(ids).not.toContain('argentina');
  });
});

// ─── getSpeculativeTracks ─────────────────────────────────────────────────────

describe('getSpeculativeTracks', () => {
  it('returns exactly 3 tracks', () => {
    expect(getSpeculativeTracks()).toHaveLength(3);
  });

  it('all returned tracks have hasLiveData=false', () => {
    for (const track of getSpeculativeTracks()) {
      expect(track.hasLiveData).toBe(false);
    }
  });

  it('contains madrid, bhuj, and argentina', () => {
    const ids = getSpeculativeTracks().map((t) => t.id).sort();
    expect(ids).toEqual(['argentina', 'bhuj', 'madrid']);
  });
});

// ─── Metadata sanity ─────────────────────────────────────────────────────────

describe('circuit metadata sanity', () => {
  it('Monaco is the shortest listed circuit', () => {
    const lengths = TRACK_REGISTRY.map((t) => t.lengthKm);
    const min = Math.min(...lengths);
    const monaco = getTrackById('monaco');
    expect(monaco?.lengthKm).toBe(min);
  });

  it('Spa is the longest listed circuit', () => {
    const lengths = TRACK_REGISTRY.map((t) => t.lengthKm);
    const max = Math.max(...lengths);
    const spa = getTrackById('spa');
    expect(spa?.lengthKm).toBe(max);
  });

  it('Monaco has 0 DRS zones', () => {
    expect(getTrackById('monaco')?.drsZones).toBe(0);
  });

  it('all DRS zone counts are non-negative integers', () => {
    for (const track of TRACK_REGISTRY) {
      expect(Number.isInteger(track.drsZones)).toBe(true);
      expect(track.drsZones).toBeGreaterThanOrEqual(0);
    }
  });
});
