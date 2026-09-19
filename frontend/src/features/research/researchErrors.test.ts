import { describe, it, expect } from 'vitest';
import { mapResearchError } from './researchErrors';
import { ApiError } from '../../api/researchRuns';

describe('mapResearchError', () => {
  it('flags 401 as an auth error', () => {
    const view = mapResearchError(
      new ApiError(401, { code: 'AUTH_REQUIRED', message: 'nope' })
    );
    expect(view.isAuthError).toBe(true);
    expect(view.message).toMatch(/session has expired/i);
  });

  it('explains a 503 market-data failure', () => {
    const view = mapResearchError(
      new ApiError(503, { code: 'MARKET_DATA_FAILED', message: 'upstream' })
    );
    expect(view.isAuthError).toBe(false);
    expect(view.message).toMatch(/market data could not be retrieved/i);
  });

  it('maps MARKET_DATA_FAILED regardless of status', () => {
    const view = mapResearchError(
      new ApiError(500, { code: 'MARKET_DATA_FAILED', message: 'upstream' })
    );
    expect(view.message).toMatch(/market data could not be retrieved/i);
  });

  it('surfaces correlation ids when present', () => {
    const view = mapResearchError(
      new ApiError(500, {
        code: 'X',
        message: 'boom',
        run_id: 'run-1',
        request_id: 'req-1',
      })
    );
    expect(view.runId).toBe('run-1');
    expect(view.requestId).toBe('req-1');
  });

  it('falls back safely for a non-ApiError', () => {
    const view = mapResearchError(new Error('socket hang up'));
    expect(view.message).toBe('socket hang up');
    expect(view.runId).toBeNull();
  });

  it('falls back safely for a non-Error', () => {
    const view = mapResearchError('weird');
    expect(view.message).toMatch(/could not be completed/i);
  });
});
