import { describe, it, expect } from 'vitest';
import { formatRunDuration, buildStatusStrip, recentSymbols } from './runChrome';
import type { ResearchRun } from '../../types/research';

const run = (over: Partial<ResearchRun>): ResearchRun =>
  ({
    run_id: 'r1',
    symbol: 'AAPL',
    created_at: '2026-09-19T20:00:00.000Z',
    completed_at: '2026-09-19T20:00:01.840Z',
    as_of: '2026-09-19T00:00:00.000Z',
    workflow_status: 'succeeded',
    research_status: 'informational',
    versions: { workflow: 'eod-workflow-v1' },
    ...over,
  }) as ResearchRun;

describe('runChrome', () => {
  it('formats a real run duration in seconds', () => {
    expect(formatRunDuration(run({}))).toBe('1.84S');
  });

  it('returns null when the run has not completed', () => {
    expect(formatRunDuration(run({ completed_at: null }))).toBeNull();
  });

  it('builds a strip with run, as-of and workflow version', () => {
    const strip = buildStatusStrip(run({}))!;
    expect(strip).toContain('RUN 1.84S');
    expect(strip).toContain('EOD-WORKFLOW-V1');
  });

  it('never emits fabricated latency or node counts', () => {
    const strip = buildStatusStrip(run({}))!;
    expect(strip).not.toMatch(/latency:\s*\d+ms/i);
    expect(strip).not.toMatch(/nodes active/i);
  });

  it('returns null when there is no run', () => {
    expect(buildStatusStrip(null)).toBeNull();
  });

  it('lists distinct recent symbols newest first', () => {
    const runs = [
      run({ symbol: 'AAPL' }),
      run({ symbol: 'MSFT' }),
      run({ symbol: 'AAPL' }),
      run({ symbol: 'NVDA' }),
      run({ symbol: 'TSLA' }),
    ];
    expect(recentSymbols(runs, 3)).toEqual(['AAPL', 'MSFT', 'NVDA']);
  });
});
