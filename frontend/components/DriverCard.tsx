/**
 * @file DriverCard.tsx
 * @description Compact telemetry card for the selected driver in RaceCommandCenter.
 *
 * Redesign goals (2026-04):
 *  - Full driver name + code visible without truncation (using driver.code as
 *    the headline, team name and full name as subtitle)
 *  - All stat labels fully readable — no truncation
 *  - Horizontal stat rows instead of small grid chips
 *  - ERS, Fuel, and AI Tactical Overlay consolidated in a tighter layout
 *  - Responsive: works well at any column width from 280px upward
 */

import React from 'react';
import { motion } from 'framer-motion';
import type { DriverTelemetry, DriverProfile, StrategyRecommendation } from '../types';
import { COLORS, TEAM_COLORS } from '../constants';
import { Zap, Thermometer, Fuel, Wind, Activity } from 'lucide-react';
import ConceptTooltip from './ConceptTooltip';

interface DriverCardProps {
  telemetry: DriverTelemetry;
  driver: DriverProfile;
  strategy: StrategyRecommendation | null;
}

/** Inline bar stat row — full label, no truncation. */
const StatRow: React.FC<{
  icon: React.ReactNode;
  label: string;
  value: string;
  color: string;
  pct?: number; // 0-100, renders bar if provided
}> = ({ icon, label, value, color, pct }) => (
  <div className="flex items-center gap-3 py-2 border-b border-white/[0.04] last:border-0">
    <div className="shrink-0" style={{ color }}>{icon}</div>
    <span className="text-[11px] font-bold uppercase tracking-wider text-gray-400 flex-1">{label}</span>
    <div className="flex items-center gap-2">
      {pct !== undefined && (
        <div className="w-16 h-1.5 rounded-full overflow-hidden bg-white/5">
          <motion.div
            className="h-full rounded-full"
            style={{ backgroundColor: color }}
            initial={{ width: 0 }}
            animate={{ width: `${Math.min(pct, 100)}%` }}
            transition={{ duration: 0.8, ease: 'easeOut' }}
          />
        </div>
      )}
      <span className="text-[12px] font-mono font-bold tabular-nums" style={{ color }}>{value}</span>
    </div>
  </div>
);

const DriverCard: React.FC<DriverCardProps> = ({ telemetry, driver, strategy }) => {
  const maxFuel = 110;
  const fuelPct = Math.min((telemetry.fuel_remaining_kg / maxFuel) * 100, 100);

  const fuelColor =
    fuelPct > 30 ? COLORS.accent.green : fuelPct > 10 ? COLORS.accent.yellow : COLORS.accent.red;

  // Prefer driver.code (3-letter) as headline, fall back to first word of name
  const headline = driver.code ?? driver.name.split(' ')[0];
  const teamColor = TEAM_COLORS[driver.team] ?? '#888';

  return (
    <div
      className="rounded-xl border shadow-2xl relative overflow-hidden"
      style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}
    >
      {/* Team colour accent top bar */}
      <div className="h-1 w-full" style={{ backgroundColor: teamColor }} />

      {/* Team glow in corner */}
      <div
        className="absolute top-0 right-0 w-40 h-40 opacity-10 pointer-events-none"
        style={{ background: `radial-gradient(circle at top right, ${teamColor}, transparent)` }}
      />

      <div className="p-4">
        {/* ── Header: Code + Position ──────────────────────────── */}
        <div className="flex justify-between items-start mb-3">
          <div className="min-w-0">
            {/* Code as big headline */}
            <div className="text-2xl font-display font-black uppercase tracking-tight text-white leading-none">
              {headline}
            </div>
            {/* Full name beneath */}
            <div className="text-xs text-gray-400 font-medium mt-0.5 truncate max-w-[160px]">
              {driver.name}
            </div>
            <div
              className="text-[10px] font-bold uppercase tracking-widest mt-0.5"
              style={{ color: teamColor }}
            >
              {driver.team}
            </div>
          </div>
          <div className="text-right shrink-0">
            <div
              className="text-4xl font-mono font-black leading-none"
              style={{ color: COLORS.accent.red }}
            >
              P{telemetry.position}
            </div>
            <div className="text-[10px] text-gray-500 mt-1 uppercase font-bold">
              +{telemetry.gap_to_ahead.toFixed(2)}s gap
            </div>
          </div>
        </div>

        {/* ── Telemetry Stats (rows, no truncation) ───────────── */}
        <div
          className="rounded-lg px-3 py-1 mb-3 border"
          style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}
        >
          <StatRow
            icon={<Wind className="w-3.5 h-3.5" />}
            label="Aero Loss"
            value={`${telemetry.aero_loss_percent.toFixed(1)}%`}
            color={telemetry.aero_loss_percent > 10 ? COLORS.accent.red : COLORS.accent.blue}
            pct={telemetry.aero_loss_percent * 4}
          />
          <StatRow
            icon={<Fuel className="w-3.5 h-3.5" />}
            label="Fuel Remaining"
            value={`${telemetry.fuel_remaining_kg.toFixed(1)} kg`}
            color={fuelColor}
            pct={fuelPct}
          />
          <StatRow
            icon={<Thermometer className="w-3.5 h-3.5" />}
            label="Tire Age"
            value={`${telemetry.tire_age_laps} laps`}
            color={COLORS.tires?.[telemetry.tire_compound] ?? '#aaa'}
            pct={Math.min(telemetry.tire_age_laps * 3, 100)}
          />
          <StatRow
            icon={<Zap className="w-3.5 h-3.5" />}
            label="ERS Energy"
            value={`${telemetry.ers_deployment.toFixed(0)}%`}
            color={COLORS.accent.purple}
            pct={telemetry.ers_deployment}
          />
          <StatRow
            icon={<Activity className="w-3.5 h-3.5" />}
            label="Lateral G-Force"
            value={`${telemetry.g_force_lateral.toFixed(2)} G`}
            color="#FB923C"
          />
        </div>

        {/* ── ERS Mode pill ────────────────────────────────────── */}
        <div
          className="rounded-lg px-3 py-2 border flex items-center justify-between mb-3"
          style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}
        >
          <ConceptTooltip term="ERS">
            <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider flex items-center gap-1">
              <Zap className="w-3 h-3 text-purple-400" /> ERS Mode
            </span>
          </ConceptTooltip>
          <span className="text-xs font-mono font-bold text-purple-400">{telemetry.ers_mode}</span>
        </div>

        {/* ── AI Tactical Overlay ──────────────────────────────── */}
        <div
          className="rounded-lg p-3 border"
          style={{ backgroundColor: 'var(--bg-secondary)', borderColor: `${COLORS.accent.green}33` }}
        >
          <div className="text-[10px] font-bold text-green-400 uppercase tracking-wider mb-2">
            AI Tactical Overlay
          </div>
          <div className="flex items-end justify-between gap-2">
            <div className="min-w-0">
              <div className="text-base font-display font-black text-white uppercase">
                {strategy?.driving_style.mode ?? '-'}
              </div>
              <div className="text-[10px] text-gray-500 leading-tight mt-0.5">
                {strategy?.driving_style.reason ?? 'No strategy data'}
              </div>
            </div>
            <div className="text-right shrink-0">
              <div className="text-[9px] font-mono text-gray-500 uppercase">
                Target {strategy?.driving_style.ers_target_mode ?? '-'}
              </div>
              <ConceptTooltip term="Brake Bias">
                <div className="text-xs font-bold text-white">
                  BB: {strategy?.brake_bias.recommended_bias.toFixed(0) ?? '--'}%
                </div>
              </ConceptTooltip>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DriverCard;
