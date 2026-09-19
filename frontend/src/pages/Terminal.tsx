import { useLocation, Outlet } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../context/AuthContext';
import { listResearchRuns } from '../api/researchRuns';
import { MicroLabel } from '../components/ui';
import SideNav from '../components/nav/SideNav';
import BottomNav from '../components/nav/BottomNav';

export default function Terminal() {
  const { pathname } = useLocation();
  const isSettings = pathname.startsWith('/app/settings');
  const { user, signOut } = useAuth();
  const ownerId = user?.id ?? null;

  const { data: historyData } = useQuery({
    queryKey: ['research-runs', ownerId],
    queryFn: () => listResearchRuns(),
    enabled: ownerId !== null,
  });

  const activeModel = historyData?.items?.[0]?.model_info?.model ?? null;

  return (
    <div className="dark font-body text-on-background selection:bg-primary selection:text-on-primary h-screen overflow-hidden flex flex-col bg-[#0e0e0e]">
      {/* TopAppBar Shell */}
      <header className="bg-[#0e0e0e] text-[#c6c6c7] font-['Inter'] font-normal border-b border-[#191a1a] w-full z-50 shrink-0">
        <div className="w-full max-w-7xl mx-auto px-6 flex items-center justify-between h-16">
          <div className="flex items-center gap-2">
            <span className="text-xl font-bold tracking-tighter text-[#c6c6c7]">Vantage</span>
            <span className="text-[10px] font-label uppercase tracking-widest text-outline hidden sm:block">
              Quant AI
            </span>
          </div>

          <div className="flex flex-col items-center">
            <span className="text-[10px] font-label uppercase tracking-[0.3em] text-primary animate-pulse">
              {isSettings ? 'SYSTEM SETTINGS' : 'ANALYTICAL TERMINAL'}
            </span>
          </div>

          <button
            onClick={() => signOut()}
            className="flex items-center gap-2 text-[#484848] hover:text-error transition-colors font-label text-[10px] uppercase tracking-widest group"
          >
            <span className="hidden sm:block group-hover:pr-1 transition-all">Sign Out</span>
            <span className="material-symbols-outlined text-sm">logout</span>
          </button>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden relative">
        {/* SideNavBar (Hidden on Mobile) */}
        <aside className="hidden lg:flex w-64 bg-[#0e0e0e] flex-col border-r border-[#191a1a] z-40 shrink-0">
          <div className="p-8 flex flex-col gap-12 h-full">
            <SideNav />
            <div className="mt-auto border-t border-[#191a1a] pt-6 flex flex-col gap-2">
              <MicroLabel>Active Model</MicroLabel>
              <span className="font-label text-xs text-primary">{activeModel ?? '—'}</span>
            </div>
          </div>
        </aside>

        {/* Main Content Area */}
        <main className="flex-1 overflow-y-auto w-full">
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
