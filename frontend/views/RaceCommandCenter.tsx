/**
 * @file RaceCommandCenter.tsx
 * @description Primary operational view for Apex Intelligence.
 * Linked to: GET /api/v1/race/state, GET /api/v1/drivers, POST /strategy/recommend
 */

import React, { useState, useEffect, useMemo } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { motion } from 'framer-motion';
import { AlertTriangle, HelpCircle, ChevronRight, Info } from 'lucide-react';
import PositionTower from '../components/PositionTower';
import DriverCard from '../components/DriverCard';
import AIStrategist from '../components/AIStrategist';
import ConceptTooltip from '../components/ConceptTooltip';
import ConnectionBadge from '../components/ConnectionBadge';
import { MOCK_DRIVERS, MOCK_RACE_STATE, getMockTelemetry, getMockStrategy, COLORS, F1_GLOSSARY } from '../constants';
import { DriverTelemetry, DriverProfile } from '../types';
import { useDrivers, useBackendStatus } from '../hooks/useApi';
import { fetchRaceState, fetchStrategyRecommendation } from '../api/endpoints';

interface BadgeProps { label: string; value: string; color?: string; pulse?: boolean; }
function Badge({ label, value, color, pulse }: BadgeProps) {
  return (
    <div className="flex flex-col">
      <span className="text-[9px] font-bold text-gray-400 uppercase tracking-widest">{label}</span>
      <div className="flex items-center gap-2">
        {pulse && <div className="w-2 h-2 rounded-full bg-current animate-pulse" style={{ color: color || '#FFF' }} />}
        <span className="text-lg font-mono font-bold" style={{ color: color || '#FFF' }}>{value}</span>
      </div>
    </div>
  );
}

function LegendItem({ color, label }: { color: string, label: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
      <span className="text-[10px] font-bold text-gray-500 uppercase">{label}</span>
    </div>
  );
}

const RaceCommandCenter: React.FC = () => {
  const { data: apiDrivers, isLive: driversLive } = useDrivers();
  const { online } = useBackendStatus();

  // Use all drivers from API if available, else mock
  const drivers: DriverProfile[] = useMemo(() => {
    if (apiDrivers && apiDrivers.length > 0) {
      return apiDrivers;
    }
    return MOCK_DRIVERS;
  }, [apiDrivers]);

  const [selectedDriverId, setSelectedDriverId] = useState<string>('');
  const [showBeginnerTips, setShowBeginnerTips] = useState(false);
  const [raceState, setRaceState] = useState(MOCK_RACE_STATE);
  const [telemetries, setTelemetries] = useState<DriverTelemetry[]>([]);

  // Set initial selected driver when drivers load
  useEffect(() => {
    if (drivers.length > 0 && !selectedDriverId) {
      setSelectedDriverId(drivers[0].driver_id);
    }
  }, [drivers, selectedDriverId]);

  // Initialize telemetries from drivers
  useEffect(() => {
    setTelemetries(drivers.map((d, i) => getMockTelemetry(d.driver_id, i + 1)));
  }, [drivers]);

  // Try to load real race state
  useEffect(() => {
    if (!online) return;
    fetchRaceState('2024_1', 23)
      .then(({ raceState: rs }) => {
        setRaceState(prev => ({ ...prev, ...rs }));
      })
      .catch(() => { /* keep mock */ });
  }, [online]);

  // Simulate telemetry jitter
  useEffect(() => {
    const interval = setInterval(() => {
      setTelemetries(prev => prev.map(t => ({
        ...t,
        ers_deployment: Math.max(0, Math.min(100, t.ers_deployment + (Math.random() * 2 - 1)))
      })));
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  const selectedDriver = drivers.find(d => d.driver_id === selectedDriverId) || drivers[0];
  const selectedTelemetry = telemetries.find(t => t.driver_id === selectedDriverId) || telemetries[0];
  const selectedStrategy = getMockStrategy(selectedDriverId);

  const lapTimeData = Array.from({ length: 15 }, (_, i) => ({
    lap: i + 8,
    time: 74.2 + Math.random() * 0.4,
    benchmark: 74.1,
  }));

  if (!selectedDriver || !selectedTelemetry) return null;

  return (
    <div className="flex h-full overflow-hidden">
      <PositionTower
        telemetry={telemetries}
        drivers={drivers}
        selectedDriverId={selectedDriverId}
        onSelectDriver={setSelectedDriverId}
      />

      <div className="flex-1 p-8 overflow-y-auto space-y-8">
        <div className="flex justify-between items-end border-b pb-4" style={{ borderColor: 'var(--border-color)' }}>
          <div>
            <h1 className="text-4xl font-display font-black tracking-tighter uppercase italic">{raceState.circuit}</h1>
            <div className="flex gap-6 mt-2">
              <Badge label="LAP" value={`${raceState.current_lap} / ${raceState.total_laps}`} />
              <Badge label="GRIP" value={`${raceState.track_grip_level}%`} color={COLORS.accent.blue} />
              <Badge label="STATUS" value={raceState.flag} color={COLORS.accent.green} pulse />
            </div>
          </div>
          <div className="text-right flex flex-col items-end gap-2">
            <ConnectionBadge isLive={driversLive} />
            <button
              onClick={() => setShowBeginnerTips(!showBeginnerTips)}
              className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-accent-blue/10 border border-accent-blue/20 text-accent-blue text-[10px] font-bold uppercase hover:bg-accent-blue/20 transition-colors"
            >
              <HelpCircle className="w-3 h-3" />
              {showBeginnerTips ? 'Hide Beginner Tips' : 'Show Beginner Tips'}
            </button>
            <div className="text-[10px] text-gray-500 font-bold uppercase tracking-widest">Global Telemetry Hub</div>
            <div className="text-2xl font-mono font-bold">01:14:23</div>
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-12 gap-8">
          <div className="xl:col-span-5 space-y-8">
            <DriverCard
              telemetry={selectedTelemetry}
              driver={selectedDriver}
              strategy={selectedStrategy}
            />
            <AIStrategist />
          </div>

          <div className="xl:col-span-7 space-y-8">
            <div className="rounded-xl p-6 border h-[350px] shadow-xl" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
              <div className="flex justify-between items-center mb-6">
                <h3 className="text-xs font-display font-bold uppercase tracking-widest text-gray-400">Sector Consistency</h3>
                <div className="flex gap-4">
                  <LegendItem color={COLORS.accent.red} label={selectedDriver.code} />
                  <LegendItem color="#333" label="Session Benchmark" />
                </div>
              </div>
              <div className="w-full h-[250px]">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={lapTimeData}>
                    <defs>
                      <linearGradient id="colorTime" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={COLORS.accent.red} stopOpacity={0.2} />
                        <stop offset="95%" stopColor={COLORS.accent.red} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" vertical={false} />
                    <XAxis dataKey="lap" stroke="var(--text-secondary)" fontSize={10} tick={{ fill: 'var(--text-secondary)' }} />
                    <YAxis domain={['auto', 'auto']} stroke="var(--text-secondary)" fontSize={10} tick={{ fill: 'var(--text-secondary)' }} />
                    <Tooltip
                      contentStyle={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', fontSize: '12px', color: 'var(--text-primary)' }}
                      itemStyle={{ color: 'var(--text-primary)' }}
                    />
                    <Area type="monotone" dataKey="time" stroke={COLORS.accent.red} fillOpacity={1} fill="url(#colorTime)" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="rounded-xl p-6 border shadow-xl" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
              <h3 className="text-xs font-display font-bold uppercase tracking-widest text-gray-400 mb-4">Monte Carlo Simulation Outputs</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-[11px] font-mono">
                  <thead>
                    <tr className="text-gray-500 border-b border-white/10 uppercase">
                      <th className="py-2">Path Variant</th>
                      <th className="py-2">Pit Matrix</th>
                      <th className="py-2 text-right">Win Probability</th>
                      <th className="py-2 text-right">Risk Factor</th>
                    </tr>
                  </thead>
                  <tbody style={{ color: 'var(--text-secondary)' }}>
                    <tr className="border-b border-white/5 hover:bg-white/5 transition-colors group">
                      <td className="py-3 font-bold text-white flex items-center gap-2">
                        Variant-Alpha
                        <ConceptTooltip term="Undercut">
                          <span className="text-accent-blue/60 group-hover:text-accent-blue transition-colors cursor-help">(Undercut)</span>
                        </ConceptTooltip>
                      </td>
                      <td className="py-3">L28, L55</td>
                      <td className="py-3 text-right text-accent-green">18.4%</td>
                      <td className="py-3 text-right text-red-500">AGGRESSIVE</td>
                    </tr>
                    <tr className="border-b border-white/5 hover:bg-white/5 transition-colors">
                      <td className="py-3 font-bold text-white">Variant-Gamma (Optimal)</td>
                      <td className="py-3">L32, L58</td>
                      <td className="py-3 text-right text-accent-green">22.1%</td>
                      <td className="py-3 text-right text-yellow-500">BALANCED</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>

        {showBeginnerTips && (
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            className="fixed right-6 top-24 w-80 z-40 p-5 rounded-2xl bg-[#1A1A1A]/95 backdrop-blur-xl border border-accent-blue/20 shadow-[0_20px_50px_rgba(0,0,0,0.5)]"
          >
            <div className="flex items-center gap-2 mb-4">
              <div className="p-2 rounded-lg bg-accent-blue/20 text-accent-blue">
                <Info className="w-4 h-4" />
              </div>
              <h3 className="text-sm font-display font-bold uppercase tracking-wider">Race Day Intelligence</h3>
            </div>
            <div className="space-y-4">
              <Tip complexity="Beginner" title="Look for the Delta" description="The 'Delta' shows the real-time gap between cars. If it's decreasing, an overtake might be coming!" />
              <Tip complexity="Intermediate" title="ERS Management" description="Watch the Purple ERS bar. Drivers save energy (Harvest) to use later for attacking (Overtake)." />
              <Tip complexity="Expert" title="Dirty Air Effects" description="When a car is within 1s of another, 'Dirty Air' reduces their grip, making it harder to stay close in corners." />
            </div>
            <div className="mt-6 pt-4 border-t border-white/10">
              <p className="text-[10px] text-gray-400 italic">Hover over dashed terms anywhere in the dashboard for instant definitions.</p>
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
};

function Tip({ title, description, complexity }: { title: string, description: string, complexity: 'Beginner' | 'Intermediate' | 'Expert' }) {
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
