import { NavLink, useParams, Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import ResearchHistory from '../features/research/ResearchHistory';
import { Panel, PanelHeader } from './ui';

const TABS = [
  { slug: 'profile', label: 'User Profile' },
  { slug: 'runs', label: 'Research Run Log' },
] as const;

export default function UserSettingsPanel() {
  const { user, signOut } = useAuth();
  const { tab } = useParams<{ tab: string }>();

  if (tab !== 'profile' && tab !== 'runs') {
    return <Navigate to="/app/settings/profile" replace />;
  }

  const handleLogout = async () => {
    await signOut();
  };

  return (
    <div className="w-full flex flex-col gap-8 pb-16">
      {/* Section Header with Tabs */}
      <div className="space-y-6 border-b border-outline-variant/30 pb-4">
        <div>
          <h1 className="text-3xl font-headline tracking-tight text-on-surface">
            System Configurations
          </h1>
          <p className="text-on-surface-variant font-body text-sm mt-1">
            Manage user session and audit past research runs.
          </p>
        </div>

        {/* Internal Tabs */}
        <div className="flex gap-6 border-b border-outline-variant/30">
          {TABS.map((t) => (
            <NavLink
              key={t.slug}
              to={`/app/settings/${t.slug}`}
              className={({ isActive }) =>
                `font-label text-[11px] uppercase tracking-widest pb-2 transition-colors ${
                  isActive
                    ? 'text-primary border-b border-primary'
                    : 'text-outline-variant hover:text-primary'
                }`
              }
            >
              {t.label}
            </NavLink>
          ))}
        </div>
      </div>

      {tab === 'profile' && (
        <div className="space-y-8">
          <Panel className="space-y-6">
            <PanelHeader>Authenticated Operator</PanelHeader>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-1.5">
                <label className="text-xs font-label text-outline uppercase tracking-widest">
                  User Email
                </label>
                <div className="w-full bg-surface-container-low border-b border-outline-variant/30 text-on-surface font-label text-sm py-2.5 px-3 select-all">
                  {user?.email || 'Anonymous Operator'}
                </div>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-label text-outline uppercase tracking-widest">
                  User Identifier
                </label>
                <div className="w-full bg-surface-container-low border-b border-outline-variant/30 text-outline font-label text-xs py-3 px-3 select-all truncate">
                  {user?.id || 'Unidentified'}
                </div>
              </div>
            </div>
          </Panel>

          {/* Session Control Block */}
          <section className="flex justify-end">
            <button
              type="button"
              onClick={handleLogout}
              className="bg-transparent border border-error-container text-error hover:bg-error-container/20 transition-colors py-3 px-8 font-label text-sm tracking-widest uppercase flex items-center gap-3"
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
                power_settings_new
              </span>
              Terminate Session
            </button>
          </section>
        </div>
      )}

      {tab === 'runs' && (
        <Panel>
          <div className="mb-6">
            <PanelHeader>Durable Research Runs</PanelHeader>
          </div>
          <ResearchHistory />
        </Panel>
      )}
    </div>
  );
}
