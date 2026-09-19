import { useState, useEffect, useRef } from 'react';
import { useMutation, useQuery, useQueryClient, useInfiniteQuery } from '@tanstack/react-query';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import { createResearchRun, listResearchRuns, getResearchRun } from '../../api/researchRuns';
import { useAuth } from '../../context/AuthContext';
import type { ResearchRun } from '../../types/research';
import ResearchResult from './ResearchResult';
import ResearchHistory from './ResearchHistory';
import ResearchError from './ResearchError';
import { buildStatusStrip, recentSymbols } from './runChrome';
import { MicroLabel, Drawer } from '../../components/ui';

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
  const [showHistory, setShowHistory] = useState(false);

  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { signOut } = useAuth();

  useEffect(() => {
    setShowHistory(false);
  }, [pathname]);

  const { data: routeRun } = useQuery({
    queryKey: ['research-run', runId],
    queryFn: () => getResearchRun(runId!),
    enabled: Boolean(runId),
  });

  const selectedRun: ResearchRun | null = routeRun ?? null;
  const isHistorical = Boolean(runId) && runId !== liveRunId;

  const { data: historyData } = useInfiniteQuery({
    queryKey: ['research-runs', ownerId],
    queryFn: ({ pageParam }) => listResearchRuns(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage?.next_cursor ?? undefined,
    enabled: ownerId !== null,
    staleTime: 30_000,
  });

  const allRuns = historyData?.pages.flatMap((page) => page.items) ?? [];
  const recent = recentSymbols(allRuns);

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


  return (
    <div className="w-full max-w-5xl mx-auto px-6 flex flex-col gap-12">
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

        {mutation.isError && (
          <ResearchError
            error={mutation.error}
            onRetry={handleRetry}
            onReauth={handleSignOutAndAuth}
            retrying={mutation.isPending}
          />
        )}

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
      <Drawer open={showHistory} onClose={() => setShowHistory(false)} title="Research History">
        <ResearchHistory />
      </Drawer>
    </div>
  );
}
