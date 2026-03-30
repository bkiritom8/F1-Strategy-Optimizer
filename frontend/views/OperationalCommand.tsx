import React, { useState } from 'react';
import { DollarSign, Database, Play, Square, Terminal, Lock } from 'lucide-react';
import { COLORS } from '../constants';
import { apiFetch } from '../services/client';

const OperationalCommand: React.FC = () => {
  const [ingestionActive, setIngestionActive] = useState(false);
  const [loading, setLoading] = useState(false);

  const toggleIngestion = async (action: 'start' | 'stop') => {
    setLoading(true);
    try {
      await apiFetch('/api/v1/jobs/ingestion', {
        method: 'POST',
        body: JSON.stringify({ action }),
      });
      setIngestionActive(action === 'start');
    } catch (err) {
      console.error('Failed to toggle ingestion:', err);
    } finally {
      setLoading(false);
    }
  };
  
  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 animate-fade-in">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-4xl font-display font-black tracking-tighter uppercase italic text-white text-shadow-glow">Operational Command</h1>
          <p className="text-gray-500 uppercase text-xs tracking-widest mt-2 font-mono">
            GCP Terraform Infrastructure Control
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Cost Center */}
        <div className="rounded-2xl p-8 border shadow-xl bg-black/40 backdrop-blur-md relative overflow-hidden" style={{ borderColor: 'var(--border-color)' }}>
          <div className="absolute top-0 right-0 w-32 h-32 bg-green-500/5 rounded-full blur-3xl -mr-10 -mt-10 pointer-events-none" />
          <div className="flex items-center gap-3 mb-6 relative z-10">
            <div className="p-3 bg-green-500/20 rounded-xl text-green-500 border border-green-500/30">
              <DollarSign className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-lg font-display font-black uppercase tracking-widest text-white">Cost Center</h3>
              <p className="text-[10px] text-gray-500 font-mono tracking-widest uppercase">GCP Billing f1optimizer</p>
            </div>
          </div>
          
          <div className="space-y-6 relative z-10">
            <div>
              <div className="flex justify-between text-xs mb-2 font-mono uppercase tracking-widest text-gray-400">
                <span>Current Spend</span>
                <span>Budget: $200.00</span>
              </div>
              <div className="w-full bg-black border border-white/10 rounded-full h-3 overflow-hidden">
                <div className="bg-gradient-to-r from-green-500 to-green-300 h-3 rounded-full shadow-[0_0_10px_rgba(34,197,94,0.5)]" style={{ width: '35%' }}></div>
              </div>
              <div className="mt-2 text-3xl font-black font-display text-white tracking-tighter">$70.45</div>
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              <div className="p-4 rounded-xl border border-white/5 bg-white/5">
                <div className="text-[10px] uppercase tracking-widest text-gray-500 font-bold mb-1">Cloud Run API</div>
                <div className="text-lg font-mono text-white">$14.20</div>
              </div>
              <div className="p-4 rounded-xl border border-white/5 bg-white/5">
                <div className="text-[10px] uppercase tracking-widest text-gray-500 font-bold mb-1">Vertex AI Custom</div>
                <div className="text-lg font-mono text-white">$42.15</div>
              </div>
            </div>
          </div>
        </div>

        {/* Database Terminal */}
        <div className="rounded-2xl p-8 border shadow-xl bg-black/40 backdrop-blur-md relative overflow-hidden" style={{ borderColor: 'var(--border-color)' }}>
          <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500/5 rounded-full blur-3xl -mr-10 -mt-10 pointer-events-none" />
          <div className="flex items-center gap-3 mb-6 relative z-10">
            <div className="p-3 bg-blue-500/20 rounded-xl text-blue-500 border border-blue-500/30">
              <Database className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-lg font-display font-black uppercase tracking-widest text-white">Database Terminal</h3>
              <p className="text-[10px] text-gray-500 font-mono tracking-widest uppercase">db-f1-micro (Cloud SQL)</p>
            </div>
          </div>
          
          <div className="bg-black/80 rounded-xl border border-white/10 p-5 font-mono text-[11px] h-48 overflow-y-auto space-y-2 custom-scrollbar relative z-10 shadow-inner">
            <div className="text-blue-400">$ gcloud sql instances describe db-f1-micro</div>
            <div className="text-gray-300">Loading instance details...</div>
            <div className="text-green-400">status: RUNNABLE</div>
            <div className="text-gray-300">state: {"{"} state: "ONLINE" {"}"}</div>
            <div className="text-gray-300">storage: {"{"} diskSize: "10GB", usage: "1.2GB" {"}"}</div>
            <div className="text-yellow-400 mt-4">Last automatic backup: 2026-03-25T03:00:00Z</div>
            <div className="text-blue-400 mt-4">$ _</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Ingestion Control */}
        <div className="rounded-2xl p-8 border shadow-xl bg-black/40 backdrop-blur-md relative overflow-hidden" style={{ borderColor: 'var(--border-color)' }}>
           <div className="absolute top-0 right-0 w-32 h-32 bg-purple-500/5 rounded-full blur-3xl -mr-10 -mt-10 pointer-events-none" />
           <div className="flex justify-between items-start mb-6 relative z-10">
              <div className="flex items-center gap-3">
                <div className="p-3 bg-purple-500/20 rounded-xl text-purple-500 border border-purple-500/30">
                  <Terminal className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-lg font-display font-black uppercase tracking-widest text-white">Ingestion Control</h3>
                  <p className="text-[10px] text-gray-500 font-mono tracking-widest uppercase">Cloud Run Jobs</p>
                </div>
              </div>
              <div className="flex border border-white/10 rounded-lg overflow-hidden font-bold h-9 bg-black/50 backdrop-blur-sm">
                <button 
                  onClick={() => toggleIngestion('start')}
                  disabled={loading}
                  className={`flex items-center justify-center gap-2 px-4 transition-colors ${ingestionActive ? 'bg-green-600 border-green-500 text-white shadow-[0_0_15px_#16a34a]' : 'hover:bg-white/10 text-gray-400'} ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  <Play className="w-3 h-3" />
                  <span className="text-[10px] uppercase tracking-widest">Start</span>
                </button>
                <div className="w-[1px] bg-white/10" />
                <button 
                  onClick={() => toggleIngestion('stop')}
                  disabled={loading}
                  className={`flex items-center justify-center gap-2 px-4 transition-colors ${!ingestionActive ? 'bg-red-600 border-red-500 text-white shadow-[0_0_15px_#dc2626]' : 'hover:bg-white/10 text-gray-400'} ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  <Square className="w-3 h-3" />
                  <span className="text-[10px] uppercase tracking-widest">Stop</span>
                </button>
              </div>
           </div>
           
           <div className="space-y-4 relative z-10">
              <div className="p-4 rounded-xl border border-white/5 bg-white/5 flex justify-between items-center transition-all hover:bg-white/10">
                 <div>
                   <div className="text-sm font-bold text-white tracking-widest">fastf1_worker</div>
                   <div className="text-[10px] text-gray-500 uppercase tracking-widest font-mono mt-1">Telemetry Fetcher</div>
                 </div>
                 <div className="text-right">
                    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[9px] uppercase font-bold tracking-widest border ${ingestionActive ? 'text-green-400 bg-green-400/10 border-green-500/20' : 'text-gray-400 bg-gray-500/10 border-gray-500/20'}`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${ingestionActive ? 'bg-green-400 animate-pulse' : 'bg-gray-400'}`} />
                      {ingestionActive ? 'Processing' : 'Stopped'}
                    </span>
                 </div>
              </div>
              <div className="p-4 rounded-xl border border-white/5 bg-white/5 flex justify-between items-center transition-all hover:bg-white/10">
                 <div>
                   <div className="text-sm font-bold text-white tracking-widest">lap_times_worker</div>
                   <div className="text-[10px] text-gray-500 uppercase tracking-widest font-mono mt-1">Timing Aggregator</div>
                 </div>
                 <div className="text-right">
                    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[9px] uppercase font-bold tracking-widest border ${ingestionActive ? 'text-green-400 bg-green-400/10 border-green-500/20' : 'text-gray-400 bg-gray-500/10 border-gray-500/20'}`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${ingestionActive ? 'bg-green-400 animate-pulse' : 'bg-gray-400'}`} />
                      {ingestionActive ? 'Processing' : 'Stopped'}
                    </span>
                 </div>
              </div>
           </div>
        </div>

        {/* Security & IAM */}
        <div className="rounded-2xl p-8 border shadow-xl bg-black/40 backdrop-blur-md relative overflow-hidden" style={{ borderColor: 'var(--border-color)' }}>
          <div className="absolute top-0 right-0 w-32 h-32 bg-red-500/5 rounded-full blur-3xl -mr-10 -mt-10 pointer-events-none" />
          <div className="flex items-center gap-3 mb-6 relative z-10">
            <div className="p-3 bg-red-500/20 rounded-xl text-red-500 border border-red-500/30">
              <Lock className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-lg font-display font-black uppercase tracking-widest text-white">Security & IAM</h3>
              <p className="text-[10px] text-gray-500 font-mono tracking-widest uppercase">Service Account Policies</p>
            </div>
          </div>
          
          <div className="bg-[#0f0f0f] rounded-xl border border-white/10 p-5 space-y-4 relative z-10 shadow-inner">
             <div className="flex justify-between items-center pb-3 border-b border-white/5">
                <span className="text-xs text-gray-400 font-mono">f1-ingest-sa@f1optimizer</span>
                <span className="text-[10px] uppercase font-bold text-green-500 bg-green-500/10 px-2 py-0.5 rounded border border-green-500/20 shadow-[0_0_10px_rgba(34,197,94,0.1)]">Active</span>
             </div>
             <div>
                <div className="text-[10px] uppercase tracking-widest text-gray-500 font-bold mb-2">Attached Roles</div>
                <div className="space-y-2">
                  <div className="text-xs text-blue-300 font-mono bg-blue-500/10 px-3 py-1.5 rounded border border-blue-500/20 w-max hover:bg-blue-500/20 transition-colors cursor-default">roles/storage.objectAdmin</div>
                  <div className="text-xs text-blue-300 font-mono bg-blue-500/10 px-3 py-1.5 rounded border border-blue-500/20 w-max hover:bg-blue-500/20 transition-colors cursor-default">roles/cloudsql.client</div>
                  <div className="text-xs text-blue-300 font-mono bg-blue-500/10 px-3 py-1.5 rounded border border-blue-500/20 w-max hover:bg-blue-500/20 transition-colors cursor-default">roles/run.invoker</div>
                </div>
             </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default OperationalCommand;
