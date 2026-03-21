
import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { DriverTelemetry, DriverProfile } from '../types';
import { TEAM_COLORS, COLORS } from '../constants';

interface PositionTowerProps {
  telemetry: DriverTelemetry[];
  drivers: DriverProfile[];
  selectedDriverId: string;
  onSelectDriver: (id: string) => void;
}

const PositionTower: React.FC<PositionTowerProps> = ({ telemetry, drivers, selectedDriverId, onSelectDriver }) => {
  const sortedTelemetry = [...telemetry].sort((a, b) => a.position - b.position);

  return (
    <div className="flex flex-col h-full border-r select-none transition-colors duration-300" style={{ backgroundColor: 'var(--bg-primary)', borderColor: 'var(--border-color)' }}>
      <div className="p-3 border-b flex justify-between items-center" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}>
        <span className="font-display font-bold text-xs uppercase tracking-widest text-gray-400 opacity-50">Interval</span>
        <span className="font-display font-bold text-xs uppercase tracking-widest text-gray-400 opacity-50">Laps</span>
      </div>
      <div className="flex-1 overflow-y-auto scrollbar-hide">
        <AnimatePresence initial={false}>
          {sortedTelemetry.map((t) => {
            const driver = drivers.find(d => d.driver_id === t.driver_id);
            const isSelected = selectedDriverId === t.driver_id;
            const teamColor = driver ? TEAM_COLORS[driver.team] || '#FFF' : '#FFF';

            return (
              <motion.div
                key={t.driver_id}
                layout
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ type: 'spring', stiffness: 300, damping: 30 }}
                onClick={() => onSelectDriver(t.driver_id)}
                className={`flex items-center h-10 border-b cursor-pointer transition-colors relative ${
                  isSelected ? (isSelected && document.body.classList.contains('dark') ? 'bg-white/10' : 'bg-black/5') : 'hover:bg-black/5'
                }`}
                style={{ borderColor: 'var(--border-color)' }}
              >
                {/* Team Bar */}
                <div className="w-1.5 h-full" style={{ backgroundColor: teamColor }} />
                
                {/* Position */}
                <div className="w-8 flex justify-center font-mono text-sm font-bold" style={{ color: isSelected ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
                  {t.position}
                </div>

                {/* Driver Info */}
                <div className="flex-1 px-2 flex items-center justify-between">
                  <span className={`font-display font-bold text-sm tracking-tighter ${isSelected ? 'text-[var(--text-primary)]' : 'text-gray-400'}`}>
                    {driver?.code}
                  </span>
                  
                  {/* Tire indicator */}
                  <div className="flex items-center gap-2">
                    <div 
                      className="w-3 h-3 rounded-full border border-black/20"
                      style={{ backgroundColor: COLORS.tires[t.tire_compound] }}
                    />
                    <span className="font-mono text-[10px] text-gray-500">
                      {t.position === 1 ? 'LEADER' : `+${t.gap_to_leader.toFixed(3)}`}
                    </span>
                  </div>
                </div>

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
