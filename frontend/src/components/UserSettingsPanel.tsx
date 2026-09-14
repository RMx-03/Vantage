import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import ResearchHistory from '../features/research/ResearchHistory';

type SettingsTab = 'profile' | 'history';

export default function UserSettingsPanel() {
  const { user, signOut } = useAuth();
  const [activeTab, setActiveTab] = useState<SettingsTab>('profile');

  const handleLogout = async () => {
    await signOut();
  };

  return (
    <div className="w-full flex flex-col gap-8 pb-16">
      {/* Section Header with Tabs */}
      <div className="space-y-6 border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">System Configurations</h1>
          <p className="text-slate-400 text-sm mt-1">Manage user session and audit past research runs.</p>
        </div>

        {/* Internal Tabs */}
        <div className="flex gap-6 border-b border-slate-800">
          <button
            onClick={() => setActiveTab('profile')}
            className={`text-xs uppercase font-mono tracking-wider pb-3 transition-colors border-b-2 ${
              activeTab === 'profile'
                ? 'text-indigo-400 border-indigo-400 font-bold'
                : 'text-slate-400 hover:text-slate-200 border-transparent'
            }`}
          >
            User Profile
          </button>
          <button
            onClick={() => setActiveTab('history')}
            className={`text-xs uppercase font-mono tracking-wider pb-3 transition-colors border-b-2 ${
              activeTab === 'history'
                ? 'text-indigo-400 border-indigo-400 font-bold'
                : 'text-slate-400 hover:text-slate-200 border-transparent'
            }`}
          >
            Research Run Log
          </button>
        </div>
      </div>

      {activeTab === 'profile' && (
        <div className="space-y-8">
          <section className="bg-slate-900/60 border border-slate-800 rounded-xl p-6 space-y-6 backdrop-blur-sm">
            <h2 className="text-xs uppercase font-mono tracking-widest text-slate-400 border-b border-slate-800 pb-2">
              Authenticated Operator
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-400">User Email</label>
                <div className="w-full bg-slate-950/80 border border-slate-800 text-slate-200 font-mono text-sm py-2.5 px-3 rounded-lg select-all">
                  {user?.email || 'Anonymous Operator'}
                </div>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-400">User Identifier</label>
                <div className="w-full bg-slate-950/80 border border-slate-800 text-slate-400 font-mono text-xs py-3 px-3 rounded-lg select-all truncate">
                  {user?.id || 'Unidentified'}
                </div>
              </div>
            </div>
          </section>

          {/* Session Control Block */}
          <section className="flex justify-end">
            <button
              onClick={handleLogout}
              className="bg-rose-950/20 border border-rose-500/30 text-rose-300 hover:bg-rose-950/40 hover:text-rose-200 transition-colors py-2.5 px-6 text-xs font-semibold rounded-lg uppercase tracking-wider"
            >
              Sign Out Session
            </button>
          </section>
        </div>
      )}

      {activeTab === 'history' && (
        <section className="bg-slate-900/60 border border-slate-800 rounded-xl p-6 backdrop-blur-sm">
          <h2 className="text-xs uppercase font-mono tracking-widest text-slate-400 border-b border-slate-800 pb-3 mb-6">
            Durable Research Runs
          </h2>
          <ResearchHistory />
        </section>
      )}
    </div>
  );
}
