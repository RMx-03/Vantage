import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ResearchHistory from './ResearchHistory';
import { formatUtcDate } from './dateFormatters';
import { AuthProvider } from '../../context/AuthContext';
import * as api from '../../api/researchRuns';
import { historicalRun, informationalRun } from '../../test/fixtures';
import { renderWithRouter } from '../../test/renderWithRouter';

import type { ResearchRun, SafeError } from '../../types/research';

const authMock = vi.hoisted(() => ({
  listeners: [] as Array<(event: string, session: unknown) => void>,
  session: null as { user: { id: string } } | null,
}));

vi.mock('../../lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: () => Promise.resolve({ data: { session: authMock.session } }),
      onAuthStateChange: (listener: (event: string, session: unknown) => void) => {
        authMock.listeners.push(listener);
        return { data: { subscription: { unsubscribe: vi.fn() } } };
      },
      signOut: () => Promise.resolve({ error: null }),
    },
  },
}));

vi.mock('../../api/researchRuns', () => ({
  listResearchRuns: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number;
    error: SafeError;
    constructor(status: number, error: SafeError) {
      super(error?.message || 'Error');
      this.status = status;
      this.error = error;
    }
  },
}));

const priorOwnerRun: ResearchRun = {
  ...historicalRun,
  run_id: 'c0eebc99-9c0b-4ef8-bb6d-6bb9bd380c33',
  symbol: 'TSLA',
};

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
}

function seedQuery(
  queryClient: QueryClient,
  queryKey: unknown[],
  runs: ResearchRun[]
) {
  queryClient.setQueryData(queryKey, {
    pages: [{ items: runs, next_cursor: null }],
    pageParams: [undefined],
  });
}

/**
 * Seeds the signed-in owner's cache once the provider has hydrated, so the seed
 * survives the purge that hydration performs and is proven to render.
 */
async function seedSignedInOwner(
  queryClient: QueryClient,
  userId: string,
  runs: ResearchRun[]
) {
  await waitFor(() => expect(api.listResearchRuns).toHaveBeenCalled());
  act(() => {
    seedQuery(queryClient, ['research-runs', userId], runs);
  });
}

function renderAsOwner(
  ui: React.ReactElement,
  userId: string | null = 'user-a',
  queryClient: QueryClient = makeQueryClient(),
  options?: { route?: string; path?: string }
) {
  authMock.session = userId === null ? null : { user: { id: userId } };
  const view = renderWithRouter(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{ui}</AuthProvider>
    </QueryClientProvider>,
    options
  );
  return { ...view, queryClient };
}

async function emitAuthState(
  event: string,
  session: { user: { id: string } } | null
) {
  authMock.session = session;
  await act(async () => {
    authMock.listeners.forEach((listener) => listener(event, session));
  });
}

function neverResolves<T>(): Promise<T> {
  return new Promise<T>(() => {});
}

describe('formatUtcDate', () => {
  it('formats market dates in UTC', () => {
    expect(formatUtcDate('2025-01-02T00:30:00+05:30')).toBe('Jan 1, 2025');
  });

  it('keeps the market session date stable across timezone offsets', () => {
    expect(formatUtcDate('2024-12-31T23:30:00-05:00')).toBe('Jan 1, 2025');
    expect(formatUtcDate('2026-07-31T20:00:00Z')).toBe('Jul 31, 2026');
  });
});

describe('ResearchHistory', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authMock.listeners.length = 0;
    authMock.session = null;
  });

  it('renders history items with accessible names', async () => {
    vi.mocked(api.listResearchRuns).mockResolvedValueOnce({
      items: [historicalRun],
      next_cursor: null,
    });

    renderAsOwner(<ResearchHistory />);

    const runLink = await screen.findByRole('link', {
      name: /AAPL.*Jul 31, 2026/i,
    });
    expect(runLink).toBeVisible();
    expect(runLink).toHaveAttribute('href', `/app/research/${historicalRun.run_id}`);
  });

  it('renders empty message when no history exists', async () => {
    vi.mocked(api.listResearchRuns).mockResolvedValueOnce({
      items: [],
      next_cursor: null,
    });

    renderAsOwner(<ResearchHistory />);
    expect(await screen.findByText(/no previous research runs/i)).toBeVisible();
  });

  it('supports pagination with load more', async () => {
    vi.mocked(api.listResearchRuns)
      .mockResolvedValueOnce({
        items: [informationalRun],
        next_cursor: 'cursor-123',
      })
      .mockResolvedValueOnce({
        items: [historicalRun],
        next_cursor: null,
      });

    renderAsOwner(<ResearchHistory />);
    expect(await screen.findByText('AAPL')).toBeVisible();

    const loadMoreButton = await screen.findByRole('button', { name: /load more/i });
    expect(loadMoreButton).toBeVisible();

    await userEvent.click(loadMoreButton);
    expect(await screen.findByRole('link', { name: /AAPL.*Jul 31, 2026/i })).toBeVisible();
  });

  it('recovers from a history request failure', async () => {
    vi.mocked(api.listResearchRuns)
      .mockRejectedValueOnce(new Error('History is temporarily unavailable.'))
      .mockResolvedValueOnce({ items: [], next_cursor: null });

    renderAsOwner(<ResearchHistory />);

    expect(await screen.findByText('History is temporarily unavailable.')).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: /Try again/i }));
    expect(await screen.findByText(/no previous research runs/i)).toBeVisible();
  });

  it('exposes the selected historical run to assistive technology', async () => {
    vi.mocked(api.listResearchRuns).mockResolvedValueOnce({
      items: [historicalRun],
      next_cursor: null,
    });

    renderAsOwner(
      <ResearchHistory />,
      'user-a',
      undefined,
      { route: `/app/research/${historicalRun.run_id}`, path: '/app/research/:runId' }
    );

    const selected = await screen.findByRole('link', {
      name: /AAPL.*Jul 31, 2026/i,
    });
    expect(selected).toHaveAttribute('aria-current', 'true');
  });

  it('scopes the history query to the signed-in owner', async () => {
    vi.mocked(api.listResearchRuns).mockResolvedValue({
      items: [historicalRun],
      next_cursor: null,
    });

    const { queryClient } = renderAsOwner(<ResearchHistory />, 'user-a');

    await screen.findByRole('link', { name: /AAPL.*Jul 31, 2026/i });
    expect(queryClient.getQueryData(['research-runs', 'user-a'])).toBeDefined();
    expect(queryClient.getQueryData(['research-runs'])).toBeUndefined();
  });

  it('never renders a prior owner cached runs when the new owner history fails', async () => {
    vi.mocked(api.listResearchRuns).mockRejectedValue(
      new Error('History is temporarily unavailable.')
    );

    const { queryClient } = renderAsOwner(<ResearchHistory />, 'user-b');
    expect(await screen.findByText('History is temporarily unavailable.')).toBeVisible();

    // Stale rows belonging to the previous owner are sitting in the cache,
    // both under their own scope and under the unscoped root key.
    seedQuery(queryClient, ['research-runs', 'user-a'], [priorOwnerRun]);
    seedQuery(queryClient, ['research-runs'], [priorOwnerRun]);
    expect(queryClient.getQueryData(['research-runs', 'user-a'])).toBeDefined();
    expect(screen.queryByRole('link', { name: /TSLA/i })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /Try again/i }));

    expect(await screen.findByText('History is temporarily unavailable.')).toBeVisible();
    expect(screen.queryByRole('link', { name: /TSLA/i })).not.toBeInTheDocument();
    expect(queryClient.getQueryData(['research-runs', 'user-a'])).toBeDefined();
  });

  it('purges prior owner data on logout', async () => {
    vi.mocked(api.listResearchRuns).mockImplementation(neverResolves);

    const { queryClient } = renderAsOwner(<ResearchHistory />, 'user-a');
    await seedSignedInOwner(queryClient, 'user-a', [priorOwnerRun]);

    expect(await screen.findByRole('link', { name: /TSLA/i })).toBeVisible();

    await emitAuthState('SIGNED_OUT', null);

    await waitFor(() =>
      expect(queryClient.getQueryData(['research-runs', 'user-a'])).toBeUndefined()
    );
    expect(screen.queryByRole('link', { name: /TSLA/i })).not.toBeInTheDocument();
  });

  it('purges prior owner data when a different user signs in', async () => {
    vi.mocked(api.listResearchRuns)
      .mockImplementationOnce(neverResolves)
      .mockResolvedValue({ items: [informationalRun], next_cursor: null });

    const { queryClient } = renderAsOwner(<ResearchHistory />, 'user-a');
    await seedSignedInOwner(queryClient, 'user-a', [priorOwnerRun]);

    expect(await screen.findByRole('link', { name: /TSLA/i })).toBeVisible();

    await emitAuthState('SIGNED_IN', { user: { id: 'user-b' } });

    expect(await screen.findByRole('link', { name: /AAPL.*Sep 11, 2026/i })).toBeVisible();
    expect(screen.queryByRole('link', { name: /TSLA/i })).not.toBeInTheDocument();
    expect(queryClient.getQueryData(['research-runs', 'user-a'])).toBeUndefined();
  });

  it('renders each run as a link to its own url', async () => {
    vi.mocked(api.listResearchRuns).mockResolvedValue({
      items: [informationalRun],
      next_cursor: null,
    });

    renderAsOwner(<ResearchHistory />, 'user-a', undefined, {
      route: '/app/research',
    });

    const link = await screen.findByRole('link', {
      name: new RegExp(informationalRun.symbol, 'i'),
    });
    expect(link).toHaveAttribute('href', `/app/research/${informationalRun.run_id}`);
  });

  it('works with no props, so the settings run log is never inert', async () => {
    vi.mocked(api.listResearchRuns).mockResolvedValue({
      items: [informationalRun],
      next_cursor: null,
    });

    renderAsOwner(<ResearchHistory />, 'user-a', undefined, {
      route: '/app/settings/runs',
    });

    expect(
      await screen.findByRole('link', { name: new RegExp(informationalRun.symbol, 'i') })
    ).toBeVisible();
  });
});
