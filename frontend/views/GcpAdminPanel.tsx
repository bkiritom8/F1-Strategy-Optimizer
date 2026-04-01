import React from 'react';
import { Activity, Server, Disc, AlertTriangle, AlertCircle, TrendingUp } from 'lucide-react';
import { COLORS } from '../constants';
import { useAdminGcpMetrics, useAdminLogs, useAdminQuotas } from '../hooks/useApi';

const GcpAdminPanel: React.FC = () => {
  const { data: metrics, loading: metricsLoading } = useAdminGcpMetrics();
  const { data: logsData, loading: logsLoading } = useAdminLogs();
  const { data: quotas, loading: quotasLoading } = useAdminQuotas();

  const renderGauge = (value: number, label: string, color: string) => {
    return (
      <div className="flex flex-col items-center p-4 bg-white/[0.04] rounded-2xl border border-white/[0.07]">
        <div className="relative w-24 h-24 flex items-center justify-center">
          <svg className="w-full h-full transform -rotate-90">
            <circle cx="48" cy="48" r="40" stroke="currentColor" strokeWidth="8" fill="transparent" className="text-gray-800" />
            <circle
              cx="48"
              cy="48"
              r="40"
              stroke={color}
              strokeWidth="8"
              fill="transparent"
              strokeDasharray={251.2}
              strokeDashoffset={251.2 - (value / 100) * 251.2}
              className="transition-all duration-1000 ease-out"
            />
          </svg>
          <div className="absolute flex flex-col items-center">
            <span className="text-xl font-bold font-mono text-white">{value.toFixed(1)}%</span>
          </div>
        </div>
        <span className="text-[10px] uppercase tracking-[4px] text-white/40 mt-3">{label}</span>
      </div>
    );
  };

  return (
    <div className="space-y-6 animate-fade-in bg-transparent">
      {/* Header section */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-2xl font-bold tracking-tight uppercase italic text-white flex items-center gap-3">
            <Server className="w-6 h-6 text-blue-500" />
            Live Cloud Infrastructure
          </h2>
          <p className="text-sm text-white/40 mt-1 font-mono">GCP Cloud Run & Monitoring Metrics</p>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 bg-blue-500/10 border border-blue-500/30 rounded-full">
          <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
          <span className="text-[10px] uppercase tracking-widest text-blue-400 font-bold">Live Stream</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column - Metrics & Quotas */}
        <div className="lg:col-span-1 space-y-6">
          {/* Hardware Metrics */}
          <div className="bg-white/[0.04] backdrop-blur-md rounded-3xl p-6 border border-white/[0.07] shadow-xl relative overflow-hidden">
            <h3 className="text-[10px] uppercase tracking-[4px] text-white/40 mb-6 flex items-center gap-2">
              <Activity className="w-4 h-4 text-green-500" /> Server Load
            </h3>
            
            {metricsLoading ? (
              <div className="flex justify-center py-10"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white" /></div>
            ) : metrics ? (
              <div className="grid grid-cols-2 gap-4">
                {renderGauge(metrics.cpu_usage_percent, 'CPU Usage', COLORS.accent.green)}
                {renderGauge(metrics.memory_usage_percent, 'Memory', COLORS.accent.blue)}
                <div className="col-span-2 flex justify-between items-center p-4 bg-white/[0.04] rounded-xl mt-2 border border-white/[0.07]">
                  <div>
                    <p className="text-[10px] uppercase tracking-[4px] text-white/40 mb-1">Active Instances</p>
                    <p className="text-xl font-mono text-white">{metrics.active_instances}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-[10px] uppercase tracking-[4px] text-white/40 mb-1">Total Requests</p>
                    <p className="text-xl font-mono text-green-400">{metrics.request_count}</p>
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-sm text-red-500 font-mono">Failed to load metrics</p>
            )}
          </div>

          {/* Quotas */}
          <div className="bg-white/[0.04] backdrop-blur-md rounded-3xl p-6 border border-white/[0.07] shadow-xl relative overflow-hidden">
            <h3 className="text-[10px] uppercase tracking-[4px] text-white/40 mb-6 flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-purple-500" /> Usage Quotas
            </h3>
            
            {quotasLoading ? (
               <div className="flex justify-center py-4"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white" /></div>
            ) : quotas ? (
              <div className="space-y-4">
                <div className="bg-white/[0.04] p-4 rounded-xl border border-white/[0.07]">
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-xs uppercase tracking-widest text-purple-400 font-bold">Gemini API</span>
                    <span className="text-xs font-mono text-white">{quotas.gemini_api.tokens_used.toLocaleString()} / 1M</span>
                  </div>
                  <div className="w-full h-2 bg-white/[0.07] rounded-full overflow-hidden">
                    <div className="h-full bg-purple-500" style={{ width: `${Math.min(100, (quotas.gemini_api.tokens_used / 1000000) * 100)}%` }} />
                  </div>
                </div>
                
                <div className="bg-white/[0.04] p-4 rounded-xl border border-white/[0.07] flex justify-between items-center">
                  <div>
                    <p className="text-[10px] uppercase tracking-[4px] text-white/40 mb-1">Cloud Run Status</p>
                    <p className="text-sm font-bold text-white capitalize">{quotas.cloud_run.status}</p>
                  </div>
                  <div className="text-right">
                     <p className="text-[10px] uppercase tracking-[4px] text-white/40 mb-1">Compute Seconds</p>
                     <p className="text-sm font-mono text-white">{quotas.cloud_run.cpu_seconds.toLocaleString()}</p>
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-sm text-red-500 font-mono">Failed to load quotas</p>
            )}
          </div>
        </div>

        {/* Right Column - Logs */}
        <div className="lg:col-span-2 bg-white/[0.04] backdrop-blur-md flex flex-col rounded-3xl border border-white/[0.07] shadow-xl overflow-hidden">
          <div className="p-6 border-b border-white/[0.07] bg-white/[0.03] flex items-center justify-between">
            <h3 className="text-[10px] uppercase tracking-[4px] text-white/40 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-yellow-500" /> System Logs (Errors & Warnings)
            </h3>
            <span className="text-xs font-mono px-2 py-1 bg-yellow-500/10 text-yellow-500 rounded border border-yellow-500/20">
              {logsData?.logs.length || 0} Entries
            </span>
          </div>
          
          <div className="flex-1 p-6 overflow-y-auto min-h-[400px]">
             {logsLoading ? (
               <div className="flex h-full items-center justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-500" /></div>
             ) : logsData && logsData.logs.length > 0 ? (
               <div className="space-y-4">
                 {logsData.logs.map((log, i) => (
                   <div key={i} className="flex gap-4 p-4 rounded-xl bg-white/[0.04] border border-white/[0.07] items-start">
                     <div className="shrink-0 mt-0.5">
                       {log.severity.toUpperCase() === 'ERROR' ? (
                         <AlertCircle className="w-5 h-5 text-red-500" />
                       ) : (
                         <AlertTriangle className="w-5 h-5 text-yellow-500" />
                       )}
                     </div>
                     <div className="flex-1 overflow-hidden">
                       <div className="flex items-center gap-3 mb-1">
                         <span className={`text-[10px] font-black tracking-widest px-2 py-0.5 rounded ${log.severity.toUpperCase() === 'ERROR' ? 'bg-red-500/20 text-red-400' : 'bg-yellow-500/20 text-yellow-400'}`}>
                           {log.severity}
                         </span>
                         <span className="text-xs font-mono text-white/40">
                           {log.timestamp ? new Date(log.timestamp).toLocaleString() : 'N/A'}
                         </span>
                       </div>
                       <p className="text-sm font-mono text-gray-300 break-words whitespace-pre-wrap mt-2 leading-relaxed">
                         {log.message}
                       </p>
                     </div>
                   </div>
                 ))}
               </div>
             ) : (
               <div className="flex h-full flex-col items-center justify-center text-gray-600">
                 <Disc className="w-12 h-12 mb-4 opacity-20" />
                 <p className="text-sm font-mono uppercase tracking-widest font-bold">No High-Severity Logs</p>
                 <p className="text-xs mt-2">Systems operating normally</p>
               </div>
             )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default GcpAdminPanel;
