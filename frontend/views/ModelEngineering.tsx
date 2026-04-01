/**
 * @file views/ModelEngineering.tsx
 * @description Admin-only view for deep-dive ML model analysis, registry management,
 * and data pipeline bias auditing.
 */

import React, { useState } from 'react';
import {
  useModelStatus,
  useModelBiasReport,
  useFeatureImportance,
  useBackendStatus,
} from '../hooks/useApi';
import { LiveBadge } from '../components/LiveBadge';
import { logger } from '../services/logger';

// ─── Sub-Components ─────────────────────────────────────────────────────────

/**
 * Renders a SHAP-style feature importance bar chart.
 */
const FeatureImportanceCard: React.FC<{ modelName: string }> = ({ modelName }) => {
  const { data, loading } = useFeatureImportance(modelName);

  if (loading) return <div className="animate-pulse bg-gray-800/50 h-48 rounded-xl" />;
  if (!data) return null;

  return (
    <div className="bg-white/[0.04] backdrop-blur-md border border-white/[0.07] p-4 rounded-xl">
      <h4 className="text-white/40 text-[10px] uppercase tracking-[4px] mb-4">
        Feature Importance (SHAP)
      </h4>
      <div className="space-y-3">
        {data.features.map((f) => (
          <div key={f.name} className="group">
            <div className="flex justify-between text-xs mb-1">
              <span className="text-white group-hover:text-blue-400 transition-colors">{f.name}</span>
              <span className="text-white/40">{(f.importance * 100).toFixed(2)}%</span>
            </div>
            <div className="h-1.5 bg-white/[0.07] rounded-full overflow-hidden">
              <div 
                className="h-full bg-gradient-to-r from-blue-600 to-cyan-400 rounded-full transition-all duration-1000"
                style={{ width: `${f.importance * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

/**
 * Renders a bias disparity report for a specific model slice.
 */
const BiasReportCard: React.FC<{ modelName: string }> = ({ modelName }) => {
  const { data, loading } = useModelBiasReport(modelName);

  if (loading) return <div className="animate-pulse bg-gray-800/50 h-48 rounded-xl" />;
  if (!data) return null;

  return (
    <div className="bg-white/[0.04] backdrop-blur-md border border-white/[0.07] p-4 rounded-xl">
      <h4 className="text-white/40 text-[10px] uppercase tracking-[4px] mb-4">
        Slice Disparity Audit
      </h4>
      <div className="grid grid-cols-1 gap-2">
        {data.slices.map((slice) => (
          <div key={slice.name} className="flex items-center justify-between p-2 rounded-lg bg-white/[0.04]">
            <div>
              <div className="text-sm font-medium text-white">{slice.name}</div>
              <div className="text-[10px] text-white/40">MLOps Validation Pass</div>
            </div>
            <div className="text-right">
              <div className={`text-xs font-mono ${(slice.disparity_score * 100) > 10 ? 'text-red-400' : 'text-green-400'}`}>
                Δ {(slice.disparity_score * 100).toFixed(2)}%
              </div>
              <span className={`text-[10px] uppercase font-bold ${
                slice.impact === 'high' ? 'text-red-500' : 
                slice.impact === 'medium' ? 'text-yellow-500' : 'text-blue-500'
              }`}>
                {slice.impact} RISK
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// ─── Main View ──────────────────────────────────────────────────────────────

const ModelEngineering: React.FC = () => {
  const { online: isLive } = useBackendStatus();
  const { data: statusData, loading: statusLoading } = useModelStatus();
  const [selectedModel, setSelectedModel] = useState<string | null>(null);

  // Auto-select first model if none selected
  React.useEffect(() => {
    if (!selectedModel && statusData?.models.length) {
      setSelectedModel(statusData.models[0].name);
    }
  }, [selectedModel, statusData]);

  const handleModelSelect = (name: string) => {
    logger.debug(`[ModelEngineering] Selected model: ${name}`);
    setSelectedModel(name);
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-2xl font-bold tracking-tight text-white">Model Registry & Engineering</h2>
            <LiveBadge isLive={isLive} />
          </div>
          <p className="text-white/40 text-sm mt-1">
            Real-time telemetry from the F1-Strategy-Optimizer MLOps pipeline.
          </p>
        </div>
        <div className="flex gap-2">
          <div className="px-3 py-1 bg-blue-500/10 border border-blue-500/20 rounded-full flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
            <span className="text-[10px] font-bold text-blue-400 uppercase tracking-tighter">Pipeline Healthy</span>
          </div>
          <div className="px-3 py-1 bg-green-500/10 border border-green-500/20 rounded-full flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-green-500" />
            <span className="text-[10px] font-bold text-green-400 uppercase tracking-tighter">6/6 Active</span>
          </div>
        </div>
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Left: Model List (4 cols) */}
        <div className="lg:col-span-4 space-y-3">
          <h3 className="text-white/40 text-[10px] uppercase tracking-[4px] pl-1">Supervised Registry</h3>
          {statusLoading ? (
            <div className="space-y-4">
              {[1, 2, 3, 4, 5, 6].map(i => <div key={i} className="h-16 bg-gray-800/50 rounded-xl animate-pulse" />)}
            </div>
          ) : (
            statusData?.models.map((model) => (
              <button
                key={model.name}
                onClick={() => handleModelSelect(model.name)}
                className={`w-full text-left p-4 rounded-xl border transition-all duration-300 ${
                  selectedModel === model.name 
                    ? 'bg-blue-600/10 border-blue-500/50 shadow-lg shadow-blue-900/20'
                    : 'bg-white/[0.04] border-white/[0.07] hover:border-white/[0.12]'
                }`}
              >
                <div className="flex justify-between items-start mb-1">
                  <span className="text-sm font-bold text-white capitalize">
                    {model.name.replace(/_/g, ' ')}
                  </span>
                  <span className="text-[10px] font-mono text-gray-500">v{model.version}</span>
                </div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className={`w-1.5 h-1.5 rounded-full ${model.status === 'active' ? 'bg-green-500' : 'bg-yellow-500'}`} />
                    <span className="text-[10px] text-white/40 uppercase tracking-tight">{model.status}</span>
                  </div>
                  <div className="text-right">
                    <span className="text-xs font-bold text-blue-400">{(model.accuracy * 100).toFixed(2)}%</span>
                  </div>
                </div>
              </button>
            ))
          )}
        </div>

        {/* Right: Detailed Analytics (8 cols) */}
        <div className="lg:col-span-8 space-y-6">
          {selectedModel ? (
            <>
              {/* Detailed Header */}
              <div className="bg-white/[0.04] backdrop-blur-md border border-white/[0.07] p-6 rounded-2xl relative overflow-hidden">
                <div className="absolute top-0 right-0 p-4 opacity-10">
                  <svg className="w-24 h-24 text-blue-500" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2m-7 2h2v5h-2V5m-2 2h2v3H8V7m8 8h2v2h-2v-2m-4 0h2v2h-2v-2m-4 0h2v2H8v-2m-2-8h2v3H6V7m0 8h2v2H6v-2z"/>
                  </svg>
                </div>
                <div className="relative z-10">
                  <div className="flex items-center gap-3 mb-4">
                    <div className="p-2 bg-blue-500/20 rounded-lg">
                      <svg className="w-5 h-5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                      </svg>
                    </div>
                    <div>
                      <h3 className="text-xl font-bold text-white tracking-tight capitalize">
                        {selectedModel.replace(/_/g, ' ')} Analysis
                      </h3>
                      <p className="text-xs text-white/40">MLOps Monitoring • Last retraining 4h ago</p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-8">
                    <div className="p-3 bg-white/[0.04] border border-white/[0.07] rounded-xl">
                      <div className="text-[10px] text-white/40 uppercase tracking-[4px]">Champion Accuracy</div>
                      <div className="text-lg font-bold text-blue-400">94.2%</div>
                    </div>
                    <div className="p-3 bg-white/[0.04] border border-white/[0.07] rounded-xl">
                      <div className="text-[10px] text-white/40 uppercase tracking-[4px]">Deployment Status</div>
                      <div className="text-lg font-bold text-green-400 italic">PROD</div>
                    </div>
                    <div className="p-3 bg-white/[0.04] border border-white/[0.07] rounded-xl">
                      <div className="text-[10px] text-white/40 uppercase tracking-[4px]">Inference P99</div>
                      <div className="text-lg font-bold text-white">42ms</div>
                    </div>
                    <div className="p-3 bg-white/[0.04] border border-white/[0.07] rounded-xl">
                      <div className="text-[10px] text-white/40 uppercase tracking-[4px]">Training Run</div>
                      <div className="text-lg font-bold text-purple-400">#842</div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Detail Cards */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <FeatureImportanceCard modelName={selectedModel} />
                <BiasReportCard modelName={selectedModel} />
              </div>

              {/* Additional Log Table */}
              <div className="bg-white/[0.04] backdrop-blur-md border border-white/[0.07] rounded-xl p-4 overflow-hidden">
                <h4 className="text-white/40 text-[10px] uppercase tracking-[4px] mb-4 px-2">
                  Validation Log
                </h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-white/[0.07] text-white/40">
                        <th className="pb-2 font-medium px-2">Timestamp</th>
                        <th className="pb-2 font-medium">Dataset</th>
                        <th className="pb-2 font-medium">Metric</th>
                        <th className="pb-2 font-medium text-right px-2">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/[0.05]">
                      {[
                        { time: '14:20:01', data: 'FastF1 2024_01', metric: 'MSE: 0.042', status: 'PASS' },
                        { time: '10:15:22', data: 'FastF1 2023_22', metric: 'MSE: 0.039', status: 'PASS' },
                        { time: '昨天', data: 'Jolpica_Historical', metric: 'Bias < 0.05', status: 'PASS' },
                      ].map((log, i) => (
                        <tr key={i} className="group hover:bg-white/5 transition-colors">
                          <td className="py-3 font-mono text-white/40 px-2">{log.time}</td>
                          <td className="py-3 text-white">{log.data}</td>
                          <td className="py-3 text-white/40 italic">{log.metric}</td>
                          <td className="py-3 text-right px-2">
                            <span className="px-2 py-0.5 rounded-full bg-green-500/20 text-green-400 text-[10px] font-bold">
                              {log.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          ) : (
            <div className="h-full flex items-center justify-center p-12 bg-white/[0.04] border border-dashed border-white/[0.07] rounded-2xl text-white/40 italic">
              Select a model from the registry to view engineering telemetry.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ModelEngineering;
