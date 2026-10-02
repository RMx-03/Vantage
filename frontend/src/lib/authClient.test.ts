import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  getAccessToken,
  login,
  logout,
  refresh,
  setAccessToken,
} from './authClient';

const okJson = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

beforeEach(() => {
  setAccessToken(null);
  localStorage.clear();
  sessionStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('token storage', () => {
  it('holds the access token in memory', () => {
    setAccessToken('abc', 900);
    expect(getAccessToken()).toBe('abc');
  });

  it('never writes the token to browser storage', () => {
    // An XSS that can read storage must not find a token there.
    setAccessToken('super-secret-token', 900);
    expect(JSON.stringify(localStorage)).not.toContain('super-secret-token');
    expect(JSON.stringify(sessionStorage)).not.toContain('super-secret-token');
    expect(document.cookie).not.toContain('super-secret-token');
  });

  it('clears the token', () => {
    setAccessToken('abc', 900);
    setAccessToken(null);
    expect(getAccessToken()).toBeNull();
  });
});

describe('login', () => {
  it('stores the returned access token', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      okJson({ access_token: 'tok', token_type: 'bearer', expires_in: 900 })
    );
    await login('user@example.com', 'correct horse battery staple');
    expect(getAccessToken()).toBe('tok');
  });

  it('sends credentials so the refresh cookie is set', async () => {
    const spy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(okJson({ access_token: 't', token_type: 'bearer', expires_in: 900 }));
    await login('user@example.com', 'correct horse battery staple');
    const init = spy.mock.calls[0][1] as RequestInit;
    expect(init.credentials).toBe('include');
  });

  it('throws a typed error carrying the safe error code', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      okJson({ detail: { code: 'AUTH_INVALID', message: 'Nope', retryable: false } }, 401)
    );
    await expect(login('user@example.com', 'wrong password here')).rejects.toMatchObject({
      code: 'AUTH_INVALID',
    });
  });
});

describe('refresh', () => {
  it('returns true and stores a token on success', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      okJson({ access_token: 'fresh', token_type: 'bearer', expires_in: 900 })
    );
    expect(await refresh()).toBe(true);
    expect(getAccessToken()).toBe('fresh');
  });

  it('returns false and clears the token when the cookie is dead', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      okJson({ detail: { code: 'AUTH_REQUIRED', message: 'no', retryable: false } }, 401)
    );
    setAccessToken('stale', 900);
    expect(await refresh()).toBe(false);
    expect(getAccessToken()).toBeNull();
  });

  it('shares one in-flight request across concurrent callers', async () => {
    // Refresh tokens rotate. Two parallel refreshes would consume the same
    // cookie twice, trip reuse detection, and sign the user out.
    let resolveFetch: (r: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => {
      resolveFetch = resolve;
    });
    const spy = vi.spyOn(globalThis, 'fetch').mockReturnValue(pending);

    const all = Promise.all([refresh(), refresh(), refresh()]);
    resolveFetch(okJson({ access_token: 'one', token_type: 'bearer', expires_in: 900 }));
    const results = await all;

    expect(spy).toHaveBeenCalledTimes(1);
    expect(results).toEqual([true, true, true]);
  });
});

describe('logout', () => {
  it('clears the token even if the request fails', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('offline'));
    setAccessToken('tok', 900);
    await logout();
    expect(getAccessToken()).toBeNull();
  });
});
