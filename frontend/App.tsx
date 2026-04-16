/**
 * @file App.tsx
 * @description Root layout component for DivergeX.
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
  Map, ChevronLeft, ChevronRight, Lock, AlertTriangle
} from 'lucide-react';
import { useBackendStatus } from './hooks/useApi';
import { useAppStore } from './store/useAppStore';
import { logger } from './services/logger';
import CookieConsent from './components/CookieConsent';
import Footer from './components/Footer';
import AdminModal from './components/AdminModal';
import RacingBackground from './components/RacingBackground';

const LAZY_RELOAD_KEY = 'divergex:lazy-reload-attempted';

function lazyWithRetry<T extends React.ComponentType<any>>(
  importer: () => Promise<{ default: T }>
) {
  return React.lazy(async () => {
    try {
      const module = await importer();
      sessionStorage.removeItem(LAZY_RELOAD_KEY);
      return module;
    } catch (error: any) {
      const message = String(error?.message || '');
      const isChunkLoadError = /Failed to fetch dynamically imported module|Loading chunk [\d]+ failed|Importing a module script failed/i.test(message);
      const alreadyRetried = sessionStorage.getItem(LAZY_RELOAD_KEY) === '1';

      if (isChunkLoadError && !alreadyRetried) {
        sessionStorage.setItem(LAZY_RELOAD_KEY, '1');
        window.location.reload();
        return new Promise<never>(() => {
          // Intentionally unresolved because page is reloading.
        });
      }

      throw error;
    }
  });
}

// Lazy-load views for code splitting
const RaceCommandCenter = lazyWithRetry(() => import('./views/RaceCommandCenter'));
const DriverProfiles    = lazyWithRetry(() => import('./views/DriverProfiles'));
const StrategyHub       = lazyWithRetry(() => import('./views/StrategyHub'));
const TrackExplorer     = lazyWithRetry(() => import('./views/TrackExplorer'));
const LapByLapAnalysis  = lazyWithRetry(() => import('./views/LapByLapAnalysis'));
const AdminPage         = lazyWithRetry(() => import('./views/AdminPage'));
const LandingPage       = lazyWithRetry(() => import('./views/LandingPage'));



/**
 * Primary navigation item definition.
 * Only items marked `mobile: true` appear in the mobile bottom nav strip.
 * Admin navigation is selectively rendered: accessible exclusively through secure administrative authentication.
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

const SafetyDisclaimerModal: React.FC<{
  open: boolean;
  onContinue: () => void;
}> = ({ open, onContinue }) => {
  const continueButtonRef = React.useRef<HTMLButtonElement | null>(null);

  React.useEffect(() => {
    if (!open) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    continueButtonRef.current?.focus();

    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [open]);

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[250] flex items-center justify-center p-4 sm:p-6">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-black/90 backdrop-blur-2xl"
          />

          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="safety-disclaimer-title"
            aria-describedby="safety-disclaimer-copy"
            initial={{ opacity: 0, scale: 0.94, y: 18 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.94, y: 18 }}
            className="relative w-full max-w-2xl rounded-[32px] border border-red-500/20 bg-black/80 p-6 sm:p-8 shadow-[0_0_80px_rgba(225,6,0,0.18)]"
          >
            <div className="flex items-start gap-4 sm:gap-5">
              <div className="shrink-0 w-12 h-12 rounded-2xl bg-red-600/20 border border-red-500/20 flex items-center justify-center shadow-lg shadow-red-900/20">
                <AlertTriangle className="w-6 h-6 text-red-400" />
              </div>

              <div className="space-y-3">
                <p className="text-[10px] font-black uppercase tracking-[0.35em] text-red-400">
                  Visual Safety Notice & Epilepsy Warning
                </p>
                <h2 id="safety-disclaimer-title" className="text-2xl sm:text-3xl font-display font-black italic uppercase tracking-tight text-white">
                  Photosensitive Epilepsy Disclaimer
                </h2>
                <p id="safety-disclaimer-copy" className="text-sm sm:text-base text-white/70 leading-relaxed">
                  This experience uses intense red accents, rapid flashing highlights, and motion-heavy telemetry animations.
                  If you have a history of epilepsy, or are sensitive to flashing lights and photosensitive seizures, do NOT continue.
                </p>
              </div>
            </div>

            <div className="mt-6 grid gap-3 sm:grid-cols-2">
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <div className="text-[10px] font-black uppercase tracking-widest text-white/30">Content Type</div>
                <p className="mt-2 text-sm text-white/70">High-contrast UI, glow effects, and animated racing telemetry.</p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <div className="text-[10px] font-black uppercase tracking-widest text-white/30">Recommendation</div>
                <p className="mt-2 text-sm text-white/70">Proceed only if you are comfortable with high-contrast animated visuals.</p>
              </div>
            </div>

            <div className="mt-8 flex flex-col sm:flex-row sm:items-center gap-3">
              <button
                ref={continueButtonRef}
                onClick={onContinue}
                className="w-full sm:w-auto px-6 py-3.5 rounded-xl bg-red-600 text-white font-black uppercase tracking-widest text-xs hover:bg-red-700 transition-colors shadow-lg shadow-red-900/30"
              >
                I Understand, Continue
              </button>
              <p className="text-[10px] text-white/30 uppercase tracking-[0.25em]">
                This warning appears on every app launch.
              </p>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};

/**
 * Root application component.
 */
const App: React.FC = () => {
  const {
    sidebarOpen,
    setSidebarOpen,
    sidebarCollapsed,
    toggleSidebarCollapsed,
    isAdmin,
    setAdminModalOpen,
  } = useAppStore();

  const [safetyDisclaimerAccepted, setSafetyDisclaimerAccepted] = React.useState(false);


  const { online: backendOnline } = useBackendStatus();
  
  const location  = useLocation();
  const navigate  = useNavigate();

  const safetyDisclaimer = (
    <SafetyDisclaimerModal
      open={!safetyDisclaimerAccepted}
      onContinue={() => setSafetyDisclaimerAccepted(true)}
    />
  );



  /** Log route transitions (dev only). */
  React.useEffect(() => {
    logger.info(`[App] Route changed -> ${location.pathname}`);
  }, [location.pathname]);

  // Show the safety advisory every time the user visits landing/auth entry.
  React.useEffect(() => {
    if (location.pathname === '/' || location.pathname === '/login') {
      setSafetyDisclaimerAccepted(false);
    }
  }, [location.pathname]);

  // Standalone Layout Wrapper for public pages (Landing, Verify Email)
  const renderPublicPage = (children: React.ReactNode) => (
    <div className="min-h-screen bg-black text-white font-sans">
      <ViewErrorBoundary>
        <React.Suspense fallback={<ViewLoader />}>
          {children}
        </React.Suspense>
      </ViewErrorBoundary>
      {safetyDisclaimer}
      <AdminModal />
      <CookieConsent />
    </div>
  );

  if (location.pathname === '/') {
    return renderPublicPage(
      <LandingPage />
    );
  }

  if (location.pathname === '/login') {
    return renderPublicPage(
      <LandingPage />
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
          <img src="/divergex-logo.svg" alt="DivergeX" className="w-7 h-7 rounded-lg object-contain" />
          <span className="font-display font-black tracking-tighter text-lg italic">Diverge<span className="text-red-600">X</span></span>
        </button>

        <button
          onClick={() => {
            if (isAdmin) {
              navigate('/admin');
            } else {
              setAdminModalOpen(true);
            }
          }}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-full border border-white/10 bg-white/[0.04] text-[10px] font-black uppercase tracking-[0.25em] text-white/70 hover:text-white hover:border-red-500/40 transition-colors"
          aria-label={isAdmin ? 'Open admin panel' : 'Open admin access'}
        >
          <Lock className="w-4 h-4" />
          <span>{isAdmin ? 'Admin' : 'Access'}</span>
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
              <img src="/divergex-logo.svg" alt="DivergeX" className="w-full h-full object-contain" />
            </button>
            <AnimatePresence>
              {!sidebarCollapsed && (
                <motion.div
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -10 }}
                  className="flex-1 overflow-hidden"
                >
                  {/* Clicking the text also navigates home */}
                  <button
                    onClick={() => { setSidebarOpen(false); navigate('/'); }}
                    className="text-left hover:opacity-80 transition-opacity pr-2 w-full"
                    aria-label="Go to home page"
                  >
                    <h1 className="font-display font-black tracking-tighter text-xl italic leading-none text-white truncate">Diverge<span className="text-red-600">X</span></h1>
                    <p className="text-[10px] font-mono text-red-500 font-bold uppercase tracking-widest mt-1 truncate">Race Intelligence</p>
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
                      ? 'bg-red-600/15 text-red-500 border border-red-600/30'
                      : 'text-white/55 hover:bg-red-600/10 hover:text-red-500 border border-transparent'
                  }`
                }
              >
                <item.icon className={`shrink-0 ${sidebarCollapsed ? 'w-6 h-6' : 'w-5 h-5'} group-hover:scale-110 transition-transform`} />
                {!sidebarCollapsed && (
                  <span className="font-medium text-sm tracking-wide whitespace-nowrap overflow-hidden">{item.label}</span>
                )}
                {'highlight' in item && item.highlight && (
                  <div className="absolute right-3 top-3 w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
                )}
              </NavLink>
            </motion.div>
          ))}

          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.5 }}
            className="pt-4 mt-4 border-t border-white/5"
          >
            {isAdmin ? (
              <NavLink
                to="/admin"
                onClick={() => setSidebarOpen(false)}
                title={sidebarCollapsed ? 'Admin Panel' : undefined}
                className={({ isActive }) =>
                  `w-full flex items-center gap-4 rounded-xl transition-all duration-300 group relative ${
                    sidebarCollapsed ? 'justify-center p-3' : 'px-4 py-3.5'
                  } ${
                    isActive
                      ? 'bg-amber-600/20 border border-amber-500/50 text-amber-400'
                      : 'border border-amber-500/30 text-amber-500/70 hover:bg-amber-500/10 hover:text-amber-400'
                  }`
                }
              >
                <Lock className={`shrink-0 ${sidebarCollapsed ? 'w-6 h-6' : 'w-5 h-5'}`} />
                {!sidebarCollapsed && (
                  <span className="font-bold text-[10px] uppercase tracking-widest whitespace-nowrap overflow-hidden">Admin Panel</span>
                )}
                {sidebarCollapsed && <span className="text-xs font-bold">ADM</span>}
              </NavLink>
            ) : (
              <button
                onClick={() => setAdminModalOpen(true)}
                title={sidebarCollapsed ? 'Admin Control' : undefined}
                className={`w-full flex items-center gap-4 rounded-xl transition-all duration-300 group relative ${
                  sidebarCollapsed ? 'justify-center p-3' : 'px-4 py-3.5'
                } text-white/40 hover:bg-red-600/10 hover:text-red-500`}
              >
                <Lock className={`shrink-0 ${sidebarCollapsed ? 'w-6 h-6' : 'w-5 h-5'} group-hover:scale-110 transition-transform`} />
                {!sidebarCollapsed && (
                  <span className="font-bold text-[10px] uppercase tracking-widest whitespace-nowrap overflow-hidden">Admin Control</span>
                )}
              </button>
            )}
          </motion.div>
        </nav>
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
        <RacingBackground view="command" theme="dark" />
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
          <Footer onAdminClick={() => {
            if (isAdmin) {
              navigate('/admin');
            } else {
              setAdminModalOpen(true);
            }
          }} />
        </div>
      </main>

      <AdminModal />


      {/* Demo Mode Badge */}
      {!backendOnline && (
        <div className="fixed top-16 lg:top-3 right-3 z-[100] px-3 py-1.5 rounded-lg bg-red-600/15 border border-red-600/30 text-red-500 text-[9px] font-black uppercase tracking-[3px] backdrop-blur-sm pointer-events-none">
          Simulated Intelligence Active
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
      <CookieConsent />
    </div>
  );
};

export default App;
