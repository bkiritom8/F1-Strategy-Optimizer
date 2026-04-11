/**
 * @file App.tsx
 * @description Root layout component for Apex Intelligence.
 *
 * Responsibilities:
 * - Declares all application routes via React Router <Routes>.
 * - Renders the collapsible left sidebar (desktop) and mobile bottom-nav bar.
 * - Shows the racing simulation background on every view.
 * - Lazy-loads every view for optimal code-splitting performance.
 * - Logs route transitions via the structured logger (dev only).
 * - Wraps views in an ErrorBoundary to prevent white-screen crashes.
 *
 * Auth model:
 * - Admin tab is NOT in the nav; only reachable after logging in with admin credentials.
 * - Live/Mock data status is admin-only; removed from the public sidebar.
 */

import React from 'react';
import { Routes, Route, NavLink, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Gauge, Users, Compass, BarChart3, Activity,
  Map, ChevronLeft, ChevronRight
} from 'lucide-react';
import { useRaces2024, useBackendStatus } from './hooks/useApi';
import { useAppStore } from './store/useAppStore';
import { DynamicSimulationBackground } from './components/DynamicSimulationBackground';
import { logger } from './services/logger';

// Lazy-load views for code splitting
const RaceCommandCenter = React.lazy(() => import('./views/RaceCommandCenter'));
const DriverProfiles    = React.lazy(() => import('./views/DriverProfiles'));
const StrategyHub       = React.lazy(() => import('./views/StrategyHub'));
const TrackExplorer     = React.lazy(() => import('./views/TrackExplorer'));
const LapByLapAnalysis  = React.lazy(() => import('./views/LapByLapAnalysis'));
const AdminPage         = React.lazy(() => import('./views/AdminPage'));
const LandingPage       = React.lazy(() => import('./views/LandingPage'));
const VerifyEmailPage   = React.lazy(() => import('./views/VerifyEmailPage'));

const APP_NAME = 'APEX F1';

/**
 * Primary navigation item definition.
 * Only items marked `mobile: true` appear in the mobile bottom nav strip.
 * Admin is intentionally absent — accessible only after admin login.
 */
const navItems = [
  { path: '/race',     label: 'Race Command',     icon: Gauge,    mobile: true  },
  { path: '/drivers',  label: 'Driver Roster',    icon: Users,    mobile: true  },
  { path: '/strategy', label: 'Strategy Hub',     icon: Compass,  mobile: true,  highlight: true },
  { path: '/circuits', label: 'Circuit Directory', icon: Map,      mobile: true  },
  { path: '/analysis', label: 'Post-Race',         icon: BarChart3, mobile: false },
];

/** Mobile bottom-nav shows all mobile-tagged routes. */
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
 */
const App: React.FC = () => {
  const {
    activeRaceRound,
    backgroundCircuitId,
    sidebarOpen,
    setSidebarOpen,
    sidebarCollapsed,
    toggleSidebarCollapsed,
    isAdmin,
  } = useAppStore();
  const { data: races } = useRaces2024();
  const { online: backendOnline } = useBackendStatus();
  const location  = useLocation();
  const navigate  = useNavigate();

  /**
   * Determine the current circuit ID for the background simulation.
   * Priority:
   * 1. Explicit background override (from Track Explorer)
   * 2. Active race round mapping
   * 3. Default fallback
   */
  const currentCircuitId = React.useMemo(() => {
    if (backgroundCircuitId) return backgroundCircuitId;
    if (!races) return 'bahrain';
    const currentRace = races.find((r) => r.round === activeRaceRound);
    return currentRace?.circuit?.id || 'bahrain';
  }, [races, activeRaceRound, backgroundCircuitId]);

  /** Log route transitions (dev only). */
  React.useEffect(() => {
    logger.info(`[App] Route changed -> ${location.pathname}`);
  }, [location.pathname]);

  // Standalone Layout Wrapper for public pages (Landing, Verify Email)
  const renderPublicPage = (children: React.ReactNode) => (
    <div className="min-h-screen bg-black text-white font-sans">
      <ViewErrorBoundary>
        <React.Suspense fallback={<ViewLoader />}>
          {children}
        </React.Suspense>
      </ViewErrorBoundary>
    </div>
  );

  if (location.pathname === '/verify-email') {
    return renderPublicPage(
      <VerifyEmailPage onGoToLogin={() => navigate('/login')} />
    );
  }

  if (location.pathname === '/') {
    return renderPublicPage(
      <LandingPage
        onLoginSuccess={() => navigate('/race')}
        onAdminLogin={() => navigate('/admin')}
      />
    );
  }

  if (location.pathname === '/login') {
    return renderPublicPage(
      <LandingPage
        showAuth={true}
        onLoginSuccess={() => navigate('/race')}
        onAdminLogin={() => navigate('/admin')}
      />
    );
  }

  return (
    <div className="flex h-screen bg-black text-white overflow-hidden font-sans">
      {/* Mobile Top Header (hidden on lg+) */}
      <div className="lg:hidden fixed top-0 left-0 right-0 h-14 backdrop-blur-xl border-b border-white/[0.07] z-50 flex items-center justify-between px-4" style={{ background: 'rgba(0,0,0,0.55)' }}>
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-2 hover:opacity-80 transition-opacity"
          aria-label="Go to home page"
        >
<img src="/apex-logo-128.png" alt="Apex" className="w-7 h-7 rounded-lg object-contain" />
          <span className="font-display font-black tracking-tighter text-lg italic">{APP_NAME}</span>
        </button>
      </div>

      {/* Sidebar */}
      <motion.aside
        initial={false}
        animate={{ width: sidebarCollapsed ? 88 : 256 }}
        transition={{ type: 'spring', damping: 20, stiffness: 200 }}
        style={{ background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(20px) saturate(180%)' }}
        className={`
        fixed lg:static inset-y-0 left-0 z-[60]
        border-r border-white/[0.07] flex flex-col transition-transform duration-300 ease-in-out
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
        <div className="p-6 pb-4 relative flex items-center justify-between">
          <div className="flex items-center gap-4 overflow-hidden w-full">
            {/* Logo button - navigates to landing page */}
            <button
              onClick={() => { setSidebarOpen(false); navigate('/'); }}
              className="w-10 h-10 rounded-xl shrink-0 overflow-hidden shadow-lg shadow-red-900/20 hover:opacity-80 transition-opacity"
              aria-label="Go to home page"
            >
              <img src="/apex-logo-128.png" alt="Apex Intelligence" className="w-full h-full object-contain" />
            </button>
            <AnimatePresence>
              {!sidebarCollapsed && (
                <motion.div
                  initial={{ opacity: 0, width: 0 }}
                  animate={{ opacity: 1, width: 'auto' }}
                  exit={{ opacity: 0, width: 0 }}
                  className="whitespace-nowrap flex-1 overflow-hidden"
                >
                  {/* Clicking the text also navigates home */}
                  <button
                    onClick={() => { setSidebarOpen(false); navigate('/'); }}
                    className="text-left hover:opacity-80 transition-opacity pr-2"
                    aria-label="Go to home page"
                  >
                    <h1 className="font-display font-black tracking-tighter text-xl italic leading-none text-white">{APP_NAME}</h1>
                    <p className="text-[10px] font-mono text-red-500 font-bold uppercase tracking-widest mt-1">Race Intelligence</p>
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
                onClick={() => setSidebarOpen(false)}
                title={sidebarCollapsed ? item.label : undefined}
                className={({ isActive }) =>
                  `w-full flex items-center gap-4 rounded-xl transition-all duration-300 group relative ${
                    sidebarCollapsed ? 'justify-center p-3' : 'px-4 py-3.5'
                  } ${
                    isActive
                      ? 'bg-red-600 text-white shadow-lg shadow-red-900/20'
                      : 'text-white/40 hover:bg-white/[0.05] hover:text-white'
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

        {/* Admin shortcut pill - only visible when logged in as admin */}
        {isAdmin && (
          <div className="px-4 pb-4">
            <NavLink
              to="/admin"
              onClick={() => setSidebarOpen(false)}
              title={sidebarCollapsed ? 'Admin Panel' : undefined}
              className={({ isActive }) =>
                `w-full flex items-center gap-3 rounded-xl transition-all duration-300 border ${
                  sidebarCollapsed ? 'justify-center p-3' : 'px-4 py-3'
                } ${
                  isActive
                    ? 'bg-amber-600/20 border-amber-500/50 text-amber-400'
                    : 'border-amber-500/30 text-amber-500/70 hover:bg-amber-500/10 hover:text-amber-400'
                }`
              }
            >
              {!sidebarCollapsed && (
                <span className="text-xs font-bold uppercase tracking-widest">Admin Panel</span>
              )}
              {sidebarCollapsed && <span className="text-xs font-bold">ADM</span>}
            </NavLink>
          </div>
        )}
      </motion.aside>

      {/* Mobile Overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[55] lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Main Content */}
      <main className="flex-1 relative flex flex-col min-w-0 pt-14 pb-24 lg:pt-0 lg:pb-0">
        <DynamicSimulationBackground key={currentCircuitId} circuitId={currentCircuitId} />
        <div className="relative z-10 h-full flex flex-col overflow-y-auto scrollbar-hide">
          <div className="flex-1">
            <ViewErrorBoundary>
              <React.Suspense fallback={<ViewLoader />}>
                <Routes>
                  <Route path="/race"     element={<RaceCommandCenter />} />
                  <Route path="/drivers"  element={<DriverProfiles />} />
                  <Route path="/strategy" element={<StrategyHub />} />
                  <Route path="/circuits" element={<TrackExplorer />} />
                  <Route path="/analysis" element={<LapByLapAnalysis />} />
                  <Route path="/admin"    element={<AdminPage />} />
                  <Route path="*"         element={<Navigate to="/race" replace />} />
                </Routes>
              </React.Suspense>
            </ViewErrorBoundary>
          </div>

          {/* Global Legal Footer for Auth Views */}
          <footer className="py-8 px-6 border-t border-white/5 bg-black/40 backdrop-blur-md">
            <div className="max-w-7xl mx-auto space-y-6">
              <div className="flex flex-wrap justify-center gap-x-8 gap-y-2">
                {[
                  { label: 'Privacy Policy', href: '/privacy-policy.html' },
                  { label: 'Cookie Policy',  href: '/cookie-policy.html' },
                  { label: 'Terms',          href: '/terms.html' },
                  { label: 'Sitemap',        href: '/sitemap.xml' },
                  { label: 'Docs',           href: '/docs.html' },
                  { label: 'Contact',        href: '/contact.html' },
                ].map(link => (
                  <a 
                    key={link.label} 
                    href={link.href} 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="text-[10px] font-bold uppercase tracking-widest text-white/30 hover:text-white transition-colors"
                  >
                    {link.label}
                  </a>
                ))}
              </div>

              <div className="flex items-center justify-center gap-2 opacity-40">
                <img src="/apex-logo-40.png" alt="Apex" className="w-4 h-4" />
                <span className="text-[10px] font-black uppercase tracking-widest italic">{APP_NAME}</span>
                <span className="text-[9px] text-white/50 uppercase font-bold tracking-[0.2em]">
                  &middot; &copy; {new Date().getFullYear()} Apex Strategy Labs
                </span>
              </div>
            </div>
          </footer>
        </div>
      </main>


      {/* Demo Mode Badge */}
      {!backendOnline && (
        <div className="fixed top-16 lg:top-3 right-3 z-[100] px-3 py-1.5 rounded-lg bg-amber-500/15 border border-amber-500/30 text-amber-400 text-[9px] font-bold uppercase tracking-[3px] backdrop-blur-sm pointer-events-none">
          Pipeline Data Mode
        </div>
      )}

      {/* Mobile Bottom Navigation Bar */}
      <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-50 backdrop-blur-xl border-t border-white/[0.07] flex items-stretch h-16 safe-area-inset-bottom" style={{ background: 'rgba(0,0,0,0.55)' }}>
        {mobileNavItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `flex-1 flex flex-col items-center justify-center gap-0.5 relative transition-colors ${
                isActive
                  ? 'text-red-600'
                  : 'text-white/40'
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
