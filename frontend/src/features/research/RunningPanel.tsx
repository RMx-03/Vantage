import { useEffect, useState } from 'react';
import type { ResearchRun } from '../../types/research';

function elapsedSeconds(createdAt: string): number {
  const started = Date.parse(createdAt);
  if (Number.isNaN(started)) return 0;
  return Math.max(0, Math.floor((Date.now() - started) / 1000));
}

export default function RunningPanel({
  run,
  exhausted,
  onCheckAgain,
}: {
  run: ResearchRun;
  exhausted: boolean;
  onCheckAgain: () => void;
}) {
  const [elapsed, setElapsed] = useState(() => elapsedSeconds(run.created_at));

  useEffect(() => {
    const id = setInterval(() => setElapsed(elapsedSeconds(run.created_at)), 1000);
    return () => clearInterval(id);
  }, [run.created_at]);

  return (
    <div role="status" className="flex flex-col gap-2 py-4">
      <div className="flex items-center gap-4">
        <div className="w-2 h-2 bg-primary animate-pulse" />
        <p className="text-outline text-xs font-label uppercase tracking-[0.2em] animate-pulse">
          Running research analysis for {run.symbol}…
        </p>
      </div>
      <span className="text-xs font-label text-outline pl-6">
        Fetching the EOD snapshot, news evidence, and interpretation
      </span>
      <span className="text-xs font-label text-outline pl-6">{elapsed}s elapsed</span>
      {exhausted && (
        <div className="pl-6 flex flex-col gap-2 items-start">
          <p className="text-xs font-label text-on-surface-variant">
            This run is taking longer than expected. It will appear in your history when it
            finishes.
          </p>
          <button
            type="button"
            onClick={onCheckAgain}
            className="px-4 py-2 bg-surface-container hover:bg-surface-container-highest text-on-surface text-xs font-bold font-label uppercase tracking-widest border border-outline-variant transition-colors"
          >
            Check again
          </button>
        </div>
      )}
    </div>
  );
}
