import React, { useState, useEffect, useMemo } from 'react';
import { useRaces2024, useRaces2025 } from '../hooks/useApi';
import { Trophy, ArrowUp, ArrowDown, Minus, Flag, Zap } from 'lucide-react';
import { TEAM_COLORS } from '../constants';

function getTeamColor(constructorName: string): string {
  return TEAM_COLORS[constructorName] || '#555';
}

function GainLoss({ grid, finish }: { grid: number; finish: number }) {
  const diff = grid - finish;
  if (diff > 0) return <span className="flex items-center gap-1 text-emerald-400 font-bold text-xs"><ArrowUp className="w-3 h-3" />+{diff}</span>;
  if (diff < 0) return <span className="flex items-center gap-1 text-red-400 font-bold text-xs"><ArrowDown className="w-3 h-3" />{diff}</span>;
  return <span className="flex items-center gap-1 text-white/30 font-bold text-xs"><Minus className="w-3 h-3" />0</span>;
}

type SeasonYear = 2024 | 2025;

const LapByLapAnalysis: React.FC = () => {
  const { data: races2024 } = useRaces2024();
  const { data: races2025 } = useRaces2025();
  const [activeYear, setActiveYear] = useState<SeasonYear>(2025);
  const [selectedRaceId, setSelectedRaceId] = useState<number | null>(null);

  const races = activeYear === 2025 ? races2025 : races2024;

  useEffect(() => {
    if (races && races.length > 0) setSelectedRaceId(races[0].round);
  }, [races]);

  const selectedRace = races?.find((r: any) => r.round === selectedRaceId) || races?.[0];
  const results = selectedRace?.results || [];

  const heroStats = useMemo(() => {
    if (!results.length) return null;
    const winner = results[0];
    const fastestLap = results.reduce((best: any, r: any) =>
      r.fastestLap?.rank === 1 ? r : best, null);
    const dnfs = results.filter((r: any) => r.status !== 'Finished' && r.status !== 'Lapped').length;
    const biggestGainer = results.reduce((best: any, r: any) => {
      const gain = r.grid - r.position;
      return gain > (best.grid - best.position) ? r : best;
    }, results[0]);
    return { winner, fastestLap, dnfs, biggestGainer };
  }, [results]);

  return (
    <div className="p-4 sm:p-8 max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl md:text-4xl font-display font-bold tracking-tight uppercase italic">Race Results Archive</h1>
          <p className="text-[10px] uppercase tracking-[4px] text-white/40 mt-2">Detailed session analysis with position delta tracking</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex rounded-xl overflow-hidden border border-white/10">
            {([2025, 2024] as SeasonYear[]).map(yr => (
              <button key={yr} onClick={() => setActiveYear(yr)}
                className={`px-4 py-2 text-xs font-black uppercase tracking-widest transition-all ${activeYear === yr ? 'bg-red-600 text-white' : 'bg-transparent text-white/40 hover:text-white'}`}>
                {yr}
              </button>
            ))}
          </div>
          <select value={selectedRaceId || ''} onChange={e => setSelectedRaceId(Number(e.target.value))}
            className="px-4 py-2.5 rounded-xl border text-sm font-bold bg-black/40 backdrop-blur-sm focus:outline-none cursor-pointer border-white/10 text-white">
            {races?.map((r: any) => (
              <option key={r.round} value={r.round} className="bg-black text-white">R{r.round} — {r.name}</option>
            ))}
          </select>
        </div>
      </div>

      {heroStats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="rounded-2xl border border-yellow-500/20 bg-yellow-500/5 p-4">
            <div className="flex items-center gap-2 mb-2"><Trophy className="w-4 h-4 text-yellow-500" /><span className="text-[9px] font-bold uppercase tracking-widest text-yellow-500/70">Winner</span></div>
            <p className="text-lg font-black text-white uppercase tracking-tight">{heroStats.winner.driver.name || heroStats.winner.driver.code}</p>
            <p className="text-[10px] text-white/40 mt-1">From P{heroStats.winner.grid}</p>
          </div>
          <div className="rounded-2xl border border-purple-500/20 bg-purple-500/5 p-4">
            <div className="flex items-center gap-2 mb-2"><Zap className="w-4 h-4 text-purple-400" /><span className="text-[9px] font-bold uppercase tracking-widest text-purple-400/70">Fastest Lap</span></div>
            <p className="text-lg font-mono font-bold text-white">{heroStats.fastestLap?.fastestLap?.time || 'N/A'}</p>
            <p className="text-[10px] text-white/40 mt-1">{heroStats.fastestLap?.driver?.name || ''}</p>
          </div>
          <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-4">
            <div className="flex items-center gap-2 mb-2"><ArrowUp className="w-4 h-4 text-emerald-400" /><span className="text-[9px] font-bold uppercase tracking-widest text-emerald-400/70">Top Mover</span></div>
            <p className="text-lg font-black text-white uppercase tracking-tight">{heroStats.biggestGainer.driver.code || heroStats.biggestGainer.driver.name}</p>
            <p className="text-[10px] text-white/40 mt-1">P{heroStats.biggestGainer.grid} → P{heroStats.biggestGainer.position} (+{heroStats.biggestGainer.grid - heroStats.biggestGainer.position})</p>
          </div>
          <div className="rounded-2xl border border-red-500/20 bg-red-500/5 p-4">
            <div className="flex items-center gap-2 mb-2"><Flag className="w-4 h-4 text-red-400" /><span className="text-[9px] font-bold uppercase tracking-widest text-red-400/70">Retirements</span></div>
            <p className="text-3xl font-mono font-bold text-white">{heroStats.dnfs}</p>
            <p className="text-[10px] text-white/40 mt-1">out of {results.length} starters</p>
          </div>
        </div>
      )}

      {selectedRace && (
        <div className="rounded-2xl border overflow-x-auto shadow-xl border-white/[0.07] bg-white/[0.02] backdrop-blur-sm">
          <table className="w-full text-left whitespace-nowrap">
            <thead className="bg-white/[0.04]">
              <tr className="text-[9px] font-bold text-white/40 uppercase tracking-[3px] border-b border-white/[0.07]">
                <th className="p-4 w-12">Pos</th>
                <th className="p-4">Driver</th>
                <th className="p-4 hidden lg:table-cell">Team</th>
                <th className="p-4 text-center">Grid</th>
                <th className="p-4 text-center">+/-</th>
                <th className="p-4 text-right">Points</th>
                <th className="p-4 text-right hidden md:table-cell">Status</th>
                <th className="p-4 text-right hidden md:table-cell">Fastest Lap</th>
              </tr>
            </thead>
            <tbody className="text-sm font-mono">
              {results.map((r: any) => {
                const isPodium = r.position <= 3;
                const isDNF = r.status !== 'Finished' && r.status !== 'Lapped';
                const teamColor = getTeamColor(r.constructor);
                return (
                  <tr key={r.driver.id} className={`border-b border-white/[0.04] transition-colors hover:bg-white/[0.03] ${isDNF ? 'opacity-50' : ''}`}>
                    <td className="p-4"><div className="flex items-center gap-2"><div className="w-1 h-6 rounded-full" style={{ backgroundColor: teamColor }} /><span className={`font-black ${isPodium ? 'text-yellow-500' : 'text-white'}`}>{r.position}</span></div></td>
                    <td className="p-4"><span className="font-bold text-white">{r.driver.name?.toUpperCase() ?? r.driver.code?.toUpperCase()}</span></td>
                    <td className="p-4 hidden lg:table-cell text-white/40 text-xs">{r.constructor}</td>
                    <td className="p-4 text-center text-white/50">{r.grid}</td>
                    <td className="p-4 text-center"><GainLoss grid={r.grid} finish={r.position} /></td>
                    <td className="p-4 text-right">{r.points > 0 ? <span className="font-bold text-emerald-400">+{r.points}</span> : <span className="text-white/20">0</span>}</td>
                    <td className="p-4 text-right hidden md:table-cell text-[10px] text-white/30 uppercase tracking-wider">{isDNF ? <span className="text-red-400">{r.status}</span> : r.status}</td>
                    <td className="p-4 text-right hidden md:table-cell">{r.fastestLap?.rank === 1 ? <span className="text-purple-400 font-bold">{r.fastestLap.time} ⚡</span> : <span className="text-white/30">{r.fastestLap?.time || '—'}</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default LapByLapAnalysis;
