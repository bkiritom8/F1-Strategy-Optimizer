
import React from 'react';
import { motion } from 'framer-motion';
import { DriverTelemetry, DriverProfile, StrategyRecommendation } from '../types';
import { COLORS, TEAM_COLORS } from '../constants';
import { Zap, Thermometer, Fuel, Wind, ChevronRight, Activity } from 'lucide-react';
import ConceptTooltip from './ConceptTooltip';

interface DriverCardProps {
  telemetry: DriverTelemetry;
  driver: DriverProfile;
  strategy: StrategyRecommendation;
}

const DriverCard: React.FC<DriverCardProps> = ({ telemetry, driver, strategy }) => {
  // F1 cars start with ~110kg max. We'll use 110 as the baseline for the gauge.
  const maxFuel = 110;
  const fuelPercentage = (telemetry.fuel_remaining_kg / maxFuel) * 100;
  
  const getFuelColor = (pct: number) => {
    if (pct > 30) return COLORS.accent.green;
    if (pct > 10) return COLORS.accent.yellow;
    return COLORS.accent.red;
  };

  const fuelColor = getFuelColor(fuelPercentage);

  return (
    <div className="rounded-xl p-6 border shadow-2xl relative overflow-hidden min-h-[450px]" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
      <div 
        className="absolute top-0 right-0 w-32 h-32 opacity-10 pointer-events-none" 
        style={{ background: `radial-gradient(circle at top right, ${TEAM_COLORS[driver.team]}, transparent)` }} 
      />
      
      {/* Header Info */}
      <div className="flex justify-between items-start mb-6">
        <div>
          <h2 className="text-3xl font-display font-bold leading-none">{driver.name}</h2>
          <p className="text-gray-500 font-medium uppercase tracking-widest text-xs mt-1">{driver.team}</p>
        </div>
        <div className="text-right">
          <div className="text-4xl font-mono font-bold text-accent-red leading-none">P{telemetry.position}</div>
          <div className="text-[10px] text-gray-500 mt-1 uppercase">Interval: +{telemetry.gap_to_ahead}s</div>
        </div>
      </div>

      {/* Grid of Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatItem icon={<Wind className="w-4 h-4" />} label="Aero Loss" value={`${telemetry.aero_loss_percent}%`} color={telemetry.aero_loss_percent > 10 ? COLORS.accent.red : COLORS.accent.blue} />
        <StatItem icon={<Fuel className="w-4 h-4" />} label="Fuel" value={`${telemetry.fuel_remaining_kg.toFixed(1)} KG`} color={fuelColor} />
        <StatItem icon={<Thermometer className="w-4 h-4" />} label="Tire Age" value={`${telemetry.tire_age_laps} LAPS`} color={COLORS.tires[telemetry.tire_compound]} />
        <StatItem icon={<Zap className="w-4 h-4 text-purple-500" />} label="ERS Energy" value={`${telemetry.ers_deployment.toFixed(0)}%`} color={COLORS.accent.purple} />
        <StatItem icon={<Activity className="w-4 h-4 text-orange-500" />} label="G-Force" value={`${telemetry.g_force_lateral.toFixed(1)}G`} color="#FB923C" />
      </div>

      {/* Energy & Fuel Management Bars */}
      <div className="space-y-4 mb-6">
        {/* ERS Bar */}
        <div className="rounded-lg p-4 border" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}>
          <div className="flex justify-between items-center mb-2">
            <ConceptTooltip term="ERS">
              <span className="text-[10px] font-bold text-gray-500 uppercase tracking-tighter flex items-center gap-1">
                <Zap className="w-3 h-3 text-purple-500" /> ERS Mode: {telemetry.ers_mode}
              </span>
            </ConceptTooltip>
            <span className="text-[10px] text-purple-400 font-mono">{telemetry.ers_deployment.toFixed(0)}%</span>
          </div>
          <div className="h-1.5 w-full rounded-full overflow-hidden" style={{ backgroundColor: 'var(--bg-tertiary)' }}>
            <motion.div 
              initial={{ width: 0 }}
              animate={{ width: `${telemetry.ers_deployment}%` }}
              className="h-full bg-purple-500 shadow-[0_0_10px_rgba(168,85,247,0.5)]" 
            />
          </div>
        </div>

        {/* Fuel Gauge Bar */}
        <div className="rounded-lg p-4 border" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}>
          <div className="flex justify-between items-center mb-2">
            <span className="text-[10px] font-bold text-gray-500 uppercase tracking-tighter flex items-center gap-1">
              <Fuel className="w-3 h-3" style={{ color: fuelColor }} /> Fuel Status
            </span>
            <span className="text-[10px] font-mono" style={{ color: fuelColor }}>{fuelPercentage.toFixed(1)}%</span>
          </div>
          <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
            <motion.div 
              initial={{ width: 0 }}
              animate={{ width: `${fuelPercentage}%` }}
              style={{ backgroundColor: fuelColor }}
              className="h-full shadow-[0_0_10px_rgba(255,255,255,0.1)]" 
            />
          </div>
          <div className="flex justify-between mt-2">
             <span className="text-[8px] text-gray-600 font-bold uppercase">Target: {strategy.driving_style.fuel_target_kg_per_lap} kg/L</span>
             <span className="text-[8px] text-gray-600 font-bold uppercase">Rem: {telemetry.fuel_remaining_kg.toFixed(1)}kg</span>
          </div>
        </div>
      </div>

      {/* Recommended Strategy Badge */}
      <div className="border rounded-lg p-4" style={{ backgroundColor: 'var(--bg-tertiary)', borderColor: 'var(--border-color)' }}>
        <div className="flex items-center gap-2 mb-2">
          <span className="text-[10px] font-bold text-accent-green uppercase tracking-tighter">AI Tactical Overlay</span>
        </div>
        <div className="flex justify-between items-end">
          <div>
            <div className="text-xl font-display font-bold text-white uppercase tracking-wider">{strategy.driving_style.mode}</div>
            <div className="text-[10px] text-gray-500 max-w-[200px] leading-tight mt-1">{strategy.driving_style.reason}</div>
          </div>
          <div className="text-right">
             <div className="text-xs font-mono text-gray-400 uppercase">Target {strategy.driving_style.ers_target_mode}</div>
             <ConceptTooltip term="Brake Bias">
               <div className="text-sm font-bold text-white">Target BB: {strategy.brake_bias.recommended_bias}%</div>
             </ConceptTooltip>
          </div>
        </div>
      </div>
    </div>
  );
};

const StatItem = ({ icon, label, value, color }: { icon: React.ReactNode, label: string, value: string, color: string }) => (
  <div className="rounded-lg p-3 border hover:bg-black/5 transition-colors" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}>
    <div className="flex items-center gap-2 mb-1" style={{ color }}>
      {icon}
      <span className="text-[10px] font-bold uppercase tracking-widest text-gray-500">{label}</span>
    </div>
    <div className="text-lg font-mono font-bold">{value}</div>
  </div>
);

export default DriverCard;
