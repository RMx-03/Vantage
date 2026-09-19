import { ApiError } from '../../api/researchRuns';

export interface ResearchErrorView {
  message: string;
  isAuthError: boolean;
  runId: string | null;
  requestId: string | null;
}

const FALLBACK = 'Research run could not be completed. Please try again later.';

export function mapResearchError(err: unknown): ResearchErrorView {
  if (err instanceof ApiError) {
    const runId = err.error.run_id ?? null;
    const requestId = err.error.request_id ?? null;

    if (err.status === 401) {
      return {
        message: 'Your session has expired. Please sign in again.',
        isAuthError: true,
        runId,
        requestId,
      };
    }

    if (err.status === 503 || err.error.code === 'MARKET_DATA_FAILED') {
      return {
        message:
          'Market data could not be retrieved. Please check the symbol and market hours, then retry.',
        isAuthError: false,
        runId,
        requestId,
      };
    }

    return {
      message: err.error.message || FALLBACK,
      isAuthError: false,
      runId,
      requestId,
    };
  }

  if (err instanceof Error) {
    return { message: err.message || FALLBACK, isAuthError: false, runId: null, requestId: null };
  }

  return { message: FALLBACK, isAuthError: false, runId: null, requestId: null };
}
