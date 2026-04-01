/**
 * @file StrategyHub.tsx
 * @description Combined Strategy Simulator + AI Strategist view.
 *
 * Left panel  — Monte Carlo pit strategy builder (presets + custom stint builder, no dropdowns).
 * Right panel — AI chat interface wired to POST /llm/chat (FastAPI backend).
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
  Send, User, Bot, Sparkles, Zap,
} from 'lucide-react';
import { simulateStrategy } from '../services/endpoints';
import { apiFetch } from '../services/client';
import type { TireCompound } from '../types';

// ── Strategy constants ────────────────────────────────────────────────────────

const STRATEGY_PRESETS = [
  { name: 'Optimal 2-Stop', win_prob: 0.22, podium_prob: 0.45, risk: 'Low',  stints: [{ comp: 'MEDIUM', laps: 32 }, { comp: 'HARD', laps: 28 }, { comp: 'SOFT', laps: 18 }] },
  { name: 'Aggressive Undercut', win_prob: 0.18, podium_prob: 0.38, risk: 'High', stints: [{ comp: 'MEDIUM', laps: 28 }, { comp: 'HARD', laps: 30 }, { comp: 'SOFT', laps: 20 }] },
  { name: 'Conserve 1-Stop', win_prob: 0.04, podium_prob: 0.12, risk: 'Low',  stints: [{ comp: 'MEDIUM', laps: 45 }, { comp: 'HARD', laps: 33 }] },
];

const COMPOUNDS: TireCompound[] = ['SOFT', 'MEDIUM', 'HARD', 'INTERMEDIATE', 'WET'];
const TOTAL_LAPS = 57; // default race length (no race selector)

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
  // ── Strategy state ──────────────────────────────────────────────────────────
  const [selectedPreset, setSelectedPreset] = useState(STRATEGY_PRESETS[0]);
  const [mode, setMode] = useState<'preset' | 'custom'>('preset');
  const [customStints, setCustomStints] = useState<Stint[]>([
    { pitLap: 20, compound: 'MEDIUM' },
    { pitLap: 42, compound: 'HARD' },
  ]);
  const [driverName, setDriverName] = useState('Max Verstappen');
  const [simResult, setSimResult] = useState<SimResult | null>(null);
  const [simLoading, setSimLoading] = useState(false);
  const [simSource, setSimSource] = useState<'live' | 'local' | null>(null);

  // ── Chat state ──────────────────────────────────────────────────────────────
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      content: 'I am the Apex AI Strategist, powered by the F1 backend. Ask me anything about tire management, undercut opportunities, pit windows, or Grand Prix strategy.',
    },
  ]);
  const [chatLoading, setChatLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [chatMessages]);

  // ── Strategy helpers ────────────────────────────────────────────────────────

  const strategyArray: [number, string][] = useMemo(() => {
    if (mode === 'preset') {
      let lap = 0;
      return selectedPreset.stints.map(s => { lap += s.laps; return [lap, s.comp] as [number, string]; });
    }
    return customStints.map(s => [s.pitLap, s.compound] as [number, string]);
  }, [mode, selectedPreset, customStints]);

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
    ? selectedPreset.stints
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

  const runSimulation = useCallback(async () => {
    setSimLoading(true);
    setSimResult(null);
    setSimSource(null);
    // Convert display name → snake_case id for the API
    const driverId = driverName.trim().toLowerCase().replace(/\s+/g, '_');
    try {
      const result = await simulateStrategy({ race_id: '2024_1', driver_id: driverId, strategy: strategyArray });
      setSimResult(result);
      setSimSource('live');
    } catch {
      // Local fallback approximation
      setSimResult({
        predicted_final_position: 3,
        predicted_total_time_s: 5400,
        lap_times_s: Array.from({ length: TOTAL_LAPS }, (_, i) => 74 + Math.sin(i * 0.15) * 0.8),
        win_probability: currentWinProb,
        podium_probability: currentPodiumProb,
        strategy: strategyArray,
      });
      setSimSource('local');
    } finally {
      setSimLoading(false);
    }
  }, [strategyArray, currentWinProb, currentPodiumProb, driverName]);

  const addStint = () => {
    const lastLap = customStints.length > 0 ? customStints[customStints.length - 1].pitLap + 15 : 20;
    setCustomStints([...customStints, { pitLap: Math.min(lastLap, TOTAL_LAPS - 5), compound: 'HARD' }]);
  };
  const removeStint = (idx: number) => setCustomStints(customStints.filter((_, i) => i !== idx));
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
      const res = await apiFetch<{ answer: string; latency_ms: number; model: string; cache_hit: boolean }>(
        '/llm/chat',
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question }) },
      );
      setChatMessages(prev => [
        ...prev,
        { role: 'assistant', content: res.answer, model: res.model, cache_hit: res.cache_hit, latency_ms: res.latency_ms },
      ]);
    } catch (err) {
      setChatMessages(prev => [
        ...prev,
        { role: 'assistant', content: `Backend error: ${err instanceof Error ? err.message : 'Unknown error'}. Check that the API is running.` },
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="p-6 md:p-8 max-w-[1600px] mx-auto space-y-6 h-full flex flex-col">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-4xl font-display font-bold tracking-tight uppercase italic">Strategy Hub</h1>
          <p className="text-[10px] uppercase tracking-[4px] text-white/40 mt-2 font-mono flex items-center gap-2">
            <Sparkles className="w-3 h-3 text-blue-400" />
            Monte Carlo Simulation · AI Strategist · Backend LLM
          </p>
        </div>
        {/* Driver name input — plain text, no dropdown */}
        <div className="flex flex-col gap-1">
          <span className="text-[9px] font-mono text-white/40 uppercase tracking-widest">Driver</span>
          <input
            type="text"
            value={driverName}
            onChange={e => { setDriverName(e.target.value); setSimResult(null); }}
            placeholder="e.g. Max Verstappen"
            className="px-3 py-2 rounded-xl border text-sm font-bold bg-transparent focus:outline-none focus:ring-1 focus:ring-red-600 w-48"
            style={{ borderColor: 'var(--border-color)', color: 'var(--text-primary)', backgroundColor: 'var(--card-bg)' }}
          />
        </div>
      </div>

      {/* Two-column layout */}
      <div className="flex-1 grid grid-cols-1 xl:grid-cols-12 gap-6 min-h-0">

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
                {/* Driver label above cards */}
                <p className="text-[10px] font-mono text-white/40 uppercase tracking-widest">
                  Simulating: <span className="text-white font-bold">{toDriverName(driverName)}</span>
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
                    {/* Compound pill buttons — no dropdown */}
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
              {simSource && (
                <div className="ml-auto flex items-center gap-2">
                  <div className={`w-1.5 h-1.5 rounded-full ${simSource === 'live' ? 'bg-green-500' : 'bg-yellow-500'}`} />
                  <span className={`text-[9px] font-mono font-bold uppercase ${simSource === 'live' ? 'text-green-500' : 'text-yellow-500'}`}>
                    {simSource === 'live' ? 'Live Backend' : 'Local Approx'}
                  </span>
                </div>
              )}
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
                        className={`p-3.5 rounded-2xl text-sm leading-relaxed shadow-sm ${
                          m.role === 'user'
                            ? 'bg-blue-600 text-white rounded-tr-none'
                            : 'bg-white/[0.05] rounded-tl-none border border-white/[0.07] text-white/80'
                        }`}
                      >
                        {m.content || (chatLoading && i === chatMessages.length - 1
                          ? <Loader2 className="w-4 h-4 animate-spin text-red-600" />
                          : null
                        )}
                      </div>
                      {m.role === 'assistant' && m.model && (
                        <div className="flex items-center gap-2 px-1">
                          <span className="text-[9px] font-mono text-white/30">{m.model}</span>
                          {m.cache_hit && <span className="text-[9px] font-mono text-blue-400 uppercase">cache hit</span>}
                          {m.latency_ms != null && <span className="text-[9px] font-mono text-white/30">{m.latency_ms.toFixed(0)}ms</span>}
                        </div>
                      )}
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

      </div>
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

/** Convert API driver_id (e.g. "max_verstappen" / "verstappen") to title case. */
function toDriverName(id: string): string {
  return id
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase());
}

export default StrategyHub;
