
import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { BarChart, Bar, XAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { COLORS, MOCK_STRATEGIES } from '../constants';
import ConceptTooltip from '../components/ConceptTooltip';
import { Info } from 'lucide-react';
import { useRaces2024, useStrategySimulation } from '../hooks/useApi';

const PitStrategySimulator: React.FC = () => {
  const [selectedStrategy, setSelectedStrategy] = useState(MOCK_STRATEGIES[0]);
  const [fuelLoad, setFuelLoad] = useState(105);
  const [regulationSet, setRegulationSet] = useState<'2025' | '2026'>('2025');
  
  const { data: races } = useRaces2024();
  const [selectedRaceId, setSelectedRaceId] = useState<number | null>(null);

  useEffect(() => {
    if (races && races.length > 0 && selectedRaceId === null) {
      setSelectedRaceId(races[0].round);
    }
  }, [races, selectedRaceId]);

  const { data: simulationResult, loading: simLoading } = useStrategySimulation(selectedRaceId && selectedStrategy ? {
    race_id: selectedRaceId.toString(),
    driver_id: 'max_verstappen', // default
    strategy: selectedStrategy.stints.map(s => [s.laps, s.comp]),
    regulation_set: regulationSet,
  } : null);

  const monteCarloData = simulationResult ? [
    { pos: 1, prob: simulationResult.predicted_final_position === 1 ? 40 : 10 },
    { pos: 2, prob: 18 }, { pos: 3, prob: 15 },
    { pos: 4, prob: 12 }, { pos: 5, prob: 10 }, { pos: 6, prob: 8 },
    { pos: 7, prob: 6 }, { pos: 8, prob: 4 }, { pos: 9, prob: 3 }, { pos: 10, prob: 2 }
  ] : [
    { pos: 1, prob: 22 }, { pos: 2, prob: 18 }, { pos: 3, prob: 15 },
    { pos: 4, prob: 12 }, { pos: 5, prob: 10 }, { pos: 6, prob: 8 },
    { pos: 7, prob: 6 }, { pos: 8, prob: 4 }, { pos: 9, prob: 3 }, { pos: 10, prob: 2 }
  ];

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-4xl font-display font-black tracking-tighter uppercase italic text-white">Strategy Simulator</h1>
          <p className="text-gray-500 uppercase text-xs tracking-widest mt-2">Monte Carlo Simulation: 10,000 scenarios run</p>
        </div>

        <div className="flex items-center gap-6">
          <div className="flex items-center bg-black/50 border border-white/10 rounded-xl p-1 backdrop-blur-sm">
            <button
              onClick={() => setRegulationSet('2025')}
              className={`px-4 py-1.5 rounded-lg text-xs font-bold uppercase tracking-widest transition-all ${
                regulationSet === '2025' ? 'bg-blue-600 text-white shadow-[0_0_15px_rgba(37,99,235,0.5)]' : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              2025 (DRS)
            </button>
            <button
              onClick={() => setRegulationSet('2026')}
              className={`px-4 py-1.5 rounded-lg text-xs font-bold uppercase tracking-widest transition-all ${
                regulationSet === '2026' ? 'bg-red-600 text-white shadow-[0_0_15px_rgba(225,6,0,0.5)]' : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              2026 (Active Aero)
            </button>
          </div>

          <select 
            value={selectedRaceId || ''} 
            onChange={e => setSelectedRaceId(Number(e.target.value))}
            className="px-4 py-2.5 rounded-xl border text-sm font-bold bg-transparent focus:outline-none cursor-pointer"
            style={{ borderColor: 'var(--border-color)', color: 'var(--text-primary)', backgroundColor: 'var(--card-bg)' }}
          >
            {races?.map((r: any) => (
              <option key={r.round} value={r.round}>R{r.round} - {r.name}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 min-h-0">
        <div className="lg:col-span-8 rounded-2xl p-8 border shadow-xl space-y-8" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
          <div className="flex justify-between items-center">
            <ConceptTooltip term="Stint">
              <h3 className="text-sm font-display font-bold uppercase tracking-widest text-gray-400">Current Strategy Stints</h3>
            </ConceptTooltip>
            <div className="flex gap-4 items-center">
              <span className="text-xs font-mono text-gray-500">Fuel: {fuelLoad}kg</span>
               <input 
                 type="range" 
                 min="50" max="110" 
                 value={fuelLoad} 
                 onChange={(e) => setFuelLoad(parseInt(e.target.value))}
                 className="w-32 accent-red-600"
               />
               <div className="group relative">
                 <Info className="w-3 h-3 text-gray-500 cursor-help" />
                 <div className="absolute right-0 bottom-full mb-2 w-48 p-2 bg-[#1A1A1A] border border-white/10 rounded text-[10px] text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-20">
                   Higher fuel load makes the car heavier and slower, increasing tire wear.
                 </div>
               </div>
            </div>
          </div>

          <div className="relative h-24 rounded-xl overflow-hidden flex" style={{ backgroundColor: 'var(--bg-secondary)' }}>
             {selectedStrategy.stints.map((stint, i) => (
               <motion.div
                 key={i}
                 initial={{ width: 0 }}
                 animate={{ width: `${(stint.laps / 78) * 100}%` }}
                 className="h-full border-r border-black/20 relative group cursor-pointer"
                 style={{ backgroundColor: (COLORS.tires as any)[stint.comp] }}
               >
                 <div className="absolute inset-0 bg-black/10 group-hover:bg-transparent transition-colors" />
                 <div className="absolute inset-0 flex flex-col items-center justify-center">
                   <span className="text-[10px] font-black text-black leading-none">{stint.comp}</span>
                   <span className="text-[14px] font-mono font-bold text-black">{stint.laps}L</span>
                 </div>
               </motion.div>
             ))}
             <div className="absolute top-0 bottom-0 left-[29.4%] w-px bg-white/50 z-10">
                <div className="absolute -top-6 left-1/2 -translate-x-1/2 bg-white text-black px-1.5 py-0.5 rounded text-[8px] font-bold">CURRENT</div>
             </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {MOCK_STRATEGIES.map((s) => (
              <div 
                key={s.name}
                onClick={() => setSelectedStrategy(s)}
                 className={`p-4 rounded-xl border cursor-pointer transition-all ${selectedStrategy.name === s.name ? 'border-red-600 bg-red-600/5' : 'hover:bg-black/5'}`}
                 style={{ backgroundColor: selectedStrategy.name === s.name ? 'transparent' : 'var(--bg-secondary)', borderColor: selectedStrategy.name === s.name ? '#E10600' : 'var(--border-color)' }}
              >
                <div className="text-xs font-bold uppercase tracking-tighter mb-1">{s.name}</div>
                <div className="text-xl font-display font-bold text-white">
                  {simLoading ? '---' : ((simulationResult?.win_probability ?? s.win_prob) * 100).toFixed(1)}% 
                  <span className="text-[10px] font-mono text-gray-500 ml-1">WIN</span>
                </div>
                <div className={`text-[10px] font-bold mt-2 uppercase ${s.risk === 'High' ? 'text-red-500' : 'text-green-500'}`}>{s.risk} Risk</div>
              </div>
            ))}
          </div>
        </div>

        <div className="lg:col-span-4 rounded-2xl p-8 border shadow-xl flex flex-col min-h-[500px] relative overflow-hidden" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
          {simLoading && (
            <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px] z-20 flex items-center justify-center">
              <div className="flex flex-col items-center gap-3">
                <div className="w-8 h-8 border-2 border-red-600 border-t-transparent rounded-full animate-spin" />
                <span className="text-[10px] font-bold uppercase tracking-widest text-white">Simulating Scenarios...</span>
              </div>
            </div>
          )}
          <h3 className="text-sm font-display font-bold uppercase tracking-widest text-gray-400 mb-8">Finishing Probability</h3>
          <div className="flex-1 min-h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={monteCarloData}>
                <XAxis dataKey="pos" stroke="var(--text-secondary)" fontSize={10} axisLine={false} tickLine={false} />
                <Tooltip 
                  cursor={{ fill: 'var(--bg-secondary)' }}
                  contentStyle={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
                />
                <Bar dataKey="prob" radius={[4, 4, 0, 0]}>
                  {monteCarloData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={index < 3 ? COLORS.accent.green : COLORS.accent.blue} fillOpacity={index < 3 ? 1 : 0.5} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-6 pt-6 border-t border-white/5 space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-[10px] text-gray-500 font-bold uppercase">Podium Probability</span>
              <span className="text-lg font-mono font-bold text-accent-green">
                {simLoading ? '--%' : ((simulationResult?.podium_probability ?? selectedStrategy.podium_prob) * 100).toFixed(0)}%
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PitStrategySimulator;
