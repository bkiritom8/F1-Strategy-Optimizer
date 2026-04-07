
import React, { useState, useEffect } from 'react';
import { useRaces2024 } from '../hooks/useApi';

const LapByLapAnalysis: React.FC = () => {
  const { data: races } = useRaces2024();
  const [selectedRaceId, setSelectedRaceId] = useState<number | null>(null);

  useEffect(() => {
    if (races && races.length > 0 && selectedRaceId === null) {
      setSelectedRaceId(races[0].round);
    }
  }, [races, selectedRaceId]);

  const selectedRace = races?.find((r: any) => r.round === selectedRaceId) || races?.[0];

  return (
    <div className="p-4 sm:p-8 max-w-7xl mx-auto space-y-8">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-4xl font-display font-bold tracking-tight uppercase italic">Race Results Archive</h1>
          <p className="text-[10px] uppercase tracking-[4px] text-white/40 mt-2">Historical telemetry archives: 2024 Season</p>
        </div>

        {/* Race Selector */}
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

      <div className="space-y-3">
        {selectedRace && (
          <div className="rounded-2xl border overflow-x-auto shadow-xl" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
            <table className="w-full text-left whitespace-nowrap">
              <thead className="bg-white/[0.06]">
                <tr className="text-[10px] font-bold text-white/40 uppercase tracking-widest border-b" style={{ borderColor: 'var(--border-color)' }}>
                  <th className="p-4">Pos</th>
                  <th className="p-4">Driver</th>
                  <th className="p-4">Constructor</th>
                  <th className="p-4 text-center">Laps</th>
                  <th className="p-4 text-center">Grid</th>
                  <th className="p-4 text-right">Points</th>
                  <th className="p-4 text-right">Status</th>
                  <th className="p-4 text-right">Fastest Lap</th>
                </tr>
              </thead>
              <tbody className="text-sm font-mono">
                {selectedRace?.results?.map((r: any) => (
                  <tr key={r.driver.id} className="border-b hover:bg-white/[0.03] transition-colors" style={{ borderColor: 'var(--border-color)' }}>
                    <td className="p-4 font-bold" style={{ color: 'var(--text-primary)' }}>{r.position}</td>
                    <td className="p-4">
                      <span className="font-bold mr-2 lg:hidden">{(r.driver.code || '').toUpperCase()}</span>
                      <span className="hidden lg:inline font-bold">{r.driver.name?.toUpperCase() ?? r.driver.id.toUpperCase()}</span>
                    </td>
                    <td className="p-4 text-white/40">{r.constructor}</td>
                    <td className="p-4 text-center">{r.laps}</td>
                    <td className="p-4 text-center text-white/40">{r.grid}</td>
                    <td className="p-4 text-right font-bold text-green-500">{r.points > 0 ? `+${r.points}` : '0'}</td>
                    <td className="p-4 text-right text-white/40 text-xs">{r.status}</td>
                    <td className="p-4 text-right text-purple-400">{r.fastestLap?.time || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default LapByLapAnalysis;
