import React, { useState } from 'react';
import { Lock, Shield, Activity, Cpu, TrendingUp, Database, Radio } from 'lucide-react';
import ValidationPerformance from './ValidationPerformance';
import SystemMonitoringHealth from './SystemMonitoringHealth';
import ModelEngineering from './ModelEngineering';
import GcpAdminPanel from './GcpAdminPanel';
import { COLORS } from '../constants';

const AdminPage: React.FC = () => {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [password, setPassword] = useState('');
  const [error, setError] = useState(false);
  const [activeTab, setActiveTab] = useState<'validation' | 'health' | 'engineering' | 'backend' | 'database' | 'security'>('backend');

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
      <div className="flex h-full items-center justify-center p-6 bg-transparent">
        <div className="absolute inset-0 overflow-hidden pointer-events-none opacity-20 bg-[url('https://www.transparenttextures.com/patterns/carbon-fibre.png')]" />
        
        <form onSubmit={handleLogin} className="relative z-10 w-full max-w-md p-6 sm:p-10 mx-4 sm:mx-0 rounded-3xl shadow-[0_0_50px_rgba(0,0,0,0.5)] space-y-8 bg-white/[0.04] backdrop-blur-md border border-white/[0.07]">
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
    <div className="flex flex-col h-full overflow-hidden bg-transparent">
      <div className="px-4 sm:px-8 pt-8 pb-4 shrink-0 flex items-center gap-4 border-b relative z-10 bg-transparent overflow-x-auto hide-scrollbar" style={{ borderColor: 'var(--border-color)' }}>
        <TabButton id="validation" active={activeTab === 'validation'} onClick={() => setActiveTab('validation')} icon={Shield} color="red" label="Validation" />
        <TabButton id="health" active={activeTab === 'health'} onClick={() => setActiveTab('health')} icon={Activity} color="blue" label="Health" />
        <TabButton id="engineering" active={activeTab === 'engineering'} onClick={() => setActiveTab('engineering')} icon={Cpu} color="purple" label="Engineering" />
        <div className="w-px h-6 bg-white/10 mx-2 hidden md:block" />
        <TabButton id="backend" active={activeTab === 'backend'} onClick={() => setActiveTab('backend')} icon={TrendingUp} color="yellow" label="GCP Backend" />
        <TabButton id="database" active={activeTab === 'database'} onClick={() => setActiveTab('database')} icon={Database} color="green" label="Database" />
        <TabButton id="security" active={activeTab === 'security'} onClick={() => setActiveTab('security')} icon={Lock} color="cyan" label="Security" />
      </div>
      
      <div className="flex-1 overflow-y-auto relative z-0 hide-scrollbar p-8">
        {activeTab === 'validation' && <ValidationPerformance />}
        {activeTab === 'health' && <SystemMonitoringHealth />}
        {activeTab === 'engineering' && <ModelEngineering />}
        {activeTab === 'backend' && <GcpAdminPanel />}
        {(['database', 'security'].includes(activeTab)) && (
          <div className="flex flex-col items-center justify-center p-20 border border-dashed border-white/[0.07] rounded-3xl bg-white/[0.04] text-white/40">
            <Lock className="w-12 h-12 mb-4 opacity-20" />
            <h3 className="text-xl font-bold font-bold tracking-tight uppercase tracking-widest italic">Terminal Restricted</h3>
            <p className="text-xs mt-2 text-white/40">This module requires direct Cloud Shell credentials (IAM: f1-ingest-sa)</p>
          </div>
        )}
      </div>
    </div>
  );
};

interface TabButtonProps { id: string; active: boolean; onClick: () => void; icon: any; color: string; label: string; }
function TabButton({ active, onClick, icon: Icon, color, label }: TabButtonProps) {
  const colorMap: Record<string, string> = {
    red: 'bg-red-600 shadow-red-600/20',
    blue: 'bg-blue-600 shadow-blue-600/20',
    purple: 'bg-purple-600 shadow-purple-600/20',
    yellow: 'bg-yellow-600 shadow-yellow-600/20',
    green: 'bg-green-600 shadow-green-600/20',
    cyan: 'bg-cyan-600 shadow-cyan-600/20',
  };
  return (
    <button
      onClick={onClick}
      className={`shrink-0 flex items-center gap-2 px-5 py-2.5 rounded-xl text-[10px] whitespace-nowrap font-black uppercase tracking-widest transition-all ${
        active ? `${colorMap[color]} text-white shadow-lg scale-105` : 'hover:bg-white/5 text-white/40 border border-transparent hover:border-white/10'
      }`}
    >
      <Icon className="w-4 h-4" />
      {label}
    </button>
  );
}

export default AdminPage;
