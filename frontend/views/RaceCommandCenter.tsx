/**
 * @file RaceCommandCenter.tsx
 * @description Primary operational view for Apex Intelligence.
 *
 * Features added:
 * - Predictive Intelligence panels (Safety Car risk, Overtake probability)
 * - DRS zone status indicator per driver
 * - Sector timing breakdown with visual bars
 * - Live race state integration with mock fallback
 */

import React, { useState, useEffect, useMemo } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle, HelpCircle, ChevronRight, Info, Shield, Zap, Radio, Timer, Menu, X } from 'lucide-react';
import PositionTower from '../components/PositionTower';
import DriverCard from '../components/DriverCard';
import { LiveBadge } from '../components/LiveBadge';

import ConceptTooltip from '../components/ConceptTooltip';
import { COLORS, F1_GLOSSARY } from '../constants';
import type { RaceState, DriverTelemetry, StrategyRecommendation } from '../types';

// ── Local fallbacks (previously in constants, removed with mock-data cleanup) ──

const DEFAULT_RACE_STATE: RaceState = {
  race_id: '2024_1', circuit: 'bahrain', current_lap: 1, total_laps: 57,
  weather: 'dry', track_temp_celsius: 38, air_temp_celsius: 28,
  track_grip_level: 95, flag: 'GREEN',
};

function getMockTelemetry(driver_id: string, position: number): DriverTelemetry {
  const seed = driver_id.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
  return {
    driver_id, position,
    gap_to_leader: position === 1 ? 0 : (position - 1) * 1.2 + ((seed * 7) % 3),
    gap_to_ahead: position === 1 ? 0 : 1.2 + ((seed * 3) % 2),
    gap_to_behind: 1.4 + ((seed * 5) % 2),
    current_lap_time: 94 + ((seed * 11) % 4000) / 1000,
    last_lap_time: 93.5 + ((seed * 13) % 3000) / 1000,
    best_lap_time: 92.8 + ((seed * 17) % 2000) / 1000,
    speed_kph: 280 + (seed % 40),
    ers_deployment: 60 + (seed % 30),
    ers_mode: 'BALANCED' as const,
    fuel_remaining_kg: 50 - (seed % 20),
    tire_compound: (['SOFT', 'MEDIUM', 'HARD'] as const)[seed % 3],
    tire_age_laps: 5 + (seed % 20),
    tire_wear_percent: 30 + (seed % 40),
    tire_temp_fl: 88 + (seed % 12), tire_temp_fr: 87 + (seed % 12),
    tire_temp_rl: 90 + (seed % 10), tire_temp_rr: 89 + (seed % 10),
    aero_loss_percent: position > 3 ? 8 + (seed % 10) : 0,
    drs_active: seed % 3 === 0,
    g_force_lateral: 3.5 + (seed % 20) / 10,
    g_force_longitudinal: 4.2 + (seed % 15) / 10,
    tire_grip_remaining: 70 - (seed % 30),
  };
}

function getMockStrategy(driver_id: string): StrategyRecommendation {
  const seed = driver_id.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
  return {
    driver_id,
    current_lap: 20 + (seed % 10),
    pit_recommendation: {
      recommended_pit_lap: 28 + (seed % 8),
      confidence: 0.75 + ((seed % 20) / 100),
      tire_compound: (['MEDIUM', 'HARD'] as const)[seed % 2],
      expected_position_after_pit: 1 + (seed % 5),
      win_probability: 0.20 + ((seed % 25) / 100),
      podium_probability: 0.45 + ((seed % 30) / 100),
    },
    driving_style: {
      mode: (['PUSH', 'BALANCED', 'CONSERVE'] as const)[seed % 3],
      ers_target_mode: 'BALANCED' as const,
      reason: 'Maintain gap while managing tire wear',
      fuel_target_kg_per_lap: 1.65 + ((seed % 10) / 100),
    },
    brake_bias: { recommended_bias: 56 + (seed % 4), reason: 'Front-limited under braking' },
    warnings: [],
  };
}
import type { DriverProfile } from '../types';
import { useDrivers, useBackendStatus, useRaces2024, useOvertakeMetric, useSafetyCarProb } from '../hooks/useApi';
import { fetchRaceState, fetchStrategyRecommendation } from '../services/endpoints';
import { useAppStore } from '../store/useAppStore';

/* ── Tiny sub-components ──────────────────────────────────────────────── */

interface BadgeProps { label: string; value: string; color?: string; pulse?: boolean | null; }
function Badge({ label, value, color, pulse }: BadgeProps) {
  return (
    <div className="flex flex-col">
      <span className="text-[9px] font-bold text-gray-500 uppercase tracking-widest">{label}</span>
      <div className="flex items-center gap-2">
        {pulse && <div className="w-2 h-2 rounded-full bg-current animate-pulse" style={{ color: color || 'var(--text-primary)' }} />}
        <span className="text-lg font-mono font-bold" style={{ color: color || 'var(--text-primary)' }}>{value}</span>
      </div>
    </div>
  );
}

function LegendItem({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
      <span className="text-[10px] font-bold text-gray-500 uppercase">{label}</span>
    </div>
  );
}

/** Circular progress gauge for probabilities. Compact layout for 2-col mobile grid. */
function ProbGauge({ value, label, icon: Icon, color, subtitle }: {
  value: number; label: string; icon: React.ElementType; color: string; subtitle?: string;
}) {
  const pct = Math.min(value * 100, 100);
  // Smaller radius so the gauge fits comfortably in half-width columns on mobile
  const r = 28;
  const circ = 2 * Math.PI * r;
  const offset = circ - (pct / 100) * circ;
  const riskLevel = pct > 40 ? 'HIGH' : pct > 20 ? 'ELEV' : 'LOW';
  const riskColor = pct > 40 ? COLORS.accent.red : pct > 20 ? COLORS.accent.yellow : COLORS.accent.green;

  return (
    <div
      className="flex flex-col gap-2 p-3 rounded-xl border backdrop-blur-sm"
      style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}
    >
      {/* Label row */}
      <div className="flex items-center gap-1.5">
        <Icon className="w-3.5 h-3.5 shrink-0" style={{ color }} />
        <span className="text-[10px] font-bold uppercase tracking-wide text-gray-300 leading-tight">{label}</span>
      </div>

      {/* Gauge + risk side by side */}
      <div className="flex items-center gap-3">
        <div className="relative shrink-0" style={{ width: 64, height: 64 }}>
          <svg viewBox="0 0 64 64" className="w-full h-full -rotate-90">
            <circle cx="32" cy="32" r={r} fill="none" stroke="var(--border-color)" strokeWidth="4" />
            <motion.circle
              cx="32" cy="32" r={r} fill="none" stroke={color} strokeWidth="4"
              strokeLinecap="round" strokeDasharray={circ}
              initial={{ strokeDashoffset: circ }}
              animate={{ strokeDashoffset: offset }}
              transition={{ duration: 1.2, ease: 'easeOut' }}
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-[11px] font-mono font-black leading-none" style={{ color }}>
              {pct.toFixed(1)}%
            </span>
          </div>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1 mb-1">
            <div className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: riskColor }} />
            <span className="text-[10px] font-bold uppercase" style={{ color: riskColor }}>{riskLevel} RISK</span>
          </div>
          {subtitle && (
            <p className="text-[9px] text-gray-500 leading-snug">{subtitle}</p>
          )}
        </div>
      </div>
    </div>
  );
}

/** DRS status indicator for the selected driver. */
function DRSCard({ active, zonesTotal }: { active: boolean; zonesTotal: number }) {
  return (
    <div className="p-4 rounded-xl border backdrop-blur-sm" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
      <div className="flex items-center gap-2 mb-3">
        <Zap className="w-4 h-4 text-green-400" />
        <span className="text-xs font-display font-bold uppercase tracking-wider text-gray-300">DRS Status</span>
        <span className="text-[9px] font-mono text-gray-500 ml-auto">{zonesTotal} ZONES</span>
      </div>
      <div className="flex items-center gap-3">
        <motion.div
          animate={{ scale: active ? [1, 1.15, 1] : 1, opacity: active ? 1 : 0.3 }}
          transition={{ repeat: active ? Infinity : 0, duration: 1.5 }}
          className="w-10 h-10 rounded-xl flex items-center justify-center border"
          style={{
            backgroundColor: active ? 'rgba(0, 210, 190, 0.15)' : 'rgba(255,255,255,0.03)',
            borderColor: active ? COLORS.accent.green : 'var(--border-color)',
          }}
        >
          <span className="text-sm font-black" style={{ color: active ? COLORS.accent.green : '#555' }}>
            {active ? 'OPEN' : 'SHUT'}
          </span>
        </motion.div>
        <div>
          <div className="text-sm font-bold" style={{ color: active ? COLORS.accent.green : 'var(--text-secondary)' }}>
            {active ? 'Flap Open' : 'Flap Closed'}
          </div>
          <div className="text-[10px] text-gray-500">
            {active ? 'Drag reduced, +12 km/h top speed' : 'Within 1s required for activation'}
          </div>
        </div>
      </div>
    </div>
  );
}

/** Sector timing breakdown with visual bars. */
function SectorTimingCard({ driverCode, sectors }: {
  driverCode: string;
  sectors: { s1: number; s2: number; s3: number; bestS1: number; bestS2: number; bestS3: number };
}) {
  const total = sectors.s1 + sectors.s2 + sectors.s3;
  const bestTotal = sectors.bestS1 + sectors.bestS2 + sectors.bestS3;
  const delta = total - bestTotal;

  const renderBar = (current: number, best: number, label: string, color: string) => {
    const isPB = current <= best * 1.001;
    const barColor = isPB ? '#A855F7' : color;
    const maxVal = Math.max(current, best) * 1.05;
    return (
      <div className="space-y-1">
        <div className="flex justify-between items-center">
          <span className="text-[10px] font-bold text-gray-500 uppercase">{label}</span>
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono font-bold" style={{ color: barColor }}>
              {(current / 1000).toFixed(2)}s
            </span>
            {isPB && <span className="text-[8px] font-black text-purple-400 bg-purple-500/20 px-1 rounded">PB</span>}
          </div>
        </div>
        <div className="h-2 rounded-full overflow-hidden" style={{ backgroundColor: 'var(--bg-secondary)' }}>
          <motion.div
            className="h-full rounded-full"
            style={{ backgroundColor: barColor }}
            initial={{ width: 0 }}
            animate={{ width: `${(current / maxVal) * 100}%` }}
            transition={{ duration: 0.8, ease: 'easeOut' }}
          />
        </div>
      </div>
    );
  };

  return (
    <div className="p-4 rounded-xl border backdrop-blur-sm" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Timer className="w-4 h-4 text-blue-400" />
          <span className="text-xs font-display font-bold uppercase tracking-wider text-gray-300">Sector Timing</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-gray-500">{driverCode}</span>
          <span className={`text-xs font-mono font-bold ${delta <= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {delta <= 0 ? '' : '+'}{(delta / 1000).toFixed(2)}s
          </span>
        </div>
      </div>
      <div className="space-y-3">
        {renderBar(sectors.s1, sectors.bestS1, 'Sector 1', COLORS.accent.red)}
        {renderBar(sectors.s2, sectors.bestS2, 'Sector 2', COLORS.accent.blue)}
        {renderBar(sectors.s3, sectors.bestS3, 'Sector 3', COLORS.accent.green)}
      </div>
      <div className="mt-3 pt-3 border-t border-white/5 flex justify-between">
        <span className="text-[10px] text-gray-500 font-bold uppercase">Lap Total</span>
        <span className="text-sm font-mono font-bold text-white">{(total / 1000).toFixed(2)}s</span>
      </div>
    </div>
  );
}

/* ── Main View ────────────────────────────────────────────────────────── */

const RaceCommandCenter: React.FC = () => {
  const { data: apiDrivers, isLive: driversLive } = useDrivers();
  const { online } = useBackendStatus();
  const { data: races } = useRaces2024();

  const { activeRaceRound, setActiveRaceRound, setSelectedDriverId: setStoreDriverId } = useAppStore();
  const [selectedRaceId, setSelectedRaceId] = useState<number | null>(activeRaceRound || null);

  // Predictive ML Metrics
  const { data: overtakeData } = useOvertakeMetric('VER', 'NOR');
  const { data: safetyCarData } = useSafetyCarProb('2024_1');

  useEffect(() => {
    if (races && races.length > 0 && selectedRaceId === null) {
      setSelectedRaceId(races[0].round);
    }
  }, [races, selectedRaceId]);

  const selectedRace = races?.find((r: any) => r.round === selectedRaceId) || races?.[0];

  const drivers: DriverProfile[] = useMemo(() => {
    if (selectedRace) {
      const raceDrivers = selectedRace.results
        .map((result: any) => {
          const apiDriver = apiDrivers?.find(d => d.driver_id === result.driver.id);
          if (apiDriver) return apiDriver;

          // no mock driver lookup — fall through to inline default below

          return {
            driver_id: result.driver.id, name: result.driver.name, team: result.constructor,
            code: result.driver.code || result.driver.id.slice(0, 3).toUpperCase(), nationality: 'Unknown',
            career_races: 50, career_wins: 0, aggression_score: 80, consistency_score: 82,
            pressure_response: 75, tire_management: 80, wet_weather_skill: 78, qualifying_pace: 85,
            race_pace: 83, overtaking_ability: 79, defensive_ability: 81, fuel_efficiency: 80,
            experience_years: 3, rookie_status: false,
          } as DriverProfile;
        });
      return raceDrivers.slice(0, 20);
    }
    return [];
  }, [selectedRace, apiDrivers]);

  const [selectedDriverId, setSelectedDriverId] = useState('');
  const [showBeginnerTips, setShowBeginnerTips] = useState(false);
  const [mobileTowerOpen, setMobileTowerOpen] = useState(false);
  const [raceState, setRaceState] = useState<RaceState>(DEFAULT_RACE_STATE);
  const [telemetries, setTelemetries] = useState<DriverTelemetry[]>([]);

  useEffect(() => {
    if (drivers.length > 0 && !selectedDriverId) setSelectedDriverId(drivers[0].driver_id);
  }, [drivers, selectedDriverId]);

  useEffect(() => {
    setTelemetries(drivers.map((d, i) => getMockTelemetry(d.driver_id, i + 1)));
  }, [drivers]);

  useEffect(() => {
    if (!online) return;
    fetchRaceState('2024_1', 23)
      .then(({ raceState: rs }) => setRaceState(prev => ({ ...prev, ...rs })))
      .catch(() => {});
  }, [online]);

  useEffect(() => {
    const interval = setInterval(() => {
      setTelemetries(prev => prev.map(t => ({
        ...t,
        ers_deployment: Math.max(0, Math.min(100, t.ers_deployment + (Math.random() * 2 - 1))),
      })));
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  // Sync selections to global store so other views preserve context
  useEffect(() => {
    if (selectedRaceId) setActiveRaceRound(selectedRaceId);
  }, [selectedRaceId, setActiveRaceRound]);

  useEffect(() => {
    if (selectedDriverId) setStoreDriverId(selectedDriverId);
  }, [selectedDriverId, setStoreDriverId]);

  const selectedDriver = drivers.find(d => d.driver_id === selectedDriverId) || drivers[0];
  const selectedTelemetry = telemetries.find(t => t.driver_id === selectedDriverId) || telemetries[0];
  const selectedStrategy = getMockStrategy(selectedDriverId);

  // Deterministic sector times based on selected driver
  const sectorData = useMemo(() => {
    const seed = selectedDriverId.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
    const base1 = 24100 + (seed % 500);
    const base2 = 28300 + ((seed * 7) % 600);
    const base3 = 22100 + ((seed * 13) % 400);
    return {
      s1: base1 + Math.floor((seed * 3) % 200), s2: base2 + Math.floor((seed * 11) % 300),
      s3: base3 + Math.floor((seed * 5) % 150),
      bestS1: base1, bestS2: base2, bestS3: base3,
    };
  }, [selectedDriverId]);

  // DRS zone count based on circuit (fallback to 3)
  const drsZones = useMemo(() => {
    const circuitDRS: Record<string, number> = {
      'albert_park': 4, 'jeddah': 3, 'bahrain': 3, 'shanghai': 2, 'miami': 3,
      'imola': 2, 'monaco': 0, 'barcelona': 2, 'villeneuve': 3, 'silverstone': 2,
      'hungaroring': 1, 'spa': 2, 'zandvoort': 1, 'monza': 2, 'marina_bay': 2,
      'suzuka': 1, 'lusail': 2, 'americas': 2, 'interlagos': 2, 'las_vegas': 2,
      'yas_marina': 2,
    };
    const id = selectedRace?.circuit?.id || '';
    return circuitDRS[id] || 3;
  }, [selectedRace]);

  const lapTimeData = useMemo(() => Array.from({ length: 15 }, (_, i) => {
    const lap = i + 8;
    const seed = (lap * 13) + (selectedDriverId.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0));
    const deterministicRandom = ((seed * 9301 + 49297) % 233280) / 233280;
    return { lap, time: 74.2 + deterministicRandom * 0.4, benchmark: 74.1 };
  }), [selectedDriverId]);

  if (!selectedDriver || !selectedTelemetry) return null;

  return (
    <div className="flex h-full overflow-hidden relative">
      <div className="hidden lg:block w-72 shrink-0 h-full border-r border-white/5 transition-colors duration-300 z-10">
        <PositionTower
          telemetry={telemetries}
          drivers={drivers}
          selectedDriverId={selectedDriverId}
          onSelectDriver={setSelectedDriverId}
        />
      </div>

      <AnimatePresence>
        {mobileTowerOpen && (
           <>
             <motion.div 
               initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
               className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[80] lg:hidden"
               onClick={() => setMobileTowerOpen(false)}
             />
             <motion.div 
               initial={{ x: '-100%' }} animate={{ x: 0 }} exit={{ x: '-100%' }} transition={{ type: 'spring', damping: 25, stiffness: 200 }}
               className="fixed top-0 left-0 bottom-0 w-[85vw] max-w-sm bg-[#0A0A0A] z-[90] lg:hidden border-r shadow-2xl"
               style={{ borderColor: 'var(--border-color)' }}
             >
                <div className="h-14 flex items-center justify-between px-4 border-b" style={{ borderColor: 'var(--border-color)' }}>
                  <span className="font-display font-black uppercase text-sm tracking-widest text-white/40">Live Grid</span>
                  <button onClick={() => setMobileTowerOpen(false)} className="p-2 hover:bg-white/5 rounded-lg transition-colors">
                    <X className="w-5 h-5 text-white/40" />
                  </button>
                </div>
                <div className="h-[calc(100%-56px)] overflow-hidden">
                  <PositionTower
                    telemetry={telemetries}
                    drivers={drivers}
                    selectedDriverId={selectedDriverId}
                    onSelectDriver={(id) => { setSelectedDriverId(id); setMobileTowerOpen(false); }}
                  />
                </div>
             </motion.div>
           </>
        )}
      </AnimatePresence>

      <div className="flex-1 p-4 md:p-6 overflow-y-auto flex flex-col gap-4 md:gap-5">
        {/* ── Header ─────────────────────────────────────────────────── */}
        <div className="flex justify-between items-end border-b pb-4 shrink-0" style={{ borderColor: 'var(--border-color)' }}>
          <div className="min-w-0 pr-4">
            <div className="flex items-center gap-3 md:gap-4 flex-wrap">
              <button
                 onClick={() => setMobileTowerOpen(true)}
                 className="lg:hidden p-2 rounded-xl border bg-white/5 hover:bg-white/10 transition-colors"
                 style={{ borderColor: 'var(--border-color)' }}
              >
                <Menu className="w-4 h-4 text-white/60" />
              </button>
              <h1 className="text-2xl sm:text-3xl lg:text-4xl font-display font-bold tracking-tight uppercase italic truncate">
                {selectedRace ? selectedRace.name : raceState.circuit}
              </h1>
              <LiveBadge isLive={online} />
              <select
                value={selectedRaceId || ''}
                onChange={e => setSelectedRaceId(Number(e.target.value))}
                className="px-3 py-1.5 rounded-xl border text-sm font-bold bg-transparent focus:outline-none cursor-pointer"
                style={{ borderColor: 'var(--border-color)', color: 'var(--text-primary)', backgroundColor: 'var(--card-bg)' }}
              >
                {races?.map((r: any) => (
                  <option key={r.round} value={r.round}>R{r.round} - {r.name}</option>
                ))}
              </select>
            </div>
            <div className="flex gap-4 sm:gap-6 mt-3 flex-wrap">
              <Badge label="LAP" value={`${raceState.current_lap} / ${raceState.total_laps}`} />
              <Badge label="TRACK" value={`${raceState.track_temp_celsius}°C`} color={COLORS.accent.yellow} />
              <Badge label="GRIP" value={`${raceState.track_grip_level}%`} color={COLORS.accent.blue} />
              <Badge label="FLAG" value={raceState.flag} color={raceState.flag === 'GREEN' ? COLORS.accent.green : COLORS.accent.yellow} pulse />
            </div>
          </div>
          <div className="flex flex-col items-end gap-2 shrink-0">
            <button
              onClick={() => setShowBeginnerTips(!showBeginnerTips)}
              className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-accent-blue/10 border border-accent-blue/20 text-accent-blue text-[10px] font-bold uppercase hover:bg-accent-blue/20 transition-colors"
            >
              <HelpCircle className="w-3 h-3" />
              {showBeginnerTips ? 'Hide Tips' : 'Beginner Tips'}
            </button>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-widest">Global Telemetry Hub</div>
            <div className="text-2xl font-mono font-bold">01:14:23</div>
          </div>
        </div>

        {/* ── Predictive Intelligence + DRS + Sectors ────────────────── */}
        {/* 2-col on mobile/tablet: gauges side by side; 4-col on desktop */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 shrink-0">
          <ProbGauge
            value={safetyCarData?.probability || 0.08}
            label="Safety Car Risk"
            icon={Shield}
            color={safetyCarData && safetyCarData.probability > 0.3 ? COLORS.accent.red : COLORS.accent.yellow}
            subtitle={`Model v${safetyCarData?.model_version || '1.2.0'} · updates every 30s`}
          />
          <ProbGauge
            value={overtakeData?.probability || 0.12}
            label="Overtake Prob."
            icon={Radio}
            color={COLORS.accent.green}
            subtitle={`${selectedDriver.code ?? selectedDriver.name.split(' ')[0]} vs NOR`}
          />
          <DRSCard active={selectedTelemetry.drs_active} zonesTotal={drsZones} />
          <SectorTimingCard driverCode={selectedDriver.code ?? selectedDriver.name.split(' ')[0]} sectors={sectorData} />
        </div>

        {/* ── Main Grid: Driver Card (left) + Charts (right) ──────────── */}
        {/*
          Desktop (lg+): 3-col grid — driver card takes 1 col, charts take 2 cols.
          Tablet (md):   2-col — driver card left, chart right stacked.
          Mobile:        single column stack.
        */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Driver Card — always full width on mobile, 1 col on tablet+ */}
          <div className="md:col-span-1">
            <DriverCard telemetry={selectedTelemetry} driver={selectedDriver} strategy={selectedStrategy} />
          </div>

          {/* Charts — 2 cols on tablet+, stacked on mobile */}
          <div className="md:col-span-2 flex flex-col gap-4">

            {/* Lap Time Trace — fixed height to avoid needing scroll */}
            <div
              className="rounded-xl p-4 border shadow-xl flex flex-col"
              style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}
            >
              <div className="flex justify-between items-center mb-3 shrink-0">
                <h3 className="text-xs font-display font-bold uppercase tracking-widest text-gray-400">
                  Lap Time Trace
                </h3>
                <div className="flex gap-3">
                  <LegendItem
                    color={COLORS.accent.red}
                    label={selectedDriver.code ?? selectedDriver.name.split(' ')[0]}
                  />
                  <LegendItem color="#555" label="Benchmark" />
                </div>
              </div>
              {/* Chart at fixed 200px height — no min-h that forces scroll */}
              <div className="w-full" style={{ height: 200 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={lapTimeData} margin={{ top: 4, right: 4, left: -16, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorTime" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={COLORS.accent.red} stopOpacity={0.2} />
                        <stop offset="95%" stopColor={COLORS.accent.red} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" vertical={false} />
                    <XAxis
                      dataKey="lap"
                      stroke="var(--text-secondary)"
                      fontSize={9}
                      tick={{ fill: 'var(--text-secondary)' }}
                      tickLine={false}
                    />
                    <YAxis
                      domain={['auto', 'auto']}
                      stroke="var(--text-secondary)"
                      fontSize={9}
                      tick={{ fill: 'var(--text-secondary)' }}
                      tickLine={false}
                      width={36}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'var(--bg-secondary)',
                        border: '1px solid var(--border-color)',
                        fontSize: '11px',
                        color: 'var(--text-primary)',
                        borderRadius: 8,
                      }}
                      itemStyle={{ color: 'var(--text-primary)' }}
                      formatter={(v: number) => [`${v.toFixed(3)}s`, '']}
                    />
                    <Area
                      type="monotone"
                      dataKey="benchmark"
                      stroke="#444"
                      fill="none"
                      strokeWidth={1}
                      strokeDasharray="4 4"
                    />
                    <Area
                      type="monotone"
                      dataKey="time"
                      stroke={COLORS.accent.red}
                      fillOpacity={1}
                      fill="url(#colorTime)"
                      strokeWidth={2}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Monte Carlo Table — compact, no overflow */}
            <div
              className="rounded-xl p-4 border shadow-xl"
              style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}
            >
              <h3 className="text-xs font-display font-bold uppercase tracking-widest text-gray-400 mb-3">
                Monte Carlo Strategy Variants
              </h3>
              <div className="space-y-2">
                {[
                  { name: 'Variant-Alpha', term: 'Undercut' as const, pits: 'L28, L55', win: '18.4%', risk: 'AGGRESSIVE', riskColor: COLORS.accent.red },
                  { name: 'Variant-Gamma', term: null, pits: 'L32, L58', win: '22.1%', risk: 'BALANCED', riskColor: COLORS.accent.yellow, optimal: true },
                ].map(row => (
                  <div
                    key={row.name}
                    className="flex items-center gap-2 px-3 py-2.5 rounded-lg border"
                    style={{ borderColor: row.optimal ? `${COLORS.accent.green}40` : 'var(--border-color)', backgroundColor: row.optimal ? `${COLORS.accent.green}08` : 'var(--bg-secondary)' }}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[11px] font-bold text-white">{row.name}</span>
                        {row.optimal && <span className="text-[8px] font-black px-1 rounded bg-green-500/20 text-green-400 uppercase">Optimal</span>}
                        {row.term && (
                          <ConceptTooltip term={row.term}>
                            <span className="text-[9px] text-blue-400/60 cursor-help">(Undercut)</span>
                          </ConceptTooltip>
                        )}
                      </div>
                      <div className="text-[10px] font-mono text-gray-500 mt-0.5">Pit: {row.pits}</div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-sm font-mono font-bold text-green-400">{row.win}</div>
                      <div className="text-[9px] font-bold uppercase" style={{ color: row.riskColor }}>{row.risk}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* ── Beginner Tips Overlay ───────────────────────────────────── */}
        {showBeginnerTips && (
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            className="fixed right-6 top-24 w-80 z-40 p-5 rounded-2xl bg-white/[0.04] backdrop-blur-md border border-white/[0.07] shadow-[0_20px_50px_rgba(0,0,0,0.5)]"
          >
            <div className="flex items-center gap-2 mb-4">
              <div className="p-2 rounded-lg bg-accent-blue/20 text-accent-blue"><Info className="w-4 h-4" /></div>
              <h3 className="text-sm font-display font-bold uppercase tracking-wider">Race Day Intelligence</h3>
            </div>
            <div className="space-y-4">
              <Tip complexity="Beginner" title="Look for the Delta" description="The 'Delta' shows the real-time gap between cars. If it's decreasing, an overtake might be coming!" />
              <Tip complexity="Intermediate" title="Sector Colors" description="Purple = personal best. Green = session best. Yellow = slower than session best. Watch sector bars above!" />
              <Tip complexity="Expert" title="SC Probability Gauge" description="The Safety Car gauge uses ML to predict incidents. Above 30% means high risk; strategy windows open up." />
            </div>
            <div className="mt-6 pt-4 border-t border-white/10">
              <p className="text-[10px] text-gray-500 italic">Hover over dashed terms anywhere in the dashboard for instant definitions.</p>
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
};

function Tip({ title, description, complexity }: { title: string; description: string; complexity: 'Beginner' | 'Intermediate' | 'Expert' }) {
  const color = complexity === 'Beginner' ? '#00D2BE' : complexity === 'Intermediate' ? '#9B59B6' : '#E10600';
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <span className="text-[8px] font-black uppercase px-1 rounded text-white" style={{ backgroundColor: color }}>{complexity}</span>
        <span className="text-xs font-bold text-white">{title}</span>
      </div>
      <p className="text-[10px] text-gray-400 leading-snug">{description}</p>
    </div>
  );
}

export default RaceCommandCenter;
