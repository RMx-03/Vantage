import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import UserSettingsPanel from '../components/UserSettingsPanel';
import ResearchWorkspace from '../features/research/ResearchWorkspace';
import { MicroLabel } from '../components/ui';

export default function Terminal() {
  const [showSettings, setShowSettings] = useState(false);
  const { signOut } = useAuth();

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
              {showSettings ? 'SYSTEM SETTINGS' : 'ANALYTICAL TERMINAL'}
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
            <nav className="flex flex-col gap-4">
              <button
                onClick={() => setShowSettings(false)}
                className={`flex items-center gap-4 p-3 w-full transition-colors duration-150 font-['Inter'] text-sm tracking-tight ${
                  !showSettings
                    ? 'text-[#c6c6c7] bg-[#191a1a]'
                    : 'text-[#484848] hover:bg-[#131313] hover:text-[#c6c6c7]'
                }`}
              >
                <span className="material-symbols-outlined">terminal</span>
                Terminal
              </button>
              <button
                disabled
                aria-disabled="true"
                className="flex items-center gap-4 p-3 w-full text-outline-variant cursor-not-allowed font-body text-sm tracking-tight"
              >
                <span aria-hidden="true" className="material-symbols-outlined">
                  account_balance_wallet
                </span>
                Portfolio
                <MicroLabel className="ml-auto">Phase 2</MicroLabel>
              </button>
              <button
                disabled
                aria-disabled="true"
                className="flex items-center gap-4 p-3 w-full text-outline-variant cursor-not-allowed font-body text-sm tracking-tight"
              >
                <span aria-hidden="true" className="material-symbols-outlined">
                  query_stats
                </span>
                Risk
                <MicroLabel className="ml-auto">Phase 2</MicroLabel>
              </button>
              <button
                onClick={() => setShowSettings(true)}
                className={`flex items-center gap-4 p-3 w-full transition-colors duration-150 font-['Inter'] text-sm tracking-tight ${
                  showSettings
                    ? 'text-[#c6c6c7] bg-[#191a1a]'
                    : 'text-[#484848] hover:bg-[#131313] hover:text-[#c6c6c7]'
                }`}
              >
                <span className="material-symbols-outlined">settings</span>
                Settings
              </button>
            </nav>
            <div className="mt-auto border-t border-[#191a1a] pt-6 flex flex-col gap-2">
              <MicroLabel>Active Model</MicroLabel>
              <span className="font-label text-xs text-primary">—</span>
            </div>
          </div>
        </aside>

        {/* Main Content Area */}
        <main className="flex-1 overflow-y-auto w-full">
          <div className="py-12 md:py-24">
            {showSettings ? <UserSettingsPanel /> : <ResearchWorkspace />}
          </div>
        </main>
      </div>

      {/* BottomNavBar (Mobile) */}
      <nav className="lg:hidden w-full z-50 flex justify-around items-center h-16 bg-[#0e0e0e] border-t border-[#191a1a] shrink-0">
        <button
          onClick={() => setShowSettings(false)}
          className={`flex flex-col items-center justify-center p-2 flex-1 h-full transition-transform ${
            !showSettings ? 'text-[#c6c6c7] bg-[#191a1a]' : 'text-[#484848] hover:bg-[#131313]'
          }`}
        >
          <span className="material-symbols-outlined">terminal</span>
          <span className="font-label text-[10px] uppercase tracking-widest mt-1">Terminal</span>
        </button>
        <button
          disabled
          aria-disabled="true"
          className="flex flex-col items-center justify-center p-2 flex-1 h-full text-outline-variant cursor-not-allowed"
        >
          <span aria-hidden="true" className="material-symbols-outlined">
            account_balance_wallet
          </span>
          <span className="font-label text-[10px] uppercase tracking-widest mt-1">Portfolio</span>
        </button>
        <button
          disabled
          aria-disabled="true"
          className="flex flex-col items-center justify-center p-2 flex-1 h-full text-outline-variant cursor-not-allowed"
        >
          <span aria-hidden="true" className="material-symbols-outlined">
            query_stats
          </span>
          <span className="font-label text-[10px] uppercase tracking-widest mt-1">Risk</span>
        </button>
        <button
          onClick={() => setShowSettings(true)}
          className={`flex flex-col items-center justify-center p-2 flex-1 h-full transition-transform ${
            showSettings ? 'text-[#c6c6c7] bg-[#191a1a]' : 'text-[#484848] hover:bg-[#131313]'
          }`}
        >
          <span className="material-symbols-outlined">settings</span>
          <span className="font-label text-[10px] uppercase tracking-widest mt-1">Settings</span>
        </button>
      </nav>
    </div>
  );
}
