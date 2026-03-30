import React, { useState } from 'react';
import { Lock, Shield, Activity, Cpu } from 'lucide-react';
import ValidationPerformance from './ValidationPerformance';
import SystemMonitoringHealth from './SystemMonitoringHealth';
import ModelEngineering from './ModelEngineering';
import OperationalCommand from './OperationalCommand';
import { COLORS } from '../constants';

const AdminPage: React.FC = () => {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [password, setPassword] = useState('');
  const [error, setError] = useState(false);
  const [activeTab, setActiveTab] = useState<'validation' | 'health' | 'engineering' | 'operational'>('validation');

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (password === 'f1race@mlops') {
      setIsAuthenticated(true);
      setError(false);
    } else {
      setError(true);
      setPassword('');
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="flex h-full items-center justify-center p-6 bg-[#0F0F0F]">
        <div className="absolute inset-0 overflow-hidden pointer-events-none opacity-20 bg-[url('https://www.transparenttextures.com/patterns/carbon-fibre.png')]" />
        
        <form onSubmit={handleLogin} className="relative z-10 w-full max-w-md p-10 rounded-3xl border shadow-[0_0_50px_rgba(0,0,0,0.5)] space-y-8 backdrop-blur-xl" style={{ backgroundColor: 'rgba(20,20,20,0.85)', borderColor: 'var(--border-color)' }}>
          <div className="flex flex-col items-center gap-6 text-center">
            <div className="w-20 h-20 rounded-2xl flex items-center justify-center bg-red-600/10 border border-red-500/20 shadow-[0_0_20px_rgba(225,6,0,0.15)] relative overflow-hidden">
               <div className="absolute inset-0 bg-gradient-to-br from-red-600/20 to-transparent" />
               <Lock className="w-10 h-10 text-red-500 relative z-10" />
            </div>
            <div>
              <h1 className="text-3xl font-display font-black tracking-tighter uppercase italic text-white">Admin Access</h1>
              <p className="text-xs uppercase font-mono tracking-widest text-red-500 mt-2 font-bold">Restricted MLOps Area</p>
            </div>
          </div>
          
          <div className="space-y-6">
            <div>
              <input
                type="password"
                value={password}
                onChange={(e) => { setPassword(e.target.value); setError(false); }}
                placeholder="Enter access code"
                className="w-full bg-black/40 border rounded-xl px-5 py-4 text-sm font-mono focus:outline-none focus:border-red-500 transition-colors shadow-inner"
                style={{ borderColor: error ? COLORS.accent.red : 'var(--border-color)', color: 'var(--text-primary)' }}
                autoFocus
              />
              {error && <p className="text-[10px] text-red-500 mt-3 flex items-center gap-1 uppercase tracking-wider font-bold"><Lock className="w-3 h-3"/> Access Denied. Verify Credentials.</p>}
            </div>
            <button type="submit" className="w-full bg-red-600 hover:bg-red-700 text-white font-black uppercase tracking-widest text-sm py-4 rounded-xl transition-all hover:scale-[1.02] active:scale-95 shadow-lg shadow-red-900/20">
              Unlock Terminal
            </button>
          </div>
        </form>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden bg-[#0A0A0A]">
      <div className="px-8 pt-8 pb-4 shrink-0 flex items-center gap-4 border-b relative z-10 bg-[#0F0F0F]" style={{ borderColor: 'var(--border-color)' }}>
        <button
          onClick={() => setActiveTab('validation')}
          className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold uppercase tracking-widest transition-all ${
            activeTab === 'validation' ? 'bg-red-600 text-white shadow-lg shadow-red-600/20 scale-105' : 'hover:bg-white/5 text-gray-400 border border-transparent hover:border-white/10'
          }`}
        >
          <Shield className={`w-4 h-4 ${activeTab === 'validation' ? 'text-white' : 'text-gray-500'}`} />
          Model Validation
        </button>
        <button
          onClick={() => setActiveTab('health')}
          className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold uppercase tracking-widest transition-all ${
            activeTab === 'health' ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/20 scale-105' : 'hover:bg-white/5 text-gray-400 border border-transparent hover:border-white/10'
          }`}
        >
          <Activity className={`w-4 h-4 ${activeTab === 'health' ? 'text-white' : 'text-gray-500'}`} />
          MLOps Health
        </button>
        <button
          onClick={() => setActiveTab('engineering')}
          className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold uppercase tracking-widest transition-all ${
            activeTab === 'engineering' ? 'bg-purple-600 text-white shadow-lg shadow-purple-600/20 scale-105' : 'hover:bg-white/5 text-gray-400 border border-transparent hover:border-white/10'
          }`}
        >
          <Cpu className={`w-4 h-4 ${activeTab === 'engineering' ? 'text-white' : 'text-gray-500'}`} />
          Model Engineering
        </button>
        <button
          onClick={() => setActiveTab('operational')}
          className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold uppercase tracking-widest transition-all ${
            activeTab === 'operational' ? 'bg-emerald-600 text-white shadow-lg shadow-emerald-600/20 scale-105' : 'hover:bg-white/5 text-gray-400 border border-transparent hover:border-white/10'
          }`}
        >
          <Activity className={`w-4 h-4 ${activeTab === 'operational' ? 'text-white' : 'text-gray-500'}`} />
          Operational Command
        </button>
      </div>
      
      <div className="flex-1 overflow-y-auto relative z-0 hide-scrollbar p-8">
        {activeTab === 'validation' && <ValidationPerformance />}
        {activeTab === 'health' && <SystemMonitoringHealth />}
        {activeTab === 'engineering' && <ModelEngineering />}
        {activeTab === 'operational' && <OperationalCommand />}
      </div>
    </div>
  );
};

export default AdminPage;
