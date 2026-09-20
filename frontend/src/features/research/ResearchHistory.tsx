import { Link, useParams } from 'react-router-dom';
import { useInfiniteQuery } from '@tanstack/react-query';
import { listResearchRuns } from '../../api/researchRuns';
import { useAuth } from '../../context/AuthContext';
import { formatUtcDate } from './dateFormatters';
import { StatusChip } from '../../components/ui';

interface ResearchHistoryProps {
  onNavigate?: () => void;
}

export default function ResearchHistory({
  onNavigate,
}: ResearchHistoryProps = {}) {
  const { runId } = useParams<{ runId?: string }>();
  const { user } = useAuth();
  const ownerId = user?.id ?? null;

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
    // Scoped to the owner so one user's history can never be read from the
    // cache by the next user signed into the same browser session.
    queryKey: ['research-runs', ownerId],
    queryFn: ({ pageParam }) => listResearchRuns(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: ownerId !== null,
    staleTime: 30_000,
  });

  const runs = data?.pages.flatMap((page) => page.items) ?? [];

  if (ownerId === null || isLoading) {
    return (
      <div className="flex items-center justify-center p-8 text-sm text-outline font-label">
        <span className="animate-pulse">Loading research history...</span>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="p-4 border border-error-container bg-error-container/30 text-error text-sm font-label">
        <p className="font-medium">Failed to load research history.</p>
        <p className="text-xs text-error mt-1">
          {error instanceof Error ? error.message : 'An error occurred while fetching runs.'}
        </p>
        <button
          onClick={() => refetch()}
          className="mt-3 text-xs bg-surface-container hover:bg-surface-container-highest px-3 py-1.5 border border-outline-variant transition-colors text-on-surface uppercase tracking-widest font-bold"
        >
          Try again
        </button>
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div className="p-8 text-center text-sm text-outline font-label">
        No previous research runs found.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="space-y-2">
        {runs.map((run) => {
          const formattedDate = formatUtcDate(run.as_of || run.created_at);
          const isSelected = runId === run.run_id;
          const accessibleName = `${run.symbol} - ${formattedDate}`;

          return (
            <Link
              key={run.run_id}
              to={`/app/research/${run.run_id}`}
              onClick={onNavigate}
              aria-label={accessibleName}
              aria-current={isSelected ? 'true' : undefined}
              className={`w-full text-left p-4 border transition-colors flex flex-col gap-1.5 ${
                isSelected
                  ? 'border-primary bg-surface-container-highest text-on-surface'
                  : 'border-outline-variant/30 bg-surface-container-low hover:border-outline-variant hover:bg-surface-container text-on-surface-variant'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-label font-bold text-base tracking-tight text-on-surface">
                  {run.symbol}
                </span>
                <span className="text-xs text-outline font-label">{formattedDate}</span>
              </div>

              <div className="flex items-center justify-between text-xs gap-2 pt-1 border-t border-outline-variant/30">
                <StatusChip
                  status={run.research_status ?? (run.workflow_status === 'failed' ? 'failed' : 'unknown')}
                  label={run.research_status ?? run.workflow_status}
                />

                <span className="text-[10px] font-label text-outline">
                  {run.run_id.slice(0, 8)}...
                </span>
              </div>
            </Link>
          );
        })}
      </div>

      {hasNextPage && (
        <button
          onClick={() => fetchNextPage()}
          disabled={isFetchingNextPage}
          className="w-full py-2.5 px-4 text-xs font-medium text-on-surface-variant bg-surface-container-low hover:bg-surface-container border border-outline-variant/30 hover:border-outline-variant transition-colors disabled:opacity-50 font-label uppercase tracking-widest"
        >
          {isFetchingNextPage ? 'Loading more...' : 'Load more'}
        </button>
      )}
    </div>
  );
}
