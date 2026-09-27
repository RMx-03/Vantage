import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as authClient from '../lib/authClient';
import { informationalRun } from '../test/fixtures';
import {
  ApiError,
  createResearchRun,
  getResearchRun,
  listResearchRuns,
} from './researchRuns';

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

afterEach(() => {
  vi.restoreAllMocks();
  authClient.setAccessToken(null);
});

describe('research-runs API client', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authClient.setAccessToken('access-token', 900);
  });

  it('normalizes a symbol and sends the bearer token', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(informationalRun), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      })
    );
    await expect(createResearchRun(' aapl ')).resolves.toEqual(informationalRun);
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/v1\/research-runs$/),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ symbol: 'AAPL' }),
        headers: expect.objectContaining({ Authorization: 'Bearer access-token' }),
      })
    );
  });

  it('preserves the typed safe error returned by the API', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          detail: {
            code: 'INVALID_CURSOR',
            message: 'The history cursor is invalid.',
            retryable: false,
          },
        }),
        { status: 400, headers: { 'Content-Type': 'application/json' } }
      )
    );
    await expect(listResearchRuns('bad cursor')).rejects.toEqual(
      new ApiError(400, {
        code: 'INVALID_CURSOR',
        message: 'The history cursor is invalid.',
        retryable: false,
      })
    );
  });

  it('uses a generic safe error when the response is not JSON', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response('gateway response', { status: 502, statusText: 'Bad Gateway' })
    );
    await expect(getResearchRun('run-id')).rejects.toMatchObject({
      status: 502,
      error: {
        code: 'REQUEST_FAILED',
        message: 'Bad Gateway',
        retryable: true,
      },
    });
  });

  it('uses the default safe message when a failed response has no status text', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response('', { status: 500, statusText: '' })
    );

    await expect(getResearchRun('run-id')).rejects.toMatchObject({
      status: 500,
      error: {
        code: 'REQUEST_FAILED',
        message: 'An error occurred while communicating with the server.',
        retryable: true,
      },
    });
  });

  it('encodes pagination cursors', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ items: [], next_cursor: null }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    );
    await listResearchRuns('a cursor/+');
    expect(fetchSpy.mock.calls[0][0]).toContain('before=a%20cursor%2F%2B');
  });
});

describe('authenticated requests', () => {
  it('sends the in-memory access token as a bearer header', async () => {
    authClient.setAccessToken('tok-123', 900);
    const spy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(json({ items: [], next_before: null }));

    await listResearchRuns();

    const init = spy.mock.calls[0][1] as RequestInit;
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer tok-123');
  });

  it('fails fast with AUTH_REQUIRED when there is no token and refresh fails', async () => {
    vi.spyOn(authClient, 'refresh').mockResolvedValue(false);
    await expect(listResearchRuns()).rejects.toMatchObject({
      error: { code: 'AUTH_REQUIRED' },
    });
  });

  it('refreshes once on 401 and retries the request', async () => {
    authClient.setAccessToken('stale', 900);
    const refreshSpy = vi.spyOn(authClient, 'refresh').mockImplementation(async () => {
      authClient.setAccessToken('fresh', 900);
      return true;
    });
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        json({ detail: { code: 'AUTH_TOKEN_EXPIRED', message: 'x', retryable: false } }, 401)
      )
      .mockResolvedValueOnce(json({ items: [], next_before: null }));

    await listResearchRuns();

    expect(refreshSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    const retry = fetchSpy.mock.calls[1][1] as RequestInit;
    expect(new Headers(retry.headers).get('Authorization')).toBe('Bearer fresh');
  });

  it('does not retry more than once', async () => {
    // A retry loop against a permanently 401ing API would hammer the server.
    authClient.setAccessToken('stale', 900);
    vi.spyOn(authClient, 'refresh').mockResolvedValue(true);
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        json({ detail: { code: 'AUTH_INVALID', message: 'x', retryable: false } }, 401)
      );

    await expect(listResearchRuns()).rejects.toBeInstanceOf(ApiError);
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });
});
