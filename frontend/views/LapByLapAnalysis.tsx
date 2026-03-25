
import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, ChevronUp, Zap, Clock, TrendingUp } from 'lucide-react';
import { LineChart, Line, ResponsiveContainer } from 'recharts';

const LapByLapAnalysis: React.FC = () => {
  const [expandedLap, setExpandedLap] = useState<number | null>(null);

  const laps = Array.from({ length: 20 }, (_, i) => ({
    number: 23 - i,
    time: "1:14.231",
    delta: i === 0 ? "-0.123" : "+0.045",
    pos: 1,
    tire_wear: 78 - i,
    fuel: 42.5 + i,
    telemetry: Array.from({ length: 10 }, () => ({ v: Math.random() * 100 }))
  }));

  return (
    <div className="p-8 max-w-5xl mx-auto space-y-8">
      <div>
        <h1 className="text-4xl font-display font-black tracking-tighter uppercase italic">Lap Analysis</h1>
        <p className="text-gray-500 uppercase text-xs tracking-widest mt-2">Historical telemetry archives: Race 2024.08</p>
      </div>

      <div className="space-y-3">
        {laps.map((lap) => (
          <div 
            key={lap.number}
            className={`rounded-xl border border-white/5 overflow-hidden transition-all shadow-sm ${expandedLap === lap.number ? 'ring-1 ring-red-600' : ''}`}
            style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}
          >
            <div 
              className="p-4 flex items-center justify-between cursor-pointer hover:bg-black/5 transition-colors"
              onClick={() => setExpandedLap(expandedLap === lap.number ? null : lap.number)}
            >
              <div className="flex items-center gap-6">
                <span className="text-2xl font-display font-black text-gray-400 w-12 italic">L{lap.number}</span>
                <div>
                  <div className="text-lg font-mono font-bold" style={{ color: 'var(--text-primary)' }}>{lap.time}</div>
                  <div className={`text-[10px] font-bold ${lap.delta.startsWith('-') ? 'text-accent-green' : 'text-accent-red'}`}>{lap.delta} vs prev</div>
                </div>
              </div>

              <div className="flex gap-8 items-center">
                <div className="hidden md:flex flex-col items-end">
                   <span className="text-[9px] text-gray-500 font-bold uppercase">Tire Wear</span>
                   <span className="text-sm font-mono" style={{ color: 'var(--text-secondary)' }}>{lap.tire_wear}%</span>
                </div>
                <div className="hidden md:flex flex-col items-end">
                   <span className="text-[9px] text-gray-500 font-bold uppercase">Fuel Rem.</span>
                   <span className="text-sm font-mono" style={{ color: 'var(--text-secondary)' }}>{lap.fuel.toFixed(1)}kg</span>
                </div>
                {expandedLap === lap.number ? <ChevronUp className="w-5 h-5 text-gray-500" /> : <ChevronDown className="w-5 h-5 text-gray-500" />}
              </div>
            </div>

            <AnimatePresence>
              {expandedLap === lap.number && (
                <motion.div
                  initial={{ height: 0 }}
                  animate={{ height: 'auto' }}
                  exit={{ height: 0 }}
                  className="border-t p-6 grid grid-cols-1 md:grid-cols-3 gap-8"
                  style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}
                >
                  <div className="space-y-4">
                    <h4 className="text-[10px] font-bold text-gray-500 uppercase flex items-center gap-2"><Zap className="w-3 h-3"/> Speed Trace</h4>
                    <div className="h-16">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={lap.telemetry}>
                          <Line type="monotone" dataKey="v" stroke="#E10600" dot={false} strokeWidth={2} />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                  <div className="space-y-4">
                    <h4 className="text-[10px] font-bold text-gray-500 uppercase flex items-center gap-2"><Clock className="w-3 h-3"/> Sector Deltas</h4>
                    <div className="flex justify-between text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>
                       <span>S1: 21.23</span>
                       <span>S2: 32.10</span>
                       <span>S3: 20.90</span>
                    </div>
                  </div>
                  <div className="space-y-4">
                    <h4 className="text-[10px] font-bold text-gray-500 uppercase flex items-center gap-2"><TrendingUp className="w-3 h-3"/> AI Observations</h4>
                    <p className="text-[10px] text-gray-500 italic">Optimal brake bias adherence: 98.4%. Suggest earlier lift-off at T12.</p>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        ))}
      </div>
    </div>
  );
};

export default LapByLapAnalysis;
