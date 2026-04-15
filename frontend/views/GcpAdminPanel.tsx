import React from 'react';
import { Activity, AlertCircle, AlertTriangle, Disc, RefreshCcw, Server, TrendingUp } from 'lucide-react';
import { useAdminGcpMetrics, useAdminLogs, useAdminQuotas, useBackendStatus } from '../hooks/useApi';
import { LiveBadge } from '../components/LiveBadge';

const GcpAdminPanel: React.FC = () => {
  const { online: isLive } = useBackendStatus();
  const { data: metrics, loading: metricsLoading } = useAdminGcpMetrics();
  const { data: logsData, loading: logsLoading, error: logsError, refetch: refetchLogs } = useAdminLogs();
  const { data: quotas, loading: quotasLoading, error: quotasError, refetch: refetchQuotas } = useAdminQuotas();

  const formatLogMessage = (log: any) => {
    const candidates = [
      log?.message,
      log?.textPayload,
      log?.jsonPayload?.message,
      log?.jsonPayload?.text,
      log?.payload,
    ];

    const firstMessage = candidates.find((value) => typeof value === 'string' && value.trim());
    if (firstMessage) return firstMessage.trim();

    return 'Cloud Logging entry did not include a message payload.';
  };

  const renderMetricCard = (title: string, value: React.ReactNode, caption: string, icon: React.ReactNode) => (
    <div className="rounded-2xl bg-white/[0.04] border border-white/[0.07] p-5 shadow-lg shadow-black/10">
      <div className="flex items-center justify-between gap-4 mb-4">
        <div>
          <div className="text-[10px] uppercase tracking-[4px] text-white/40 mb-1">{title}</div>
          <div className="text-2xl font-bold text-white">{value}</div>
        </div>
        <div className="w-11 h-11 rounded-2xl bg-white/[0.05] border border-white/[0.07] flex items-center justify-center text-white/60">
          {icon}
        </div>
      </div>
      <p className="text-xs text-white/40">{caption}</p>
    </div>
  );

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-white flex items-center gap-3">
            <TrendingUp className="w-6 h-6 text-yellow-400" />
            GCP Backend
          </h2>
          <p className="text-white/40 text-sm mt-1">System load, request volume, admin log visibility, and quota status</p>
        </div>
        <LiveBadge isLive={isLive} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {metricsLoading ? (
          [...Array(4)].map((_, index) => <div key={index} className="h-28 rounded-2xl bg-white/5 animate-pulse" />)
        ) : metrics ? (
          <>
            {renderMetricCard('CPU', `${metrics.cpu_usage_percent}%`, 'Current CPU usage across active instances', <Activity className="w-5 h-5" />)}
            {renderMetricCard('Memory', `${metrics.memory_usage_percent}%`, 'Heap and container memory pressure', <Server className="w-5 h-5" />)}
            {renderMetricCard('Instances', metrics.active_instances, 'Active Cloud Run instances', <Disc className="w-5 h-5" />)}
            {renderMetricCard('Requests', metrics.request_count, 'Requests observed in the current window', <TrendingUp className="w-5 h-5" />)}
          </>
        ) : null}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-red-500" />
                System Logs (Errors & Warnings)
              </h3>
              <p className="text-white/40 text-sm mt-1">Recent log entries from Cloud Logging</p>
            </div>
            {logsError && (
              <button
                onClick={refetchLogs}
                className="inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-red-600/15 text-red-300 text-[10px] font-black uppercase tracking-widest border border-red-500/20 hover:bg-red-600/25 transition-colors"
              >
                <RefreshCcw className="w-4 h-4" />
                Retry
              </button>
            )}
          </div>

          {logsLoading ? (
            <div className="space-y-3">
              {[...Array(4)].map((_, index) => (
                <div key={index} className="h-24 rounded-2xl bg-white/5 animate-pulse" />
              ))}
            </div>
          ) : logsError ? (
            <div className="rounded-2xl border border-red-500/20 bg-red-500/10 p-5 space-y-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-red-500/15 border border-red-500/20 flex items-center justify-center">
                  <AlertCircle className="w-5 h-5 text-red-300" />
                </div>
                <div>
                  <div className="text-sm font-bold text-white">Log endpoint unavailable</div>
                  <div className="text-xs text-white/55">The backend did not return structured log data.</div>
                </div>
              </div>
              <p className="text-xs font-mono text-red-200/80 break-all">{logsError}</p>
            </div>
          ) : (logsData?.logs || []).length > 0 ? (
            <div className="space-y-3">
              {(logsData?.logs || []).map((log: any, index: number) => (
                <div key={index} className="rounded-2xl bg-white/[0.04] border border-white/[0.07] p-4">
                  <div className="flex items-center justify-between gap-4 mb-3">
                    <div className="flex items-center gap-3">
                      <span className={`inline-flex items-center px-2.5 py-1 rounded-md text-[10px] font-black uppercase tracking-widest ${
                        log.severity === 'ERROR' ? 'bg-red-600/20 text-red-400' :
                        log.severity === 'WARNING' ? 'bg-yellow-600/20 text-yellow-400' :
                        'bg-blue-600/20 text-blue-400'
                      }`}>
                        {log.severity || 'ERROR'}
                      </span>
                      <span className="text-[10px] font-mono text-white/35">
                        {log.timestamp ? new Date(log.timestamp).toLocaleString() : 'N/A'}
                      </span>
                    </div>
                  </div>
                  <p className="text-sm font-mono text-white/80 leading-relaxed break-words whitespace-pre-wrap">
                    {formatLogMessage(log)}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-white/[0.07] bg-white/[0.03] p-8 text-center text-white/40">
              <div className="w-12 h-12 mx-auto mb-4 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center">
                <Disc className="w-6 h-6 opacity-30" />
              </div>
              <p className="text-sm font-black uppercase tracking-widest">No High-Severity Logs</p>
              <p className="text-xs mt-2">Systems operating normally</p>
            </div>
          )}
        </div>

        <div className="space-y-4">
          <div>
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              <Server className="w-5 h-5 text-green-400" />
              Quota Status
            </h3>
            <p className="text-white/40 text-sm mt-1">Usage limits and backend health checks</p>
          </div>

          {quotasLoading ? (
            <div className="space-y-3">
              {[...Array(2)].map((_, index) => <div key={index} className="h-28 rounded-2xl bg-white/5 animate-pulse" />)}
            </div>
          ) : quotasError ? (
            <div className="rounded-2xl border border-red-500/20 bg-red-500/10 p-5 space-y-3">
              <div className="text-sm font-bold text-white">Quota data unavailable</div>
              <p className="text-xs text-white/60 break-all">{quotasError}</p>
              <button
                onClick={refetchQuotas}
                className="inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-red-600 text-white text-[10px] font-black uppercase tracking-widest hover:bg-red-700 transition-colors"
              >
                <RefreshCcw className="w-4 h-4" />
                Retry
              </button>
            </div>
          ) : quotas ? (
            <div className="space-y-4">
              <div className="rounded-2xl bg-white/[0.04] border border-white/[0.07] p-5">
                <div className="text-[10px] uppercase tracking-[4px] text-white/40 mb-2">Gemini API</div>
                <div className="flex items-center justify-between gap-4 mb-3">
                  <div className="text-2xl font-bold text-white">{quotas.gemini_api.tokens_used}</div>
                  <div className="text-xs font-black uppercase tracking-widest text-white/40">/ {quotas.gemini_api.quota_limit}</div>
                </div>
                <div className="h-2 rounded-full bg-white/10 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${quotas.gemini_api.status === 'critical' ? 'bg-red-500' : 'bg-green-500'}`}
                    style={{ width: `${Math.min(100, (quotas.gemini_api.tokens_used / Math.max(1, quotas.gemini_api.quota_limit)) * 100)}%` }}
                  />
                </div>
                <p className="text-xs text-white/40 mt-2 uppercase tracking-widest">{quotas.gemini_api.status}</p>
              </div>

              <div className="rounded-2xl bg-white/[0.04] border border-white/[0.07] p-5">
                <div className="text-[10px] uppercase tracking-[4px] text-white/40 mb-2">Cloud Run</div>
                <div className="flex items-center justify-between gap-4 mb-3">
                  <div className="text-2xl font-bold text-white">{quotas.cloud_run.cpu_seconds}</div>
                  <div className="text-xs font-black uppercase tracking-widest text-white/40">/ {quotas.cloud_run.quota_limit}</div>
                </div>
                <div className="h-2 rounded-full bg-white/10 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${quotas.cloud_run.status === 'critical' ? 'bg-red-500' : 'bg-cyan-400'}`}
                    style={{ width: `${Math.min(100, (quotas.cloud_run.cpu_seconds / Math.max(1, quotas.cloud_run.quota_limit)) * 100)}%` }}
                  />
                </div>
                <p className="text-xs text-white/40 mt-2 uppercase tracking-widest">{quotas.cloud_run.status}</p>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
};

export default GcpAdminPanel;