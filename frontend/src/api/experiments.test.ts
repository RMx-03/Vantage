import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as authClient from '../lib/authClient';
import {
  POLL_FAST_MS,
  POLL_SLOW_MS,
} from '../features/research/runPolling';
import type { Experiment, ExperimentSpec } from '../types/experiments';
import {
  createExperiment,
  deleteExperiment,
  experimentPollInterval,
  exportExperiment,
  getExperiment,
  listExperiments,
  planExperiment,
  replayExperiment,
} from './experiments';
import { ApiError } from './researchRuns';

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

const spec: ExperimentSpec = {
  question: 'How did an equal-weight hold do?',
  symbols: ['AAPL', 'MSFT'],
  start: '2022-03-01',
  strategy: { template: 'buy_and_hold' },
};

const running: Experiment = {
  id: 'exp-1',
  status: 'running',
  research_status: null,
  created_at: '2026-11-22T00:00:00Z',
  started_at: '2026-11-22T00:00:00Z',
  spec,
  spec_hash: 'h',
  inputs_bytes: 0,
  versions: {},
  label: 'Exploratory: list chosen today, survivorship bias possible',
};

const call = (spy: ReturnType<typeof vi.spyOn>, i = 0) =>
  spy.mock.calls[i] as [string, RequestInit];

afterEach(() => {
  vi.restoreAllMocks();
  authClient.setAccessToken(null);
});

describe('experiments API client', () => {
  beforeEach(() => authClient.setAccessToken('access-token', 900));

  it('plans without starting anything', async () => {
    const plan = { sessions: 460, engine_invocations: 4 };
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json(plan));
    await expect(planExperiment(spec)).resolves.toEqual(plan);
    const [url, init] = call(spy);
    expect(url).toMatch(/\/api\/v1\/experiments\/plan$/);
    expect(init).toMatchObject({ method: 'POST', body: JSON.stringify(spec) });
  });

  it('submits and resolves the 202 body as the experiment', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json(running, 202));
    await expect(createExperiment(spec)).resolves.toEqual(running);
    const [url, init] = call(spy);
    expect(url).toMatch(/\/api\/v1\/experiments$/);
    expect(init.method).toBe('POST');
    expect(init.headers).toMatchObject({ Authorization: 'Bearer access-token' });
  });

  it('reads, lists, replays and deletes by id', async () => {
    const spy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json(running))
      .mockResolvedValueOnce(json([]))
      .mockResolvedValueOnce(json({ ...running, id: 'exp-2', replay_of: 'exp-1' }, 202))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    await getExperiment('exp-1');
    await listExperiments(5);
    await expect(replayExperiment('exp-1')).resolves.toMatchObject({ replay_of: 'exp-1' });
    await expect(deleteExperiment('exp-1')).resolves.toBeUndefined();
    expect(call(spy, 0)[0]).toMatch(/\/experiments\/exp-1$/);
    expect(call(spy, 1)[0]).toMatch(/\/experiments\?limit=5$/);
    expect(call(spy, 2)[0]).toMatch(/\/experiments\/exp-1\/replay$/);
    expect(call(spy, 2)[1].method).toBe('POST');
    expect(call(spy, 3)[0]).toMatch(/\/experiments\/exp-1$/);
    expect(call(spy, 3)[1].method).toBe('DELETE');
  });

  it('downloads an export as a named blob with the bearer token', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response('section,date\n', {
        status: 200,
        headers: { 'Content-Type': 'text/csv; charset=utf-8' },
      })
    );
    const file = await exportExperiment('exp-1', 'csv');
    expect(file.filename).toBe('experiment-exp-1.csv');
    expect(await file.blob.text()).toBe('section,date\n');
    const [url, init] = call(spy);
    expect(url).toMatch(/\/experiments\/exp-1\/export\?format=csv$/);
    expect(init.headers).toMatchObject({ Authorization: 'Bearer access-token' });
  });

  it('refreshes once on 401 through the auth client', async () => {
    vi.spyOn(authClient, 'refresh').mockImplementation(async () => {
      authClient.setAccessToken('fresh-token', 900);
      return true;
    });
    const spy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(json(running));
    await expect(getExperiment('exp-1')).resolves.toEqual(running);
    expect(call(spy, 1)[1].headers).toMatchObject({ Authorization: 'Bearer fresh-token' });
  });

  it.each([
    [409, 'EXPERIMENT_IN_FLIGHT'],
    [409, 'EXPERIMENT_QUOTA_REACHED'],
    [429, 'RUN_CAPACITY_EXCEEDED'],
  ])('surfaces a %i with its code %s', async (status, code) => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      json({ detail: { code, message: 'Refused.', retryable: status === 429 } }, status)
    );
    const error = await createExperiment(spec).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status, error: { code } });
  });

  it('surfaces a failed export with its safe error', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      json({ detail: { code: 'NOT_FOUND', message: 'Experiment not found.' } }, 404)
    );
    await expect(exportExperiment('nope', 'json')).rejects.toMatchObject({
      status: 404,
      error: { code: 'NOT_FOUND' },
    });
  });
});

describe('experimentPollInterval', () => {
  it('reuses the research-run schedule', () => {
    expect(experimentPollInterval(running, 1)).toBe(POLL_FAST_MS);
    expect(experimentPollInterval(running, 11)).toBe(POLL_SLOW_MS);
    expect(experimentPollInterval(running, 81)).toBe(false);
  });

  it('stops once the experiment is finished or missing', () => {
    expect(experimentPollInterval({ ...running, status: 'succeeded' }, 1)).toBe(false);
    expect(experimentPollInterval(undefined, 1)).toBe(false);
  });
});
