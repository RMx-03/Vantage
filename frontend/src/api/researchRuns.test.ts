import { beforeEach, describe, expect, it, vi } from 'vitest';
import { informationalRun } from '../test/fixtures';

const { getSession } = vi.hoisted(() => ({ getSession: vi.fn() }));

vi.mock('../lib/supabase', () => ({
  supabase: { auth: { getSession } },
}));

import {
  ApiError,
  createResearchRun,
  getResearchRun,
  listResearchRuns,
} from './researchRuns';

describe('research-runs API client', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getSession.mockResolvedValue({
      data: { session: { access_token: 'access-token' } },
    });
  });

  it('requires an authenticated session before making a request', async () => {
    getSession.mockResolvedValueOnce({ data: { session: null } });
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    await expect(createResearchRun('AAPL')).rejects.toMatchObject({
      status: 401,
      error: { code: 'AUTH_REQUIRED', retryable: false },
    });
    expect(fetchSpy).not.toHaveBeenCalled();
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
