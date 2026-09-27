import { getAccessToken, refresh } from '../lib/authClient';
import type { ResearchRun, ResearchRunPage, SafeError } from '../types/research';

export class ApiError extends Error {
  status: number;
  error: SafeError;

  constructor(status: number, error: SafeError) {
    super(error.message);
    this.status = status;
    this.error = error;
    this.name = 'ApiError';
  }
}

const API_BASE_URL = (import.meta.env.VITE_API_URL as string) || '';

const AUTH_REQUIRED: SafeError = {
  code: 'AUTH_REQUIRED',
  message: 'Your session has expired.',
  retryable: false,
};

async function send(path: string, init: RequestInit, token: string): Promise<Response> {
  return fetch(`${API_BASE_URL}/api/v1${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...init.headers,
    },
  });
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let token = getAccessToken();

  if (!token) {
    // No token in memory — a fresh page load, or one that expired. The refresh
    // cookie may still be good.
    if (!(await refresh())) throw new ApiError(401, AUTH_REQUIRED);
    token = getAccessToken();
    if (!token) throw new ApiError(401, AUTH_REQUIRED);
  }

  let response = await send(path, init, token);

  // Exactly one retry. `refresh` is single-flight, so parallel 401s share one
  // rotation rather than racing and tripping reuse detection.
  if (response.status === 401) {
    if (!(await refresh())) throw new ApiError(401, AUTH_REQUIRED);
    const retryToken = getAccessToken();
    if (!retryToken) throw new ApiError(401, AUTH_REQUIRED);
    response = await send(path, init, retryToken);
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    const errorBody = body as { detail?: SafeError } | null;
    const errorDetail: SafeError = errorBody?.detail ?? {
      code: 'REQUEST_FAILED',
      message:
        response.statusText || 'An error occurred while communicating with the server.',
      retryable: response.status >= 500,
    };
    throw new ApiError(response.status, errorDetail);
  }

  return body as T;
}

export const createResearchRun = (symbol: string): Promise<ResearchRun> =>
  request<ResearchRun>('/research-runs', {
    method: 'POST',
    body: JSON.stringify({ symbol: symbol.trim().toUpperCase() }),
  });

export const getResearchRun = (id: string): Promise<ResearchRun> =>
  request<ResearchRun>(`/research-runs/${id}`);

export const listResearchRuns = (before?: string): Promise<ResearchRunPage> =>
  request<ResearchRunPage>(
    `/research-runs?limit=20${before ? `&before=${encodeURIComponent(before)}` : ''}`
  );
