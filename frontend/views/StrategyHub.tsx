/**
 * @file StrategyHub.tsx
 * @description Combined Strategy Simulator + AI Strategist view.
 *
 * Left panel  : Monte Carlo pit strategy builder (presets + custom stint builder, no dropdowns).
 * Right panel : AI chat interface wired to POST /llm/chat (FastAPI backend).
 */

import React, { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LineChart, Line,
} from 'recharts';
import { COLORS } from '../constants';
import ConceptTooltip from '../components/ConceptTooltip';
import {
  Plus, X, Play, Loader2, Trophy, Timer, TrendingUp,
  Send, User, Bot, Sparkles, Zap, Flag,
} from 'lucide-react';
import { simulateStrategy, chatWithStrategist } from '../services/endpoints';
import { useRaces2024, useDrivers } from '../hooks/useApi';
import type { TireCompound } from '../types';
import RaceSimulation from '../components/RaceSimulation';

type HubTab = 'strategy' | 'simulation';

// ── Local fallback simulation ─────────────────────────────────────────────────
// Used when the backend is unreachable. Produces results that vary meaningfully
// based on driver, track, and stint choices so the UI isn't stuck showing P3/5400s.

const _DRIVER_QUALITY: Record<string, number> = {
  max_verstappen: 0.97, hamilton: 0.95, norris: 0.93, leclerc: 0.92,
  russell: 0.89, piastri: 0.88, alonso: 0.87, sainz: 0.86, perez: 0.85,
  antonelli: 0.87, lawson: 0.83, gasly: 0.81, ricciardo: 0.80, hadjar: 0.80,
  albon: 0.79, doohan: 0.79, colapinto: 0.79, tsunoda: 0.78, bortoleto: 0.79,
  bearman: 0.77, hulkenberg: 0.76, ocon: 0.76, stroll: 0.74, bottas: 0.74,
  magnussen: 0.72, zhou: 0.71, sargeant: 0.64,
};

const _COMPOUND_PACE: Record<string, number> = {
  SOFT: -0.40, MEDIUM: 0.0, HARD: 0.30, INTERMEDIATE: 2.5, WET: 5.0,
};
const _COMPOUND_DEG: Record<string, number> = {
  SOFT: 0.095, MEDIUM: 0.050, HARD: 0.026, INTERMEDIATE: 0.08, WET: 0.06,
};

function localSimulate({
  driver_id,
  race_id,
  stints,
  numPitStops,
}: {
  driver_id: string;
  race_id: string;
  stints: Array<{ comp: string; laps: number }>;
  numPitStops: number;
}): SimResult {
  const dSeed = driver_id.split('').reduce((a, c, i) => (a + c.charCodeAt(0) * (i + 1)) | 0, 0);
  const tSeed = race_id.split('').reduce((a, c, i) => (a + c.charCodeAt(0) * (i + 1)) | 0, 0);

  const quality = _DRIVER_QUALITY[driver_id] ?? Math.min(0.90, 0.65 + (Math.abs(dSeed) % 25) / 100);
  const BASE_LAP = 75 + (Math.abs(tSeed) % 38); // 75–113s depending on track

  const lap_times_s: number[] = [];
  for (const stint of stints) {
    for (let tireAge = 0; tireAge < stint.laps && lap_times_s.length < TOTAL_LAPS; tireAge++) {
      const lap   = lap_times_s.length + 1;
      const pace  = _COMPOUND_PACE[stint.comp] ?? 0;
      const deg   = (_COMPOUND_DEG[stint.comp] ?? 0.05) * tireAge;
      const drv   = (1 - quality) * 2.2;
      const noise = ((lap * Math.abs(dSeed) * 13 + Math.abs(tSeed) * 7) % 200 - 100) / 2000;
      lap_times_s.push(+(BASE_LAP + pace + deg + drv + noise).toFixed(3));
    }
  }
  while (lap_times_s.length < TOTAL_LAPS) {
    lap_times_s.push(+(lap_times_s[lap_times_s.length - 1]! + 0.04).toFixed(3));
  }

  const predicted_total_time_s = Math.round(
    lap_times_s.reduce((a, b) => a + b, 0) + numPitStops * 22,
  );

  // Strategy efficiency: reward compounds used appropriately
  const stratBonus = stints.reduce((b, s) => {
    if (s.comp === 'SOFT' && s.laps <= 20) return b + 0.02;
    if (s.comp === 'HARD' && s.laps >= 25) return b + 0.01;
    return b;
  }, 0);

  const posBase = Math.max(1, Math.round((1 - quality - stratBonus) * 22) + 1);
  const posVariance = (Math.abs(tSeed + dSeed * 3) % 5) - 2; // -2 to +2
  const predicted_final_position = Math.max(1, Math.min(20, posBase + posVariance));

  const winProb    = Math.max(0.005, ((21 - predicted_final_position) / 20) * quality * 0.32);
  const podiumProb = Math.min(0.95, Math.max(winProb + 0.01, ((21 - predicted_final_position) / 20) * quality * 0.60));

  const strategyOut: [number, string][] = stints.map((s, i) => {
    let endLap = 0;
    for (let j = 0; j <= i; j++) endLap += stints[j].laps;
    return [Math.min(endLap, TOTAL_LAPS), s.comp];
  });

  return {
    predicted_final_position,
    predicted_total_time_s,
    lap_times_s,
    win_probability:    +winProb.toFixed(4),
    podium_probability: +podiumProb.toFixed(4),
    strategy: strategyOut,
  };
}

// ── Strategy constants ────────────────────────────────────────────────────────

const STRATEGY_PRESETS = [
  { name: 'Optimal 2-Stop', win_prob: 0.22, podium_prob: 0.45, risk: 'Low',  stints: [{ comp: 'MEDIUM', laps: 32 }, { comp: 'HARD', laps: 28 }, { comp: 'SOFT', laps: 18 }] },
  { name: 'Aggressive Undercut', win_prob: 0.18, podium_prob: 0.38, risk: 'High', stints: [{ comp: 'MEDIUM', laps: 28 }, { comp: 'HARD', laps: 30 }, { comp: 'SOFT', laps: 20 }] },
  { name: 'Conserve 1-Stop', win_prob: 0.04, podium_prob: 0.12, risk: 'Low',  stints: [{ comp: 'MEDIUM', laps: 45 }, { comp: 'HARD', laps: 33 }] },
];

const COMPOUNDS: TireCompound[] = ['SOFT', 'MEDIUM', 'HARD', 'INTERMEDIATE', 'WET'];
const TOTAL_LAPS = 57;

// ── Types ─────────────────────────────────────────────────────────────────────

interface Stint {
  pitLap: number;
  compound: TireCompound;
}

interface SimResult {
  predicted_final_position: number;
  predicted_total_time_s: number;
  lap_times_s: number[];
  win_probability: number;
  podium_probability: number;
  strategy: [number, string][];
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  model?: string;
  cache_hit?: boolean;
  latency_ms?: number;
}

// ── Main component ─────────────────────────────────────────────────────────────

const StrategyHub: React.FC = () => {
  // ── Tab state ───────────────────────────────────────────────────────────────
  const [hubTab, setHubTab] = useState<HubTab>('strategy');

  const { data: races2024 } = useRaces2024();
  const { data: apiDrivers } = useDrivers();

  const DRIVERS_LIST = useMemo(() => {
    if (!apiDrivers || apiDrivers.length === 0) {
      return [{ id: 'max_verstappen', name: 'Max Verstappen' }];
    }
    return apiDrivers.map((d: any) => ({
      id: d.driver_id,
      name: d.name || d.driver_id.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase()),
    }));
  }, [apiDrivers]);

  const TRACKS_LIST = useMemo(() => {
    if (!races2024 || races2024.length === 0) {
      return [{ id: '2024_1', name: 'Bahrain Grand Prix' }];
    }
    return races2024.map((r: any) => ({
      id: `2024_${r.round}`,
      name: r.name || `Round ${r.round}`,
    }));
  }, [races2024]);

  // ── Strategy state ──────────────────────────────────────────────────────────
  const [selectedPreset, setSelectedPreset] = useState(STRATEGY_PRESETS[0]);
  const [mode, setMode] = useState<'preset' | 'custom'>('preset');
  const [customStints, setCustomStints] = useState<Stint[]>([
    { pitLap: 20, compound: 'MEDIUM' },
    { pitLap: 42, compound: 'HARD' },
  ]);
  /** Selected driver */
  const [selectedDriverId, setSelectedDriverId] = useState('');
  /** Starting tire compound - applied at race start before the first pit stop. */
  const [startingTire, setStartingTire] = useState<TireCompound>('MEDIUM');
  /** Selected race for the simulation context. */
  const [selectedTrackId, setSelectedTrackId] = useState('');
  const [simResult, setSimResult] = useState<SimResult | null>(null);
  const [simLoading, setSimLoading] = useState(false);

  // ── Chat state ──────────────────────────────────────────────────────────────
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      content: 'I am the DivergeX AI Strategist, powered by the F1 backend. Ask me anything about tire management, undercut opportunities, pit windows, or Grand Prix strategy.',
    },
  ]);
  const [chatLoading, setChatLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    console.debug('[StrategyHub] Component mounted');
    return () => console.debug('[StrategyHub] Component unmounted');
  }, []);

  useEffect(() => {
    if (DRIVERS_LIST.length > 0 && !selectedDriverId) {
      setSelectedDriverId(DRIVERS_LIST[0].id);
    }
  }, [DRIVERS_LIST, selectedDriverId]);

  useEffect(() => {
    if (TRACKS_LIST.length > 0 && !selectedTrackId) {
      setSelectedTrackId(TRACKS_LIST[0].id);
    }
  }, [TRACKS_LIST, selectedTrackId]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [chatMessages]);

  // ── Strategy helpers ────────────────────────────────────────────────────────

  const strategyArray: [number, string][] = useMemo(() => {
    if (mode === 'preset') {
      let lap = 0;
      return selectedPreset.stints.map((s, i) => {
        // First stint uses the user-selected starting tire, not the preset default
        const comp = i === 0 ? startingTire : s.comp;
        lap += s.laps;
        return [lap, comp] as [number, string];
      });
    }
    return customStints.map(s => [s.pitLap, s.compound] as [number, string]);
  }, [mode, selectedPreset, customStints, startingTire]);

  const monteCarloData = useMemo(() => {
    if (simResult?.predicted_final_position) {
      const peak = simResult.predicted_final_position;
      return Array.from({ length: 10 }, (_, i) => {
        const pos = i + 1;
        const dist = Math.abs(pos - peak);
        return { pos, prob: Math.max(2, Math.round(30 * Math.exp(-0.5 * dist * dist))) };
      });
    }
    const wp = mode === 'preset' ? selectedPreset.win_prob : 0.15;
    return [
      { pos: 1, prob: Math.round(wp * 100) }, { pos: 2, prob: Math.round(wp * 80) },
      { pos: 3, prob: Math.round(wp * 60) }, { pos: 4, prob: 12 }, { pos: 5, prob: 10 },
      { pos: 6, prob: 8 }, { pos: 7, prob: 6 }, { pos: 8, prob: 4 }, { pos: 9, prob: 3 }, { pos: 10, prob: 2 },
    ];
  }, [simResult, mode, selectedPreset]);

  const displayStints = mode === 'preset'
    ? selectedPreset.stints.map((s, i) => i === 0 ? { ...s, comp: startingTire } : s)
    : (() => {
        const stints: { comp: string; laps: number }[] = [];
        let prevLap = 0;
        for (const s of customStints) {
          stints.push({ comp: s.compound, laps: s.pitLap - prevLap });
          prevLap = s.pitLap;
        }
        if (prevLap < TOTAL_LAPS) {
          stints.push({ comp: customStints[customStints.length - 1]?.compound || 'HARD', laps: TOTAL_LAPS - prevLap });
        }
        return stints;
      })();

  const currentWinProb   = simResult ? simResult.win_probability   : (mode === 'preset' ? selectedPreset.win_prob   : 0.15);
  const currentPodiumProb = simResult ? simResult.podium_probability : (mode === 'preset' ? selectedPreset.podium_prob : 0.35);

  /**
   * Runs the Monte Carlo pit strategy simulation via the backend API.
   * Falls back to a local approximation if the backend is unreachable.
   * Uses the selected driver, track, and starting tire from UI state.
   */
  const runSimulation = useCallback(async () => {
    setSimLoading(true);
    setSimResult(null);
    try {
      const result = await simulateStrategy({
        race_id: selectedTrackId,
        driver_id: selectedDriverId,
        strategy: strategyArray,
      });
      setSimResult(result);
    } catch {
      // Local fallback when backend is unavailable — results vary by driver, track, and strategy
      const fallbackStints: Array<{ comp: string; laps: number }> = mode === 'preset'
        ? selectedPreset.stints.map((s, i) => ({ comp: i === 0 ? startingTire : s.comp, laps: s.laps }))
        : (() => {
            const result: Array<{ comp: string; laps: number }> = [];
            let prev = 0;
            for (const s of customStints) {
              result.push({ comp: s.compound, laps: s.pitLap - prev });
              prev = s.pitLap;
            }
            if (prev < TOTAL_LAPS) {
              result.push({ comp: customStints[customStints.length - 1]?.compound || 'HARD', laps: TOTAL_LAPS - prev });
            }
            return result;
          })();

      setSimResult(localSimulate({
        driver_id: selectedDriverId,
        race_id: selectedTrackId,
        stints: fallbackStints,
        numPitStops: fallbackStints.length - 1,
      }));
    } finally {
      setSimLoading(false);
    }
  }, [strategyArray, selectedDriverId, selectedTrackId, mode, selectedPreset, customStints, startingTire]);

  const addStint = () => {
    const lastLap = customStints.length > 0 ? customStints[customStints.length - 1].pitLap + 15 : 20;
    setCustomStints([...customStints, { pitLap: Math.min(lastLap, TOTAL_LAPS - 5), compound: 'HARD' }]);
  };
  const removeStint = (idx: number) => {
    if (customStints.length <= 1) return;
    setCustomStints(customStints.filter((_, i) => i !== idx));
  };
  const updateStint = (idx: number, field: keyof Stint, value: any) =>
    setCustomStints(customStints.map((s, i) => (i === idx ? { ...s, [field]: value } : s)));

  // ── Chat handler ────────────────────────────────────────────────────────────

  const handleChat = async () => {
    const question = chatInput.trim();
    if (!question || chatLoading) return;
    setChatInput('');
    setChatMessages(prev => [...prev, { role: 'user', content: question }]);
    setChatLoading(true);
    try {
      const history = chatMessages.slice(1).map(m => ({ role: m.role, content: m.content }));
      const res = await chatWithStrategist(question, history, {
        circuit: selectedTrackId,
        driver: selectedDriverId,
        tire_compound: startingTire,
      });
      setChatMessages(prev => [
        ...prev,
        { role: 'assistant', content: res.answer, model: res.model, cache_hit: res.cache_hit, latency_ms: res.latency_ms },
      ]);
    } catch (err) {
      setChatMessages(prev => [
        ...prev,
        { role: 'assistant', content: 'Unable to reach the AI Strategist. The backend may be starting up: please try again in a moment. In demo mode, the pit strategy simulator on the left is fully available.' },
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="p-6 md:p-8 max-w-[1600px] mx-auto space-y-6 h-full flex flex-col">
      {/* Header */}
      <div className="flex flex-col gap-4">
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
          <div>
            <h1 className="text-4xl font-display font-bold tracking-tight uppercase italic">Strategy Hub</h1>
            <p className="text-[10px] uppercase tracking-[4px] text-white/40 mt-2 font-mono flex items-center gap-2">
              <Sparkles className="w-3 h-3 text-blue-400" />
              Monte Carlo Simulation · AI Strategist
            </p>
          </div>
          {/* Tab switcher */}
          <div className="flex rounded-xl overflow-hidden border" style={{ borderColor: 'var(--border-color)' }}>
            <button
              onClick={() => setHubTab('strategy')}
              className={`flex items-center gap-1.5 px-4 py-2 text-xs font-bold uppercase transition-colors ${hubTab === 'strategy' ? 'bg-red-600 text-white' : 'text-white/40 hover:text-white'}`}
            >
              <Zap className="w-3 h-3" /> Strategy
            </button>
            <button
              onClick={() => setHubTab('simulation')}
              className={`flex items-center gap-1.5 px-4 py-2 text-xs font-bold uppercase transition-colors ${hubTab === 'simulation' ? 'bg-red-600 text-white' : 'text-white/40 hover:text-white'}`}
            >
              <Flag className="w-3 h-3" /> Race Sim
            </button>
          </div>
        </div>
        {/* Strategy controls row | driver, track, starting tire */}
        {hubTab === 'strategy' && (
          <div className="flex flex-wrap gap-3 items-end p-4 rounded-2xl border" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
            {/* Driver dropdown */}
            <div className="flex flex-col gap-1">
              <span className="text-[9px] font-mono text-white/40 uppercase tracking-widest">Driver</span>
              <select
                value={selectedDriverId}
                onChange={e => { setSelectedDriverId(e.target.value); setSimResult(null); }}
                className="px-3 py-2 rounded-xl border text-sm font-bold focus:outline-none focus:ring-1 focus:ring-red-600 cursor-pointer min-w-[200px]"
                style={{ borderColor: 'var(--border-color)', color: 'var(--text-primary)', backgroundColor: 'var(--card-bg)' }}
              >
                {DRIVERS_LIST.map(d => (
                  <option key={d.id} value={d.id}>{d.name}</option>
                ))}
              </select>
            </div>
            {/* Track dropdown */}
            <div className="flex flex-col gap-1">
              <span className="text-[9px] font-mono text-white/40 uppercase tracking-widest">Circuit</span>
              <select
                value={selectedTrackId}
                onChange={e => { setSelectedTrackId(e.target.value); setSimResult(null); }}
                className="px-3 py-2 rounded-xl border text-sm font-bold focus:outline-none focus:ring-1 focus:ring-red-600 cursor-pointer min-w-[240px]"
                style={{ borderColor: 'var(--border-color)', color: 'var(--text-primary)', backgroundColor: 'var(--card-bg)' }}
              >
                {TRACKS_LIST.map(t => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </div>
            {/* Starting tire selector */}
            <div className="flex flex-col gap-1">
              <span className="text-[9px] font-mono text-white/40 uppercase tracking-widest">Starting Tire</span>
              <div className="flex gap-1">
                {(['SOFT', 'MEDIUM', 'HARD'] as TireCompound[]).map(c => (
                  <button
                    key={c}
                    onClick={() => { setStartingTire(c); setSimResult(null); }}
                    className={`px-3 py-2 rounded-xl text-xs font-black uppercase transition-all border ${
                      startingTire === c ? 'text-black shadow-lg scale-105' : 'text-white/50 hover:text-white'
                    }`}
                    style={{
                      backgroundColor: startingTire === c ? (COLORS.tires as any)[c] : 'transparent',
                      borderColor: (COLORS.tires as any)[c],
                    }}
                    title={`Start on ${c} tyres`}
                  >
                    {c.slice(0, 3)}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Race Simulation tab */}
      {hubTab === 'simulation' && (
        <div className="flex-1 grid grid-cols-1 xl:grid-cols-12 gap-6 min-h-0">
          <div className="xl:col-span-7 flex flex-col gap-6 min-h-0 overflow-y-auto scrollbar-hide">
            <RaceSimulation />
          </div>
          <div className="xl:col-span-5 flex flex-col gap-6 min-h-0">
            <div className="rounded-2xl border p-5 text-center space-y-3" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
              <Flag className="w-8 h-8 mx-auto text-red-600" />
              <p className="text-sm font-display font-bold uppercase tracking-wide text-white/60">RL Race Simulation</p>
              <p className="text-[10px] font-mono text-white/30 leading-relaxed">
                Configure your driver and circuit, then race against 19 AI competitors.
                The PPO RL agent pauses at key strategic moments - Safety Cars, tire cliff,
                undercut windows - and asks whether to follow its recommendation or override.
                Use the AI chat for real-time strategy advice during the race.
              </p>
              <div className="grid grid-cols-2 gap-2 text-left pt-2">
                {[
                  { label: 'RL Engine', value: 'PPO Agent' },
                  { label: 'Rivals', value: '19 AI drivers' },
                  { label: 'Decisions', value: 'Up to 7 prompts' },
                  { label: 'Fallback', value: 'Heuristic rules' },
                ].map(({ label, value }) => (
                  <div key={label} className="rounded-lg px-3 py-2" style={{ backgroundColor: 'var(--bg-secondary)' }}>
                    <p className="text-[8px] font-mono text-white/30 uppercase">{label}</p>
                    <p className="text-xs font-bold text-white/70">{value}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Two-column layout | Strategy tab */}
      {hubTab === 'strategy' && <div className="flex-1 grid grid-cols-1 xl:grid-cols-12 gap-6 min-h-0">

        {/* ── Left: Strategy Simulator ─────────────────────────────────────── */}
        <div className="xl:col-span-7 flex flex-col gap-6 min-h-0">

          {/* Sim result cards */}
          <AnimatePresence>
            {simResult && (
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="space-y-2"
              >
                {/* Driver + track label above cards */}
                <p className="text-[10px] font-mono text-white/40 uppercase tracking-widest">
                  Simulating: <span className="text-white font-bold">{DRIVERS_LIST.find(d => d.id === selectedDriverId)?.name ?? selectedDriverId}</span>
                  <span className="text-white/30"> &middot; </span>
                  <span className="text-white/70">{TRACKS_LIST.find(t => t.id === selectedTrackId)?.name ?? selectedTrackId}</span>
                  <span className="text-white/30"> &middot; </span>
                  Starting on <span style={{ color: (COLORS.tires as any)[startingTire] }}>{startingTire}</span>
                </p>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <ResultCard icon={Trophy}     label="Predicted Finish" value={`P${simResult.predicted_final_position}`}               color={simResult.predicted_final_position <= 3 ? COLORS.accent.green : COLORS.accent.yellow} />
                  <ResultCard icon={Timer}      label="Race Time"         value={formatTime(simResult.predicted_total_time_s)}           color={COLORS.accent.blue} />
                  <ResultCard icon={TrendingUp} label="Win Probability"   value={`${(simResult.win_probability * 100).toFixed(2)}%`}     color={COLORS.accent.green} />
                  <ResultCard icon={TrendingUp} label="Podium Prob"       value={`${(simResult.podium_probability * 100).toFixed(2)}%`}  color={COLORS.accent.purple} />
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Strategy builder card */}
          <div className="rounded-2xl p-6 border shadow-xl space-y-5 flex-1" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>

            {/* Header row */}
            <div className="flex items-center justify-between flex-wrap gap-3">
              <ConceptTooltip term="Stint">
                <h3 className="text-sm font-display font-bold uppercase tracking-widest text-white/40">Strategy Stints</h3>
              </ConceptTooltip>
              <div className="flex items-center gap-3">
                {/* Mode toggle */}
                <div className="flex rounded-xl overflow-hidden border" style={{ borderColor: 'var(--border-color)' }}>
                  <button onClick={() => setMode('preset')} className={`px-4 py-2 text-xs font-bold uppercase transition-colors ${mode === 'preset' ? 'bg-red-600 text-white' : 'text-white/40 hover:text-white'}`}>Presets</button>
                  <button onClick={() => setMode('custom')} className={`px-4 py-2 text-xs font-bold uppercase transition-colors ${mode === 'custom' ? 'bg-red-600 text-white' : 'text-white/40 hover:text-white'}`}>Custom</button>
                </div>
                {/* Run button */}
                <button
                  onClick={runSimulation}
                  disabled={simLoading}
                  className="flex items-center gap-2 px-4 py-2 rounded-xl bg-red-600 text-white font-bold text-sm hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-lg shadow-red-900/20"
                >
                  {simLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                  {simLoading ? 'Running...' : 'Simulate'}
                </button>
              </div>
            </div>

            {/* Stint visual bar */}
            <div className="relative h-16 rounded-xl overflow-hidden flex" style={{ backgroundColor: 'var(--bg-secondary)' }}>
              {displayStints.map((stint, i) => (
                <motion.div
                  key={i}
                  initial={{ width: 0 }}
                  animate={{ width: `${(stint.laps / TOTAL_LAPS) * 100}%` }}
                  className="h-full border-r border-black/20 relative group"
                  style={{ backgroundColor: (COLORS.tires as any)[stint.comp] }}
                >
                  <div className="absolute inset-0 bg-black/10 group-hover:bg-transparent transition-colors" />
                  <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="text-[9px] font-black text-black leading-none">{stint.comp.slice(0, 1)}</span>
                    <span className="text-xs font-mono font-bold text-black">{stint.laps}L</span>
                  </div>
                </motion.div>
              ))}
            </div>

            {/* Presets or custom builder */}
            {mode === 'preset' ? (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {STRATEGY_PRESETS.map(s => (
                  <div
                    key={s.name}
                    onClick={() => { setSelectedPreset(s); setSimResult(null); }}
                    className="p-4 rounded-xl border cursor-pointer transition-all"
                    style={{
                      backgroundColor: selectedPreset.name === s.name ? 'transparent' : 'var(--bg-secondary)',
                      borderColor: selectedPreset.name === s.name ? '#E10600' : 'var(--border-color)',
                    }}
                  >
                    <div className="text-xs font-bold uppercase tracking-tighter mb-1">{s.name}</div>
                    <div className="text-xl font-display font-bold" style={{ color: 'var(--text-primary)' }}>{(s.win_prob * 100).toFixed(2)}% <span className="text-[10px] font-mono text-gray-500">WIN</span></div>
                    <div className={`text-[10px] font-bold mt-2 uppercase ${s.risk === 'High' ? 'text-red-500' : 'text-green-500'}`}>{s.risk} Risk</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="space-y-3">
                {customStints.map((stint, idx) => (
                  <div key={idx} className="flex items-center gap-3 p-3 rounded-xl border flex-wrap" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}>
                    <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: (COLORS.tires as any)[stint.compound] }} />
                    <span className="text-xs font-bold text-white/40 uppercase w-12 flex-shrink-0">Stop {idx + 1}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] text-white/40">Lap</span>
                      <input
                        type="number" min={1} max={TOTAL_LAPS}
                        value={stint.pitLap}
                        onChange={e => updateStint(idx, 'pitLap', parseInt(e.target.value) || 1)}
                        className="w-14 px-2 py-1 rounded-lg border text-sm font-mono bg-transparent text-center"
                        style={{ borderColor: 'var(--border-color)', color: 'var(--text-primary)' }}
                      />
                    </div>
                    {/* Compound pill buttons | no dropdown */}
                    <div className="flex gap-1 flex-wrap">
                      {COMPOUNDS.map(c => (
                        <button
                          key={c}
                          onClick={() => updateStint(idx, 'compound', c)}
                          className={`px-2 py-0.5 rounded text-[9px] font-black uppercase transition-colors ${stint.compound === c ? 'text-black shadow' : 'text-white/40 hover:text-white'}`}
                          style={{ backgroundColor: stint.compound === c ? (COLORS.tires as any)[c] : 'transparent', border: `1px solid ${(COLORS.tires as any)[c]}` }}
                        >
                          {c.slice(0, 3)}
                        </button>
                      ))}
                    </div>
                    <button onClick={() => removeStint(idx)} className="ml-auto p-1.5 rounded-lg hover:bg-red-600/20 text-gray-500 hover:text-red-400 transition-colors">
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ))}
                <button
                  onClick={addStint}
                  className="w-full py-3 rounded-xl border-2 border-dashed text-sm font-bold text-white/40 hover:text-white hover:border-red-600/50 transition-colors flex items-center justify-center gap-2"
                  style={{ borderColor: 'var(--border-color)' }}
                >
                  <Plus className="w-4 h-4" /> Add Pit Stop
                </button>
              </div>
            )}

            {/* Lap time trace */}
            {simResult && simResult.lap_times_s.length > 0 && (
              <div className="pt-4 border-t" style={{ borderColor: 'var(--border-color)' }}>
                <h4 className="text-xs font-display font-bold uppercase tracking-widest text-white/40 mb-3">Lap Time Trace</h4>
                <div className="h-32">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={simResult.lap_times_s.map((t, i) => ({ lap: i + 1, time: t }))}>
                      <XAxis dataKey="lap" stroke="var(--text-secondary)" fontSize={9} />
                      <YAxis domain={['auto', 'auto']} stroke="var(--text-secondary)" fontSize={9} />
                      <Tooltip contentStyle={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', fontSize: '11px', color: 'var(--text-primary)' }} />
                      <Line type="monotone" dataKey="time" stroke={COLORS.accent.red} strokeWidth={1.5} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}
          </div>

          {/* Finishing distribution */}
          <div className="rounded-2xl p-5 border shadow-xl" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
            <h3 className="text-xs font-display font-bold uppercase tracking-widest text-white/40 mb-4">Finishing Probability</h3>
            <div className="h-40">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={monteCarloData}>
                  <XAxis dataKey="pos" stroke="var(--text-secondary)" fontSize={10} axisLine={false} tickLine={false} />
                  <YAxis stroke="var(--text-secondary)" fontSize={10} axisLine={false} tickLine={false} />
                  <Tooltip cursor={{ fill: 'var(--bg-secondary)' }} contentStyle={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }} formatter={(v: number) => [`${v}%`, 'Probability']} />
                  <Bar dataKey="prob" radius={[4, 4, 0, 0]}>
                    {monteCarloData.map((_, i) => <Cell key={i} fill={i < 3 ? COLORS.accent.green : COLORS.accent.blue} fillOpacity={i < 3 ? 1 : 0.4} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-3 pt-3 border-t border-white/5 flex gap-6">
              <div>
                <span className="text-[9px] text-white/40 font-bold uppercase block">Win Prob</span>
                <span className="text-base font-mono font-bold text-green-400">{(currentWinProb * 100).toFixed(2)}%</span>
              </div>
              <div>
                <span className="text-[9px] text-white/40 font-bold uppercase block">Podium Prob</span>
                <span className="text-base font-mono font-bold text-purple-400">{(currentPodiumProb * 100).toFixed(2)}%</span>
              </div>
            </div>
          </div>
        </div>

        {/* ── Right: AI Chat ────────────────────────────────────────────────── */}
        <div className="xl:col-span-5 flex flex-col min-h-[500px] xl:min-h-0">
          <div className="flex-1 rounded-2xl border shadow-2xl overflow-hidden flex flex-col" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>

            {/* Chat header */}
            <div className="px-5 py-4 border-b flex items-center gap-3" style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-secondary)' }}>
              <div className="w-8 h-8 rounded-lg bg-red-600 flex items-center justify-center shadow-lg">
                <Bot className="w-5 h-5 text-white" />
              </div>
              <div>
                <h3 className="text-sm font-display font-bold uppercase tracking-tight">AI Strategist</h3>
                <p className="text-[10px] font-mono text-white/40 flex items-center gap-1">
                  <Zap className="w-2.5 h-2.5 text-blue-400" /> FastAPI LLM Backend
                </p>
              </div>
            </div>

            {/* Messages */}
            <div ref={scrollRef} className="flex-1 overflow-y-auto p-5 space-y-5 scrollbar-hide">
              <AnimatePresence initial={false}>
                {chatMessages.map((m, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    className={`flex gap-3 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    {m.role === 'assistant' && (
                      <div className="w-7 h-7 rounded-lg bg-red-600 flex items-center justify-center flex-shrink-0 mt-1">
                        <Bot className="w-4 h-4 text-white" />
                      </div>
                    )}
                    <div className="max-w-[85%] flex flex-col gap-1">
                      <div
                        className={`p-3.5 rounded-2xl text-sm leading-relaxed shadow-sm break-words ${
                          m.role === 'user'
                            ? 'bg-blue-600 text-white rounded-tr-none'
                            : 'bg-white/[0.05] rounded-tl-none border border-white/[0.07] text-white/80'
                        }`}
                      >
                        {m.content
                          ? (m.role === 'assistant' ? <ChatMarkdown text={m.content} /> : m.content)
                          : (chatLoading && i === chatMessages.length - 1
                              ? <Loader2 className="w-4 h-4 animate-spin text-red-600" />
                              : null
                            )
                        }
                      </div>
                    </div>
                    {m.role === 'user' && (
                      <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 border mt-1" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}>
                        <User className="w-4 h-4 text-white/40" />
                      </div>
                    )}
                  </motion.div>
                ))}
              </AnimatePresence>

              {chatLoading && chatMessages[chatMessages.length - 1]?.role !== 'assistant' && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-3 justify-start">
                  <div className="w-7 h-7 rounded-lg bg-red-600 flex items-center justify-center flex-shrink-0">
                    <Bot className="w-4 h-4 text-white" />
                  </div>
                  <div className="p-3.5 rounded-2xl rounded-tl-none border bg-white/[0.05] border-white/[0.07]">
                    <Loader2 className="w-4 h-4 animate-spin text-red-600" />
                  </div>
                </motion.div>
              )}
            </div>

            {/* Input bar */}
            <div className="p-4 border-t" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}>
              <div className="flex gap-3">
                <input
                  type="text"
                  value={chatInput}
                  onChange={e => setChatInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleChat(); } }}
                  placeholder="Ask the strategist… e.g. 'Undercut viable on Lap 18?'"
                  className="flex-1 border rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-1 focus:ring-red-600 transition-all placeholder:text-gray-500 bg-black/20"
                  style={{ borderColor: 'var(--border-color)', color: 'var(--text-primary)' }}
                />
                <button
                  onClick={handleChat}
                  disabled={chatLoading || !chatInput.trim()}
                  className="bg-red-600 text-white p-3 rounded-xl hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-lg"
                >
                  {chatLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
                </button>
              </div>
            </div>
          </div>
        </div>

      </div>}

    </div>
  );
};

// ── Helpers ────────────────────────────────────────────────────────────────────

function ResultCard({ icon: Icon, label, value, color }: { icon: React.ElementType; label: string; value: string; color: string }) {
  return (
    <motion.div
      initial={{ scale: 0.95, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      className="p-4 rounded-xl border backdrop-blur-sm"
      style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}
    >
      <div className="flex items-center gap-2 mb-1">
        <Icon className="w-4 h-4" style={{ color }} />
        <span className="text-[10px] font-bold text-white/40 uppercase tracking-tighter">{label}</span>
      </div>
      <span className="text-2xl font-display font-black" style={{ color }}>{value}</span>
    </motion.div>
  );
}

function formatTime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = (seconds % 60).toFixed(3);
  const ss = s.padStart(6, '0');
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`;
}


/**
 * Lightweight markdown renderer for AI chat responses.
 * Handles: ## headings, **bold**, numbered lists, bullet lists,
 * horizontal rules (---), and inline bold without adding dependencies.
 */
function ChatMarkdown({ text }: { text: string }) {
  const lines = text.split('\n');
  const elements: React.ReactNode[] = [];
  let listItems: string[] = [];
  let listType: 'ol' | 'ul' | null = null;

  const flushList = (key: string) => {
    if (listItems.length === 0) return;
    if (listType === 'ol') {
      elements.push(
        <ol key={key} className="list-decimal list-inside space-y-0.5 my-1 pl-1">
          {listItems.map((item, j) => (
            <li key={j} className="text-white/80 text-sm leading-relaxed">
              <InlineMd text={item} />
            </li>
          ))}
        </ol>
      );
    } else {
      elements.push(
        <ul key={key} className="space-y-0.5 my-1 pl-1">
          {listItems.map((item, j) => (
            <li key={j} className="flex gap-2 text-sm leading-relaxed text-white/80">
              <span className="text-red-500 mt-0.5 flex-shrink-0">•</span>
              <InlineMd text={item} />
            </li>
          ))}
        </ul>
      );
    }
    listItems = [];
    listType = null;
  };

  lines.forEach((line, i) => {
    // Horizontal rule
    if (/^---+$/.test(line.trim())) {
      flushList(`hr-flush-${i}`);
      elements.push(<hr key={`hr-${i}`} className="border-white/10 my-2" />);
      return;
    }
    // H2 / H3
    if (line.startsWith('## ')) {
      flushList(`h2-flush-${i}`);
      elements.push(
        <p key={i} className="text-xs font-bold uppercase tracking-widest text-white/50 mt-3 mb-1">
          {line.slice(3)}
        </p>
      );
      return;
    }
    if (line.startsWith('### ')) {
      flushList(`h3-flush-${i}`);
      elements.push(
        <p key={i} className="text-[11px] font-bold uppercase tracking-wider text-white/40 mt-2 mb-0.5">
          {line.slice(4)}
        </p>
      );
      return;
    }
    // Numbered list item
    const olMatch = line.match(/^\d+\.\s+(.*)/);
    if (olMatch) {
      if (listType !== 'ol') { flushList(`ol-flush-${i}`); listType = 'ol'; }
      listItems.push(olMatch[1]);
      return;
    }
    // Bullet list item (*, -, •)
    const ulMatch = line.match(/^[*\-•]\s+(.*)/);
    if (ulMatch) {
      if (listType !== 'ul') { flushList(`ul-flush-${i}`); listType = 'ul'; }
      listItems.push(ulMatch[1]);
      return;
    }
    // Flush any open list before a normal line
    flushList(`flush-${i}`);
    // Blank line → small gap
    if (line.trim() === '') {
      elements.push(<div key={i} className="h-1" />);
      return;
    }
    // Normal paragraph
    elements.push(
      <p key={i} className="text-sm leading-relaxed text-white/80">
        <InlineMd text={line} />
      </p>
    );
  });

  flushList('final');
  return <div className="space-y-0.5">{elements}</div>;
}

/**
 * Renders inline markdown: **bold** and *italic* within a line of text.
 */
function InlineMd({ text }: { text: string }) {
  // Split on **bold** or *italic* tokens
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/);
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith('**') && part.endsWith('**')) {
          return <strong key={i} className="font-bold text-white">{part.slice(2, -2)}</strong>;
        }
        if (part.startsWith('*') && part.endsWith('*')) {
          return <em key={i} className="italic text-white/90">{part.slice(1, -1)}</em>;
        }
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}

export default StrategyHub;
