import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getAccessToken, refreshSession, setAccessToken } from './authClient';

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

const tokens = { access_token: 'fresh', token_type: 'bearer', expires_in: 900 };

beforeEach(() => {
  setAccessToken(null);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('refreshSession outcomes', () => {
  it('reports refreshed and stores the new token', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(tokens));
    expect(await refreshSession()).toBe('refreshed');
    expect(getAccessToken()).toBe('fresh');
  });

  it('reports unauthenticated on 401 and clears the token', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json({ detail: { code: 'AUTH_INVALID', message: 'x', retryable: false } }, 401)
    );
    setAccessToken('stale', 900);
    expect(await refreshSession()).toBe('unauthenticated');
    expect(getAccessToken()).toBeNull();
  });

  it('reports unavailable on a network failure and keeps the token', async () => {
    // A blip is not a sign-out: the access token and refresh cookie may both
    // still be valid.
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));
    setAccessToken('still-valid', 900);
    expect(await refreshSession()).toBe('unavailable');
    expect(getAccessToken()).toBe('still-valid');
  });

  it('reports unavailable on a server error and keeps the token', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json({ detail: { code: 'EXTERNAL_SERVICE_UNAVAILABLE', message: 'x', retryable: true } }, 503)
    );
    setAccessToken('still-valid', 900);
    expect(await refreshSession()).toBe('unavailable');
    expect(getAccessToken()).toBe('still-valid');
  });
});

describe('a refresh racing a login', () => {
  it('does not erase a token stored by a login that finished first', async () => {
    // A mount-time refresh can still be in flight when the user signs in. Its
    // late 401 describes the old, cookieless state and must not wipe the
    // token the login just stored.
    let resolveFetch: (r: Response) => void = () => {};
    vi.spyOn(globalThis, 'fetch').mockReturnValue(
      new Promise<Response>((resolve) => {
        resolveFetch = resolve;
      })
    );

    const pending = refreshSession();
    setAccessToken('from-login', 900);
    resolveFetch(json({ detail: { code: 'AUTH_REQUIRED', message: 'x', retryable: false } }, 401));

    await pending;
    expect(getAccessToken()).toBe('from-login');
  });
});

describe('refreshing across tabs', () => {
  it('serialises refreshes through a named Web Lock when the browser has one', async () => {
    // Every tab shares one refresh cookie, and it rotates on each use. Two
    // tabs refreshing at once would present the same cookie twice and the
    // server would revoke the whole session. A cross-tab lock prevents it.
    const request = vi.fn(async (_name: string, _opts: unknown, run: () => Promise<unknown>) => run());
    vi.stubGlobal('navigator', { ...navigator, locks: { request } });
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(tokens));

    expect(await refreshSession()).toBe('refreshed');
    expect(request).toHaveBeenCalledTimes(1);
    expect(request.mock.calls[0][0]).toBe('vantage-auth-refresh');
    expect(request.mock.calls[0][1]).toMatchObject({ mode: 'exclusive' });
  });

  it('still refreshes in browsers without Web Locks', async () => {
    vi.stubGlobal('navigator', { ...navigator, locks: undefined });
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(tokens));
    expect(await refreshSession()).toBe('refreshed');
  });
});
