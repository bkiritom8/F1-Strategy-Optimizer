/**
 * @file components/RaceSimulation.tsx
 * @description Interactive RL-driven race simulation panel.
 *
 * The component opens a WebSocket to /api/v1/simulation/ws, drives the race
 * lap-by-lap, renders a live track visualisation with per-driver cars, shows
 * key-moment prompts with RL strategy suggestions, and presents final race
 * stats when the simulation ends.
 *
 * Sections
 * ────────
 * SimSetup        — race/driver/strategy config form (pre-simulation)
 * RaceTrack       — animated SVG track with N driver dots
 * StandingsTower  — live position tower
 * StrategyPrompt  — RL recommendation card + accept/override buttons
 * LapTimeline     — compact scrollable lap log
 * SimChat         — LLM interface wired to simulation context
 * RaceResults     — final podium + stats after simulation ends
 */

import React, {
  useState, useRef, useEffect, useCallback, useMemo,
} from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Play, StopCircle, Zap, Bot, Send, Loader2, User,
  AlertTriangle, ChevronRight, Check, X, Radio,
} from 'lucide-react';
import { COLORS, TEAM_COLORS } from '../constants';
import { apiFetch } from '../services/client';
import { API_BASE } from '../services/client';
import TrackDisplay, { TRACK_REGISTRY } from './tracks/TrackMaps';

// ── Types ─────────────────────────────────────────────────────────────────────

interface DriverLapState {
  driver_id: string;
  display_name: string;
  code: string;
  position: number;
  compound: string;
  tire_age: number;
  gap_to_leader: number;
  lap_time_ms: number;
  pit_stop: boolean;
  new_compound: string | null;
  team: string;
  is_user: boolean;
}

interface LapSnap {
  lap: number;
  safety_car: boolean;
  standings: DriverLapState[];
  user: {
    position: number;
    compound: string;
    tire_age: number;
    fuel_kg: number;
    lap_time_ms: number;
    gap_to_leader: number;
    gap_to_ahead: number;
    safety_car: boolean;
    action_taken: number;
    action_name: string;
  };
  rl_action: number;
  rl_action_name: string;
}

interface PromptState {
  lap: number;
  reason: string;
  rl_action: number;
  rl_action_name: string;
  action_probs: number[];
  confidence: number;
  alternatives: { action: number; name: string; prob: number }[];
  current_state: {
    position: number;
    compound: string;
    tire_age: number;
    fuel_kg: number;
    gap_to_leader: number;
    gap_to_ahead: number;
    safety_car: boolean;
    total_laps: number;
  };
}

interface DecisionRecord {
  lap: number;
  reason: string;
  rl_action: number;
  rl_action_name: string;
  user_action: number;
  user_action_name: string;
  accepted: boolean;
}

interface RaceFinished {
  final_standings: { position: number; driver_id: string; display_name: string; total_time_s: number; pit_stops: number }[];
  strategy_summary: { driver_id: string; stints: { compound: string; laps: number }[] }[];
  user_final_position: number;
  total_laps: number;
  circuit_name: string;
  decision_history: DecisionRecord[];
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  latency_ms?: number;
}

type SimPhase = 'setup' | 'running' | 'prompt' | 'finished';

// ── Constants ─────────────────────────────────────────────────────────────────

const ACTION_LABELS: Record<number, string> = {
  0: 'Stay Neutral',
  1: 'Stay Balanced',
  2: 'Push Hard',
  3: 'Pit → SOFT',
  4: 'Pit → MEDIUM',
  5: 'Pit → HARD',
  6: 'Pit → INTER',
};

const ACTION_IS_PIT = (a: number) => a >= 3;

const COMPOUND_COLORS: Record<string, string> = {
  SOFT: COLORS.tires.SOFT,
  MEDIUM: COLORS.tires.MEDIUM,
  HARD: COLORS.tires.HARD,
  INTERMEDIATE: COLORS.tires.INTERMEDIATE,
  INTER: COLORS.tires.INTERMEDIATE,
  WET: COLORS.tires.WET,
};

const AVAILABLE_DRIVERS = [
  { id: 'max_verstappen',    name: 'Max Verstappen',    team: 'Red Bull'      },
  { id: 'lando_norris',      name: 'Lando Norris',      team: 'McLaren'       },
  { id: 'charles_leclerc',   name: 'Charles Leclerc',   team: 'Ferrari'       },
  { id: 'lewis_hamilton',    name: 'Lewis Hamilton',    team: 'Ferrari'       },
  { id: 'george_russell',    name: 'George Russell',    team: 'Mercedes'      },
  { id: 'oscar_piastri',     name: 'Oscar Piastri',     team: 'McLaren'       },
  { id: 'carlos_sainz',      name: 'Carlos Sainz',      team: 'Williams'      },
  { id: 'fernando_alonso',   name: 'Fernando Alonso',   team: 'Aston Martin'  },
  { id: 'liam_lawson',       name: 'Liam Lawson',       team: 'Red Bull'      },
  { id: 'kimi_antonelli',    name: 'Kimi Antonelli',    team: 'Mercedes'      },
  { id: 'yuki_tsunoda',      name: 'Yuki Tsunoda',      team: 'RB'            },
  { id: 'alex_albon',        name: 'Alex Albon',        team: 'Williams'      },
  { id: 'nico_hulkenberg',   name: 'Nico Hülkenberg',   team: 'Sauber'        },
  { id: 'oliver_bearman',    name: 'Oliver Bearman',    team: 'Haas'          },
  { id: 'michael_schumacher',name: 'Michael Schumacher',team: 'Ferrari'       },
  { id: 'ayrton_senna',      name: 'Ayrton Senna',      team: 'McLaren'       },
  { id: 'sebastian_vettel',  name: 'Sebastian Vettel',  team: 'Red Bull'      },
];

const AVAILABLE_RACES = [
  { id: '2025_4',  name: 'Bahrain GP',       circuit_id: 'bahrain'     },
  { id: '2025_1',  name: 'Australian GP',    circuit_id: 'melbourne'   },
  { id: '2025_3',  name: 'Japanese GP',      circuit_id: 'suzuka'      },
  { id: '2025_9',  name: 'Spanish GP',       circuit_id: 'barcelona'   },
  { id: '2025_8',  name: 'Monaco GP',        circuit_id: 'monaco'      },
  { id: '2025_12', name: 'British GP',       circuit_id: 'silverstone' },
  { id: '2025_11', name: 'Austrian GP',      circuit_id: 'spielberg'   },
  { id: '2025_13', name: 'Belgian GP',       circuit_id: 'spa'         },
  { id: '2025_16', name: 'Italian GP',       circuit_id: 'monza'       },
  { id: '2025_18', name: 'Singapore GP',     circuit_id: 'singapore'   },
  { id: '2025_19', name: 'US GP',            circuit_id: 'cota'        },
  { id: '2025_22', name: 'Las Vegas GP',     circuit_id: 'vegas'       },
  { id: '2025_24', name: 'Abu Dhabi GP',     circuit_id: 'yas_marina'  },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function msToLapTime(ms: number): string {
  if (!ms || ms <= 0) return '-';
  const s = ms / 1000;
  const m = Math.floor(s / 60);
  const rem = (s % 60).toFixed(3).padStart(6, '0');
  return `${m}:${rem}`;
}

function ordinal(n: number): string {
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

function positionColor(pos: number): string {
  if (pos === 1) return COLORS.accent.yellow;
  if (pos <= 3) return COLORS.accent.green;
  if (pos <= 10) return COLORS.accent.blue;
  return '#6B7280';
}

function compoundDot(compound: string, size = 10) {
  const col = COMPOUND_COLORS[compound?.toUpperCase()] ?? '#888';
  return (
    <span
      className="inline-block rounded-full flex-shrink-0"
      style={{ width: size, height: size, backgroundColor: col, border: '1px solid rgba(255,255,255,0.2)' }}
    />
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────────

/** Animated track with driver dots positioned around the circuit. */
const RaceTrackViz: React.FC<{
  circuitId: string;
  standings: DriverLapState[];
  userDriverId: string;
  totalLaps: number;
  currentLap: number;
  safetyCarActive: boolean;
}> = ({ circuitId, standings, userDriverId, totalLaps, currentLap, safetyCarActive }) => {
  const trackInfo = TRACK_REGISTRY.find(t => t.id === circuitId);

  return (
    <div className="relative rounded-xl overflow-hidden border" style={{ borderColor: 'var(--border-color)', backgroundColor: '#0A0A0A' }}>
      {/* Header strip */}
      <div className="flex items-center justify-between px-4 py-2 border-b" style={{ borderColor: 'var(--border-color)' }}>
        <div className="flex items-center gap-2">
          <Radio className="w-3.5 h-3.5 text-red-500 animate-pulse" />
          <span className="text-xs font-mono font-bold uppercase tracking-widest text-white/60">
            LAP {currentLap} / {totalLaps}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {safetyCarActive && (
            <motion.span
              animate={{ opacity: [1, 0.4, 1] }}
              transition={{ duration: 0.8, repeat: Infinity }}
              className="text-[9px] font-black px-2 py-0.5 rounded bg-yellow-400 text-black uppercase tracking-wider"
            >
              SAFETY CAR
            </motion.span>
          )}
          <span className="text-[9px] font-mono text-white/30 uppercase">
            {trackInfo?.name ?? circuitId}
          </span>
        </div>
      </div>

      {/* SVG Track */}
      <div className="flex items-center justify-center py-4 px-6">
        <div className="relative" style={{ width: 320, height: 220 }}>
          <TrackDisplay
            trackId={circuitId}
            width={320}
            height={220}
            strokeColor="rgba(255,255,255,0.45)"
            strokeWidth={3}
            showStartFinish
            animated={false}
          />
          {/* Driver dots: SVG overlay so elements render correctly in SVG context.
              Ellipse uses position-index spread (330°) so leader at top and last
              car never overlap. ViewBox matches TrackDisplay's 300x200 space. */}
          <svg
            className="absolute inset-0"
            width={320}
            height={220}
            viewBox="0 0 300 200"
            style={{ pointerEvents: 'none' }}
          >
            {standings.map((d) => {
              const totalCars = standings.length || 20;
              const frac = (d.position - 1) / totalCars;
              // 330° span starting from top (-90°), leader at top, cars spread clockwise
              const angle = frac * (330 / 360) * 2 * Math.PI - Math.PI / 2;
              const rx = 118, ry = 78;
              const cx = 150 + rx * Math.cos(angle);
              const cy = 100 + ry * Math.sin(angle);
              const isUser = d.driver_id === userDriverId;
              const teamColor = (TEAM_COLORS as any)[d.team] ?? '#888';
              return (
                <g key={d.driver_id}>
                  <title>{`P${d.position} ${d.display_name}`}</title>
                  <circle
                    cx={cx}
                    cy={cy}
                    r={isUser ? 6 : 4}
                    fill={isUser ? COLORS.accent.red : teamColor}
                    stroke={isUser ? '#fff' : 'rgba(255,255,255,0.3)'}
                    strokeWidth={isUser ? 2 : 1}
                    style={isUser ? { filter: 'drop-shadow(0 0 4px #E10600)' } : undefined}
                  />
                  {isUser && (
                    <text
                      x={cx}
                      y={cy + 12}
                      textAnchor="middle"
                      fontSize={6}
                      fill="#fff"
                      fontWeight="bold"
                    >
                      {d.code?.slice(0, 3)}
                    </text>
                  )}
                </g>
              );
            })}
          </svg>
        </div>
      </div>

      {/* Mini driver legend */}
      <div className="px-4 pb-3 grid grid-cols-4 gap-1">
        {standings.slice(0, 8).map(d => {
          const teamColor = (TEAM_COLORS as any)[d.team] ?? '#888';
          const isUser = d.driver_id === userDriverId;
          return (
            <div key={d.driver_id} className={`flex items-center gap-1.5 px-1.5 py-1 rounded ${isUser ? 'ring-1 ring-red-600/50' : ''}`}
              style={{ backgroundColor: isUser ? 'rgba(225,6,0,0.08)' : 'transparent' }}>
              <span className="text-[8px] font-mono text-white/30 w-3">{d.position}</span>
              <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: teamColor }} />
              <span className="text-[8px] font-mono font-bold truncate" style={{ color: isUser ? COLORS.accent.red : 'rgba(255,255,255,0.6)' }}>
                {d.code ?? d.display_name?.slice(0, 3).toUpperCase()}
              </span>
              {compoundDot(d.compound, 6)}
            </div>
          );
        })}
      </div>
    </div>
  );
};

/** Live position tower — full 20-driver list. */
const StandingsTower: React.FC<{
  standings: DriverLapState[];
  userDriverId: string;
}> = ({ standings, userDriverId }) => (
  <div className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--card-bg)' }}>
    <div className="px-4 py-2 border-b" style={{ borderColor: 'var(--border-color)' }}>
      <span className="text-[9px] font-mono font-bold uppercase tracking-widest text-white/40">Live Standings</span>
    </div>
    <div className="overflow-y-auto max-h-[380px] scrollbar-hide">
      {standings.map(d => {
        const isUser = d.driver_id === userDriverId;
        const teamColor = (TEAM_COLORS as any)[d.team] ?? '#888';
        return (
          <div
            key={d.driver_id}
            className={`flex items-center gap-2 px-3 py-1.5 border-b transition-colors ${isUser ? 'bg-red-600/10' : ''}`}
            style={{ borderColor: 'var(--border-color)' }}
          >
            <span className="text-[10px] font-mono font-bold w-5 text-right" style={{ color: positionColor(d.position) }}>
              {d.position}
            </span>
            <span className="w-1.5 h-3 rounded-sm flex-shrink-0" style={{ backgroundColor: teamColor }} />
            <span className={`text-xs font-bold flex-1 truncate ${isUser ? 'text-red-400' : 'text-white/80'}`}>
              {d.code ?? d.display_name}
              {isUser && <span className="ml-1 text-[8px] text-red-500 font-black">YOU</span>}
            </span>
            <div className="flex items-center gap-1">
              {compoundDot(d.compound, 7)}
              <span className="text-[8px] font-mono text-white/30">{d.tire_age}L</span>
            </div>
            {d.pit_stop && (
              <span className="text-[7px] font-black px-1 rounded bg-yellow-500/20 text-yellow-400 uppercase">PIT</span>
            )}
            {d.position > 1 && (
              <span className="text-[8px] font-mono text-white/20 w-12 text-right">
                +{d.gap_to_leader.toFixed(1)}s
              </span>
            )}
          </div>
        );
      })}
    </div>
  </div>
);

/** RL strategy prompt card. */
const StrategyPrompt: React.FC<{
  prompt: PromptState;
  onAccept: () => void;
  onOverride: (action: number) => void;
  loading: boolean;
}> = ({ prompt, onAccept, onOverride, loading }) => {
  const isPit = ACTION_IS_PIT(prompt.rl_action);
  const [showAlts, setShowAlts] = useState(false);

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.96, y: 10 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.96 }}
      className="rounded-2xl border-2 overflow-hidden"
      style={{ borderColor: isPit ? COLORS.accent.yellow : COLORS.accent.red, backgroundColor: 'var(--card-bg)' }}
    >
      {/* Alert header */}
      <div
        className="flex items-center gap-3 px-5 py-3"
        style={{ backgroundColor: isPit ? 'rgba(255,242,0,0.08)' : 'rgba(225,6,0,0.10)' }}
      >
        <motion.div animate={{ scale: [1, 1.15, 1] }} transition={{ duration: 0.6, repeat: Infinity }}>
          <AlertTriangle className="w-5 h-5" style={{ color: isPit ? COLORS.accent.yellow : COLORS.accent.red }} />
        </motion.div>
        <div className="flex-1 min-w-0">
          <p className="text-[10px] font-mono font-bold uppercase tracking-widest text-white/40">
            Lap {prompt.lap} · RL Strategy Prompt
          </p>
          <p className="text-sm font-bold text-white leading-tight">{prompt.reason}</p>
        </div>
        <Zap className="w-4 h-4 text-blue-400 flex-shrink-0" />
      </div>

      <div className="p-5 space-y-4">
        {/* Current state mini-grid */}
        <div className="grid grid-cols-4 gap-2">
          {[
            { label: 'Position', value: `P${prompt.current_state.position}` },
            { label: 'Tire', value: `${prompt.current_state.compound} ${prompt.current_state.tire_age}L` },
            { label: 'Gap Ahead', value: `${prompt.current_state.gap_to_ahead.toFixed(1)}s` },
            { label: 'Fuel', value: `${prompt.current_state.fuel_kg.toFixed(0)}kg` },
          ].map(({ label, value }) => (
            <div key={label} className="rounded-lg p-2 text-center" style={{ backgroundColor: 'var(--bg-secondary)' }}>
              <p className="text-[8px] font-mono text-white/30 uppercase">{label}</p>
              <p className="text-xs font-bold text-white">{value}</p>
            </div>
          ))}
        </div>

        {/* RL recommendation */}
        <div className="rounded-xl border p-4 space-y-3" style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-secondary)' }}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Zap className="w-4 h-4 text-blue-400" />
              <span className="text-[9px] font-mono text-white/40 uppercase tracking-widest">RL Recommendation</span>
            </div>
            <span className="text-[9px] font-mono text-green-400">{(prompt.confidence * 100).toFixed(0)}% confidence</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-lg font-display font-black text-white uppercase">
              {ACTION_LABELS[prompt.rl_action]}
            </span>
            {isPit && (
              <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-yellow-400/20 text-yellow-400">
                PIT STOP
              </span>
            )}
          </div>

          {/* Probability bar */}
          <div className="space-y-1">
            {[3,4,5,0,1,2].map(a => {
              const prob = prompt.action_probs[a] ?? 0;
              const isRecommended = a === prompt.rl_action;
              return (
                <div key={a} className="flex items-center gap-2">
                  <span className={`text-[8px] font-mono w-20 text-right ${isRecommended ? 'text-white font-bold' : 'text-white/30'}`}>
                    {ACTION_LABELS[a]}
                  </span>
                  <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: 'rgba(255,255,255,0.05)' }}>
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${(prob * 100).toFixed(1)}%` }}
                      className="h-full rounded-full"
                      style={{ backgroundColor: isRecommended ? COLORS.accent.green : 'rgba(255,255,255,0.15)' }}
                    />
                  </div>
                  <span className="text-[8px] font-mono w-7 text-white/30">{(prob * 100).toFixed(0)}%</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Decision buttons */}
        <div className="flex gap-3">
          <button
            onClick={onAccept}
            disabled={loading}
            className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl font-bold text-sm transition-all
              bg-green-600 hover:bg-green-500 text-white disabled:opacity-50 shadow-lg shadow-green-900/30"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
            Accept RL Advice
          </button>
          <button
            onClick={() => setShowAlts(v => !v)}
            className="px-4 py-3 rounded-xl font-bold text-sm border transition-all text-white/60 hover:text-white hover:border-white/40"
            style={{ borderColor: 'var(--border-color)' }}
          >
            Override
          </button>
        </div>

        {/* Override options */}
        <AnimatePresence>
          {showAlts && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden space-y-2"
            >
              <p className="text-[9px] font-mono text-white/30 uppercase tracking-widest">Choose your own action:</p>
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(ACTION_LABELS).map(([a, label]) => {
                  const ai = parseInt(a);
                  if (ai === prompt.rl_action) return null;
                  const prob = (prompt.action_probs[ai] ?? 0) * 100;
                  return (
                    <button
                      key={a}
                      onClick={() => onOverride(ai)}
                      disabled={loading}
                      className="flex items-center justify-between px-3 py-2 rounded-lg border text-xs font-bold transition-all
                        hover:border-blue-500/50 hover:bg-blue-600/10 disabled:opacity-40"
                      style={{ borderColor: 'var(--border-color)' }}
                    >
                      <span className="text-white/70">{label}</span>
                      <span className="text-[9px] font-mono text-white/30">{prob.toFixed(0)}%</span>
                    </button>
                  );
                })}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
};

/** Compact scrollable lap log. */
const LapTimeline: React.FC<{ laps: LapSnap[]; userDriverId: string }> = ({ laps, userDriverId }) => {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [laps.length]);

  return (
    <div className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--card-bg)' }}>
      <div className="px-4 py-2 border-b" style={{ borderColor: 'var(--border-color)' }}>
        <span className="text-[9px] font-mono font-bold uppercase tracking-widest text-white/40">Lap Log</span>
      </div>
      <div ref={ref} className="overflow-y-auto max-h-52 scrollbar-hide">
        {laps.length === 0 && (
          <p className="text-[10px] font-mono text-white/20 p-4 text-center">Simulation starting…</p>
        )}
        {laps.map(snap => {
          const u = snap.user;
          return (
            <div
              key={snap.lap}
              className="flex items-center gap-3 px-3 py-1.5 border-b text-[10px] font-mono"
              style={{ borderColor: 'var(--border-color)', backgroundColor: snap.safety_car ? 'rgba(255,242,0,0.04)' : 'transparent' }}
            >
              <span className="text-white/30 w-8">L{snap.lap}</span>
              <span className="font-bold" style={{ color: positionColor(u.position) }}>P{u.position}</span>
              {compoundDot(u.compound, 7)}
              <span className="text-white/50">{msToLapTime(u.lap_time_ms)}</span>
              {u.action_name.startsWith('PIT') && (
                <span className="px-1.5 py-0.5 rounded text-[7px] font-black uppercase bg-yellow-500/20 text-yellow-400">{u.action_name}</span>
              )}
              {snap.safety_car && (
                <span className="px-1.5 py-0.5 rounded text-[7px] font-black uppercase bg-yellow-400/20 text-yellow-300">SC</span>
              )}
              <span className="ml-auto text-white/20">{u.fuel_kg.toFixed(0)}kg</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

/** AI chat wired to simulation context. */
const SimChat: React.FC<{
  messages: ChatMessage[];
  onSend: (q: string) => void;
  loading: boolean;
}> = ({ messages, onSend, loading }) => {
  const [input, setInput] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages.length]);

  const send = () => {
    const q = input.trim();
    if (!q || loading) return;
    setInput('');
    onSend(q);
  };

  return (
    <div className="flex flex-col rounded-xl border overflow-hidden" style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--card-bg)' }}>
      <div className="flex items-center gap-2 px-4 py-2.5 border-b" style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-secondary)' }}>
        <div className="w-6 h-6 rounded-lg bg-red-600 flex items-center justify-center">
          <Bot className="w-3.5 h-3.5 text-white" />
        </div>
        <span className="text-xs font-display font-bold uppercase tracking-tight">AI Strategist</span>
        <span className="ml-auto text-[8px] font-mono text-white/20 uppercase">Simulation Context</span>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-3 scrollbar-hide min-h-[180px] max-h-[280px]">
        {messages.map((m, i) => (
          <div key={i} className={`flex gap-2 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {m.role === 'assistant' && (
              <div className="w-5 h-5 rounded bg-red-600 flex items-center justify-center flex-shrink-0 mt-0.5">
                <Bot className="w-3 h-3 text-white" />
              </div>
            )}
            <div
              className={`max-w-[85%] px-3 py-2 rounded-xl text-xs leading-relaxed ${
                m.role === 'user'
                  ? 'bg-blue-600 text-white rounded-tr-none'
                  : 'bg-white/[0.05] border border-white/[0.07] text-white/80 rounded-tl-none'
              }`}
            >
              {m.content}
              {m.role === 'assistant' && m.latency_ms != null && (
                <span className="block text-[8px] font-mono text-white/20 mt-1">{m.latency_ms.toFixed(0)}ms</span>
              )}
            </div>
            {m.role === 'user' && (
              <div className="w-5 h-5 rounded border flex items-center justify-center flex-shrink-0 mt-0.5"
                style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-secondary)' }}>
                <User className="w-3 h-3 text-white/40" />
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="flex gap-2 justify-start">
            <div className="w-5 h-5 rounded bg-red-600 flex items-center justify-center">
              <Bot className="w-3 h-3 text-white" />
            </div>
            <div className="px-3 py-2 rounded-xl rounded-tl-none bg-white/[0.05] border border-white/[0.07]">
              <Loader2 className="w-3 h-3 animate-spin text-red-500" />
            </div>
          </div>
        )}
      </div>

      <div className="p-3 border-t flex gap-2" style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-secondary)' }}>
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
          placeholder="Ask about tires, undercut, pit window…"
          className="flex-1 px-3 py-2 rounded-lg border text-xs focus:outline-none focus:ring-1 focus:ring-red-600 bg-black/20 placeholder:text-gray-500"
          style={{ borderColor: 'var(--border-color)', color: 'var(--text-primary)' }}
        />
        <button
          onClick={send}
          disabled={loading || !input.trim()}
          className="p-2 rounded-lg bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
        >
          {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
        </button>
      </div>
    </div>
  );
};

/** Podium and full stats after race ends. */
const RaceResults: React.FC<{
  result: RaceFinished;
  userDriverId: string;
  onReset: () => void;
}> = ({ result, userDriverId, onReset }) => {
  const userPos = result.user_final_position;
  const userStints = result.strategy_summary.find(s => s.driver_id === userDriverId)?.stints ?? [];
  const accepted = result.decision_history.filter(d => d.accepted).length;
  const overridden = result.decision_history.filter(d => !d.accepted).length;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-5"
    >
      {/* Hero */}
      <div
        className="rounded-2xl border p-6 text-center space-y-3"
        style={{
          borderColor: userPos <= 3 ? COLORS.accent.green : 'var(--border-color)',
          backgroundColor: userPos <= 3 ? 'rgba(0,210,190,0.06)' : 'var(--card-bg)',
        }}
      >
        <p className="text-[9px] font-mono uppercase tracking-widest text-white/30">{result.circuit_name}</p>
        <div className="text-6xl font-display font-black" style={{ color: positionColor(userPos) }}>
          {ordinal(userPos)}
        </div>
        <p className="text-white/50 text-sm">
          {userPos === 1 ? '🏆 Race Winner!' : userPos <= 3 ? '🥇 Podium finish!' : userPos <= 10 ? 'Points finish' : 'Outside points'}
        </p>

        {/* Strategy pills */}
        <div className="flex items-center justify-center gap-2 flex-wrap pt-1">
          {userStints.map((stint, i) => (
            <div key={i} className="flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-bold"
              style={{ backgroundColor: `${COMPOUND_COLORS[stint.compound.toUpperCase()] ?? '#888'}20`, color: COMPOUND_COLORS[stint.compound.toUpperCase()] ?? '#888' }}>
              {compoundDot(stint.compound, 8)}
              {stint.compound.slice(0, 1)} - {stint.laps}L
            </div>
          ))}
        </div>
      </div>

      {/* Decision Stats */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'Prompts', value: result.decision_history.length, color: COLORS.accent.blue, icon: Radio },
          { label: 'RL Accepted', value: accepted, color: COLORS.accent.green, icon: Check },
          { label: 'Overridden', value: overridden, color: COLORS.accent.yellow, icon: X },
        ].map(({ label, value, color, icon: Icon }) => (
          <div key={label} className="rounded-xl border p-3 text-center" style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--card-bg)' }}>
            <Icon className="w-4 h-4 mx-auto mb-1" style={{ color }} />
            <p className="text-xl font-display font-black" style={{ color }}>{value}</p>
            <p className="text-[8px] font-mono text-white/30 uppercase">{label}</p>
          </div>
        ))}
      </div>

      {/* Decision History */}
      {result.decision_history.length > 0 && (
        <div className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--card-bg)' }}>
          <div className="px-4 py-2 border-b" style={{ borderColor: 'var(--border-color)' }}>
            <span className="text-[9px] font-mono font-bold uppercase tracking-widest text-white/40">Strategy Decisions</span>
          </div>
          {result.decision_history.map((d, i) => (
            <div key={i} className="flex items-start gap-3 px-4 py-2.5 border-b text-xs" style={{ borderColor: 'var(--border-color)' }}>
              <span className="text-white/30 font-mono w-8 flex-shrink-0">L{d.lap}</span>
              <div className="flex-1 min-w-0">
                <p className="text-white/60 truncate">{d.reason}</p>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-[9px] font-mono text-blue-400">RL: {ACTION_LABELS[d.rl_action]}</span>
                  {!d.accepted && (
                    <>
                      <ChevronRight className="w-2.5 h-2.5 text-white/20" />
                      <span className="text-[9px] font-mono text-yellow-400">You: {ACTION_LABELS[d.user_action]}</span>
                    </>
                  )}
                </div>
              </div>
              {d.accepted
                ? <Check className="w-3.5 h-3.5 text-green-500 flex-shrink-0 mt-0.5" />
                : <X className="w-3.5 h-3.5 text-yellow-400 flex-shrink-0 mt-0.5" />
              }
            </div>
          ))}
        </div>
      )}

      {/* Final standings */}
      <div className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--card-bg)' }}>
        <div className="px-4 py-2 border-b" style={{ borderColor: 'var(--border-color)' }}>
          <span className="text-[9px] font-mono font-bold uppercase tracking-widest text-white/40">Final Classification</span>
        </div>
        {result.final_standings.slice(0, 10).map(d => (
          <div key={d.driver_id} className={`flex items-center gap-3 px-4 py-2 border-b text-xs ${d.driver_id === userDriverId ? 'bg-red-600/10' : ''}`}
            style={{ borderColor: 'var(--border-color)' }}>
            <span className="font-mono font-bold w-4" style={{ color: positionColor(d.position) }}>{d.position}</span>
            <span className={`flex-1 font-bold ${d.driver_id === userDriverId ? 'text-red-400' : 'text-white/80'}`}>
              {d.display_name}{d.driver_id === userDriverId && ' ★'}
            </span>
            <span className="font-mono text-white/30">{d.pit_stops} pit{d.pit_stops !== 1 ? 's' : ''}</span>
            <span className="font-mono text-white/20 w-20 text-right">{d.position === 1 ? 'WINNER' : `+${(d.total_time_s - result.final_standings[0]?.total_time_s).toFixed(3)}s`}</span>
          </div>
        ))}
      </div>

      <button
        onClick={onReset}
        className="w-full py-3 rounded-xl font-bold text-sm border-2 border-red-600 text-red-500 hover:bg-red-600 hover:text-white transition-all"
      >
        New Simulation
      </button>
    </motion.div>
  );
};

// ── Main Component ─────────────────────────────────────────────────────────────

const RaceSimulation: React.FC = () => {
  // ── Setup state ─────────────────────────────────────────────────────────────
  const [selectedRace, setSelectedRace] = useState(AVAILABLE_RACES[0]);
  const [selectedDriver, setSelectedDriver] = useState(AVAILABLE_DRIVERS[0]);
  const [startPosition, setStartPosition] = useState(5);
  const [startCompound, setStartCompound] = useState<'SOFT'|'MEDIUM'|'HARD'>('MEDIUM');

  // ── Simulation state ─────────────────────────────────────────────────────────
  const [phase, setPhase] = useState<SimPhase>('setup');
  const [laps, setLaps] = useState<LapSnap[]>([]);
  const [currentStandings, setCurrentStandings] = useState<DriverLapState[]>([]);
  const [totalLaps, setTotalLaps] = useState(57);
  const [circuitId, setCircuitId] = useState('bahrain');
  const [raceName, setRaceName] = useState('');
  const [currentLap, setCurrentLap] = useState(0);
  const [safetyCarActive, setSafetyCarActive] = useState(false);
  const [activePrompt, setActivePrompt] = useState<PromptState | null>(null);
  const [promptLoading, setPromptLoading] = useState(false);
  const [finishedResult, setFinishedResult] = useState<RaceFinished | null>(null);
  const [statusMsg, setStatusMsg] = useState('');

  // ── Chat state ───────────────────────────────────────────────────────────────
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([{
    role: 'assistant',
    content: 'I\'m your race strategist. Once the simulation starts, ask me about tire windows, undercut timing, SC strategy, or anything about your race.',
  }]);
  const [chatLoading, setChatLoading] = useState(false);

  // ── WebSocket ref ────────────────────────────────────────────────────────────
  const wsRef = useRef<WebSocket | null>(null);

  // ── Playback engine ───────────────────────────────────────────────────────────
  // Full race compressed into RACE_PLAYBACK_MS (1.5 min). Laps stream into
  // lapBufferRef from the WebSocket; the setInterval loop advances one lap at
  // a time at the computed per-lap interval regardless of batch boundaries.
  const RACE_PLAYBACK_MS = 90_000; // 1.5 minutes
  const lapBufferRef = useRef<LapSnap[]>([]);
  const playbackIdxRef = useRef(0);
  const playbackTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const totalLapsRef = useRef(57);           // mirror of totalLaps state for callbacks
  const raceFinishedDataRef = useRef<RaceFinished | null>(null); // deferred until playback ends

  const stopPlayback = useCallback(() => {
    if (playbackTimerRef.current !== null) {
      clearInterval(playbackTimerRef.current);
      playbackTimerRef.current = null;
    }
  }, []);

  // Start the steady-tick playback loop (idempotent — safe to call multiple times).
  const startPlayback = useCallback(() => {
    if (playbackTimerRef.current !== null) return;
    const lapIntervalMs = Math.max(100, RACE_PLAYBACK_MS / totalLapsRef.current);
    playbackTimerRef.current = setInterval(() => {
      const idx = playbackIdxRef.current;
      const lapSnap = lapBufferRef.current[idx];
      if (!lapSnap) {
        // Buffer not yet filled — wait for more laps from WS.
        // If the backend finished and there are no more laps, end playback.
        if (raceFinishedDataRef.current) {
          stopPlayback();
          setFinishedResult(raceFinishedDataRef.current);
          setPhase('finished');
        }
        return;
      }
      setCurrentLap(lapSnap.lap);
      setSafetyCarActive(lapSnap.safety_car);
      if (lapSnap.standings?.length > 0) setCurrentStandings(lapSnap.standings);
      setStatusMsg(`Lap ${lapSnap.lap} / ${totalLapsRef.current}`);
      playbackIdxRef.current = idx + 1;
    }, lapIntervalMs);
  }, [stopPlayback]);

  // ── Cleanup ──────────────────────────────────────────────────────────────────
  const closeWs = useCallback(() => {
    stopPlayback();
    if (wsRef.current) {
      wsRef.current.onmessage = null;
      wsRef.current.onerror = null;
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }
  }, [stopPlayback]);

  useEffect(() => () => closeWs(), [closeWs]);

  // ── Build context string for LLM ─────────────────────────────────────────────
  const simContext = useMemo(() => {
    if (laps.length === 0) return '';
    const last = laps[laps.length - 1];
    return `[Simulation context - Lap ${last.lap}/${totalLaps}, ${raceName}] `
      + `Driver: ${selectedDriver.name}, P${last.user.position}, `
      + `${last.user.compound} tires age ${last.user.tire_age}L, `
      + `fuel ${last.user.fuel_kg.toFixed(0)}kg, `
      + `gap to leader ${last.user.gap_to_leader.toFixed(1)}s, `
      + `SC ${last.user.safety_car ? 'ACTIVE' : 'clear'}. `;
  }, [laps, totalLaps, raceName, selectedDriver]);

  // ── Chat handler ─────────────────────────────────────────────────────────────
  const handleChat = useCallback(async (question: string) => {
    setChatMessages(prev => [...prev, { role: 'user', content: question }]);
    setChatLoading(true);
    try {
      const history = chatMessages.slice(1).map(m => ({ role: m.role, content: m.content }));
      const contextQ = simContext ? simContext + question : question;
      const res = await apiFetch<{ answer: string; latency_ms: number }>('/llm/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: contextQ, history }),
      });
      setChatMessages(prev => [...prev, { role: 'assistant', content: res.answer, latency_ms: res.latency_ms }]);
    } catch {
      setChatMessages(prev => [...prev, { role: 'assistant', content: 'Backend unreachable. Check the API is running.' }]);
    } finally {
      setChatLoading(false);
    }
  }, [chatMessages, simContext]);

  // ── Start simulation ──────────────────────────────────────────────────────────
  const startSimulation = useCallback(() => {
    closeWs();
    // Reset playback engine
    lapBufferRef.current = [];
    playbackIdxRef.current = 0;
    raceFinishedDataRef.current = null;
    setPhase('running');
    setLaps([]);
    setCurrentStandings([]);
    setCurrentLap(0);
    setSafetyCarActive(false);
    setActivePrompt(null);
    setFinishedResult(null);
    setStatusMsg('Connecting to simulation…');

    // Normalise API_BASE: strip trailing slashes, then rebuild as ws(s)://
    // Handles both "https://backend.run.app" and "https://backend.run.app/"
    const cleanBase = API_BASE.replace(/\/+$/, '');
    const wsProto = (cleanBase.startsWith('https://') || window.location.protocol === 'https:') ? 'wss' : 'ws';
    const wsHost = cleanBase ? cleanBase.replace(/^https?:\/\//, '') : window.location.host;
    const wsUrl = `${wsProto}://${wsHost}/api/v1/simulation/ws`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setStatusMsg('Sending race configuration…');
      ws.send(JSON.stringify({
        type: 'start',
        race_id: selectedRace.id,
        driver_id: selectedDriver.id,
        start_position: startPosition,
        start_compound: startCompound,
      }));
    };

    ws.onmessage = (ev: MessageEvent) => {
      const msg = JSON.parse(ev.data as string);

      if (msg.type === 'setup_ack') {
        const tl: number = msg.total_laps ?? 57;
        totalLapsRef.current = tl;
        setTotalLaps(tl);
        // Map backend circuit_id values to the TRACK_REGISTRY IDs used by TrackDisplay.
        // Backend uses historical/canonical names; frontend uses short display names.
        const CIRCUIT_ID_MAP: Record<string, string> = {
          albert_park: 'melbourne',
          catalunya:   'barcelona',
          red_bull_ring: 'spielberg',
          hungaroring: 'budapest',
          marina_bay:  'singapore',
          americas:    'cota',
          rodriguez:   'mexico',
          las_vegas:   'vegas',
          losail:      'lusail',
          villeneuve:  'montreal',
        };
        const rawId: string = msg.circuit_id ?? '';
        setCircuitId(CIRCUIT_ID_MAP[rawId] ?? rawId);
        setRaceName(msg.circuit_name);
        setStatusMsg(`Race loaded: ${msg.circuit_name} · ${tl} laps — starting…`);
        // Initialise standings from starting grid so drivers appear immediately
        if (Array.isArray(msg.drivers) && msg.drivers.length > 0) {
          const gridStandings: DriverLapState[] = [...(msg.drivers as any[])]
            .sort((a: any, b: any) => a.start_position - b.start_position)
            .map((d: any, idx: number) => ({
              driver_id: d.driver_id,
              display_name: d.display_name,
              code: d.code,
              position: d.start_position,
              compound: d.start_compound,
              tire_age: 0,
              gap_to_leader: idx * 0.5,
              lap_time_ms: 0,
              pit_stop: false,
              new_compound: null,
              team: d.team,
              is_user: d.is_user,
            }));
          setCurrentStandings(gridStandings);
          setCurrentLap(0);
        }
      }

      else if (msg.type === 'laps') {
        const newLaps: LapSnap[] = msg.data;
        setLaps(prev => [...prev, ...newLaps]);
        // Append to playback buffer; loop will advance at the computed interval
        lapBufferRef.current.push(...newLaps);
        startPlayback();
      }

      else if (msg.type === 'prompt') {
        // Auto-accept all strategy prompts so the race runs without pausing.
        // The key-moment reason appears briefly in the status bar.
        setStatusMsg(`Strategy: ${msg.reason}`);
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'accept' }));
        }
      }

      else if (msg.type === 'finished') {
        // Store result but don't switch phase yet — playback loop will do that
        // once it exhausts the lap buffer, so the user sees every lap played out.
        // Close the WebSocket directly (not via closeWs) so the playback loop
        // keeps running until the buffer is empty.
        raceFinishedDataRef.current = msg as RaceFinished;
        ws.onmessage = null;
        ws.onclose = null;
        ws.close();
        wsRef.current = null;
        setStatusMsg('Final lap — race finishing…');
      }

      else if (msg.type === 'error') {
        setStatusMsg(`Error: ${msg.message}`);
        setPhase('setup');
        closeWs();
      }
    };

    ws.onerror = () => {
      setStatusMsg('WebSocket error - check the backend is running');
      setPhase('setup');
    };

    ws.onclose = (ev) => {
      if (phase !== 'finished') {
        setStatusMsg(`Disconnected (code ${ev.code})`);
      }
    };
  }, [selectedRace, selectedDriver, startPosition, startCompound, closeWs, startPlayback, phase]);

  // ── Accept RL recommendation ─────────────────────────────────────────────────
  const handleAccept = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    setPromptLoading(true);
    wsRef.current.send(JSON.stringify({ type: 'accept' }));
    setActivePrompt(null);
    setPhase('running');
    setPromptLoading(false);
  }, []);

  // ── Override with custom action ───────────────────────────────────────────────
  const handleOverride = useCallback((action: number) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    setPromptLoading(true);
    wsRef.current.send(JSON.stringify({ type: 'override', action }));
    setActivePrompt(null);
    setPhase('running');
    setPromptLoading(false);
  }, []);

  // ── Stop simulation ───────────────────────────────────────────────────────────
  const stopSimulation = useCallback(() => {
    closeWs();
    lapBufferRef.current = [];
    playbackIdxRef.current = 0;
    raceFinishedDataRef.current = null;
    setPhase('setup');
    setStatusMsg('');
  }, [closeWs]);

  // ── Reset ─────────────────────────────────────────────────────────────────────
  const reset = useCallback(() => {
    closeWs();
    lapBufferRef.current = [];
    playbackIdxRef.current = 0;
    raceFinishedDataRef.current = null;
    setPhase('setup');
    setLaps([]);
    setCurrentStandings([]);
    setCurrentLap(0);
    setFinishedResult(null);
    setActivePrompt(null);
    setStatusMsg('');
  }, [closeWs]);

  // ── Render ────────────────────────────────────────────────────────────────────

  // SETUP PHASE
  if (phase === 'setup') {
    return (
      <div className="space-y-5">
        {/* Section header */}
        <div>
          <h3 className="text-sm font-display font-bold uppercase tracking-widest text-white/40">Race Simulation Setup</h3>
          <p className="text-[10px] font-mono text-white/20 mt-1">Configure your driver, circuit, and starting strategy - then race against AI with RL strategy suggestions</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Circuit selector */}
          <div className="space-y-2">
            <label className="text-[9px] font-mono text-white/40 uppercase tracking-widest block">Circuit</label>
            <div className="grid grid-cols-2 gap-2 max-h-48 overflow-y-auto scrollbar-hide pr-1">
              {AVAILABLE_RACES.map(r => (
                <button
                  key={r.id}
                  onClick={() => setSelectedRace(r)}
                  className={`px-3 py-2 rounded-xl border text-left text-xs font-bold transition-all ${
                    selectedRace.id === r.id
                      ? 'border-red-600 bg-red-600/10 text-white'
                      : 'text-white/40 hover:text-white'
                  }`}
                  style={{ borderColor: selectedRace.id === r.id ? '#E10600' : 'var(--border-color)' }}
                >
                  {r.name}
                </button>
              ))}
            </div>
          </div>

          {/* Driver selector */}
          <div className="space-y-2">
            <label className="text-[9px] font-mono text-white/40 uppercase tracking-widest block">Your Driver</label>
            <div className="space-y-1 max-h-48 overflow-y-auto scrollbar-hide pr-1">
              {AVAILABLE_DRIVERS.map(d => {
                const teamColor = (TEAM_COLORS as any)[d.team] ?? '#888';
                return (
                  <button
                    key={d.id}
                    onClick={() => setSelectedDriver(d)}
                    className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl border text-left transition-all ${
                      selectedDriver.id === d.id ? 'border-red-600 bg-red-600/10' : 'hover:bg-white/[0.03]'
                    }`}
                    style={{ borderColor: selectedDriver.id === d.id ? '#E10600' : 'var(--border-color)' }}
                  >
                    <span className="w-1.5 h-4 rounded-sm flex-shrink-0" style={{ backgroundColor: teamColor }} />
                    <span className={`text-xs font-bold flex-1 ${selectedDriver.id === d.id ? 'text-white' : 'text-white/50'}`}>{d.name}</span>
                    <span className="text-[8px] font-mono text-white/20">{d.team}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Grid position + compound */}
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <label className="text-[9px] font-mono text-white/40 uppercase tracking-widest block">Grid Position</label>
            <div className="flex items-center gap-3">
              <input
                type="range" min={1} max={20} value={startPosition}
                onChange={e => setStartPosition(parseInt(e.target.value))}
                className="flex-1 accent-red-600"
              />
              <span className="text-lg font-display font-black text-white w-10 text-center">P{startPosition}</span>
            </div>
          </div>
          <div className="space-y-2">
            <label className="text-[9px] font-mono text-white/40 uppercase tracking-widest block">Starting Tires</label>
            <div className="flex gap-2">
              {(['SOFT','MEDIUM','HARD'] as const).map(c => (
                <button
                  key={c}
                  onClick={() => setStartCompound(c)}
                  className={`flex-1 py-2 rounded-xl text-xs font-black transition-all ${startCompound === c ? 'text-black shadow-lg' : 'text-white/40 border hover:text-white'}`}
                  style={{
                    backgroundColor: startCompound === c ? COMPOUND_COLORS[c] : 'transparent',
                    borderColor: startCompound === c ? COMPOUND_COLORS[c] : 'var(--border-color)',
                  }}
                >
                  {c.slice(0, 1)}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Circuit preview */}
        {selectedRace.circuit_id && (
          <div className="rounded-xl overflow-hidden border" style={{ borderColor: 'var(--border-color)' }}>
            <TrackDisplay
              trackId={selectedRace.circuit_id}
              width={undefined}
              height={120}
              strokeColor="rgba(255,255,255,0.25)"
              strokeWidth={3}
              animated
              showStartFinish
              className="w-full"
            />
          </div>
        )}

        {/* Launch button */}
        <button
          onClick={startSimulation}
          className="w-full py-4 rounded-xl font-bold text-sm bg-red-600 text-white hover:bg-red-500 transition-all
            flex items-center justify-center gap-2 shadow-xl shadow-red-900/30"
        >
          <Play className="w-5 h-5" />
          Start Race Simulation
        </button>

        <p className="text-[9px] font-mono text-white/20 text-center">
          PPO RL agent · 20 AI drivers · Up to 7 strategic prompts
        </p>
      </div>
    );
  }

  // FINISHED PHASE
  if (phase === 'finished' && finishedResult) {
    return (
      <RaceResults
        result={finishedResult}
        userDriverId={selectedDriver.id}
        onReset={reset}
      />
    );
  }

  // RUNNING PHASE (prompt phase no longer exists — prompts are auto-accepted)
  const lapProgress = totalLaps > 0 ? Math.min(1, currentLap / totalLaps) : 0;

  return (
    <div className="space-y-4">
      {/* Status bar + race progress */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <motion.div
              animate={{ scale: [1, 1.3, 1] }}
              transition={{ duration: 1, repeat: Infinity }}
              className="w-2 h-2 rounded-full bg-red-500"
            />
            <span className="text-[10px] font-mono text-white/50">{statusMsg}</span>
          </div>
          <button
            onClick={stopSimulation}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-bold text-white/40 hover:text-red-400 hover:border-red-600/40 transition-all"
            style={{ borderColor: 'var(--border-color)' }}
          >
            <StopCircle className="w-3.5 h-3.5" />
            Stop
          </button>
        </div>
        {/* Race progress bar — spans full 1.5-min playback */}
        <div className="h-1 rounded-full overflow-hidden" style={{ backgroundColor: 'rgba(255,255,255,0.06)' }}>
          <motion.div
            className="h-full rounded-full bg-red-600"
            animate={{ width: `${lapProgress * 100}%` }}
            transition={{ duration: 0.3, ease: 'linear' }}
          />
        </div>
      </div>

      {/* Track viz */}
      <RaceTrackViz
        circuitId={circuitId}
        standings={currentStandings}
        userDriverId={selectedDriver.id}
        totalLaps={totalLaps}
        currentLap={currentLap}
        safetyCarActive={safetyCarActive}
      />

      {/* Standings + lap log */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <StandingsTower standings={currentStandings} userDriverId={selectedDriver.id} />
        <LapTimeline laps={laps} userDriverId={selectedDriver.id} />
      </div>

      {/* AI Chat */}
      <SimChat
        messages={chatMessages}
        onSend={handleChat}
        loading={chatLoading}
      />
    </div>
  );
};

export default RaceSimulation;
