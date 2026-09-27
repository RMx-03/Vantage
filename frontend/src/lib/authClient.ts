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

// A single shared refresh promise. Refresh tokens rotate on use, so two
// concurrent refreshes would present the same cookie twice and the second
// would be treated as token reuse, revoking the whole family.
let inFlightRefresh: Promise<boolean> | null = null;

export class AuthApiError extends Error {
  code: string;
  status: number;
  retryable: boolean;

  constructor(status: number, error: SafeError) {
    super(error.message);
    this.name = 'AuthApiError';
    this.status = status;
    this.code = error.code;
    this.retryable = error.retryable;
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

export function refresh(): Promise<boolean> {
  if (inFlightRefresh) return inFlightRefresh;

  inFlightRefresh = (async () => {
    try {
      const tokens = await authRequest<TokenResponse>('/refresh', { method: 'POST' });
      setAccessToken(tokens.access_token, tokens.expires_in);
      return true;
    } catch {
      setAccessToken(null);
      return false;
    } finally {
      inFlightRefresh = null;
    }
  })();

  return inFlightRefresh;
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
