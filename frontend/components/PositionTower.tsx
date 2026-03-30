/**
 * @file components/PositionTower.tsx
 * @description Vertically-scrollable race standings sidebar.
 *
 * Renders the live position tower used in the Race Command Center.
 * Each row represents one driver on track: position, team colour bar,
 * driver code, tyre compound, and gap to leader.
 *
 * Rows are sorted by on-track position and animate their vertical position
 * via Framer Motion's `layout` prop so position changes transition smoothly.
 *
 * On mobile the component is hidden in favour of a slide-up sheet; the
 * parent (`RaceCommandCenter`) controls visibility via a tab/toggle.
 */

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { DriverTelemetry, DriverProfile } from '../types';
import { TEAM_COLORS, COLORS } from '../constants';

// ─── Types ───────────────────────────────────────────────────────────────────

/** Props for the PositionTower component. */
interface PositionTowerProps {
  /** Array of per-driver telemetry snapshots for the current lap. */
  telemetry: DriverTelemetry[];
  /** Full driver profile list used to look up team, code, and metadata. */
  drivers: DriverProfile[];
  /** driver_id of the currently selected driver (highlighted in the tower). */
  selectedDriverId: string;
  /** Callback invoked when the user taps a driver row. */
  onSelectDriver: (id: string) => void;
}

// ─── Component ───────────────────────────────────────────────────────────────

/**
 * Renders a compact, animated race standings column.
 *
 * @param telemetry        - Current-lap driver telemetry snapshots.
 * @param drivers          - Full driver profile list for metadata lookup.
 * @param selectedDriverId - ID of the driver whose row should be highlighted.
 * @param onSelectDriver   - Called with the driver ID when a row is clicked.
 */
const PositionTower: React.FC<PositionTowerProps> = ({
  telemetry,
  drivers,
  selectedDriverId,
  onSelectDriver,
}) => {
  /** Sort telemetry descending by on-track position (P1 first). */
  const sortedTelemetry = [...telemetry].sort((a, b) => a.position - b.position);

  return (
    <div
      className="flex flex-col h-full border-r select-none transition-colors duration-300"
      style={{ backgroundColor: 'var(--bg-primary)', borderColor: 'var(--border-color)' }}
    >
      {/* Column headers */}
      <div
        className="p-3 border-b flex justify-between items-center"
        style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}
      >
        <span className="font-display font-bold text-xs uppercase tracking-widest text-gray-400 opacity-50">
          Interval
        </span>
        <span className="font-display font-bold text-xs uppercase tracking-widest text-gray-400 opacity-50">
          Laps
        </span>
      </div>

      {/* Scrollable driver rows */}
      <div className="flex-1 overflow-y-auto scrollbar-hide">
        <AnimatePresence initial={false}>
          {sortedTelemetry.map((t) => {
            const driver    = drivers.find((d) => d.driver_id === t.driver_id);
            const isSelected = selectedDriverId === t.driver_id;
            const teamColor  = driver ? (TEAM_COLORS[driver.team] || '#FFF') : '#FFF';

            /** Gap display: P1 shows "LEADER", all others show "+X.XXX". */
            const gapLabel = t.position === 1
              ? 'LEADER'
              : `+${t.gap_to_leader.toFixed(3)}`;

            return (
              <motion.div
                key={t.driver_id}
                layout
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ type: 'spring', stiffness: 300, damping: 30 }}
                onClick={() => onSelectDriver(t.driver_id)}
                className={`flex items-center h-9 border-b cursor-pointer transition-colors relative ${
                  isSelected
                    ? 'bg-black/5 dark:bg-white/10'
                    : 'hover:bg-black/5 dark:hover:bg-white/5'
                }`}
                style={{ borderColor: 'var(--border-color)' }}
              >
                {/* Team colour bar */}
                <div className="w-1.5 h-full" style={{ backgroundColor: teamColor }} />

                {/* Grid position number */}
                <div
                  className="w-6 flex justify-center font-mono text-sm font-bold"
                  style={{ color: isSelected ? 'var(--text-primary)' : 'var(--text-secondary)' }}
                >
                  {t.position}
                </div>

                {/* Driver code + tyre + gap */}
                <div className="flex-1 px-1 flex items-center justify-between min-w-0">
                  <span
                    className={`font-display font-bold text-sm tracking-tighter truncate ${
                      isSelected ? 'text-[var(--text-primary)]' : 'text-gray-400'
                    }`}
                  >
                    {driver?.code ?? t.driver_id.slice(0, 3).toUpperCase()}
                  </span>

                  <div className="flex items-center gap-1.5 shrink-0">
                    {/* Tyre compound colour dot */}
                    <div
                      className="w-3 h-3 rounded-full border border-black/20"
                      style={{ backgroundColor: COLORS.tires[t.tire_compound] }}
                    />
                    <span className="font-mono text-[10px] text-gray-500 whitespace-nowrap">
                      {gapLabel}
                    </span>
                  </div>
                </div>

                {/* Active indicator bar — slides between rows via layoutId */}
                {isSelected && (
                  <motion.div
                    layoutId="active-indicator"
                    className="absolute right-0 top-0 bottom-0 w-1 bg-red-600 shadow-[0_0_10px_rgba(225,6,0,0.5)]"
                  />
                )}
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </div>
  );
};

export default PositionTower;
