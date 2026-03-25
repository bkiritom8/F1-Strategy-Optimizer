/**
 * @file views/AdminPage.tsx
 * @description Admin Control Center for Apex Intelligence.
 *
 * Provides operational visibility into five areas:
 *   Overview  – system health summary
 *   Cost Center – GCP budget tracker ($200 cap)
 *   Database Terminal – Cloud SQL status
 *   Ingestion Control – Cloud Run job cards
 *   Security / IAM – service account permissions
 *
 * All data is mock/static; no real GCP API calls are made here.
 * Authentication is gated by the VITE_ADMIN_PASSWORD env variable.
 */

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Shield, DollarSign, Database, Cpu, Lock,
  CheckCircle, AlertTriangle, XCircle, RefreshCw,
  Play, Square, Activity, Server, Key, Eye, EyeOff
} from 'lucide-react';

// ─── Types ──────────────────────────────────────────────────────────────────

type TabId = 'overview' | 'costs' | 'database' | 'ingestion' | 'security' | 'models';

interface Tab { id: TabId; label: string; icon: React.ElementType }

// ─── Constants ───────────────────────────────────────────────────────────────

const TABS: Tab[] = [
  { id: 'overview',   label: 'Overview',         icon: Activity  },
  { id: 'costs',      label: 'Cost Center',       icon: DollarSign },
  { id: 'database',   label: 'Database Terminal', icon: Database  },
  { id: 'ingestion',  label: 'Ingestion Control', icon: Cpu       },
  { id: 'security',   label: 'Security / IAM',    icon: Lock      },
  { id: 'models',     label: 'Model Registry',    icon: Shield    },
];

const ADMIN_PASSWORD = import.meta.env.VITE_ADMIN_PASSWORD || 'apexadmin';

// ─── Sub-components ──────────────────────────────────────────────────────────

function StatusPill({ status }: { status: 'healthy' | 'degraded' | 'down' }) {
  const cfg = {
    healthy:  { color: 'bg-green-500/20 text-green-400 border-green-500/30', icon: CheckCircle, label: 'HEALTHY' },
    degraded: { color: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30', icon: AlertTriangle, label: 'DEGRADED' },
    down:     { color: 'bg-red-500/20 text-red-400 border-red-500/30', icon: XCircle, label: 'DOWN' },
  }[status];
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[10px] font-bold uppercase tracking-wider ${cfg.color}`}>
      <Icon className="w-3 h-3" /> {cfg.label}
    </span>
  );
}

function KPICard({ label, value, sub, color = '#E10600' }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="rounded-xl p-5 border border-white/5 bg-white/5 dark:bg-white/5 space-y-1">
      <p className="text-[10px] font-mono font-bold uppercase tracking-widest text-gray-500">{label}</p>
      <p className="text-2xl font-mono font-black" style={{ color }}>{value}</p>
      {sub && <p className="text-[11px] text-gray-500">{sub}</p>}
    </div>
  );
}

// ─── Tab: Overview ───────────────────────────────────────────────────────────

function OverviewTab() {
  const services = [
    { name: 'Cloud Run API', status: 'healthy' as const,  latency: '142ms' },
    { name: 'Cloud SQL',     status: 'healthy' as const,  latency: '8ms'   },
    { name: 'GCS Bucket',    status: 'healthy' as const,  latency: '21ms'  },
    { name: 'BigQuery',      status: 'degraded' as const, latency: '1.2s'  },
    { name: 'ML Registry',   status: 'degraded' as const, latency: '—'     },
  ];
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard label="API Uptime"    value="99.4%"  sub="Last 30 days"  color="#00D2BE" />
        <KPICard label="Requests / hr" value="1,240"  sub="Rolling 1h avg" />
        <KPICard label="Avg Latency"   value="148ms"  sub="p95: 620ms"    color="#FFF200" />
        <KPICard label="Active Models" value="2 / 4"  sub="2 fallback"    color="#9B59B6" />
      </div>
      <div className="rounded-xl border border-white/5 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-white/5">
            <tr className="text-[10px] font-mono uppercase tracking-widest text-gray-500">
              <th className="text-left px-4 py-3">Service</th>
              <th className="text-left px-4 py-3">Status</th>
              <th className="text-right px-4 py-3">Latency</th>
            </tr>
          </thead>
          <tbody>
            {services.map((s, i) => (
              <tr key={s.name} className={`border-t border-white/5 ${i % 2 === 0 ? 'bg-white/[0.02]' : ''}`}>
                <td className="px-4 py-3 font-mono text-[12px] text-gray-300">{s.name}</td>
                <td className="px-4 py-3"><StatusPill status={s.status} /></td>
                <td className="px-4 py-3 text-right font-mono text-[12px] text-gray-400">{s.latency}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Tab: Cost Center ─────────────────────────────────────────────────────────

const BUDGET_TOTAL = 200;
const BUDGET_SPENT = 47.83;

const COST_BREAKDOWN = [
  { service: 'Cloud Run',      spend: 18.40, color: '#E10600' },
  { service: 'Cloud SQL',      spend: 14.20, color: '#3671C6' },
  { service: 'Cloud Storage',  spend:  8.90, color: '#27F4D2' },
  { service: 'BigQuery',       spend:  4.22, color: '#9B59B6' },
  { service: 'Networking',     spend:  2.11, color: '#FF8000' },
];

function CostCenterTab() {
  const pct = (BUDGET_SPENT / BUDGET_TOTAL) * 100;
  const alertPct = 80;
  return (
    <div className="space-y-6">
      {/* Budget gauge */}
      <div className="rounded-xl p-6 border border-white/5 bg-white/5 space-y-4">
        <div className="flex justify-between items-end">
          <div>
            <p className="text-[10px] font-mono uppercase tracking-widest text-gray-500">GCP Monthly Budget</p>
            <p className="text-4xl font-mono font-black text-white mt-1">
              ${BUDGET_SPENT.toFixed(2)}<span className="text-lg text-gray-500 font-normal"> / ${BUDGET_TOTAL}</span>
            </p>
          </div>
          <span className={`text-sm font-bold ${pct >= alertPct ? 'text-red-400' : 'text-green-400'}`}>
            {pct.toFixed(1)}% used
          </span>
        </div>
        <div className="h-3 rounded-full bg-white/10 overflow-hidden">
          <motion.div
            className="h-full rounded-full"
            style={{ background: pct >= alertPct ? '#E10600' : '#00D2BE' }}
            initial={{ width: 0 }}
            animate={{ width: `${pct}%` }}
            transition={{ duration: 1, ease: 'easeOut' }}
          />
        </div>
        <p className="text-[11px] text-gray-500">Alert threshold: {alertPct}% (${(BUDGET_TOTAL * alertPct / 100).toFixed(0)})</p>
      </div>

      {/* Per-service breakdown */}
      <div className="rounded-xl border border-white/5 overflow-hidden">
        <div className="px-4 py-3 bg-white/5 text-[10px] font-mono uppercase tracking-widest text-gray-500">
          Service Breakdown (MTD)
        </div>
        <div className="divide-y divide-white/5">
          {COST_BREAKDOWN.map((row) => (
            <div key={row.service} className="px-4 py-3 flex items-center gap-4">
              <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: row.color }} />
              <span className="flex-1 font-mono text-[12px] text-gray-300">{row.service}</span>
              <div className="flex-1 h-1.5 rounded-full bg-white/10 overflow-hidden mx-4">
                <div
                  className="h-full rounded-full"
                  style={{ width: `${(row.spend / BUDGET_SPENT) * 100}%`, backgroundColor: row.color }}
                />
              </div>
              <span className="font-mono text-sm font-bold text-white w-16 text-right">${row.spend.toFixed(2)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Tab: Database Terminal ───────────────────────────────────────────────────

const DB_TABLES = [
  { table: 'lap_times',      rows: '2.4M', last_ingested: '2024-01-15 03:12 UTC', status: 'healthy' as const  },
  { table: 'driver_stats',   rows: '18K',  last_ingested: '2024-01-14 21:00 UTC', status: 'healthy' as const  },
  { table: 'race_results',   rows: '156K', last_ingested: '2024-01-13 18:30 UTC', status: 'healthy' as const  },
  { table: 'telemetry_raw',  rows: '41M',  last_ingested: '2024-01-15 04:00 UTC', status: 'degraded' as const },
  { table: 'model_runs',     rows: '892',  last_ingested: '2024-01-10 09:15 UTC', status: 'healthy' as const  },
];

function DatabaseTab() {
  const storageUsedGB = 38.4;
  const storageTotalGB = 100;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        <KPICard label="Instance"     value="db-f1-micro"  sub="Cloud SQL · PostgreSQL 15" color="#3671C6" />
        <KPICard label="Storage Used" value={`${storageUsedGB} GB`} sub={`/ ${storageTotalGB} GB`} color="#27F4D2" />
        <KPICard label="Connections"  value="4 / 25"       sub="Max pool: 25"              color="#FFF200" />
      </div>
      <div className="rounded-xl border border-white/5 overflow-hidden">
        <div className="px-4 py-3 bg-white/5">
          <div className="flex items-center gap-2">
            <Server className="w-4 h-4 text-gray-500" />
            <span className="text-[10px] font-mono uppercase tracking-widest text-gray-500">Table Status &amp; Ingestion Timestamps</span>
          </div>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-white/[0.03]">
            <tr className="text-[10px] font-mono uppercase tracking-widest text-gray-500">
              <th className="text-left px-4 py-3">Table</th>
              <th className="text-right px-4 py-3">Rows</th>
              <th className="text-left px-4 py-3 hidden md:table-cell">Last Ingested</th>
              <th className="text-left px-4 py-3">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {DB_TABLES.map((t) => (
              <tr key={t.table} className="hover:bg-white/5 transition-colors">
                <td className="px-4 py-3 font-mono text-[12px] text-gray-200">{t.table}</td>
                <td className="px-4 py-3 text-right font-mono text-[12px] text-gray-400">{t.rows}</td>
                <td className="px-4 py-3 font-mono text-[11px] text-gray-500 hidden md:table-cell">{t.last_ingested}</td>
                <td className="px-4 py-3"><StatusPill status={t.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Tab: Ingestion Control ───────────────────────────────────────────────────

interface Job { name: string; desc: string; status: 'running' | 'idle' | 'failed'; lastRun: string; nextRun: string; }

const JOBS: Job[] = [
  { name: 'fastf1_worker',    desc: 'Fetches session telemetry from FastF1',   status: 'running', lastRun: '03:00 UTC', nextRun: '04:00 UTC' },
  { name: 'lap_times_worker', desc: 'Ingests lap-time CSV from Jolpica/Ergast', status: 'idle',    lastRun: '02:30 UTC', nextRun: '05:30 UTC' },
  { name: 'driver_stats_sync',desc: 'Syncs driver career stats to Cloud SQL',   status: 'idle',    lastRun: '21:00 UTC', nextRun: '21:00 UTC' },
  { name: 'model_retrain',    desc: 'CatBoost re-training on latest data',      status: 'failed',  lastRun: '00:00 UTC', nextRun: 'Manual'    },
];

const JOB_COLORS = { running: 'text-green-400', idle: 'text-gray-400', failed: 'text-red-400' };
const JOB_BG    = { running: 'bg-green-500/10 border-green-500/20', idle: 'bg-white/5 border-white/5', failed: 'bg-red-500/10 border-red-500/20' };

function IngestionTab() {
  const [jobStates, setJobStates] = useState<Record<string, Job['status']>>(
    Object.fromEntries(JOBS.map((j) => [j.name, j.status]))
  );

  const toggle = (name: string) => {
    setJobStates((prev) => ({
      ...prev,
      [name]: prev[name] === 'running' ? 'idle' : 'running',
    }));
  };

  return (
    <div className="space-y-4">
      <p className="text-[11px] text-gray-500">Mock controls — start/stop actions are simulated and do not affect production Cloud Run jobs.</p>
      {JOBS.map((job) => {
        const status = jobStates[job.name];
        return (
          <div key={job.name} className={`rounded-xl p-5 border flex items-center gap-5 ${JOB_BG[status]}`}>
            <div className={`w-2 h-2 rounded-full shrink-0 ${status === 'running' ? 'bg-green-400 animate-pulse' : status === 'failed' ? 'bg-red-400' : 'bg-gray-500'}`} />
            <div className="flex-1 min-w-0">
              <p className="font-mono text-sm font-bold text-white">{job.name}</p>
              <p className="text-[11px] text-gray-500 mt-0.5">{job.desc}</p>
              <div className="flex gap-4 mt-1.5 text-[10px] font-mono text-gray-500">
                <span>Last: {job.lastRun}</span>
                <span>Next: {job.nextRun}</span>
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className={`text-[10px] font-bold uppercase ${JOB_COLORS[status]}`}>{status}</span>
              <button
                onClick={() => toggle(job.name)}
                className="p-2 rounded-lg bg-white/10 hover:bg-white/20 transition-colors"
                title={status === 'running' ? 'Stop job' : 'Start job'}
              >
                {status === 'running'
                  ? <Square className="w-4 h-4 text-red-400" />
                  : <Play  className="w-4 h-4 text-green-400" />}
              </button>
              <button className="p-2 rounded-lg bg-white/10 hover:bg-white/20 transition-colors" title="Refresh">
                <RefreshCw className="w-4 h-4 text-gray-400" />
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Tab: Security / IAM ──────────────────────────────────────────────────────

const IAM_ROLES = [
  { role: 'roles/run.invoker',          scope: 'Cloud Run API',     status: 'active' as const },
  { role: 'roles/storage.objectViewer', scope: 'GCS Bucket (data)', status: 'active' as const },
  { role: 'roles/cloudsql.client',      scope: 'Cloud SQL',         status: 'active' as const },
  { role: 'roles/bigquery.dataViewer',  scope: 'BigQuery dataset',  status: 'active' as const },
  { role: 'roles/secretmanager.secretAccessor', scope: 'Secret Manager', status: 'active' as const },
];

function SecurityTab() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="rounded-xl p-5 border border-white/5 bg-white/5 space-y-1">
          <p className="text-[10px] font-mono uppercase tracking-widest text-gray-500">Service Account</p>
          <p className="font-mono text-sm text-white font-bold">f1-ingest-sa@apexintelligence.iam.gserviceaccount.com</p>
        </div>
        <div className="rounded-xl p-5 border border-yellow-500/20 bg-yellow-500/5 space-y-1">
          <p className="text-[10px] font-mono uppercase tracking-widest text-yellow-500">CORS Policy</p>
          <p className="font-mono text-sm text-yellow-400 font-bold">allow_origins=["*"]</p>
          <p className="text-[11px] text-gray-500">⚠ Tighten to production domain before GA launch.</p>
        </div>
      </div>
      <div className="rounded-xl border border-white/5 overflow-hidden">
        <div className="px-4 py-3 bg-white/5 flex items-center gap-2">
          <Key className="w-4 h-4 text-gray-500" />
          <span className="text-[10px] font-mono uppercase tracking-widest text-gray-500">IAM Bindings — f1-ingest-sa</span>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-white/[0.03]">
            <tr className="text-[10px] font-mono uppercase tracking-widest text-gray-500">
              <th className="text-left px-4 py-3">Role</th>
              <th className="text-left px-4 py-3 hidden md:table-cell">Scope</th>
              <th className="text-left px-4 py-3">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {IAM_ROLES.map((r) => (
              <tr key={r.role} className="hover:bg-white/5 transition-colors">
                <td className="px-4 py-3 font-mono text-[11px] text-gray-300">{r.role}</td>
                <td className="px-4 py-3 font-mono text-[11px] text-gray-500 hidden md:table-cell">{r.scope}</td>
                <td className="px-4 py-3"><StatusPill status="healthy" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Tab: Model Registry ─────────────────────────────────────────────────────

function ModelRegistryTab() {
  const models = [
    { name: 'Strategy Predictor v1', version: '2.1.4', status: 'active', accuracy: '94.2%', drift: 'Low' },
    { name: 'Tire Degradation ML', version: '1.0.8', status: 'active', accuracy: '89.1%', drift: 'Medium' },
    { name: 'Fuel Consumption', version: '1.2.0', status: 'standby', accuracy: '91.5%', drift: 'Low' },
  ];
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="space-y-4">
          <div className="px-4 py-3 bg-white/5 rounded-xl border border-white/5">
            <h3 className="text-[10px] font-mono uppercase tracking-widest text-gray-500 mb-3">Loaded ML Models</h3>
            <div className="space-y-3">
              {models.map(m => (
                <div key={m.name} className="flex items-center justify-between p-3 rounded-lg bg-white/5 border border-white/5">
                  <div>
                    <p className="text-sm font-bold text-white">{m.name}</p>
                    <p className="text-[10px] text-gray-500 font-mono">v{m.version} • Accuracy: <span className="text-accent-green">{m.accuracy}</span></p>
                  </div>
                  <StatusPill status={m.status === 'active' ? 'healthy' : 'degraded'} />
                </div>
              ))}
            </div>
          </div>
          <div className="p-5 rounded-xl border border-white/5 bg-white/5 space-y-3">
            <h3 className="text-[10px] font-mono uppercase tracking-widest text-gray-500">Feature Importance (SHAP)</h3>
            <div className="space-y-2">
              {[
                { label: 'Tire Age', val: 85 },
                { label: 'Track Temp', val: 72 },
                { label: 'Fuel Load', val: 45 },
                { label: 'Gap Behind', val: 32 },
              ].map(f => (
                <div key={f.label} className="space-y-1">
                  <div className="flex justify-between text-[10px] font-mono">
                    <span className="text-gray-400">{f.label}</span>
                    <span className="text-white">{f.val}%</span>
                  </div>
                  <div className="h-1 bg-white/10 rounded-full overflow-hidden">
                    <div className="h-full bg-red-600" style={{ width: `${f.val}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="rounded-xl border border-white/5 bg-white/5 p-5 flex flex-col items-center justify-center space-y-4">
          <div className="w-full aspect-video rounded-lg bg-black/40 border border-white/10 flex items-center justify-center p-8">
             <div className="text-center space-y-2">
               <Activity className="w-12 h-12 text-gray-700 mx-auto" />
               <p className="text-xs font-mono text-gray-500 uppercase tracking-widest">Model Explainability Plot</p>
               <p className="text-[10px] text-gray-600">SHAP values for current session predictions</p>
             </div>
          </div>
          <button className="w-full py-2.5 rounded-xl bg-white/5 border border-white/10 text-[10px] font-bold uppercase tracking-widest hover:bg-white/10 transition-colors">
            Generate New Explainability Report
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Auth Gate ────────────────────────────────────────────────────────────────

function AuthGate({ onAuth }: { onAuth: () => void }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState(false);
  const [show, setShow] = useState(false);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (password === ADMIN_PASSWORD) {
      onAuth();
    } else {
      setError(true);
      setTimeout(() => setError(false), 1500);
    }
  };

  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="w-full max-w-md rounded-2xl p-8 border border-white/5 bg-[#1A1A1A] shadow-2xl space-y-6"
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-red-600/20 flex items-center justify-center">
            <Shield className="w-5 h-5 text-red-500" />
          </div>
          <div>
            <h2 className="text-lg font-display font-bold">Admin Access</h2>
            <p className="text-[11px] text-gray-500">Enter admin password to continue</p>
          </div>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <div className="relative">
            <input
              type={show ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              className={`w-full px-4 py-3 pr-10 rounded-xl bg-white/5 border font-mono text-sm outline-none transition-colors ${
                error ? 'border-red-500' : 'border-white/10 focus:border-red-600/50'
              }`}
            />
            <button
              type="button"
              onClick={() => setShow(!show)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
            >
              {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          {error && <p className="text-[11px] text-red-400 font-bold">Incorrect password.</p>}
          <button
            type="submit"
            className="w-full py-3 rounded-xl bg-red-600 hover:bg-red-700 font-bold text-sm transition-colors"
          >
            Unlock Admin Panel
          </button>
        </form>
      </motion.div>
    </div>
  );
}

// ─── Root Component ───────────────────────────────────────────────────────────

const TAB_CONTENT: Record<TabId, React.ReactNode> = {
  overview:  <OverviewTab />,
  costs:     <CostCenterTab />,
  database:  <DatabaseTab />,
  ingestion: <IngestionTab />,
  security:  <SecurityTab />,
  models:    <ModelRegistryTab />,
};

const AdminPage: React.FC = () => {
  const [authed, setAuthed] = useState(false);
  const [activeTab, setActiveTab] = useState<TabId>('overview');

  if (!authed) {
    return <AuthGate onAuth={() => setAuthed(true)} />;
  }

  return (
    <div className="p-6 md:p-8 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-display font-black tracking-tighter uppercase italic">Admin Control</h1>
          <p className="text-gray-500 uppercase text-xs tracking-widest mt-2">GCP Infrastructure &amp; Operational Dashboard</p>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-red-600/10 border border-red-600/20">
          <Shield className="w-3.5 h-3.5 text-red-500" />
          <span className="text-[10px] font-bold text-red-400 uppercase tracking-wider">Admin Session</span>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 rounded-xl bg-white/5 border border-white/5 overflow-x-auto no-scrollbar">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-xs font-bold uppercase tracking-wide whitespace-nowrap transition-all ${
                active
                  ? 'bg-red-600 text-white shadow-lg shadow-red-900/20'
                  : 'text-gray-400 hover:text-white hover:bg-white/5'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      <AnimatePresence mode="wait">
        <motion.div
          key={activeTab}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.15 }}
        >
          {TAB_CONTENT[activeTab]}
        </motion.div>
      </AnimatePresence>
    </div>
  );
};

export default AdminPage;
