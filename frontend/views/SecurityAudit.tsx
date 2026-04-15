/**
 * @file views/SecurityAudit.tsx
 * @description Security audit and logging dashboard for admins.
 * Displays recent error-level logs from Cloud Logging API.
 */

import React from 'react';
import { AlertTriangle, AlertCircle, RefreshCcw } from 'lucide-react';
import { useAdminLogs, useBackendStatus } from '../hooks/useApi';
import { LiveBadge } from '../components/LiveBadge';

const SecurityAudit: React.FC = () => {
  const { online: isLive } = useBackendStatus();
  const { data: logsData, loading, error, refetch } = useAdminLogs();

  const formatLogMessage = (log: any) => {
    const candidates = [
      log?.message,
      log?.textPayload,
      log?.jsonPayload?.message,
      log?.jsonPayload?.text,
    ];

    const firstMessage = candidates.find((value) => typeof value === 'string' && value.trim());
    if (firstMessage) return firstMessage.trim();

    return 'Cloud Logging entry did not include a message payload.';
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="animate-pulse space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-16 bg-white/5 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  const logs = logsData?.logs || [];

  if (error) {
    return (
      <div className="space-y-8 animate-in fade-in duration-500">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold tracking-tight text-white flex items-center gap-3">
              <AlertTriangle className="w-6 h-6 text-red-500" />
              Error Logs
            </h2>
            <p className="text-white/40 text-sm mt-1">Recent error-level events from Cloud Logging</p>
          </div>
          <LiveBadge isLive={isLive} />
        </div>

        <div className="rounded-2xl border border-red-500/20 bg-red-500/10 p-6 sm:p-8 text-center space-y-4">
          <div className="w-14 h-14 mx-auto rounded-2xl bg-red-500/15 border border-red-500/20 flex items-center justify-center">
            <AlertTriangle className="w-7 h-7 text-red-400" />
          </div>
          <div className="space-y-2">
            <h3 className="text-lg font-bold text-white">Unable to load admin logs</h3>
            <p className="text-sm text-white/60 max-w-2xl mx-auto">
              The admin log endpoint returned an error, so the panel cannot distinguish whether there are no logs or the backend is unavailable.
            </p>
            <p className="text-xs font-mono text-red-300/90 break-all">{error}</p>
          </div>
          <button
            onClick={refetch}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-red-600 text-white text-xs font-black uppercase tracking-widest hover:bg-red-700 transition-colors"
          >
            <RefreshCcw className="w-4 h-4" />
            Retry Fetch
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-white flex items-center gap-3">
            <AlertTriangle className="w-6 h-6 text-red-500" />
            Error Logs
          </h2>
          <p className="text-white/40 text-sm mt-1">Recent error-level events from Cloud Logging</p>
        </div>
        <LiveBadge isLive={isLive} />
      </div>

      {/* Logs Table */}
      {logs.length > 0 ? (
        <div className="rounded-2xl bg-white/[0.04] border border-white/[0.07] overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-white/[0.05] border-b border-white/[0.07]">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-bold uppercase tracking-widest text-white/60">Timestamp</th>
                  <th className="px-6 py-3 text-left text-xs font-bold uppercase tracking-widest text-white/60">Severity</th>
                  <th className="px-6 py-3 text-left text-xs font-bold uppercase tracking-widest text-white/60">Message</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.07]">
                {logs.map((log: any, idx: number) => (
                  <tr key={idx} className="hover:bg-white/[0.02] transition-colors">
                    <td className="px-6 py-4 text-xs text-white/40 font-mono">
                      {log.timestamp ? new Date(log.timestamp).toLocaleString() : 'N/A'}
                    </td>
                    <td className="px-6 py-4">
                      <span className={`inline-block px-2 py-1 rounded-md text-[10px] font-bold uppercase tracking-widest ${
                        log.severity === 'ERROR' ? 'bg-red-600/20 text-red-400' :
                        log.severity === 'WARNING' ? 'bg-yellow-600/20 text-yellow-400' :
                        'bg-blue-600/20 text-blue-400'
                      }`}>
                        {log.severity || 'ERROR'}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-white/70 max-w-2xl truncate font-mono">
                      {formatLogMessage(log)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center p-12 bg-white/[0.04] border border-dashed border-white/[0.07] rounded-2xl text-white/40 italic">
          <AlertCircle className="w-12 h-12 mb-4 opacity-20" />
          <p className="text-sm">No recent errors detected</p>
        </div>
      )}

      {/* Info */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="p-6 rounded-2xl bg-white/[0.04] backdrop-blur-md border border-white/[0.07] shadow-lg">
          <div className="text-[10px] uppercase tracking-[4px] text-white/40 mb-2">Log Retention</div>
          <div className="text-2xl font-bold text-white">50 entries</div>
          <p className="text-xs text-white/40 mt-2">Most recent error-level events</p>
        </div>
        <div className="p-6 rounded-2xl bg-white/[0.04] backdrop-blur-md border border-white/[0.07] shadow-lg">
          <div className="text-[10px] uppercase tracking-[4px] text-white/40 mb-2">Data Source</div>
          <div className="text-2xl font-bold text-white">Google Cloud Logging</div>
          <p className="text-xs text-white/40 mt-2">Real-time backend diagnostics</p>
        </div>
      </div>
    </div>
  );
};

export default SecurityAudit;
