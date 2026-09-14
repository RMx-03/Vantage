import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import UserSettingsPanel from '../components/UserSettingsPanel';
import ResearchWorkspace from '../features/research/ResearchWorkspace';

export default function Terminal() {
  const [showSettings, setShowSettings] = useState(false);
  const { signOut } = useAuth();

  return (
    <div className="dark font-body text-slate-100 min-h-screen flex flex-col bg-slate-950">
      {/* TopAppBar Shell */}
      <header className="bg-slate-950/90 backdrop-blur-md text-slate-200 border-b border-slate-800/80 w-full sticky top-0 z-50 shrink-0">
        <div className="w-full max-w-7xl mx-auto px-6 flex items-center justify-between h-16">
          <div className="flex items-center gap-3">
            <span className="text-xl font-bold tracking-tight text-white font-mono">
              Vantage
            </span>
            <span className="text-[10px] uppercase font-mono tracking-widest text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/20 hidden sm:block">
              EOD Research Terminal
            </span>
          </div>

          <div className="flex flex-col items-center">
            <span className="text-[11px] font-mono uppercase tracking-widest text-slate-400">
              {showSettings ? 'System Settings' : 'Research Workspace'}
            </span>
          </div>

          <div className="flex items-center gap-4">
            <button
              onClick={() => setShowSettings(!showSettings)}
              className="text-xs font-medium text-slate-300 hover:text-white px-3 py-1.5 rounded-lg border border-slate-800 hover:bg-slate-900 transition-colors"
            >
              {showSettings ? 'Back to Terminal' : 'Settings'}
            </button>
            <button
              onClick={() => signOut()}
              className="flex items-center gap-2 text-slate-400 hover:text-rose-400 transition-colors text-xs font-medium uppercase tracking-wider"
            >
              <span>Sign Out</span>
            </button>
          </div>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden relative">
        {/* Main Content Area */}
        <main className="flex-1 overflow-y-auto w-full">
          {showSettings ? (
            <div className="max-w-4xl mx-auto py-10 px-6">
              <UserSettingsPanel />
            </div>
          ) : (
            <ResearchWorkspace />
          )}
        </main>
      </div>
    </div>
  );
}
