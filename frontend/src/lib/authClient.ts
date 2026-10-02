import type { SafeError } from '../types/research';
import type { AuthUser, TokenResponse } from '../types/auth';

const API_BASE_URL = (import.meta.env.VITE_API_URL as string) || '';
const AUTH_BASE = `${API_BASE_URL}/api/v1/auth`;

// The access token lives here and nowhere else. It is deliberately not in
// localStorage, sessionStorage, or a readable cookie: script-accessible storage
// turns any XSS into a stolen session. The refresh token is in an HttpOnly
// cookie the browser attaches automatically and JavaScript cannot read.
let accessToken: string | null = null;
let expiresAtMs = 0;

/**
 * What a refresh attempt established.
 *
 * - `refreshed`: a new access token is in memory.
 * - `unauthenticated`: the server rejected the session (401). Sign out.
 * - `unavailable`: the server could not be reached or failed (network error,
 *   5xx). The session may be perfectly valid; treating this as a sign-out
 *   would log an active user out on every network blip.
 */
export type RefreshOutcome = 'refreshed' | 'unauthenticated' | 'unavailable';

// One shared refresh per tab. Refresh tokens rotate on use, so two concurrent
// refreshes would present the same cookie twice and the second would be treated
// as token reuse, revoking the whole family. Tabs are serialised separately,
// through a Web Lock (see refreshSession).
let inFlightRefresh: Promise<RefreshOutcome> | null = null;

const REFRESH_LOCK = 'vantage-auth-refresh';

export class AuthApiError extends Error {
  code: string;
  status: number;
  retryable: boolean;

  constructor(status: number, error: SafeError) {
    super(error.message);
    this.name = 'AuthApiError';
    this.status = status;
    this.code = error.code;
    this.retryable = Boolean(error.retryable);
  }
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null, expiresIn = 0): void {
  accessToken = token;
  expiresAtMs = token ? Date.now() + expiresIn * 1000 : 0;
}

export function accessTokenExpiresAt(): number {
  return expiresAtMs;
}

async function authRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${AUTH_BASE}${path}`, {
    ...init,
    // Required for the refresh cookie to be sent and set.
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...init.headers },
  });

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    const detail = (body as { detail?: SafeError } | null)?.detail ?? {
      code: 'REQUEST_FAILED',
      message: response.statusText || 'Authentication request failed.',
      retryable: response.status >= 500,
    };
    throw new AuthApiError(response.status, detail);
  }

  return body as T;
}

export async function register(email: string, password: string): Promise<void> {
  await authRequest('/register', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}

export async function login(email: string, password: string): Promise<void> {
  const tokens = await authRequest<TokenResponse>('/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
  setAccessToken(tokens.access_token, tokens.expires_in);
}

async function performRefresh(): Promise<RefreshOutcome> {
  // A login can finish while this request is in flight. Only clear the token
  // if it is still the one this refresh started from; otherwise the late
  // failure describes a session that has already been replaced.
  const startedWith = accessToken;
  try {
    const tokens = await authRequest<TokenResponse>('/refresh', { method: 'POST' });
    setAccessToken(tokens.access_token, tokens.expires_in);
    return 'refreshed';
  } catch (error) {
    if (error instanceof AuthApiError && error.status === 401) {
      if (accessToken === startedWith) setAccessToken(null);
      return 'unauthenticated';
    }
    return 'unavailable';
  }
}

export function refreshSession(): Promise<RefreshOutcome> {
  if (inFlightRefresh) return inFlightRefresh;

  // Every tab shares one rotating refresh cookie. Without cross-tab
  // serialisation, two tabs refreshing together present the same cookie twice
  // and the server revokes the whole session. Web Locks queue the second tab
  // until the first has stored the rotated cookie.
  const locks = typeof navigator !== 'undefined' ? navigator.locks : undefined;
  const run = locks?.request
    ? () =>
        locks.request(REFRESH_LOCK, { mode: 'exclusive' }, () => performRefresh()) as Promise<RefreshOutcome>
    : performRefresh;

  inFlightRefresh = run().finally(() => {
    inFlightRefresh = null;
  });
  return inFlightRefresh;
}

/** Boolean form for callers that only need "do I have a usable token now?". */
export async function refresh(): Promise<boolean> {
  return (await refreshSession()) === 'refreshed';
}

export async function logout(): Promise<void> {
  try {
    await authRequest('/logout', { method: 'POST' });
  } catch {
    // The server may be unreachable. Local state must still be cleared, or the
    // UI would keep showing a signed-in user with a token it cannot use.
  } finally {
    setAccessToken(null);
  }
}

export function fetchMe(): Promise<AuthUser> {
  return authRequest<AuthUser>('/me', {
    method: 'GET',
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
  });
}
