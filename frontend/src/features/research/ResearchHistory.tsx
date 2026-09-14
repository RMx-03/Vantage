import { useInfiniteQuery } from '@tanstack/react-query';
import { listResearchRuns } from '../../api/researchRuns';
import type { ResearchRun } from '../../types/research';

interface ResearchHistoryProps {
  onSelectRun?: (run: ResearchRun) => void;
  selectedRunId?: string;
}

export default function ResearchHistory({
  onSelectRun,
  selectedRunId,
}: ResearchHistoryProps) {
  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
    isError,
    error,
    refetch,
  } = useInfiniteQuery({
    queryKey: ['research-runs'],
    queryFn: ({ pageParam }) => listResearchRuns(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });

  const runs = data?.pages.flatMap((page) => page.items) ?? [];

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8 text-sm text-slate-400">
        <span className="animate-pulse">Loading research history...</span>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="p-4 rounded-lg border border-rose-500/30 bg-rose-950/20 text-rose-300 text-sm">
        <p className="font-medium">Failed to load research history.</p>
        <p className="text-xs text-rose-400 mt-1">
          {error instanceof Error ? error.message : 'An error occurred while fetching runs.'}
        </p>
        <button
          onClick={() => refetch()}
          className="mt-3 text-xs bg-slate-800 hover:bg-slate-700 px-3 py-1.5 rounded border border-slate-700 transition-colors"
        >
          Try again
        </button>
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div className="p-8 text-center text-sm text-slate-500">
        No previous research runs found.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="space-y-2">
        {runs.map((run) => {
          const formattedDate = new Date(run.as_of || run.created_at).toLocaleDateString(
            'en-US',
            { timeZone: 'UTC', month: 'short', day: 'numeric', year: 'numeric' }
          );
          const isSelected = selectedRunId === run.run_id;
          const accessibleName = `${run.symbol} - ${formattedDate}`;

          return (
            <button
              key={run.run_id}
              onClick={() => onSelectRun?.(run)}
              aria-label={accessibleName}
              aria-current={isSelected ? 'true' : undefined}
              className={`w-full text-left p-3.5 rounded-lg border transition-all flex flex-col gap-1.5 ${
                isSelected
                  ? 'border-indigo-500 bg-indigo-950/40 text-white'
                  : 'border-slate-800 bg-slate-900/40 hover:border-slate-700 hover:bg-slate-900/80 text-slate-200'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono font-bold text-base tracking-tight">
                  {run.symbol}
                </span>
                <span className="text-xs text-slate-400">{formattedDate}</span>
              </div>

              <div className="flex items-center justify-between text-xs gap-2 pt-1 border-t border-slate-800/40">
                <span
                  className={`capitalize text-[11px] px-2 py-0.5 rounded border font-medium ${
                    run.research_status === 'informational'
                      ? 'border-slate-600 bg-slate-800 text-slate-300'
                      : run.research_status === 'review'
                        ? 'border-amber-500/40 bg-amber-500/20 text-amber-300'
                        : 'border-rose-500/40 bg-rose-500/20 text-rose-300'
                  }`}
                >
                  {run.research_status ?? run.workflow_status}
                </span>

                <span className="text-[10px] font-mono text-slate-500">
                  {run.run_id.slice(0, 8)}...
                </span>
              </div>
            </button>
          );
        })}
      </div>

      {hasNextPage && (
        <button
          onClick={() => fetchNextPage()}
          disabled={isFetchingNextPage}
          className="w-full py-2.5 px-4 text-xs font-medium text-slate-300 bg-slate-900/80 hover:bg-slate-800 rounded-lg border border-slate-800 transition-colors disabled:opacity-50"
        >
          {isFetchingNextPage ? 'Loading more...' : 'Load more'}
        </button>
      )}
    </div>
  );
}
