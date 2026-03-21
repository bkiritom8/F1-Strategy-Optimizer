
import React from 'react';
import { MOCK_VALIDATION, COLORS } from '../constants';
import { CheckCircle2, XCircle, TrendingUp } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, ResponsiveContainer, Tooltip } from 'recharts';

const ValidationPerformance: React.FC = () => {
  const trendData = MOCK_VALIDATION.map((v, i) => ({ x: i, acc: v.podium_acc }));

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      <div>
        <h1 className="text-4xl font-display font-black tracking-tighter uppercase italic">Model Validation</h1>
        <p className="text-gray-500 uppercase text-xs tracking-widest mt-2">Ground-truth comparison against 2024 season outcomes</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <KPI label="Podium Accuracy" value="84.2%" trend="+4.5%" positive />
        <KPI label="Winner Prediction" value="71.0%" trend="+2.1%" positive />
        <KPI label="Pit Timing (±2L)" value="91.5%" trend="-0.5%" />
        <KPI label="Rank Correlation" value="0.88" trend="+0.02" positive />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        <div className="lg:col-span-8 rounded-2xl border overflow-hidden shadow-xl" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
          <table className="w-full text-left">
            <thead style={{ backgroundColor: 'var(--bg-secondary)' }}>
              <tr className="text-[10px] font-bold text-gray-500 uppercase tracking-widest border-b" style={{ borderColor: 'var(--border-color)' }}>
                <th className="p-4">Race</th>
                <th className="p-4">Predicted Winner</th>
                <th className="p-4">Actual Winner</th>
                <th className="p-4 text-center">Outcome</th>
                <th className="p-4 text-right">Podium Acc</th>
              </tr>
            </thead>
            <tbody className="text-sm font-mono">
              {MOCK_VALIDATION.map((v, i) => (
                <tr key={i} className="border-b hover:bg-black/5 transition-colors" style={{ borderColor: 'var(--border-color)' }}>
                  <td className="p-4 font-bold" style={{ color: 'var(--text-primary)' }}>{v.race}</td>
                  <td className="p-4 text-gray-500">{v.predicted_winner}</td>
                  <td className="p-4 font-bold" style={{ color: 'var(--text-primary)' }}>{v.actual_winner}</td>
                  <td className="p-4 flex justify-center">
                    {v.predicted_winner === v.actual_winner ? <CheckCircle2 className="text-green-500 w-5 h-5" /> : <XCircle className="text-red-500 w-5 h-5" />}
                  </td>
                  <td className="p-4 text-right font-bold" style={{ color: v.podium_acc > 70 ? COLORS.accent.green : COLORS.accent.yellow }}>{v.podium_acc}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="lg:col-span-4 space-y-6">
           <div className="rounded-2xl p-6 border h-[300px] shadow-xl" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
             <h3 className="text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-6">Accuracy Trend (moving avg)</h3>
             <ResponsiveContainer width="100%" height="100%">
               <AreaChart data={trendData}>
                 <defs>
                   <linearGradient id="colorAcc" x1="0" y1="0" x2="0" y2="1">
                     <stop offset="5%" stopColor={COLORS.accent.green} stopOpacity={0.3}/>
                     <stop offset="95%" stopColor={COLORS.accent.green} stopOpacity={0}/>
                   </linearGradient>
                 </defs>
                 <XAxis hide dataKey="x" />
                 <YAxis domain={[0, 100]} hide />
                 <Tooltip 
                   contentStyle={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border-color)', borderRadius: '8px', color: 'var(--text-primary)' }}
                   itemStyle={{ color: 'var(--text-primary)' }}
                 />
                 <Area type="monotone" dataKey="acc" stroke={COLORS.accent.green} fill="url(#colorAcc)" strokeWidth={3} />
               </AreaChart>
             </ResponsiveContainer>
           </div>
           <div className="rounded-2xl p-6 border italic text-[11px] text-gray-500 shadow-sm" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}>
             Note: Outliers in Australian GP attributed to unexpected DNF of Max Verstappen (Lap 3). System successfully predicted podium positions for remaining field.
           </div>
        </div>
      </div>
    </div>
  );
};

const KPI = ({ label, value, trend, positive }: any) => (
  <div className="p-6 rounded-2xl border shadow-lg" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
    <div className="text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-2">{label}</div>
    <div className="flex items-baseline gap-2">
      <span className="text-3xl font-display font-black" style={{ color: 'var(--text-primary)' }}>{value}</span>
      <span className={`text-xs font-bold ${positive ? 'text-green-500' : 'text-red-500'}`}>{trend}</span>
    </div>
  </div>
);

export default ValidationPerformance;
