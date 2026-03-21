/**
 * Main Application Component
 * Manages the high-level routing, sidebar navigation, and global layout.
 * Backend connectivity status is displayed in the sidebar footer.
 */

import React, { useState, useEffect } from 'react';
import RaceCommandCenter from './views/RaceCommandCenter';
import DriverProfiles from './views/DriverProfiles';
import PitStrategySimulator from './views/PitStrategySimulator';
import LapByLapAnalysis from './views/LapByLapAnalysis';
import ValidationPerformance from './views/ValidationPerformance';
import SystemMonitoringHealth from './views/SystemMonitoringHealth';
import AIChatbot from './views/AIChatbot';
import RacingBackground from './components/RacingBackground';
import TrackExplorer from './views/TrackExplorer';
import { useBackendStatus } from './hooks/useApi';
import { LayoutDashboard, Users, Compass, BarChart2, Activity, ShieldCheck, ChevronRight, MessageSquare, Cpu, Sun, Moon, Map, Wifi, WifiOff } from 'lucide-react';
import { APP_NAME, COLORS } from './constants';

type View = 'command' | 'profiles' | 'sim' | 'analysis' | 'health' | 'validation' | 'ai' | 'tracks';

const App: React.FC = () => {
  const [currentView, setCurrentView] = useState<View>('command');
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');
  const { online, latency } = useBackendStatus();

  useEffect(() => {
    const root = document.documentElement;
    const themeColors = COLORS[theme];

    root.style.setProperty('--bg-primary', themeColors.bg);
    root.style.setProperty('--bg-secondary', themeColors.secondary);
    root.style.setProperty('--bg-tertiary', themeColors.tertiary);
    root.style.setProperty('--text-primary', themeColors.text);
    root.style.setProperty('--text-secondary', themeColors.textSecondary);
    root.style.setProperty('--border-color', themeColors.border);
    root.style.setProperty('--card-bg', themeColors.card);

    document.body.className = theme === 'dark' ? 'dark' : 'light';
  }, [theme]);

  const navItems = [
    { id: 'command', label: 'Command Center', icon: <LayoutDashboard className="w-5 h-5" /> },
    { id: 'profiles', label: 'Driver Profiles', icon: <Users className="w-5 h-5" /> },
    { id: 'sim', label: 'Strategy Sim', icon: <Compass className="w-5 h-5" /> },
    { id: 'ai', label: 'AI Strategist', icon: <MessageSquare className="w-5 h-5" />, highlight: true },
    { id: 'tracks', label: 'Circuit Directory', icon: <Map className="w-5 h-5" /> },
    { id: 'analysis', label: 'Post-Race', icon: <BarChart2 className="w-5 h-5" /> },
    { id: 'validation', label: 'Model Validation', icon: <ShieldCheck className="w-5 h-5" /> },
    { id: 'health', label: 'MLOps Health', icon: <Activity className="w-5 h-5" /> },
  ];

  return (
    <div className={`flex h-screen font-body relative transition-colors duration-300`} style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}>
      <RacingBackground view={currentView} theme={theme} />

      <nav className={`w-16 md:w-64 backdrop-blur-2xl border-r flex flex-col items-center md:items-stretch py-6 px-3 z-50 transition-colors duration-300`}
        style={{ backgroundColor: `${theme === 'dark' ? 'rgba(26,26,26,0.9)' : 'rgba(240,239,233,0.9)'}`, borderColor: 'var(--border-color)' }}>
        <div className="flex items-center justify-between mb-10 px-2">
          <div className="flex items-center gap-3">
            <div className="bg-red-600 w-8 h-8 rounded-lg flex items-center justify-center font-display font-black text-white italic">A</div>
            <span className="hidden md:block font-display font-black tracking-tighter uppercase italic text-xl">
              {APP_NAME.split(' ')[0]}<span className="text-red-600">{APP_NAME.split(' ')[1]}</span>
            </span>
          </div>

          <button
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            className={`p-2 rounded-lg transition-colors ${theme === 'dark' ? 'hover:bg-white/10 text-yellow-400' : 'hover:bg-black/10 text-blue-600'}`}
          >
            {theme === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
          </button>
        </div>

        <div className="space-y-1 flex-1">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => setCurrentView(item.id as View)}
              className={`w-full flex items-center gap-4 p-3 rounded-xl transition-all group relative ${currentView === item.id
                  ? 'bg-red-600 text-white shadow-[0_0_20px_rgba(225,6,0,0.4)]'
                  : 'text-gray-500 hover:bg-white/5 hover:text-white'
                }`}
            >
              <div className="flex-shrink-0">{item.icon}</div>
              <span className="hidden md:block font-display font-bold uppercase tracking-widest text-[10px]">{item.label}</span>

              {item.highlight && currentView !== item.id && (
                <div className="absolute right-3 top-3 w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse hidden md:block" />
              )}

              {currentView === item.id && <ChevronRight className="hidden md:block ml-auto w-4 h-4 opacity-50" />}
            </button>
          ))}
        </div>

        {/* Backend connection status */}
        <div className={`mt-auto p-3 rounded-xl border flex items-center gap-3 transition-colors duration-300 ${theme === 'dark' ? 'md:bg-black/40' : 'md:bg-black/5'}`}
          style={{ borderColor: 'var(--border-color)' }}>
          <div className={`w-8 h-8 rounded-full flex items-center justify-center ${online ? 'bg-green-500/20 text-green-500' : 'bg-yellow-500/20 text-yellow-500'}`}>
            {online ? <Wifi className="w-4 h-4" /> : <WifiOff className="w-4 h-4" />}
          </div>
          <div className="hidden md:block">
            <div className={`text-[8px] font-bold uppercase tracking-widest ${theme === 'dark' ? 'text-gray-500' : 'text-gray-400'}`}>
              FastAPI Backend
            </div>
            <div className={`text-[10px] font-bold uppercase flex items-center gap-1 ${online ? 'text-green-500' : 'text-yellow-500'}`}>
              <div className={`w-1.5 h-1.5 rounded-full animate-pulse ${online ? 'bg-green-500' : 'bg-yellow-500'}`} />
              {online ? `Connected${latency ? ` (${latency}ms)` : ''}` : 'Mock Mode'}
            </div>
          </div>
        </div>
      </nav>

      <main className="flex-1 relative overflow-hidden bg-transparent overflow-y-auto z-10 scrollbar-hide">
        {currentView === 'command' && <RaceCommandCenter />}
        {currentView === 'profiles' && <DriverProfiles />}
        {currentView === 'sim' && <PitStrategySimulator />}
        {currentView === 'ai' && <AIChatbot />}
        {currentView === 'tracks' && <TrackExplorer theme={theme} />}
        {currentView === 'analysis' && <LapByLapAnalysis />}
        {currentView === 'validation' && <ValidationPerformance />}
        {currentView === 'health' && <SystemMonitoringHealth />}
      </main>
    </div>
  );
};

export default App;
