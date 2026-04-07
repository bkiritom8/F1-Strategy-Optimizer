/**
 * @file views/AdminPage.tsx
 * @description Admin control panel for Apex Intelligence.
 *
 * Access control: reads `isAdmin` from the Zustand store. If the user is not an
 * authenticated admin (set by logging in with Admin credentials on the landing
 * page), this view redirects to '/' instead of showing a password prompt.
 *
 * The duplicate password gate that previously lived here has been removed;
 * authentication is now handled centrally in LandingPage.tsx -> LoginModal.
 */

import React, { useState } from 'react';
import { Navigate } from 'react-router-dom';
import { Lock, Shield, Activity, Cpu, TrendingUp, Database } from 'lucide-react';
import ValidationPerformance from './ValidationPerformance';
import SystemMonitoringHealth from './SystemMonitoringHealth';
import ModelEngineering from './ModelEngineering';
import GcpAdminPanel from './GcpAdminPanel';
import { useAppStore } from '../store/useAppStore';

const AdminPage: React.FC = () => {
  const { isAdmin } = useAppStore();
  const [activeTab, setActiveTab] = useState<'validation' | 'health' | 'engineering' | 'backend' | 'database' | 'security'>('backend');

  // Gate: redirect non-admin users to the landing page
  if (!isAdmin) {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="flex flex-col h-full overflow-hidden bg-transparent">
      <div className="px-4 sm:px-8 pt-8 pb-4 shrink-0 flex items-center gap-4 border-b relative z-10 bg-transparent overflow-x-auto hide-scrollbar" style={{ borderColor: 'var(--border-color)' }}>
        <TabButton id="validation"  active={activeTab === 'validation'}  onClick={() => setActiveTab('validation')}  icon={Shield}    color="red"    label="Validation"   />
        <TabButton id="health"      active={activeTab === 'health'}      onClick={() => setActiveTab('health')}      icon={Activity}  color="blue"   label="Health"       />
        <TabButton id="engineering" active={activeTab === 'engineering'} onClick={() => setActiveTab('engineering')} icon={Cpu}       color="purple" label="Engineering"  />
        <div className="w-px h-6 bg-white/10 mx-2 hidden md:block" />
        <TabButton id="backend"     active={activeTab === 'backend'}     onClick={() => setActiveTab('backend')}     icon={TrendingUp} color="yellow" label="GCP Backend" />
        <TabButton id="database"    active={activeTab === 'database'}    onClick={() => setActiveTab('database')}    icon={Database}  color="green"  label="Database"     />
        <TabButton id="security"    active={activeTab === 'security'}    onClick={() => setActiveTab('security')}    icon={Lock}      color="cyan"   label="Security"     />
      </div>
      
      <div className="flex-1 overflow-y-auto relative z-0 hide-scrollbar p-8">
        {activeTab === 'validation'  && <ValidationPerformance />}
        {activeTab === 'health'      && <SystemMonitoringHealth />}
        {activeTab === 'engineering' && <ModelEngineering />}
        {activeTab === 'backend'     && <GcpAdminPanel />}
        {(['database', 'security'].includes(activeTab)) && (
          <div className="flex flex-col items-center justify-center p-20 border border-dashed border-white/[0.07] rounded-3xl bg-white/[0.04] text-white/40">
            <Lock className="w-12 h-12 mb-4 opacity-20" />
            <h3 className="text-xl font-bold tracking-tight uppercase tracking-widest italic">Terminal Restricted</h3>
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
    red:    'bg-red-600 shadow-red-600/20',
    blue:   'bg-blue-600 shadow-blue-600/20',
    purple: 'bg-purple-600 shadow-purple-600/20',
    yellow: 'bg-yellow-600 shadow-yellow-600/20',
    green:  'bg-green-600 shadow-green-600/20',
    cyan:   'bg-cyan-600 shadow-cyan-600/20',
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
