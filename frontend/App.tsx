/**
 * @file App.tsx
 * @description Root layout component for Apex Intelligence.
 *
 * Responsibilities:
 * - Declares all application routes via React Router `<Routes>`.
 * - Renders the collapsible left sidebar (desktop) and mobile bottom-nav bar.
 * - Manages theme toggling (dark / light) via Zustand + Tailwind `dark:` class.
 * - Shows the racing simulation background on every view.
 * - Lazy-loads every view for optimal code-splitting performance.
 * - Logs route transitions via the structured logger (dev only).
 */

import React from 'react';
import { Routes, Route, NavLink, Navigate, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Gauge, Users, Compass, BarChart3, Shield, Activity, CheckCircle, Wrench,
  MessageSquare, Cpu, Map, Wifi, WifiOff, ChevronLeft, ChevronRight, Sun, Moon
} from 'lucide-react';
import { useBackendStatus } from './hooks/useApi';
import { useAppStore } from './store/useAppStore';
import { DynamicSimulationBackground } from './components/DynamicSimulationBackground';
import { logger } from './services/logger';

// Lazy-load views for code splitting
const RaceCommandCenter = React.lazy(() => import('./views/RaceCommandCenter'));
const DriverProfiles = React.lazy(() => import('./views/DriverProfiles'));
const PitStrategySimulator = React.lazy(() => import('./views/PitStrategySimulator'));
const AIChatbot = React.lazy(() => import('./views/AIChatbot'));
const TrackExplorer = React.lazy(() => import('./views/TrackExplorer'));
const LapByLapAnalysis = React.lazy(() => import('./views/LapByLapAnalysis'));
const AdminPage = React.lazy(() => import('./views/AdminPage'));
const ValidationPerformance = React.lazy(() => import('./views/ValidationPerformance'));
const ModelEngineering = React.lazy(() => import('./views/ModelEngineering'));
const SystemMonitoringHealth = React.lazy(() => import('./views/SystemMonitoringHealth'));
const OperationalCommand = React.lazy(() => import('./views/OperationalCommand'));

const APP_NAME = 'APEX F1';

/**
 * Primary navigation item definition.
 * Only items marked `mobile: true` appear in the mobile bottom nav strip.
 */
const navItems = [
  { path: '/',            label: 'Race Command',      icon: Gauge,          mobile: true  },
  { path: '/drivers',     label: 'Driver Profiles',   icon: Users,          mobile: true  },
  { path: '/strategy',    label: 'Strategy Sim',      icon: Compass,        mobile: true  },
  { path: '/ai',          label: 'AI Strategist',     icon: MessageSquare,  mobile: true,  highlight: true },
  { path: '/circuits',    label: 'Circuit Directory',  icon: Map,            mobile: true  },
  { path: '/analysis',    label: 'Post-Race',          icon: BarChart3,      mobile: false },
  { path: '/validation',  label: 'Validation',         icon: CheckCircle,    mobile: false },
  { path: '/models',      label: 'Model Engineering',  icon: Wrench,         mobile: false },
  { path: '/monitoring',  label: 'System Health',      icon: Activity,       mobile: false },
  { path: '/admin',       label: 'Admin Control',      icon: Shield,         mobile: false },
];

/** Mobile bottom-nav, shows the first 5 mobile-tagged routes as icon tabs. */
const mobileNavItems = navItems.filter((n) => n.mobile);

/** Full-screen spinner shown while a lazy-loaded view is being fetched. */
const ViewLoader: React.FC = () => (
  <div className="flex-1 flex items-center justify-center">
    <div className="flex flex-col items-center gap-4">
      <div className="w-10 h-10 border-2 border-red-600 border-t-transparent rounded-full animate-spin" />
      <span className="text-xs font-mono text-gray-500 uppercase tracking-widest">Loading view...</span>
    </div>
  </div>
);

/**
 * Error boundary: catches render errors in lazy-loaded views and shows a
 * recovery UI instead of a white screen.
 */
class ViewErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    logger.error('[ErrorBoundary] View crash:', error.message, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex-1 flex items-center justify-center p-8">
          <div className="max-w-md text-center space-y-4">
            <div className="w-16 h-16 mx-auto rounded-2xl bg-red-600/10 flex items-center justify-center">
              <Activity className="w-8 h-8 text-red-500" />
            </div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white">
              Something went wrong
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {this.state.error?.message || 'An unexpected error occurred while rendering this view.'}
            </p>
            <button
              onClick={() => {
                this.setState({ hasError: false, error: null });
                window.location.reload();
              }}
              className="px-6 py-2.5 rounded-xl bg-red-600 text-white text-sm font-bold hover:bg-red-700 transition-colors"
            >
              Reload Page
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

/**
 * Root application component.
 *
 * Renders the full layout shell: collapsible sidebar (desktop), a top header
 * and bottom navigation bar (mobile), the dynamic racing background and all
 * lazily-loaded route views.
 */
const App: React.FC = () => {
  const { online, latency } = useBackendStatus();
  const { sidebarOpen, setSidebarOpen, sidebarCollapsed, toggleSidebarCollapsed, theme, toggleTheme } = useAppStore();
  const location = useLocation();

  /** Sync Tailwind dark class with Zustand theme state. */
  React.useEffect(() => {
    const root = window.document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
  }, [theme]);

  /** Log route transitions (dev only). */
  React.useEffect(() => {
    logger.info(`[App] Route changed -> ${location.pathname}`);
  }, [location.pathname]);

  return (
    <div className="flex h-screen bg-white dark:bg-[#0F0F0F] text-gray-900 dark:text-white overflow-hidden font-sans transition-colors duration-500">
      {/* Mobile Top Header (hidden on lg+) */}
      <div className="lg:hidden fixed top-0 left-0 right-0 h-14 bg-white/90 dark:bg-[#1A1A1A]/90 backdrop-blur-lg border-b border-gray-200 dark:border-white/5 z-50 flex items-center justify-between px-4 transition-colors duration-500">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-red-600 flex items-center justify-center">
            <Cpu className="w-4 h-4 text-white" />
          </div>
          <span className="font-display font-black tracking-tighter text-lg italic">{APP_NAME}</span>
        </div>
        <button
          onClick={toggleTheme}
          className="p-2 rounded-lg bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/10"
          aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {theme === 'dark' ? <Sun className="w-4 h-4 text-gray-400" /> : <Moon className="w-4 h-4 text-gray-600" />}
        </button>
      </div>

      {/* Sidebar */}
      <motion.aside
        initial={false}
        animate={{ width: sidebarCollapsed ? 88 : 256 }}
        transition={{ type: 'spring', damping: 20, stiffness: 200 }}
        className={`
        fixed lg:static inset-y-0 left-0 z-[60]
        bg-gray-50 dark:bg-[#141414] border-r border-gray-200 dark:border-white/5 flex flex-col transition-transform transition-colors duration-300 ease-in-out
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
        <div className="p-6 pb-4 relative flex items-center justify-between">
          <div className="flex items-center gap-4 overflow-hidden w-full">
            <div className="w-10 h-10 rounded-xl shrink-0 bg-gradient-to-br from-red-600 to-red-800 flex items-center justify-center shadow-lg shadow-red-900/20">
              <Cpu className="w-6 h-6 text-white shrink-0" />
            </div>
            <AnimatePresence>
              {!sidebarCollapsed && (
                <motion.div
                  initial={{ opacity: 0, width: 0 }}
                  animate={{ opacity: 1, width: 'auto' }}
                  exit={{ opacity: 0, width: 0 }}
                  className="whitespace-nowrap flex-1 flex items-center justify-between overflow-hidden"
                >
                  <div className="pr-2">
                    <h1 className="font-display font-black tracking-tighter text-xl italic leading-none text-gray-900 dark:text-white">{APP_NAME}</h1>
                    <p className="text-[10px] font-mono text-red-600 dark:text-red-500 font-bold uppercase tracking-widest mt-1">Race Intelligence</p>
                  </div>
                  <button onClick={toggleTheme} className="p-1.5 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-[#1A1A1A] hover:bg-gray-100 dark:hover:bg-white/10 transition-colors shadow-sm dark:shadow-none">
                    {theme === 'dark' ? <Sun className="w-4 h-4 text-gray-400" /> : <Moon className="w-4 h-4 text-gray-600" />}
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          <button
            onClick={toggleSidebarCollapsed}
            className="hidden lg:flex absolute -right-3 top-8 w-6 h-6 rounded-full border border-gray-200 dark:border-white/10 bg-white dark:bg-[#141414] hover:bg-gray-100 dark:hover:bg-white/10 items-center justify-center text-gray-400 dark:text-gray-500 hover:text-gray-900 dark:hover:text-white transition-colors z-[70] shadow-xl"
            title={sidebarCollapsed ? "Expand Sidebar" : "Collapse Sidebar"}
          >
            {sidebarCollapsed ? <ChevronRight className="w-3 h-3" /> : <ChevronLeft className="w-3 h-3" />}
          </button>
        </div>

        <nav className="flex-1 px-4 py-4 space-y-2 overflow-y-auto no-scrollbar">
          {navItems.map((item, index) => (
            <motion.div
              key={item.path}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.05 }}
            >
              <NavLink
                to={item.path}
                end={item.path === '/'}
                onClick={() => setSidebarOpen(false)}
                title={sidebarCollapsed ? item.label : undefined}
                className={({ isActive }) =>
                  `w-full flex items-center gap-4 rounded-xl transition-all duration-300 group relative ${
                    sidebarCollapsed ? 'justify-center p-3' : 'px-4 py-3.5'
                  } ${
                    isActive
                      ? 'bg-red-600 text-white shadow-lg shadow-red-900/20'
                      : 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/5 hover:text-gray-900 dark:hover:text-white'
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    <item.icon className={`shrink-0 ${sidebarCollapsed ? 'w-6 h-6' : 'w-5 h-5'} ${isActive ? 'text-white' : 'group-hover:text-red-600 dark:group-hover:text-red-500 transition-colors'}`} />
                    {!sidebarCollapsed && (
                      <span className="font-medium text-sm tracking-wide whitespace-nowrap overflow-hidden">{item.label}</span>
                    )}
                    {'highlight' in item && item.highlight && !isActive && (
                      <div className="absolute right-3 top-3 w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
                    )}
                  </>
                )}
              </NavLink>
            </motion.div>
          ))}
        </nav>

        {/* Backend Status */}
        <div className="p-4 mt-auto border-t border-gray-200 dark:border-white/5 bg-gray-100/50 dark:bg-black/20 transition-colors duration-500">
          {!sidebarCollapsed ? (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <div className="flex items-center justify-between mb-4 px-2">
                <span className="text-[10px] font-mono text-gray-400 dark:text-gray-500 uppercase tracking-widest whitespace-nowrap">Backend</span>
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${online ? 'bg-green-500 animate-pulse' : 'bg-yellow-500'}`} />
                  <span className={`text-[10px] font-mono font-bold whitespace-nowrap ${online ? 'text-green-500' : 'text-yellow-500'}`}>
                    {online ? 'LIVE' : 'MOCK'}
                  </span>
                </div>
              </div>
              <div className="flex items-center justify-between p-3 rounded-xl bg-white dark:bg-white/5 border border-gray-200 dark:border-white/5 shadow-sm dark:shadow-none transition-colors">
                <div className="flex items-center gap-3 overflow-hidden">
                  {online ? <Wifi className="shrink-0 w-4 h-4 text-green-500" /> : <WifiOff className="shrink-0 w-4 h-4 text-yellow-500" />}
                  <span className="text-[10px] font-bold text-gray-600 dark:text-gray-400 whitespace-nowrap truncate">
                    {online ? 'FastAPI Connected' : 'Using Mock Data'}
                  </span>
                </div>
                <span className="text-[10px] font-mono text-gray-900 dark:text-white whitespace-nowrap pl-2">
                  {online && latency ? `${latency}ms` : ''}
                </span>
              </div>
            </motion.div>
          ) : (
             <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center justify-center gap-3 py-2" title={online ? 'FastAPI Connected (LIVE)' : 'Using Mock Data (MOCK)'}>
                <div className={`w-2 h-2 rounded-full ${online ? 'bg-green-500 animate-pulse' : 'bg-yellow-500'}`} />
                {online ? <Wifi className="w-5 h-5 text-green-500" /> : <WifiOff className="w-5 h-5 text-yellow-500" />}
             </motion.div>
          )}
        </div>
      </motion.aside>

      {/* Mobile Overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[55] lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Main Content */}
      <main className="flex-1 relative flex flex-col min-w-0 pt-14 pb-16 lg:pt-0 lg:pb-0 bg-white/50 dark:bg-transparent">
        <DynamicSimulationBackground />
        <div className="relative z-10 h-full flex flex-col overflow-y-auto scrollbar-hide">
          <ViewErrorBoundary>
            <React.Suspense fallback={<ViewLoader />}>
              <Routes>
                <Route path="/"           element={<RaceCommandCenter />} />
                <Route path="/drivers"    element={<DriverProfiles />} />
                <Route path="/strategy"   element={<PitStrategySimulator />} />
                <Route path="/ai"         element={<AIChatbot />} />
                <Route path="/circuits"   element={<TrackExplorer theme={theme} />} />
                <Route path="/analysis"   element={<LapByLapAnalysis />} />
                <Route path="/validation" element={<ValidationPerformance />} />
                <Route path="/models"     element={<ModelEngineering />} />
                <Route path="/monitoring" element={<SystemMonitoringHealth />} />
                <Route path="/operations" element={<OperationalCommand />} />
                <Route path="/admin"      element={<AdminPage />} />
                <Route path="*"           element={<Navigate to="/" replace />} />
              </Routes>
            </React.Suspense>
          </ViewErrorBoundary>
        </div>
      </main>

      {/* Mobile Bottom Navigation Bar */}
      <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-50 bg-white/95 dark:bg-[#141414]/95 backdrop-blur-xl border-t border-gray-200 dark:border-white/5 flex items-stretch h-16 safe-area-inset-bottom">
        {mobileNavItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === '/'}
            className={({ isActive }) =>
              `flex-1 flex flex-col items-center justify-center gap-0.5 relative transition-colors ${
                isActive
                  ? 'text-red-600'
                  : 'text-gray-400 dark:text-gray-500'
              }`
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <motion.div
                    layoutId="mobile-nav-pill"
                    className="absolute inset-x-2 inset-y-1 rounded-xl bg-red-600/10 dark:bg-red-600/15"
                    transition={{ type: 'spring', stiffness: 400, damping: 35 }}
                  />
                )}
                <item.icon className={`w-5 h-5 relative z-10 ${isActive ? 'text-red-600' : ''}`} />
                <span className={`text-[9px] font-bold uppercase tracking-wide relative z-10 ${isActive ? 'text-red-600' : ''}`}>
                  {item.label.split(' ')[0]}
                </span>
                {'highlight' in item && item.highlight && !isActive && (
                  <div className="absolute top-2 right-[calc(50%-12px)] w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </div>
  );
};

export default App;
