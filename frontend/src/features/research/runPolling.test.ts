import { describe, expect, it } from 'vitest';
import {
  POLL_FAST_MS,
  POLL_SLOW_MS,
  isPollingExhausted,
  runPollInterval,
} from './runPolling';
import { informationalRun } from '../../test/fixtures';
import type { ResearchRun } from '../../types/research';

const running: ResearchRun = { ...informationalRun, workflow_status: 'running' };
const failed: ResearchRun = { ...informationalRun, workflow_status: 'failed' };

describe('runPollInterval', () => {
  it('polls fast for the first ten updates', () => {
    expect(runPollInterval(running, 1)).toBe(POLL_FAST_MS);
    expect(runPollInterval(running, 10)).toBe(POLL_FAST_MS);
  });

  it('slows down from the eleventh update to the eightieth', () => {
    expect(runPollInterval(running, 11)).toBe(POLL_SLOW_MS);
    expect(runPollInterval(running, 80)).toBe(POLL_SLOW_MS);
  });

  it('stops after the eightieth update', () => {
    expect(runPollInterval(running, 81)).toBe(false);
  });

  it('stops for terminal or missing runs', () => {
    expect(runPollInterval(informationalRun, 1)).toBe(false);
    expect(runPollInterval(failed, 1)).toBe(false);
    expect(runPollInterval(undefined, 1)).toBe(false);
  });
});

describe('isPollingExhausted', () => {
  it('is true only for a running run past the limit', () => {
    expect(isPollingExhausted(running, 81)).toBe(true);
    expect(isPollingExhausted(running, 80)).toBe(false);
    expect(isPollingExhausted(informationalRun, 81)).toBe(false);
    expect(isPollingExhausted(undefined, 81)).toBe(false);
  });
});
