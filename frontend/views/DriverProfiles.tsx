/**
 * @file DriverProfiles.tsx
 * @description Driver roster with verified data only.
 *
 * Shows: search, team filter, nationality breakdown, individual driver cards.
 * All data comes from the static pipeline (drivers.json + races-2024.json) or live API.
 *
 * NOTE: Trait Correlation Matrix and Radar Charts have been intentionally removed.
 * Those require telemetry-derived behavioral scores from the FastF1 pipeline,
 * which are not yet available. They will be added back once the backend delivers
 * real per-driver metrics (tire management, aggression index, consistency, etc.)
 * from multi-season telemetry analysis.
 */

import React, { useState, useMemo } from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts';
import { TEAM_COLORS } from '../constants';
import { motion, AnimatePresence } from 'framer-motion';
import { useDrivers, useRaces2024, useRaces2025, useRaces2026 } from '../hooks/useApi';
import { Search, Users, Trophy, Flag, MapPin, Calendar, ChevronRight, Star } from 'lucide-react';
import type { DriverProfile } from '../types';

/**
 * Driver IDs on the 2026 confirmed grid.
 * Drivers NOT in this set are shown only when the Legends toggle is active.
 */
const CURRENT_2026_DRIVERS = new Set([
  'max_verstappen', 'lawson',
  'hamilton', 'leclerc',
  'norris', 'piastri',
  'russell', 'antonelli',
  'alonso', 'stroll',
  'gasly', 'doohan', 'colapinto',
  'tsunoda', 'hadjar', 'arvid_lindblad',
  'albon', 'sainz',
  'hulkenberg', 'bortoleto',
  'ocon', 'bearman',
]);


const SEASON_YEARS = [2026, 2025, 2024] as const;
type SeasonYear = typeof SEASON_YEARS[number];

const DriverProfiles: React.FC = () => {
  const { data: drivers, loading } = useDrivers();
  const { data: races2024 } = useRaces2024();
  const { data: races2025 } = useRaces2025();
  const { data: races2026 } = useRaces2026();
  const [activeYear, setActiveYear] = useState<SeasonYear>(2026);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterTeam, setFilterTeam] = useState<string>('all');
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [showLegends, setShowLegends] = useState(false);

  const racesForYear = activeYear === 2026 ? races2026 : activeYear === 2025 ? races2025 : races2024;
  const hasRaceData = racesForYear !== null && (racesForYear as any[]).length > 0;

  // Compute season stats from race results (any year)
  const seasonStats = useMemo(() => {
    if (!racesForYear || !hasRaceData) return new Map<string, { points: number; wins: number; podiums: number; races: number; dnfs: number; avgGrid: number; avgFinish: number; bestFinish: number; team: string }>();
    const races = racesForYear as any[];
    const stats = new Map<string, { points: number; wins: number; podiums: number; races: number; dnfs: number; grids: number[]; finishes: number[]; bestFinish: number; team: string }>();

    for (const race of races) {
      for (const r of race.results) {
        const id = r.driver.id;
        if (!stats.has(id)) {
          stats.set(id, { points: 0, wins: 0, podiums: 0, races: 0, dnfs: 0, grids: [], finishes: [], bestFinish: 20, team: r.constructor });
        }
        const s = stats.get(id)!;
        s.points += r.points;
        s.races += 1;
        s.team = r.constructor;
        if (r.position <= 3) s.podiums += 1;
        if (r.position === 1) s.wins += 1;
        if (r.status !== 'Finished' && r.status !== 'Lapped') s.dnfs += 1;
        s.grids.push(r.grid);
        if (r.status === 'Finished' || r.status === 'Lapped') {
          s.finishes.push(r.position);
          if (r.position < s.bestFinish) s.bestFinish = r.position;
        }
      }
    }

    const result = new Map<string, { points: number; wins: number; podiums: number; races: number; dnfs: number; avgGrid: number; avgFinish: number; bestFinish: number; team: string }>();
    for (const [id, s] of stats) {
      const avgGrid = s.grids.length > 0 ? s.grids.reduce((a, b) => a + b, 0) / s.grids.length : 0;
      const avgFinish = s.finishes.length > 0 ? s.finishes.reduce((a, b) => a + b, 0) / s.finishes.length : 0;
      result.set(id, {
        points: s.points,
        wins: s.wins,
        podiums: s.podiums,
        races: s.races,
        dnfs: s.dnfs,
        avgGrid: Math.round(avgGrid * 100) / 100,
        avgFinish: Math.round(avgFinish * 100) / 100,
        bestFinish: s.bestFinish,
        team: s.team,
      });
    }
    return result;
  }, [racesForYear, hasRaceData]);

  /**
   * Split drivers into current-grid members and legends (historical only).
   * Legends are only rendered when the user activates the Legends toggle.
   */
  const filteredDrivers = useMemo(() => {
    if (!drivers) return [];
    return drivers.filter(d => {
      const isCurrent = CURRENT_2026_DRIVERS.has(d.driver_id);
      if (!isCurrent && !showLegends) return false;   // hide legends unless toggle is on
      const matchesSearch = searchQuery === '' ||
        d.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        d.code.toLowerCase().includes(searchQuery.toLowerCase()) ||
        d.nationality.toLowerCase().includes(searchQuery.toLowerCase());
      const team = seasonStats.get(d.driver_id)?.team || d.team;
      const matchesTeam = filterTeam === 'all' || team === filterTeam;
      return matchesSearch && matchesTeam;
    });
  }, [drivers, searchQuery, filterTeam, seasonStats, showLegends]);

  const selectedDriver = useMemo(() => {
    if (!drivers || drivers.length === 0) return null;
    if (selectedId) return drivers.find(d => d.driver_id === selectedId) || null;
    return drivers[0] || null;
  }, [drivers, selectedId]);

  const selectedStats = selectedDriver ? seasonStats.get(selectedDriver.driver_id) : null;

  // Teams from all driver profiles + season stats
  const teams = useMemo(() => {
    const teamSet = new Set<string>();
    if (drivers) {
      for (const d of drivers) {
        const team = seasonStats.get(d.driver_id)?.team || d.team;
        if (team && team !== 'Unknown') teamSet.add(team);
      }
    }
    return Array.from(teamSet).sort();
  }, [drivers, seasonStats]);

  // Nationality breakdown — all drivers we have profiles for
  const nationalityData = useMemo(() => {
    if (!drivers) return [];
    const counts: Record<string, number> = {};
    drivers.forEach(d => {
      if (d.nationality) counts[d.nationality] = (counts[d.nationality] || 0) + 1;
    });
    return Object.entries(counts)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);
  }, [drivers]);

  // Summary stats
  const totalDrivers = drivers?.length ?? 0;
  const totalWins = Array.from(seasonStats.values()).reduce((sum, s) => sum + s.wins, 0);
  const nationalities = nationalityData.length;

  if (loading && !drivers) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-white/40 font-display uppercase tracking-widest text-sm animate-pulse">
          Loading driver profiles...
        </div>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex justify-between items-start flex-wrap gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-4xl font-display font-bold tracking-tight uppercase italic">Driver Roster</h1>
          </div>
          <p className="text-[10px] uppercase tracking-[4px] text-white/40 mt-2">
            {totalDrivers} drivers · {teams.length} constructors · Stats from {activeYear} season
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Year selector */}
          <div className="flex rounded-xl overflow-hidden border" style={{ borderColor: 'var(--border-color)' }}>
            {SEASON_YEARS.map(yr => (
              <button
                key={yr}
                onClick={() => { setActiveYear(yr); setSelectedId(null); setFilterTeam('all'); }}
                className={`px-4 py-2 text-xs font-bold uppercase transition-colors ${activeYear === yr ? 'bg-red-600 text-white' : 'text-white/40 hover:text-white'}`}
              >
                {yr}
              </button>
            ))}
          </div>
          {/* Legends toggle */}
          <button
            onClick={() => setShowLegends(prev => !prev)}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl border text-xs font-bold uppercase transition-all ${
              showLegends
                ? 'bg-amber-600/20 border-amber-500/50 text-amber-400'
                : 'border-white/10 text-white/40 hover:text-white hover:bg-white/5'
            }`}
            title="Show retired / historical drivers"
          >
            <Star className={`w-3.5 h-3.5 ${showLegends ? 'fill-amber-400 text-amber-400' : ''}`} />
            Legends
          </button>
        </div>
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-3 gap-4">
        <div className="flex items-center gap-3 p-4 rounded-xl border" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
          <Users className="w-5 h-5 text-blue-500" />
          <div>
            <div className="text-[9px] text-white/40 uppercase font-bold tracking-widest">Active Drivers</div>
            <div className="text-2xl font-mono font-bold" style={{ color: 'var(--text-primary)' }}>{totalDrivers}</div>
          </div>
        </div>
        <div className="flex items-center gap-3 p-4 rounded-xl border" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
          <Trophy className="w-5 h-5 text-yellow-500" />
          <div>
            <div className="text-[9px] text-white/40 uppercase font-bold tracking-widest">Total Race Wins</div>
            <div className="text-2xl font-mono font-bold" style={{ color: 'var(--text-primary)' }}>{totalWins}</div>
          </div>
        </div>
        <div className="flex items-center gap-3 p-4 rounded-xl border" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
          <Flag className="w-5 h-5 text-green-500" />
          <div>
            <div className="text-[9px] text-white/40 uppercase font-bold tracking-widest">Nationalities</div>
            <div className="text-2xl font-mono font-bold" style={{ color: 'var(--text-primary)' }}>{nationalities}</div>
          </div>
        </div>
      </div>

      {/* Search and Filter */}
      <div className="flex gap-4 items-center relative z-20">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
          <input
            type="text"
            placeholder="Search driver by name, code, or nationality..."
            value={searchQuery}
            onChange={(e) => { setSearchQuery(e.target.value); setDropdownOpen(true); }}
            onFocus={() => setDropdownOpen(true)}
            onBlur={() => setTimeout(() => setDropdownOpen(false), 200)}
            className="w-full pl-10 pr-4 py-2.5 rounded-xl border text-sm bg-transparent focus:outline-none focus:border-red-600 transition-colors"
            style={{ borderColor: 'var(--border-color)', color: 'var(--text-primary)' }}
          />
          {dropdownOpen && filteredDrivers.length > 0 && searchQuery.length > 0 && (
            <div className="absolute top-full left-0 right-0 mt-2 rounded-xl shadow-[0_10px_40px_rgba(0,0,0,0.8)] max-h-60 overflow-y-auto z-50 py-2 border" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
              {filteredDrivers.map(d => {
                const st = seasonStats.get(d.driver_id);
                return (
                  <div
                    key={d.driver_id}
                    className="px-4 py-2 hover:bg-white/5 cursor-pointer text-sm flex items-center gap-3 transition-colors"
                    onClick={() => { setSelectedId(d.driver_id); setSearchQuery(''); setDropdownOpen(false); }}
                  >
                    <span className="font-bold w-10 text-white/40">{d.code}</span>
                    <span className="font-bold" style={{ color: 'var(--text-primary)' }}>{d.name}</span>
                    <span className="text-xs text-white/40 ml-auto">{st?.team || d.team}</span>
                    <span className="text-xs font-mono text-yellow-500">{st?.points || 0} pts</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
        <select
          value={filterTeam}
          onChange={(e) => setFilterTeam(e.target.value)}
          className="px-4 py-2.5 rounded-xl border text-sm bg-transparent focus:outline-none cursor-pointer"
          style={{ borderColor: 'var(--border-color)', color: 'var(--text-primary)', backgroundColor: 'var(--card-bg)' }}
        >
          <option value="all">All Teams</option>
          {teams.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <div className="text-[10px] text-white/40 font-mono">{filteredDrivers.length} shown</div>
      </div>

      {/* Main Grid: Driver List + Detail Card */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Driver List */}
        <div className="lg:col-span-7 space-y-3">
          <div className="text-[10px] text-white/40 font-bold uppercase tracking-widest px-1 mb-2">All Drivers</div>
          {filteredDrivers
            .slice()
            .sort((a, b) => {
              const aPoints = seasonStats.get(a.driver_id)?.points ?? -1;
              const bPoints = seasonStats.get(b.driver_id)?.points ?? -1;
              if (aPoints !== bPoints) return bPoints - aPoints;
              return (b.career_wins ?? 0) - (a.career_wins ?? 0);
            })
            .map((d, i) => {
              const st = seasonStats.get(d.driver_id);
              const isSelected = selectedDriver?.driver_id === d.driver_id;
              const teamColor = TEAM_COLORS[st?.team || d.team] || '#666';
              return (
                <motion.div
                  key={d.driver_id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.03 }}
                  onClick={() => setSelectedId(d.driver_id)}
                  className={`flex items-center gap-4 p-4 rounded-xl border cursor-pointer transition-all ${
                    isSelected ? 'border-red-600 shadow-lg shadow-red-900/10' : 'hover:bg-white/5'
                  }`}
                  style={{
                    backgroundColor: isSelected ? 'rgba(225, 6, 0, 0.03)' : 'var(--card-bg)',
                    borderColor: isSelected ? '#E10600' : 'var(--border-color)',
                  }}
                >
                  {/* Position + Team Color */}
                  <div className="flex items-center gap-3 shrink-0">
                    <span className="text-lg font-mono font-bold w-6 text-center text-white/40">{i + 1}</span>
                    <div className="w-1 h-10 rounded-full" style={{ backgroundColor: teamColor }} />
                  </div>
                  {/* Driver Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-display font-bold text-sm" style={{ color: 'var(--text-primary)' }}>{d.name}</span>
                      <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded" style={{ backgroundColor: teamColor + '20', color: teamColor }}>{d.code}</span>
                    </div>
                    <div className="text-[10px] text-white/40">{st?.team || d.team} · {d.nationality}</div>
                  </div>
                  {/* Season Stats */}
                  <div className="flex items-center gap-4 shrink-0">
                    <div className="text-right">
                      <div className="text-[9px] text-white/40 uppercase font-bold">Points</div>
                      <div className="text-sm font-mono font-bold text-yellow-500">{st?.points || 0}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-[9px] text-white/40 uppercase font-bold">Wins</div>
                      <div className="text-sm font-mono font-bold" style={{ color: 'var(--text-primary)' }}>{st?.wins || 0}</div>
                    </div>
                    <div className="text-right hidden md:block">
                      <div className="text-[9px] text-white/40 uppercase font-bold">Podiums</div>
                      <div className="text-sm font-mono font-bold text-blue-400">{st?.podiums || 0}</div>
                    </div>
                    <ChevronRight className="w-4 h-4 text-white/40 shrink-0" />
                  </div>
                </motion.div>
              );
            })}
        </div>

        {/* Driver Detail Card */}
        <div className="lg:col-span-5">
          <div className="sticky top-6 space-y-6">
            {selectedDriver && (
              <AnimatePresence mode="wait">
                <motion.div
                  key={selectedDriver.driver_id}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  className="rounded-2xl p-8 border shadow-2xl relative overflow-hidden"
                  style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}
                >
                  {(() => {
                    const teamName = selectedStats?.team || selectedDriver.team;
                    const teamColor = TEAM_COLORS[teamName] || '#666';
                    return (
                      <div
                        className="absolute top-0 right-0 w-48 h-48 opacity-10 pointer-events-none"
                        style={{ background: `radial-gradient(circle at top right, ${teamColor}, transparent)` }}
                      />
                    );
                  })()}

                  {/* Header */}
                  {(() => {
                    const teamName = selectedStats?.team || selectedDriver.team;
                    const teamColor = TEAM_COLORS[teamName] || '#666';
                    return (
                      <div className="flex gap-6 items-center mb-8">
                        <div
                          className="w-20 h-20 rounded-2xl bg-white/5 flex items-center justify-center font-display text-4xl font-black border border-white/10 italic"
                          style={{ color: teamColor }}
                        >
                          {selectedDriver.code}
                        </div>
                        <div>
                          <h2 className="text-3xl font-display font-bold tracking-tight">{selectedDriver.name}</h2>
                          <p className="text-xs text-white/40 uppercase font-black tracking-[0.2em]">{teamName}</p>
                          <div className="flex items-center gap-2 mt-1">
                            <MapPin className="w-3 h-3 text-white/40" />
                            <span className="text-[10px] text-white/40">{selectedDriver.nationality}</span>
                          </div>
                        </div>
                      </div>
                    );
                  })()}

                  {/* Season Performance Grid — only when race results are available */}
                  {selectedStats ? (
                    <>
                  <div className="text-[10px] text-white/40 font-bold uppercase tracking-widest mb-3">{activeYear} Season Performance</div>
                  <div className="grid grid-cols-3 gap-3 mb-6">
                    <StatCard label="Points" value={selectedStats.points.toString()} highlight />
                    <StatCard label="Wins" value={selectedStats.wins.toString()} />
                    <StatCard label="Podiums" value={selectedStats.podiums.toString()} />
                    <StatCard label="Avg Grid" value={selectedStats.avgGrid.toFixed(2)} />
                    <StatCard label="Avg Finish" value={selectedStats.avgFinish.toFixed(2)} />
                    <StatCard label="Best Finish" value={`P${selectedStats.bestFinish}`} />
                    <StatCard label="Races" value={selectedStats.races.toString()} />
                    <StatCard label="DNFs" value={selectedStats.dnfs.toString()} color={selectedStats.dnfs > 3 ? '#E10600' : undefined} />
                    <StatCard label="Finish Rate" value={`${(((selectedStats.races - selectedStats.dnfs) / selectedStats.races) * 100).toFixed(2)}%`} />
                  </div>

                  {/* Positions Gained Indicator */}
                  {(() => {
                    const posGained = selectedStats.avgGrid - selectedStats.avgFinish;
                    const isGainer = posGained > 0;
                    return (
                      <div className="p-4 rounded-xl border" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}>
                        <div className="text-[10px] text-white/40 font-bold uppercase tracking-widest mb-2">Avg Positions Gained Per Race</div>
                        <div className="flex items-center gap-3">
                          <span className={`text-2xl font-mono font-black ${isGainer ? 'text-green-500' : 'text-red-500'}`}>
                            {isGainer ? '+' : ''}{posGained.toFixed(2)}
                          </span>
                          <span className="text-[10px] text-white/40">
                            {isGainer ? 'Gains positions on race day (strong racer)' : 'Loses positions on race day (strong qualifier)'}
                          </span>
                        </div>
                      </div>
                    );
                  })()}

                  {/* Data Source Note — season stats */}
                    <div className="mt-6 pt-4 border-t border-white/5">
                      <p className="text-[9px] text-gray-600 italic">
                        All metrics computed from verified {activeYear} FIA race results via Jolpica API.
                        Telemetry-derived behavioral scores will be available once the FastF1 pipeline is deployed.
                      </p>
                    </div>
                    </>
                  ) : (
                    /* Career stats fallback when season race data is not yet available */
                    <>
                      <div className="text-[10px] text-white/40 font-bold uppercase tracking-widest mb-3">Career Statistics</div>
                      <div className="grid grid-cols-3 gap-3 mb-6">
                        <StatCard label="Career Races" value={selectedDriver.career_races.toString()} />
                        <StatCard label="Career Wins" value={selectedDriver.career_wins.toString()} highlight />
                        <StatCard label="Experience" value={`${selectedDriver.experience_years}yr`} />
                      </div>
                      <div className="p-4 rounded-xl border" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}>
                        <p className="text-[10px] text-white/40 font-mono uppercase tracking-widest">
                          {activeYear} season results pending — race data will appear once the pipeline ingests {activeYear} results from Jolpica API.
                        </p>
                      </div>
                    </>
                  )}

                  {/* Data Source Note */}
                  <div className="mt-6 pt-4 border-t border-white/5">
                    <p className="text-[9px] text-gray-600 italic">
                      Driver data sourced from Jolpica API (Ergast). Skill scores derived from career statistics.
                    </p>
                  </div>
                </motion.div>
              </AnimatePresence>
            )}
          </div>
        </div>
      </div>

      {/* Nationality Breakdown */}
      <div className="rounded-2xl p-6 border shadow-2xl" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
        <h3 className="text-xs font-display font-bold uppercase tracking-widest text-white/40 mb-6 px-2">
          Driver Nationalities ({activeYear} Season)
        </h3>
        <div className="h-[280px]">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={nationalityData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={100}
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
              >
                {nationalityData.map((_, index) => {
                  const colorKeys = Object.keys(TEAM_COLORS);
                  const color = TEAM_COLORS[colorKeys[index % colorKeys.length]] || '#e10600';
                  return <Cell key={`cell-${index}`} fill={color} />;
                })}
              </Pie>
              <Tooltip
                contentStyle={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border-color)', borderRadius: '8px', color: 'var(--text-primary)' }}
                itemStyle={{ color: 'var(--text-primary)' }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};

function StatCard({ label, value, highlight, color }: { label: string; value: string; highlight?: boolean; color?: string }) {
  return (
    <div className="p-3 rounded-xl border" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}>
      <div className="text-[9px] text-white/40 uppercase font-bold tracking-widest mb-1">{label}</div>
      <div
        className={`text-lg font-mono font-bold ${highlight ? 'text-yellow-500' : ''}`}
        style={{ color: color || (highlight ? undefined : 'var(--text-primary)') }}
      >
        {value}
      </div>
    </div>
  );
}

export default DriverProfiles;
