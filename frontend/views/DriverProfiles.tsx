/**
 * @file DriverProfiles.tsx
 * @description In-depth behavioral analytics for the driver roster.
 * Uses scatter plots for multi-dimensional comparison and radar charts for specific driver traits.
 * Linked to: GET /api/v1/drivers (real career stats from GCS Parquet data)
 */

import React, { useState, useMemo } from 'react';
import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Label, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, Cell } from 'recharts';
import { TEAM_COLORS } from '../constants';
import { motion } from 'framer-motion';
import { useDrivers } from '../hooks/useApi';
import ConnectionBadge from '../components/ConnectionBadge';
import { Search, Users, Trophy, Flag } from 'lucide-react';

function MetricCard({ label, value }: { label: string, value: string | number }) {
  return (
    <div className="p-4 rounded-xl border" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}>
      <div className="text-[10px] text-gray-500 uppercase font-bold tracking-widest mb-1">{label}</div>
      <div className="text-xl font-mono font-bold" style={{ color: 'var(--text-primary)' }}>{value}</div>
    </div>
  );
}

const DriverProfiles: React.FC = () => {
  const { data: drivers, loading, isLive } = useDrivers();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterTeam, setFilterTeam] = useState<string>('all');

  // Filter drivers based on search and team
  const filteredDrivers = useMemo(() => {
    if (!drivers) return [];
    return drivers.filter(d => {
      const matchesSearch = searchQuery === '' ||
        d.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        d.code.toLowerCase().includes(searchQuery.toLowerCase()) ||
        d.nationality.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesTeam = filterTeam === 'all' || d.team === filterTeam;
      return matchesSearch && matchesTeam;
    });
  }, [drivers, searchQuery, filterTeam]);

  // For the scatter plot, show only drivers with meaningful stats (races > 0)
  const scatterDrivers = useMemo(() => {
    return filteredDrivers.filter(d => d.career_races > 0).slice(0, 50);
  }, [filteredDrivers]);

  // Auto-select first driver if none selected
  const selectedDriver = useMemo(() => {
    if (!drivers || drivers.length === 0) return null;
    if (selectedId) {
      return drivers.find(d => d.driver_id === selectedId) || drivers[0];
    }
    return drivers[0];
  }, [drivers, selectedId]);

  // Unique teams from loaded data
  const teams = useMemo(() => {
    if (!drivers) return [];
    const teamSet = new Set(drivers.map(d => d.team));
    return Array.from(teamSet).filter(t => t !== 'Unknown').sort();
  }, [drivers]);

  // Stats summary
  const totalDrivers = drivers?.length || 0;
  const totalWins = drivers?.reduce((sum, d) => sum + d.career_wins, 0) || 0;
  const nationalities = new Set(drivers?.map(d => d.nationality).filter(Boolean) || []).size;

  if (loading && !drivers) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-gray-500 font-display uppercase tracking-widest text-sm animate-pulse">
          Loading driver profiles...
        </div>
      </div>
    );
  }

  const scatterData = scatterDrivers.map(d => ({
    x: d.aggression_score,
    y: d.consistency_score,
    name: d.name,
    code: d.code,
    team: d.team,
    id: d.driver_id,
    z: d.career_wins + 10
  }));

  const radarData = selectedDriver ? [
    { subject: 'Aggression', value: selectedDriver.aggression_score, fullMark: 100 },
    { subject: 'Consistency', value: selectedDriver.consistency_score, fullMark: 100 },
    { subject: 'Pressure', value: selectedDriver.pressure_response, fullMark: 100 },
    { subject: 'Tire Mgmt', value: selectedDriver.tire_management, fullMark: 100 },
    { subject: 'Wet Skill', value: selectedDriver.wet_weather_skill, fullMark: 100 },
    { subject: 'Race Pace', value: selectedDriver.race_pace, fullMark: 100 },
  ] : [];

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-4xl font-display font-black tracking-tighter uppercase italic">Apex Behavioral Intelligence</h1>
          <p className="text-gray-500 uppercase text-[10px] tracking-[0.2em] mt-2">
            {isLive
              ? `${totalDrivers} driver profiles loaded from GCS Parquet data pipeline`
              : 'Driver archetypes derived from 500+ sessions of high-frequency telemetry'}
          </p>
        </div>
        <ConnectionBadge isLive={isLive} />
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-3 gap-4">
        <div className="flex items-center gap-3 p-4 rounded-xl border" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
          <Users className="w-5 h-5 text-blue-500" />
          <div>
            <div className="text-[9px] text-gray-500 uppercase font-bold tracking-widest">Total Drivers</div>
            <div className="text-2xl font-mono font-bold" style={{ color: 'var(--text-primary)' }}>{totalDrivers}</div>
          </div>
        </div>
        <div className="flex items-center gap-3 p-4 rounded-xl border" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
          <Trophy className="w-5 h-5 text-yellow-500" />
          <div>
            <div className="text-[9px] text-gray-500 uppercase font-bold tracking-widest">Combined Wins</div>
            <div className="text-2xl font-mono font-bold" style={{ color: 'var(--text-primary)' }}>{totalWins}</div>
          </div>
        </div>
        <div className="flex items-center gap-3 p-4 rounded-xl border" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
          <Flag className="w-5 h-5 text-green-500" />
          <div>
            <div className="text-[9px] text-gray-500 uppercase font-bold tracking-widest">Nationalities</div>
            <div className="text-2xl font-mono font-bold" style={{ color: 'var(--text-primary)' }}>{nationalities}</div>
          </div>
        </div>
      </div>

      {/* Search and Filter */}
      <div className="flex gap-4 items-center">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
          <input
            type="text"
            placeholder="Search drivers by name, code, or nationality..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 rounded-xl border text-sm bg-transparent focus:outline-none focus:border-red-600 transition-colors"
            style={{ borderColor: 'var(--border-color)', color: 'var(--text-primary)' }}
          />
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
        <div className="text-[10px] text-gray-500 font-mono">
          {filteredDrivers.length} shown
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Scatter Plot */}
        <div className="lg:col-span-7 rounded-2xl p-6 border shadow-2xl h-[550px]" style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}>
          <h3 className="text-xs font-display font-bold uppercase tracking-widest text-gray-400 mb-8 px-2">
            Trait Correlation Matrix
            <span className="ml-2 text-gray-600 normal-case tracking-normal">
              ({scatterDrivers.length} drivers{scatterDrivers.length >= 50 ? ', top 50 shown' : ''})
            </span>
          </h3>
          <ResponsiveContainer width="100%" height="90%">
            <ScatterChart margin={{ top: 20, right: 30, bottom: 30, left: 30 }}>
              <CartesianGrid stroke="var(--border-color)" strokeDasharray="3 3" />
              <XAxis type="number" dataKey="x" domain={['auto', 'auto']} stroke="var(--text-secondary)" fontSize={10} tick={{ fill: 'var(--text-secondary)' }}>
                <Label value="AGGRESSION INDEX" position="bottom" fill="var(--text-secondary)" fontSize={10} dy={15} />
              </XAxis>
              <YAxis type="number" dataKey="y" domain={['auto', 'auto']} stroke="var(--text-secondary)" fontSize={10} tick={{ fill: 'var(--text-secondary)' }}>
                <Label value="CONSISTENCY INDEX" angle={-90} position="left" fill="var(--text-secondary)" fontSize={10} dx={-15} />
              </YAxis>
              <Tooltip cursor={{ strokeDasharray: '3 3' }}
                contentStyle={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border-color)', borderRadius: '8px', color: 'var(--text-primary)' }}
                itemStyle={{ color: 'var(--text-primary)' }}
              />
              <Scatter
                name="Drivers"
                data={scatterData}
                onClick={(e: any) => setSelectedId(e.id)}
                className="cursor-pointer"
              >
                {scatterData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={TEAM_COLORS[entry.team] || '#666'} />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </div>

        {/* Driver Detail */}
        <div className="lg:col-span-5 space-y-8">
          {selectedDriver && (
            <motion.div
              key={selectedDriver.driver_id}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              className="rounded-2xl p-8 border shadow-2xl relative overflow-hidden"
              style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--border-color)' }}
            >
              <div className="absolute top-0 right-0 w-48 h-48 opacity-10 pointer-events-none" style={{ background: `radial-gradient(circle at top right, ${TEAM_COLORS[selectedDriver.team] || '#666'}, transparent)` }} />

              <div className="flex gap-6 items-center mb-10">
                <div className="w-20 h-20 rounded-2xl bg-white/5 flex items-center justify-center font-display text-4xl font-black border border-white/10 italic" style={{ color: TEAM_COLORS[selectedDriver.team] || '#666' }}>
                  {selectedDriver.code}
                </div>
                <div>
                  <h2 className="text-3xl font-display font-bold tracking-tight">{selectedDriver.name}</h2>
                  <p className="text-xs text-gray-500 uppercase font-black tracking-[0.2em]">{selectedDriver.team}</p>
                  <p className="text-[10px] text-gray-600 mt-1">{selectedDriver.nationality}</p>
                </div>
              </div>

              <div className="h-[320px]">
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart cx="50%" cy="50%" outerRadius="80%" data={radarData}>
                    <PolarGrid stroke="var(--border-color)" />
                    <PolarAngleAxis dataKey="subject" stroke="var(--text-secondary)" fontSize={10} fontWeight="bold" />
                    <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} axisLine={false} />
                    <Radar
                      name={selectedDriver.name}
                      dataKey="value"
                      stroke={TEAM_COLORS[selectedDriver.team] || '#666'}
                      fill={TEAM_COLORS[selectedDriver.team] || '#666'}
                      fillOpacity={0.4}
                    />
                  </RadarChart>
                </ResponsiveContainer>
              </div>

              <div className="grid grid-cols-3 gap-4 mt-8">
                <MetricCard label="Races" value={selectedDriver.career_races} />
                <MetricCard label="Wins" value={selectedDriver.career_wins} />
                <MetricCard label="Experience" value={`${selectedDriver.experience_years}yr`} />
              </div>
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
};

export default DriverProfiles;
