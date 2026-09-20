import { supabase } from '../lib/supabase';
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

const API_BASE_URL =
  (import.meta.env.VITE_API_URL as string) ||
  (import.meta.env.VITE_API_BASE_URL as string) ||
  '';

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) {
    throw new ApiError(401, {
      code: 'AUTH_REQUIRED',
      message: 'Your session has expired.',
      retryable: false,
    });
  }

  const response = await fetch(`${API_BASE_URL}/api/v1${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${session.access_token}`,
      ...init.headers,
    },
  });

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
      message: response.statusText || 'An error occurred while communicating with the server.',
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
