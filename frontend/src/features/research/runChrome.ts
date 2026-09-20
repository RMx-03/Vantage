import type { ResearchRun } from '../../types/research';
import { formatUtcDate } from './dateFormatters';

export function formatRunDuration(run: ResearchRun): string | null {
  if (!run.completed_at) return null;
  const ms = Date.parse(run.completed_at) - Date.parse(run.created_at);
  if (!Number.isFinite(ms) || ms < 0) return null;
  return `${(ms / 1000).toFixed(2)}S`;
}

export function buildStatusStrip(run: ResearchRun | null): string | null {
  if (!run) return null;

  const parts: string[] = [];
  const duration = formatRunDuration(run);
  if (duration) parts.push(`RUN ${duration}`);
  if (run.as_of) parts.push(`AS OF ${formatUtcDate(run.as_of).toUpperCase()}`);
  if (run.versions?.workflow) {
    parts.push(`WORKFLOW ${run.versions.workflow.toUpperCase()}`);
  }

  return parts.length > 0 ? parts.join('  ·  ') : null;
}

export function recentSymbols(runs: ResearchRun[], limit = 3): string[] {
  const seen: string[] = [];
  for (const run of runs) {
    if (!seen.includes(run.symbol)) seen.push(run.symbol);
    if (seen.length === limit) break;
  }
  return seen;
}
