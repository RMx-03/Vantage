import { useEffect, useState } from 'react';
import { useLocation, useMatch, Outlet } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { getResearchRun } from '../api/researchRuns';
import { useAuth } from '../context/AuthContext';
import type { ResearchRun } from '../types/research';
import { MicroLabel } from '../components/ui';
import SideNav from '../components/nav/SideNav';
import BottomNav from '../components/nav/BottomNav';

export default function Terminal() {
  const { pathname } = useLocation();
  const isSettings = pathname.startsWith('/app/settings');
  const { signOut, user } = useAuth();
  const ownerId = user?.id ?? null;
  const match = useMatch('/app/research/:runId');
  const runId = match?.params.runId;
  const { data: run } = useQuery<ResearchRun>({
    queryKey: ['research-run', ownerId, runId],
    queryFn: () => getResearchRun(runId!),
    enabled: ownerId !== null && Boolean(runId),
  });
  const activeModel = run?.model_info?.model ?? null;

  const [sidebarOpen, setSidebarOpen] = useState(() => {
    if (typeof window === 'undefined') return true;
    try {
      return localStorage.getItem('vantage:sidebar-open') !== 'false';
    } catch {
      return true;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem('vantage:sidebar-open', String(sidebarOpen));
    } catch {
      // ignore storage errors
    }
  }, [sidebarOpen]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        setSidebarOpen((prev) => !prev);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  return (
    <div className="dark font-body text-on-background selection:bg-primary selection:text-on-primary h-screen overflow-hidden flex flex-col bg-[#0e0e0e]">
      {/* TopAppBar Shell */}
      <header className="bg-surface-dim text-on-surface font-headline border-b border-outline-variant/30 w-full z-50 shrink-0">
        <div className="w-full px-5 relative flex items-center justify-between h-14">
          {/* Left: Sidebar Toggle + Brand */}
          <div className="flex items-center gap-3 z-10">
            <button
              type="button"
              onClick={() => setSidebarOpen((prev) => !prev)}
              aria-label={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
              aria-expanded={sidebarOpen}
              title={sidebarOpen ? 'Collapse sidebar (Ctrl+B)' : 'Expand sidebar (Ctrl+B)'}
              className="hidden lg:flex p-1.5 text-outline hover:text-on-surface bg-surface-container-low hover:bg-surface-container-high border border-outline-variant/30 hover:border-outline-variant transition-colors focus:outline-none focus:ring-1 focus:ring-primary"
            >
              {sidebarOpen ? (
                <PanelLeftClose className="w-4 h-4" />
              ) : (
                <PanelLeftOpen className="w-4 h-4" />
              )}
            </button>
            <div className="flex items-center gap-2">
              <span className="text-base font-bold tracking-tight text-on-surface">Vantage</span>
              <span className="px-1.5 py-0.5 text-[9px] font-label font-bold uppercase tracking-[0.15em] text-primary bg-surface-container-high border border-outline-variant/40 hidden sm:inline-block">
                Quant AI
              </span>
            </div>
          </div>

          {/* Center: Anchored Terminal Status Capsule */}
          <div className="absolute left-1/2 -translate-x-1/2 flex items-center gap-2 px-3 py-1 bg-surface-container-low border border-outline-variant/30 pointer-events-none">
            <span className="w-1.5 h-1.5 bg-primary animate-pulse shrink-0" />
            <span className="text-[10px] font-label uppercase tracking-[0.25em] text-on-surface font-semibold">
              {isSettings ? 'SYSTEM SETTINGS' : 'ANALYTICAL TERMINAL'}
            </span>
          </div>

          {/* Right: Operator Identity & Sign Out */}
          <div className="flex items-center gap-2.5 z-10">
            {user?.email && (
              <div className="hidden md:flex items-center gap-1.5 px-2.5 py-1 bg-surface-container-low border border-outline-variant/30 text-[10px] font-label text-outline">
                <span className="w-1.5 h-1.5 bg-primary/70 shrink-0" />
                <span className="truncate max-w-[150px] text-on-surface-variant font-medium">
                  {user.email}
                </span>
              </div>
            )}
            <button
              onClick={() => signOut()}
              className="flex items-center gap-1.5 px-2.5 py-1 text-outline hover:text-error hover:bg-error-container/20 border border-outline-variant/30 hover:border-error/40 transition-colors font-label text-[10px] uppercase tracking-widest group"
            >
              <span className="hidden sm:block">Sign Out</span>
              <span className="material-symbols-outlined text-sm group-hover:translate-x-0.5 transition-transform">logout</span>
            </button>
          </div>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden relative">
        {/* SideNavBar (Hidden on Mobile, Collapsible on Desktop) */}
        <aside
          aria-label="Sidebar navigation"
          className={`hidden lg:flex flex-col bg-surface border-r border-outline-variant/30 z-40 shrink-0 transition-[width,border-color] duration-200 ease-in-out overflow-hidden ${
            sidebarOpen ? 'w-64' : 'w-0 border-r-0'
          }`}
          aria-hidden={!sidebarOpen}
          inert={!sidebarOpen}
        >
          <div className="w-64 p-5 flex flex-col justify-between h-full">
            <SideNav />
            <div className="mt-auto border-t border-outline-variant/20 pt-4">
              <div className="p-3 border border-outline-variant/40 bg-surface-container-low flex flex-col gap-1">
                <MicroLabel className="text-[9px] tracking-[0.2em] text-outline">Active Model</MicroLabel>
                <span className="font-label text-xs font-semibold text-primary tracking-wide">
                  {activeModel ?? '—'}
                </span>
              </div>
            </div>
          </div>
        </aside>

        {/* Main Content Area */}
        <main className="flex-1 overflow-y-auto [scrollbar-gutter:stable] w-full">
          <div className="py-12 md:py-24">
            <Outlet />
          </div>
        </main>
      </div>

      {/* BottomNavBar (Mobile) */}
      <BottomNav />
    </div>
  );
}
