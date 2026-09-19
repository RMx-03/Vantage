import { useState, useEffect, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { createResearchRun, listResearchRuns, getResearchRun, ApiError } from '../../api/researchRuns';
import { useAuth } from '../../context/AuthContext';
import type { ResearchRun } from '../../types/research';
import ResearchResult from './ResearchResult';
import ResearchHistory from './ResearchHistory';
import { buildStatusStrip, recentSymbols } from './runChrome';
import { MicroLabel } from '../../components/ui';

const SYMBOL_PATTERN = /^[A-Z][A-Z0-9.]{0,9}$/;

export default function ResearchWorkspace() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const prevOwnerRef = useRef(user?.id);

  useEffect(() => {
    if (prevOwnerRef.current !== undefined && prevOwnerRef.current !== user?.id) {
      navigate('/app/research', { replace: true });
    }
    prevOwnerRef.current = user?.id;
  }, [user?.id, navigate]);

  // Remounting on owner change is what guarantees that no run, error or input
  // a previous owner produced can survive into the next owner's session.
  return (
    <OwnerWorkspace key={user?.id ?? 'signed-out'} ownerId={user?.id ?? null} />
  );
}

function OwnerWorkspace({ ownerId }: { ownerId: string | null }) {
  const [symbolInput, setSymbolInput] = useState('');
  const { runId } = useParams<{ runId?: string }>();
  const [liveRunId, setLiveRunId] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(true);

  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { signOut } = useAuth();

  const { data: routeRun } = useQuery({
    queryKey: ['research-run', runId],
    queryFn: () => getResearchRun(runId!),
    enabled: Boolean(runId),
  });

  const selectedRun: ResearchRun | null = routeRun ?? null;
  const isHistorical = Boolean(runId) && runId !== liveRunId;

  const { data: historyData } = useQuery({
    queryKey: ['research-runs', ownerId],
    queryFn: () => listResearchRuns(),
    enabled: ownerId !== null,
  });

  const recent = recentSymbols(historyData?.items ?? []);

  const normalizedSymbol = symbolInput.trim().toUpperCase();
  const isValidSymbol = SYMBOL_PATTERN.test(normalizedSymbol);

  const mutation = useMutation({
    mutationFn: (sym: string) => createResearchRun(sym),
    onSuccess: (data) => {
      setLiveRunId(data.run_id);
      queryClient.setQueryData(['research-run', data.run_id], data);
      queryClient.invalidateQueries({ queryKey: ['research-runs', ownerId] });
      navigate(`/app/research/${data.run_id}`, { replace: true });
    },
  });

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!isValidSymbol || mutation.isPending) return;
    mutation.mutate(normalizedSymbol);
  };

  const handleRetry = () => {
    if (isValidSymbol) {
      mutation.mutate(normalizedSymbol);
    }
  };

  const handleSignOutAndAuth = async () => {
    await signOut();
    navigate('/auth');
  };

  const renderError = () => {
    if (!mutation.isError) return null;

    const err = mutation.error;
    let message = 'Research run could not be completed. Please try again later.';
    let isAuthError = false;
    let runId: string | null | undefined = null;
    let requestId: string | null | undefined = null;

    if (err instanceof ApiError) {
      runId = err.error.run_id;
      requestId = err.error.request_id;
      if (err.status === 401) {
        isAuthError = true;
        message = 'Your session has expired. Please sign in again.';
      } else if (err.status === 503 || err.error.code === 'MARKET_DATA_FAILED') {
        message =
          'Market data could not be retrieved. Please check the symbol and market hours, then retry.';
      } else {
        message = err.error.message || message;
      }
    } else if (err instanceof Error) {
      message = err.message || message;
    }

    return (
      <div className="border border-error-container bg-error-container/30 p-6 text-error">
        <div className="flex items-center gap-2 font-semibold text-error text-base mb-2 font-label">
          <span>Failed to complete research run</span>
        </div>
        <p className="text-sm leading-relaxed text-error font-body">{message}</p>

        {(runId || requestId) && (
          <div className="mt-3 flex flex-wrap gap-4 text-xs font-label text-error">
            {runId && <span>Run ID: {runId}</span>}
            {requestId && <span>Request ID: {requestId}</span>}
          </div>
        )}

        <div className="mt-4 flex items-center gap-3">
          {isAuthError ? (
            <button
              type="button"
              onClick={handleSignOutAndAuth}
              className="px-4 py-2 bg-error text-on-error text-xs font-bold font-label uppercase tracking-widest transition-opacity hover:opacity-90"
            >
              Sign in again
            </button>
          ) : (
            <button
              type="button"
              onClick={handleRetry}
              disabled={mutation.isPending}
              className="px-4 py-2 bg-surface-container hover:bg-surface-container-highest text-on-surface text-xs font-bold font-label uppercase tracking-widest border border-outline-variant transition-colors disabled:opacity-50"
            >
              Retry research
            </button>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className={`w-full max-w-5xl mx-auto px-6 flex flex-col gap-12 ${showHistory ? 'lg:pr-[444px]' : ''}`}>
      {/* Search Header and Input */}
      <section className="flex flex-col gap-6">
        <div className="flex items-center justify-between">
          <div className="flex flex-col gap-2">
            <h1 className="text-4xl font-extrabold tracking-tighter text-primary">Vantage.</h1>
            <p className="text-on-surface-variant font-label tracking-wide uppercase text-sm">
              Agentic Quant Terminal
            </p>
          </div>

          <button
            type="button"
            onClick={() => setShowHistory(!showHistory)}
            className="px-4 py-2 text-xs font-label uppercase tracking-widest border border-outline-variant bg-surface-container-low text-on-surface-variant hover:text-on-surface hover:border-outline transition-colors flex items-center gap-2"
          >
            <span>{showHistory ? 'Hide History' : 'View History'}</span>
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-2">
          <label
            htmlFor="symbol-input"
            className="text-xs font-label text-outline uppercase tracking-widest"
          >
            US equity symbol
          </label>
          <div className="flex flex-col md:flex-row gap-0">
            <div className="flex-1 bg-surface-container-low border border-outline-variant focus-within:border-primary transition-colors">
              <input
                id="symbol-input"
                type="text"
                value={symbolInput}
                onChange={(e) => setSymbolInput(e.target.value)}
                placeholder="e.g. AAPL, MSFT, NVDA"
                className="w-full bg-transparent border-none focus:outline-none focus:ring-0 text-on-surface font-label p-4 placeholder:text-outline-variant"
              />
            </div>
            <button
              type="submit"
              disabled={!isValidSymbol || mutation.isPending}
              className="bg-primary text-on-primary font-bold px-8 py-4 hover:opacity-90 transition-opacity uppercase tracking-widest text-xs disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Run research
            </button>
          </div>
        </form>

        {recent.length > 0 && (
          <div className="flex gap-4 overflow-x-auto">
            <MicroLabel>Recent:</MicroLabel>
            {recent.map((sym) => (
              <button
                key={sym}
                type="button"
                onClick={() => setSymbolInput(sym)}
                className="font-label text-[10px] text-primary uppercase tracking-tighter hover:text-on-surface transition-colors"
              >
                ${sym}
              </button>
            ))}
          </div>
        )}
      </section>

      {/* Main Workspace Area */}
      <div className="flex flex-col gap-6">
        {mutation.isPending && (
          <div role="status" className="flex flex-col gap-2 py-4">
            <div className="flex items-center gap-4">
              <div className="w-2 h-2 bg-primary animate-pulse" />
              <p className="text-outline text-xs font-label uppercase tracking-[0.2em] animate-pulse">
                Running research analysis for {normalizedSymbol}...
              </p>
            </div>
            <span className="text-xs font-label text-outline pl-6">
              Verifying 21 trading sessions and fetching EOD snapshot
            </span>
          </div>
        )}

        {renderError()}

        {!mutation.isPending && !mutation.isError && selectedRun && (
          <ResearchResult run={selectedRun} historical={isHistorical} />
        )}

        {!mutation.isPending && !mutation.isError && !selectedRun && (
          <div className="border border-outline-variant/30 bg-surface-container-low p-12 text-center text-outline font-label">
            <p className="text-sm">Enter a US equity symbol above to begin an EOD research run.</p>
          </div>
        )}
      </div>

      {buildStatusStrip(selectedRun) && (
        <footer className="mt-20 py-8 border-t border-outline-variant/20 flex flex-col gap-4 items-center">
          <div className="bg-primary/5 px-6 py-2 border border-primary/20">
            <span className="font-label text-[10px] text-primary uppercase tracking-[0.3em]">
              {buildStatusStrip(selectedRun)}
            </span>
          </div>
          <p className="font-label text-[10px] text-outline-variant">© 2026 VANTAGE QUANT SYSTEMS</p>
        </footer>
      )}

      {/* Slide-over History Drawer */}
      {showHistory && (
        <>
          <div
            onClick={() => setShowHistory(false)}
            className="lg:hidden fixed inset-0 z-40 bg-surface-container-lowest/60"
            aria-hidden="true"
          />
          <aside className="fixed right-0 top-16 bottom-0 z-50 w-full lg:w-[420px] bg-surface-container border-l border-outline-variant flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-outline-variant shrink-0">
              <h2 className="font-headline text-xs uppercase tracking-widest text-primary">
                Research History
              </h2>
              <button
                type="button"
                onClick={() => setShowHistory(false)}
                aria-label="Close history"
                className="text-outline hover:text-on-surface transition-colors"
              >
                <span aria-hidden="true" className="material-symbols-outlined text-lg">
                  close
                </span>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-6 py-4">
              <ResearchHistory />
            </div>
          </aside>
        </>
      )}
    </div>
  );
}
