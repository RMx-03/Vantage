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

  it('marks an explicitly non-retryable error as not retryable', () => {
    const view = mapResearchError(
      new ApiError(400, {
        code: 'UNSUPPORTED_INSTRUMENT',
        message: 'Only US equities are supported.',
        retryable: false,
      })
    );
    expect(view.isAuthError).toBe(false);
    expect(view.canRetry).toBe(false);
  });

  it('keeps a retryable error retryable', () => {
    const view = mapResearchError(
      new ApiError(503, { code: 'MARKET_DATA_FAILED', message: 'x', retryable: true })
    );
    expect(view.canRetry).toBe(true);
  });

  it('allows retry when the server states no retryability', () => {
    const view = mapResearchError(new ApiError(500, { code: 'X', message: 'boom' }));
    expect(view.canRetry).toBe(true);
  });

  it('allows retry for a transport error with no typed payload', () => {
    expect(mapResearchError(new Error('socket hang up')).canRetry).toBe(true);
    expect(mapResearchError('weird').canRetry).toBe(true);
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
