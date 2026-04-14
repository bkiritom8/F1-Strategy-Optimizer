/**
 * @file views/DatabaseMetrics.tsx
 * @description Database and resource metrics dashboard for admins.
 * Displays API quotas (Gemini, Cloud Run) and live system metrics.
 */

import React from 'react';
import { Database, BarChart3, TrendingUp, AlertCircle, Zap } from 'lucide-react';
import { useAdminGcpMetrics, useAdminQuotas, useBackendStatus } from '../hooks/useApi';
import { LiveBadge } from '../components/LiveBadge';

const DatabaseMetrics: React.FC = () => {
  const { online: isLive } = useBackendStatus();
  const { data: metricsData, loading: metricsLoading } = useAdminGcpMetrics();
  const { data: quotasData, loading: quotasLoading } = useAdminQuotas();

  const loading = metricsLoading || quotasLoading;

  if (loading) {
    return (
      <div className="space-y-8">
        <div className="animate-pulse space-y-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-24 bg-white/5 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  const metrics = metricsData || {};
  const quotas = quotasData || {};

  // Render quota bar
  const renderQuotaBar = (used: number, limit: number) => {
    const percentage = Math.min((used / limit) * 100, 100);
    return (
      <div className="space-y-2">
        <div className="flex justify-between items-center">
          <span className="text-xs text-white/60">{used.toLocaleString()} / {limit.toLocaleString()}</span>
          <span className="text-xs font-bold text-white/40">{percentage.toFixed(1)}%</span>
        </div>
        <div className="w-full h-2 bg-white/10 rounded-full overflow-hidden">
          <div
            className={`h-full transition-all ${
              percentage > 80 ? 'bg-red-600' :
              percentage > 60 ? 'bg-yellow-600' :
              'bg-green-600'
            }`}
            style={{ width: `${percentage}%` }}
          />
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-white flex items-center gap-3">
            <Database className="w-6 h-6 text-green-500" />
            Resource & API Quotas
          </h2>
          <p className="text-white/40 text-sm mt-1">System resource usage and API consumption</p>
        </div>
        <LiveBadge isLive={isLive} />
      </div>

      {/* System Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="p-6 rounded-2xl bg-white/[0.04] backdrop-blur-md border border-white/[0.07] shadow-lg">
          <div className="flex items-center justify-between mb-3">
            <div className="text-[10px] uppercase tracking-[4px] text-white/40">CPU Usage</div>
            <BarChart3 className="w-4 h-4 text-blue-500" />
          </div>
          <div className="text-3xl font-bold text-white">{(metrics.cpu_usage_percent || 0).toFixed(1)}%</div>
          <div className="mt-3 h-1.5 bg-white/10 rounded-full overflow-hidden">
            <div
              className={`h-full ${
                (metrics.cpu_usage_percent || 0) > 80 ? 'bg-red-600' :
                (metrics.cpu_usage_percent || 0) > 60 ? 'bg-yellow-600' :
                'bg-blue-600'
              }`}
              style={{ width: `${Math.min(metrics.cpu_usage_percent || 0, 100)}%` }}
            />
          </div>
          <p className="text-xs text-white/40 mt-2">Server CPU load</p>
        </div>

        <div className="p-6 rounded-2xl bg-white/[0.04] backdrop-blur-md border border-white/[0.07] shadow-lg">
          <div className="flex items-center justify-between mb-3">
            <div className="text-[10px] uppercase tracking-[4px] text-white/40">Memory Usage</div>
            <TrendingUp className="w-4 h-4 text-purple-500" />
          </div>
          <div className="text-3xl font-bold text-white">{(metrics.memory_usage_percent || 0).toFixed(1)}%</div>
          <div className="mt-3 h-1.5 bg-white/10 rounded-full overflow-hidden">
            <div
              className={`h-full ${
                (metrics.memory_usage_percent || 0) > 80 ? 'bg-red-600' :
                (metrics.memory_usage_percent || 0) > 60 ? 'bg-yellow-600' :
                'bg-purple-600'
              }`}
              style={{ width: `${Math.min(metrics.memory_usage_percent || 0, 100)}%` }}
            />
          </div>
          <p className="text-xs text-white/40 mt-2">RAM allocation</p>
        </div>

        <div className="p-6 rounded-2xl bg-white/[0.04] backdrop-blur-md border border-white/[0.07] shadow-lg">
          <div className="flex items-center justify-between mb-3">
            <div className="text-[10px] uppercase tracking-[4px] text-white/40">Request Count</div>
            <Zap className="w-4 h-4 text-yellow-500" />
          </div>
          <div className="text-3xl font-bold text-white">{((metrics.request_count || 0) / 1000).toFixed(1)}k</div>
          <p className="text-xs text-white/40 mt-2">Total API requests today</p>
        </div>
      </div>

      {/* API Quotas */}
      <div className="space-y-6">
        <h3 className="text-lg font-bold tracking-tight text-white">API Quota Usage</h3>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Gemini API */}
          {quotas?.gemini_api && (
            <div className="p-6 rounded-2xl bg-white/[0.04] backdrop-blur-md border border-white/[0.07] shadow-lg">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-red-500"></div>
                  <span className="font-bold text-white">Gemini API</span>
                </div>
                <span className={`text-[10px] font-bold uppercase tracking-widest px-2 py-1 rounded-md ${
                  quotas.gemini_api.status === 'healthy' 
                    ? 'bg-green-600/20 text-green-400' 
                    : 'bg-yellow-600/20 text-yellow-400'
                }`}>
                  {quotas.gemini_api.status}
                </span>
              </div>
              {renderQuotaBar(quotas.gemini_api.tokens_used || 0, quotas.gemini_api.quota_limit || 1000000)}
              <p className="text-xs text-white/40 mt-3">Tokens used for LLM operations</p>
            </div>
          )}

          {/* Cloud Run */}
          {quotas?.cloud_run && (
            <div className="p-6 rounded-2xl bg-white/[0.04] backdrop-blur-md border border-white/[0.07] shadow-lg">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-blue-500"></div>
                  <span className="font-bold text-white">Cloud Run</span>
                </div>
                <span className={`text-[10px] font-bold uppercase tracking-widest px-2 py-1 rounded-md ${
                  quotas.cloud_run.status === 'healthy' 
                    ? 'bg-green-600/20 text-green-400' 
                    : 'bg-yellow-600/20 text-yellow-400'
                }`}>
                  {quotas.cloud_run.status}
                </span>
              </div>
              {renderQuotaBar(quotas.cloud_run.cpu_seconds || 0, quotas.cloud_run.quota_limit || 180000)}
              <p className="text-xs text-white/40 mt-3">CPU-seconds allocated for serverless compute</p>
            </div>
          )}
        </div>
      </div>

      {/* Recommendation Card */}
      <div className="p-6 rounded-2xl bg-white/[0.04] border border-white/[0.07] flex items-start gap-4">
        <AlertCircle className="w-5 h-5 text-cyan-400 shrink-0 mt-0.5" />
        <div>
          <div className="font-bold text-white mb-1">Quota Management</div>
          <p className="text-sm text-white/60">
            Monitor these metrics to prevent service interruptions. If Gemini API exceeds 85% or Cloud Run exceeds 90%, consider scaling up your quotas.
          </p>
        </div>
      </div>
    </div>
  );
};

export default DatabaseMetrics;
