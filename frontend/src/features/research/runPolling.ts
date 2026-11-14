import type { ResearchRun } from '../../types/research';

export const POLL_FAST_MS = 1000;
export const POLL_SLOW_MS = 2000;
export const POLL_FAST_COUNT = 10;
export const POLL_MAX_COUNT = 80;

/**
 * Refetch interval for a run that may still be executing server-side.
 * `updateCount` is the query's successful-update count, so the schedule is
 * ten 1 s polls, then 2 s polls up to the eightieth (about 150 s in total).
 */
export function runPollInterval(
  run: ResearchRun | undefined,
  updateCount: number
): number | false {
  if (!run || run.workflow_status !== 'running') return false;
  if (updateCount > POLL_MAX_COUNT) return false;
  return updateCount <= POLL_FAST_COUNT ? POLL_FAST_MS : POLL_SLOW_MS;
}

export function isPollingExhausted(
  run: ResearchRun | undefined,
  updateCount: number
): boolean {
  return run?.workflow_status === 'running' && updateCount > POLL_MAX_COUNT;
}
