import { useState, useEffect, useRef } from 'react';
import { useMutation, useQuery, useQueryClient, useInfiniteQuery } from '@tanstack/react-query';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import { createResearchRun, listResearchRuns, getResearchRun } from '../../api/researchRuns';
import { useAuth } from '../../context/AuthContext';
import type { ResearchRun } from '../../types/research';
import ResearchResult from './ResearchResult';
import ResearchHistory from './ResearchHistory';
import ResearchError from './ResearchError';
import SymbolSearchForm from './SymbolSearchForm';
import ResearchStatusStrip from './ResearchStatusStrip';
import { recentSymbols } from './runChrome';
import { Drawer } from '../../components/ui';

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

  const [prevPathname, setPrevPathname] = useState(pathname);

  const { data: routeRun } = useQuery({
    queryKey: ['research-run', ownerId, runId],
    queryFn: () => getResearchRun(runId!),
    enabled: ownerId !== null && Boolean(runId),
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
      queryClient.setQueryData(['research-run', ownerId, data.run_id], data);
      queryClient.invalidateQueries({ queryKey: ['research-runs', ownerId] });
      navigate(`/app/research/${data.run_id}`, { replace: true });
    },
  });

  if (prevPathname !== pathname) {
    setPrevPathname(pathname);
    setShowHistory(false);
    if (mutation.isError) {
      mutation.reset();
    }
  }

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

        <SymbolSearchForm
          value={symbolInput}
          onChange={setSymbolInput}
          onSubmit={handleSubmit}
          recent={recent}
          onPickRecent={setSymbolInput}
          submitting={mutation.isPending}
          valid={isValidSymbol}
        />
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

      <ResearchStatusStrip run={selectedRun} />

      {/* Slide-over History Drawer */}
      <Drawer open={showHistory} onClose={() => setShowHistory(false)} title="Research History">
        <div onClick={() => setShowHistory(false)}>
          <ResearchHistory />
        </div>
      </Drawer>
    </div>
  );
}
