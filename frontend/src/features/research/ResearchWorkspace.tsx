import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { createResearchRun, ApiError } from '../../api/researchRuns';
import { useAuth } from '../../context/AuthContext';
import type { ResearchRun } from '../../types/research';
import ResearchResult from './ResearchResult';
import ResearchHistory from './ResearchHistory';

const SYMBOL_PATTERN = /^[A-Z][A-Z0-9.]{0,9}$/;

export default function ResearchWorkspace() {
  const [symbolInput, setSymbolInput] = useState('');
  const [selectedRun, setSelectedRun] = useState<ResearchRun | null>(null);
  const [isHistorical, setIsHistorical] = useState(false);
  const [showHistory, setShowHistory] = useState(true);

  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { signOut } = useAuth();

  const normalizedSymbol = symbolInput.trim().toUpperCase();
  const isValidSymbol = SYMBOL_PATTERN.test(normalizedSymbol);

  const mutation = useMutation({
    mutationFn: (sym: string) => createResearchRun(sym),
    onSuccess: (data) => {
      setSelectedRun(data);
      setIsHistorical(false);
      queryClient.invalidateQueries({ queryKey: ['research-runs'] });
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
      <div className="rounded-xl border border-rose-500/40 bg-rose-950/30 p-6 text-rose-200">
        <div className="flex items-center gap-2 font-semibold text-rose-100 text-base mb-2">
          <span>Failed to complete research run</span>
        </div>
        <p className="text-sm leading-relaxed text-rose-200/90">{message}</p>

        {(runId || requestId) && (
          <div className="mt-3 flex flex-wrap gap-4 text-xs font-mono text-rose-300/80">
            {runId && <span>Run ID: {runId}</span>}
            {requestId && <span>Request ID: {requestId}</span>}
          </div>
        )}

        <div className="mt-4 flex items-center gap-3">
          {isAuthError ? (
            <button
              onClick={handleSignOutAndAuth}
              className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold rounded-lg transition-colors"
            >
              Sign in again
            </button>
          ) : (
            <button
              onClick={handleRetry}
              disabled={mutation.isPending}
              className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white text-xs font-semibold rounded-lg border border-slate-700 transition-colors disabled:opacity-50"
            >
              Retry research
            </button>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="w-full max-w-7xl mx-auto px-4 sm:px-6 py-8 flex flex-col gap-8">
      {/* Search Header and Input */}
      <section className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 sm:p-8 backdrop-blur-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
              Vantage Research Workspace
            </h1>
            <p className="text-sm text-slate-400 mt-1">
              Deterministic, explainable US-equity end-of-day research analysis.
            </p>
          </div>

          <button
            onClick={() => setShowHistory(!showHistory)}
            className="self-start sm:self-auto px-4 py-2 text-xs font-medium rounded-lg border border-slate-700 bg-slate-800/80 text-slate-200 hover:bg-slate-800 transition-colors flex items-center gap-2"
          >
            <span>{showHistory ? 'Hide History' : 'View History'}</span>
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-3">
          <div className="flex-1 flex flex-col gap-1.5">
            <label htmlFor="symbol-input" className="text-xs font-medium text-slate-300">
              US equity symbol
            </label>
            <input
              id="symbol-input"
              type="text"
              value={symbolInput}
              onChange={(e) => setSymbolInput(e.target.value)}
              placeholder="e.g. AAPL, MSFT, NVDA"
              className="w-full bg-slate-950/60 border border-slate-700 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 rounded-lg px-4 py-3 text-white font-mono text-base placeholder:text-slate-600 transition-colors"
            />
          </div>

          <div className="flex items-end">
            <button
              type="submit"
              disabled={!isValidSymbol || mutation.isPending}
              className="w-full sm:w-auto px-8 py-3.5 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-sm rounded-lg transition-all shadow-lg shadow-indigo-500/20 disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none"
            >
              Run research
            </button>
          </div>
        </form>
      </section>

      {/* Main Workspace Layout with Optional History Drawer */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Results / Error Area */}
        <div className={showHistory ? 'lg:col-span-8 space-y-6' : 'lg:col-span-12 space-y-6'}>
          {mutation.isPending && (
            <div
              role="status"
              className="rounded-xl border border-indigo-500/30 bg-indigo-950/20 p-8 flex flex-col items-center justify-center gap-3 text-center"
            >
              <div className="w-8 h-8 rounded-full border-2 border-indigo-400 border-t-transparent animate-spin"></div>
              <p className="text-sm font-medium text-indigo-200">
                Running research analysis for {normalizedSymbol}...
              </p>
              <span className="text-xs text-slate-400">
                Verifying 21 trading sessions and fetching EOD snapshot
              </span>
            </div>
          )}

          {renderError()}

          {!mutation.isPending && !mutation.isError && selectedRun && (
            <ResearchResult run={selectedRun} historical={isHistorical} />
          )}

          {!mutation.isPending && !mutation.isError && !selectedRun && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/30 p-12 text-center text-slate-500">
              <p className="text-sm">Enter a US equity symbol above to begin an EOD research run.</p>
            </div>
          )}
        </div>

        {/* History Sidebar */}
        {showHistory && (
          <aside className="lg:col-span-4 rounded-xl border border-slate-800 bg-slate-900/80 p-6 backdrop-blur-sm">
            <div className="flex items-center justify-between mb-4 pb-2 border-b border-slate-800">
              <h2 className="text-base font-semibold text-white">Research History</h2>
              <span className="text-xs text-slate-400">Owner-scoped</span>
            </div>
            <ResearchHistory
              onSelectRun={(run) => {
                setSelectedRun(run);
                setIsHistorical(true);
              }}
              selectedRunId={selectedRun?.run_id}
            />
          </aside>
        )}
      </div>
    </div>
  );
}
