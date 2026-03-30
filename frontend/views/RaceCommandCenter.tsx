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

import ConceptTooltip from '../components/ConceptTooltip';
import { MOCK_DRIVERS, MOCK_RACE_STATE, getMockTelemetry, getMockStrategy, COLORS, F1_GLOSSARY } from '../constants';
import { DriverTelemetry, DriverProfile, TireCompound } from '../types';
import { useDrivers, useBackendStatus, useRaces2024, useOvertakeMetric, useSafetyCarProb, useRaceState, useStrategyRecommendation } from '../hooks/useApi';
import { fetchRaceState, fetchStrategyRecommendation } from '../services/endpoints';

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
  const { data: races } = useRaces2024();

  const [selectedRaceId, setSelectedRaceId] = useState<number | null>(null);
  
  // Predictive ML Metrics
  const { data: overtakeData } = useOvertakeMetric('VER', 'NOR'); // Example pairing
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
          
          const mockDriver = MOCK_DRIVERS.find(d => d.driver_id === result.driver.id || d.code === result.driver.code);
          if (mockDriver) return { ...mockDriver, driver_id: result.driver.id, team: result.constructor };

          return {
            driver_id: result.driver.id,
            name: result.driver.name,
            team: result.constructor,
            code: result.driver.code || result.driver.id.slice(0, 3).toUpperCase(),
            nationality: 'Unknown',
            career_races: 50,
            career_wins: 0,
            aggression_score: 80,
            consistency_score: 82,
            pressure_response: 75,
            tire_management: 80,
            wet_weather_skill: 78,
            qualifying_pace: 85,
            race_pace: 83,
            overtaking_ability: 79,
            defensive_ability: 81,
            fuel_efficiency: 80,
            experience_years: 3,
            rookie_status: false,
          } as DriverProfile;
        });
      return raceDrivers.length > 0 ? raceDrivers.slice(0, 20) : MOCK_DRIVERS;
    }
    return MOCK_DRIVERS;
  }, [selectedRace, apiDrivers]);

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

  const { data: liveRaceData, loading: raceLoading } = useRaceState(selectedRaceId?.toString() || '2024_1', 23);
  const { data: liveStrategy, loading: strategyLoading } = useStrategyRecommendation(selectedDriverId ? {
    race_id: selectedRaceId?.toString() || '2024_1',
    driver_id: selectedDriverId,
    current_lap: liveRaceData?.raceState.current_lap || 1,
    current_compound: 'SOFT', // Should ideally come from liveRaceData
    fuel_level: 45,
    track_temp: liveRaceData?.raceState.track_temp_celsius || 35,
    air_temp: liveRaceData?.raceState.air_temp_celsius || 25,
  } : null);

  // Initialize data from API with mock fallbacks only if offline
  useEffect(() => {
    if (liveRaceData) {
      setRaceState(liveRaceData.raceState);
      setTelemetries(liveRaceData.driverStates.map(ds => {
        const baseMock = getMockTelemetry(ds.driver_id, ds.position);
        return {
          ...baseMock,
          driver_id: ds.driver_id,
          position: ds.position,
          gap_to_leader: ds.gap_to_leader,
          tire_compound: ds.tire_compound as TireCompound,
          tire_age_laps: ds.tire_age_laps,
          fuel_remaining_kg: ds.fuel_remaining_kg,
          current_lap_time: ds.lap_time_ms / 1000,
          gap_to_ahead: ds.gap_to_ahead,
        } as DriverTelemetry;
      }));
    }
  }, [liveRaceData]);

  const selectedDriver = drivers.find(d => d.driver_id === selectedDriverId) || drivers[0];
  const selectedTelemetry = telemetries.find(t => t.driver_id === selectedDriverId) || telemetries[0];
  const selectedStrategy = liveStrategy || getMockStrategy(selectedDriverId);

  const lapTimeData = useMemo(() => Array.from({ length: 15 }, (_, i) => {
    const lap = i + 8;
    // Simple deterministic pseudo-random offset based on lap and driver
    const seed = (lap * 13) + (selectedDriverId.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0));
    const deterministicRandom = ((seed * 9301 + 49297) % 233280) / 233280;
    
    return {
      lap,
      time: 74.2 + deterministicRandom * 0.4,
      benchmark: 74.1,
    };
  }), [selectedDriverId]);

  if (!selectedDriver || !selectedTelemetry) return null;

  return (
    <div className="flex h-full overflow-hidden">
      <PositionTower
        telemetry={telemetries}
        drivers={drivers}
        selectedDriverId={selectedDriverId}
        onSelectDriver={setSelectedDriverId}
      />

      <div className="flex-1 p-4 md:p-6 overflow-hidden flex flex-col gap-4 md:gap-6">
        <div className="flex justify-between items-end border-b pb-4 shrink-0" style={{ borderColor: 'var(--border-color)' }}>
          <div>
            <div className="flex items-center gap-4">
              <h1 className="text-4xl font-display font-black tracking-tighter uppercase italic">{selectedRace ? selectedRace.name : raceState.circuit}</h1>
              {/* Race Selector */}
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
            <div className="flex gap-6 mt-2">
              <Badge label="LAP" value={`${raceState.current_lap} / ${raceState.total_laps}`} />
              <Badge label="GRIP" value={`${raceState.track_grip_level}%`} color={COLORS.accent.blue} />
              <Badge label="STATUS" value={raceState.flag} color={COLORS.accent.green} pulse />
              <div className="h-8 w-px bg-white/10 mx-2 hidden md:block" />
              <Badge 
                label="OVERTAKE PROB" 
                value={overtakeData ? `${(overtakeData.probability * 100).toFixed(1)}%` : '12.4%'} 
                color={COLORS.accent.yellow} 
              />
              <Badge 
                label="SC RISK" 
                value={safetyCarData ? `${(safetyCarData.probability * 100).toFixed(1)}%` : '8.2%'} 
                color={safetyCarData && safetyCarData.probability > 0.4 ? COLORS.accent.red : COLORS.accent.blue}
                pulse={safetyCarData && safetyCarData.probability > 0.5}
              />
            </div>
          </div>
          <div className="text-right flex flex-col items-end gap-2">
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

        {/* Header Stats: Mobile Stack, Desktop Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6 flex-1 min-h-0">
          <div className="lg:col-span-1 h-full min-h-0 overflow-y-auto pr-2 pb-16 md:pb-0 hide-scrollbar">
            <DriverCard
              telemetry={selectedTelemetry}
              driver={selectedDriver}
              strategy={selectedStrategy}
            />
          </div>

          <div className="lg:col-span-3 flex flex-col gap-4 md:gap-6 h-full min-h-0">
            <div className="rounded-xl p-4 md:p-6 border flex-1 flex flex-col shadow-xl min-h-0" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
              <div className="flex justify-between items-center mb-4 md:mb-6 shrink-0">
                <h3 className="text-xs font-display font-bold uppercase tracking-widest text-gray-400">Sector Consistency</h3>
                <div className="flex gap-4">
                  <LegendItem color={COLORS.accent.red} label={selectedDriver.code} />
                  <LegendItem color="#333" label="Session Benchmark" />
                </div>
              </div>
              <div className="w-full flex-1 min-h-[150px]">
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

            <div className="rounded-xl p-4 md:p-6 border shadow-xl shrink-0" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
              <h3 className="text-xs font-display font-bold uppercase tracking-widest text-gray-400 mb-4">Monte Carlo Simulation Outputs</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-[11px] font-mono">
                  <thead>
                    <tr className="text-gray-500 border-b border-black/10 dark:border-white/10 uppercase">
                      <th className="py-2">Path Variant</th>
                      <th className="py-2">Pit Matrix</th>
                      <th className="py-2 text-right">Win Probability</th>
                      <th className="py-2 text-right">Risk Factor</th>
                    </tr>
                  </thead>
                  <tbody style={{ color: 'var(--text-secondary)' }}>
                    <tr className="border-b border-black/5 dark:border-white/5 hover:bg-black/5 dark:hover:bg-white/5 transition-colors group">
                      <td className="py-3 font-bold text-gray-900 dark:text-white flex items-center gap-2">
                        Variant-Alpha
                        <ConceptTooltip term="Undercut">
                          <span className="text-accent-blue/60 group-hover:text-accent-blue transition-colors cursor-help">(Undercut)</span>
                        </ConceptTooltip>
                      </td>
                      <td className="py-3">L28, L55</td>
                      <td className="py-3 text-right text-accent-green">18.4%</td>
                      <td className="py-3 text-right text-red-500">AGGRESSIVE</td>
                    </tr>
                    <tr className="border-b border-black/5 dark:border-white/5 hover:bg-black/5 dark:hover:bg-white/5 transition-colors">
                      <td className="py-3 font-bold text-gray-900 dark:text-white">Variant-Gamma (Optimal)</td>
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
            className="fixed right-6 top-24 w-80 z-40 p-5 rounded-2xl bg-white/95 dark:bg-[#1A1A1A]/95 backdrop-blur-xl border border-accent-blue/20 shadow-[0_20px_50px_rgba(0,0,0,0.1)] dark:shadow-[0_20px_50px_rgba(0,0,0,0.5)]"
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
            <div className="mt-6 pt-4 border-t border-black/10 dark:border-white/10">
              <p className="text-[10px] text-gray-500 italic">Hover over dashed terms anywhere in the dashboard for instant definitions.</p>
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
        <span className="text-xs font-bold text-gray-900 dark:text-white">{title}</span>
      </div>
      <p className="text-[10px] text-gray-400 leading-snug">{description}</p>
    </div>
  );
}

export default RaceCommandCenter;
