import { NavLink, useParams, Navigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth } from '../context/AuthContext';
import ResearchHistory from '../features/research/ResearchHistory';

const isTest = import.meta.env?.MODE === 'test';

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
    <div className="w-full max-w-4xl mx-auto px-6 flex flex-col gap-10 pb-24">
      {/* Section Header with Tabs */}
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-headline tracking-tight text-on-surface">
            System Configurations
          </h1>
          <p className="text-on-surface-variant font-body text-sm mt-1">
            Manage user session and audit past research runs.
          </p>
        </div>

        {/* Internal Tabs - Baseline Aligned to Prevent Jitter */}
        <div className="flex gap-8 border-b border-outline-variant/30">
          {TABS.map((t) => (
            <NavLink
              key={t.slug}
              to={`/app/settings/${t.slug}`}
              className={({ isActive }) =>
                `font-label text-xs uppercase tracking-widest pb-3 -mb-px border-b-2 transition-colors ${
                  isActive
                    ? 'text-primary border-primary font-bold'
                    : 'text-outline border-transparent hover:text-on-surface hover:border-outline-variant'
                }`
              }
            >
              {t.label}
            </NavLink>
          ))}
        </div>
      </div>

      {/* Tab Content Area with Stable Min-Height & Smooth Transition */}
      <div className="min-h-[460px]">
        <AnimatePresence mode="wait" initial={false}>
          {tab === 'profile' && (
            <motion.div
              key="profile"
              initial={isTest ? false : { opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={isTest ? undefined : { opacity: 0, y: -4 }}
              transition={{ duration: 0.15, ease: 'easeOut' }}
            >
              <section className="bg-surface-container border border-outline-variant/30 p-8 space-y-8">
                <div className="flex items-center justify-between border-b border-outline-variant/30 pb-3">
                  <h2 className="text-xs uppercase font-label tracking-widest text-outline">
                    Authenticated Operator
                  </h2>
                  <div className="flex items-center gap-2">
                    <span className="w-1.5 h-1.5 bg-primary animate-pulse shrink-0" />
                    <span className="text-[10px] font-label uppercase tracking-widest text-primary font-bold">
                      Session Active
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="space-y-1.5">
                    <label className="text-xs font-label text-outline uppercase tracking-widest">
                      User Email
                    </label>
                    <div className="w-full bg-surface-container-low border border-outline-variant/30 text-on-surface font-label text-sm py-2.5 px-3 select-all">
                      {user?.email || 'Anonymous Operator'}
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-label text-outline uppercase tracking-widest">
                      User Identifier
                    </label>
                    <div className="w-full bg-surface-container-low border border-outline-variant/30 text-outline font-label text-xs py-3 px-3 select-all truncate">
                      {user?.id || 'Unidentified'}
                    </div>
                  </div>
                </div>

                {/* Session Security Action Block */}
                <div className="pt-6 border-t border-outline-variant/30 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div>
                    <span className="font-label text-xs uppercase tracking-wider text-on-surface font-semibold block">
                      Session Security
                    </span>
                    <span className="font-body text-xs text-outline">
                      Revoke local tokens and disconnect current operator.
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={handleLogout}
                    className="bg-surface-container-low border border-error-container text-error hover:bg-error-container/20 hover:border-error transition-colors py-2.5 px-6 font-label text-xs tracking-widest uppercase flex items-center justify-center gap-2.5 shrink-0"
                  >
                    <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                      power_settings_new
                    </span>
                    Terminate Session
                  </button>
                </div>
              </section>
            </motion.div>
          )}

          {tab === 'runs' && (
            <motion.div
              key="runs"
              initial={isTest ? false : { opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={isTest ? undefined : { opacity: 0, y: -4 }}
              transition={{ duration: 0.15, ease: 'easeOut' }}
            >
              <section className="bg-surface-container border border-outline-variant/30 p-8 space-y-6">
                <div className="flex items-center justify-between border-b border-outline-variant/30 pb-3">
                  <h2 className="text-xs uppercase font-label tracking-widest text-outline">
                    Durable Research Runs
                  </h2>
                  <span className="text-[10px] font-label text-outline uppercase tracking-widest">
                    Audit Trail
                  </span>
                </div>
                <ResearchHistory />
              </section>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
