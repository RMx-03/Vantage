import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ResearchWorkspace from './ResearchWorkspace';
import { AuthProvider } from '../../context/AuthContext';
import * as api from '../../api/researchRuns';
import { historicalRun, informationalRun } from '../../test/fixtures';

import { renderWithRouter } from '../../test/renderWithRouter';
import { Route, Routes } from 'react-router-dom';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...actual,
    useNavigate: () => {
      const realNavigate = actual.useNavigate();
      return (to: unknown, options?: unknown) => {
        if (options !== undefined) {
          mockNavigate(to, options);
        } else {
          mockNavigate(to);
        }
        return (realNavigate as (t: unknown, o?: unknown) => void)(to, options);
      };
    },
  };
});

const authMock = vi.hoisted(() => ({
  user: null as { id: string; email: string } | null,
  signOut: vi.fn(),
  // When true, useAuth resolves through the real AuthProvider instead of the
  // stub, so one test can exercise the provider/workspace seam end to end.
  useRealProvider: false,
  listeners: [] as Array<(event: string, session: unknown) => void>,
  session: null as { user: { id: string } } | null,
}));
vi.mock('../../context/AuthContext', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../context/AuthContext')>();
  return {
    ...actual,
    useAuth: () =>
      authMock.useRealProvider
        ? actual.useAuth()
        : { user: authMock.user, signOut: authMock.signOut },
  };
});

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

import type { SafeError } from '../../types/research';

vi.mock('../../api/researchRuns', () => {
  class ApiError extends Error {
    status: number;
    error: SafeError;
    constructor(status: number, error: SafeError) {
      super(error?.message || 'Error');
      this.status = status;
      this.error = error;
    }
  }

  return {
    createResearchRun: vi.fn(),
    listResearchRuns: vi.fn(),
    getResearchRun: vi.fn(),
    ApiError,
  };
});

function renderWorkspace({ route = '/app/research' }: { route?: string; path?: string } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const tree = () => (
    <QueryClientProvider client={queryClient}>
      <Routes>
        <Route path="/app/research" element={<ResearchWorkspace />} />
        <Route path="/app/research/:runId" element={<ResearchWorkspace />} />
      </Routes>
    </QueryClientProvider>
  );
  const view = renderWithRouter(tree(), { route });
  return { ...view, queryClient, rerenderWorkspace: () => view.rerender(tree()) };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

describe('ResearchWorkspace', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authMock.user = { id: 'user-a', email: 'test@example.com' };
    authMock.useRealProvider = false;
    authMock.listeners.length = 0;
    authMock.session = null;
    vi.mocked(api.listResearchRuns).mockResolvedValue({
      items: [],
      next_cursor: null,
    });
    vi.mocked(api.getResearchRun).mockResolvedValue(historicalRun);
  });

  it('validates symbol input and triggers research mutation', async () => {
    vi.mocked(api.createResearchRun).mockResolvedValueOnce(informationalRun);

    renderWorkspace();

    const input = screen.getByLabelText(/US equity symbol/i);
    const submitBtn = screen.getByRole('button', { name: /Run research/i });

    expect(submitBtn).toBeDisabled();

    await userEvent.type(input, 'aapl');
    expect(submitBtn).toBeEnabled();

    await userEvent.click(submitBtn);

    expect(api.createResearchRun).toHaveBeenCalledWith('AAPL');
    expect(await screen.findByText(informationalRun.summary!)).toBeVisible();
    expect(screen.queryByText(/approved|rejected/i)).not.toBeInTheDocument();
  });

  it.each([
    [401, 'Your session has expired'],
    [503, 'Market data could not be retrieved'],
    [500, 'Research run could not be completed'],
  ])('renders typed API failure %s', async (status, message) => {
    vi.mocked(api.createResearchRun).mockRejectedValueOnce(
      new api.ApiError(status, {
        code: status === 401 ? 'AUTH_REQUIRED' : status === 503 ? 'MARKET_DATA_FAILED' : 'INTERNAL_ERROR',
        message: status === 401 ? 'Your session has expired.' : status === 503 ? 'Market data could not be retrieved.' : 'Research run could not be completed.',
        retryable: status !== 401,
      })
    );

    renderWorkspace();

    const input = screen.getByLabelText(/US equity symbol/i);
    await userEvent.type(input, 'AAPL');
    await userEvent.click(screen.getByRole('button', { name: /Run research/i }));

    expect(await screen.findByText(new RegExp(message, 'i'))).toBeVisible();
  });

  it('loads real history and marks the selected run historical', async () => {
    vi.mocked(api.listResearchRuns).mockResolvedValueOnce({
      items: [historicalRun],
      next_cursor: null,
    });

    renderWorkspace();

    const historyLink = await screen.findByRole('link', {
      name: /AAPL.*Jul 31, 2026/i,
    });
    expect(historyLink).toBeVisible();

    await userEvent.click(historyLink);

    expect(await screen.findByText(/historical/i)).toBeVisible();
    expect(await screen.findByText(/original as of/i)).toBeVisible();
  });

  it('provides sign-in again action on 401 failure', async () => {
    vi.mocked(api.createResearchRun).mockRejectedValueOnce(
      new api.ApiError(401, {
        code: 'AUTH_REQUIRED',
        message: 'Your session has expired.',
        retryable: false,
      })
    );

    renderWorkspace();

    const input = screen.getByLabelText(/US equity symbol/i);
    await userEvent.type(input, 'AAPL');
    await userEvent.click(screen.getByRole('button', { name: /Run research/i }));

    const signinBtn = await screen.findByRole('button', { name: /Sign in again/i });
    expect(signinBtn).toBeVisible();

    await userEvent.click(signinBtn);
    expect(authMock.signOut).toHaveBeenCalled();
    expect(mockNavigate).toHaveBeenCalledWith('/auth');
  });

  it('does not show an older result after a newer run fails', async () => {
    vi.mocked(api.createResearchRun)
      .mockResolvedValueOnce(informationalRun)
      .mockRejectedValueOnce(
        new api.ApiError(503, {
          code: 'MARKET_DATA_PROVIDER_FAILED',
          message: 'Market data could not be retrieved.',
          retryable: true,
        })
      );

    renderWorkspace();
    await userEvent.type(screen.getByLabelText(/US equity symbol/i), 'AAPL');
    const runButton = screen.getByRole('button', { name: /Run research/i });
    await userEvent.click(runButton);
    expect(await screen.findByText(informationalRun.summary!)).toBeVisible();

    await userEvent.click(runButton);
    expect(await screen.findByText(/Market data could not be retrieved/i)).toBeVisible();
    expect(screen.queryByText(informationalRun.summary!)).not.toBeInTheDocument();
  });

  it('shows correlation IDs and retries the failed symbol', async () => {
    vi.mocked(api.createResearchRun)
      .mockRejectedValueOnce(
        new api.ApiError(503, {
          code: 'MARKET_DATA_PROVIDER_FAILED',
          message: 'Market data could not be retrieved.',
          run_id: 'failed-run-id',
          request_id: 'request-correlation-id',
          retryable: true,
        })
      )
      .mockResolvedValueOnce(informationalRun);

    renderWorkspace();
    await userEvent.type(screen.getByLabelText(/US equity symbol/i), 'AAPL');
    await userEvent.click(screen.getByRole('button', { name: /Run research/i }));

    expect(await screen.findByText('Run ID: failed-run-id')).toBeVisible();
    expect(screen.getByText('Request ID: request-correlation-id')).toBeVisible();

    await userEvent.click(screen.getByRole('button', { name: /Retry research/i }));

    expect(await screen.findByText(informationalRun.summary!)).toBeVisible();
    expect(api.createResearchRun).toHaveBeenCalledTimes(2);
    expect(api.createResearchRun).toHaveBeenLastCalledWith('AAPL');
  });

  it('announces pending work and prevents duplicate submission', async () => {
    const pendingRun = deferred<typeof informationalRun>();
    vi.mocked(api.createResearchRun).mockReturnValueOnce(pendingRun.promise);

    renderWorkspace();
    await userEvent.type(screen.getByLabelText(/US equity symbol/i), 'AAPL');
    await userEvent.click(screen.getByRole('button', { name: /Run research/i }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Running research analysis for AAPL'
    );
    expect(screen.getByRole('button', { name: /Run research/i })).toBeDisabled();

    pendingRun.resolve(informationalRun);
    expect(await screen.findByText(informationalRun.summary!)).toBeVisible();
  });

  it('renders a safe network error and allows retry', async () => {
    vi.mocked(api.createResearchRun).mockRejectedValueOnce(
      new Error('Network connection unavailable.')
    );

    renderWorkspace();
    await userEvent.type(screen.getByLabelText(/US equity symbol/i), 'AAPL');
    await userEvent.click(screen.getByRole('button', { name: /Run research/i }));

    expect(await screen.findByText('Network connection unavailable.')).toBeVisible();
    expect(screen.getByRole('button', { name: /Retry research/i })).toBeVisible();
  });

  it('toggles owner-scoped history without affecting the workspace', async () => {
    renderWorkspace();
    expect(await screen.findByRole('heading', { name: /Research History/i })).toBeVisible();

    await userEvent.click(screen.getByRole('button', { name: /Hide History/i }));
    expect(screen.queryByRole('heading', { name: /Research History/i })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /View History/i }));
    expect(screen.getByRole('heading', { name: /Research History/i })).toBeVisible();
  });

  it('does not display fabricated latency or node counts', async () => {
    renderWorkspace();
    expect(screen.queryByText(/latency:\s*\d+ms/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/nodes active/i)).not.toBeInTheDocument();
  });

  it('refreshes the signed-in owner history after a completed run', async () => {
    vi.mocked(api.listResearchRuns)
      .mockResolvedValueOnce({ items: [], next_cursor: null })
      .mockResolvedValue({ items: [historicalRun], next_cursor: null });
    vi.mocked(api.createResearchRun).mockResolvedValueOnce(informationalRun);

    const { queryClient } = renderWorkspace();
    expect(await screen.findByText(/no previous research runs/i)).toBeVisible();

    await userEvent.type(screen.getByLabelText(/US equity symbol/i), 'AAPL');
    await userEvent.click(screen.getByRole('button', { name: /Run research/i }));

    expect(
      await screen.findByRole('link', { name: /AAPL.*Jul 31, 2026/i })
    ).toBeVisible();
    expect(queryClient.getQueryData(['research-runs', 'user-a'])).toBeDefined();
    expect(queryClient.getQueryData(['research-runs'])).toBeUndefined();
  });

  it('clears the previous owner result when the signed-in user changes', async () => {
    vi.mocked(api.createResearchRun).mockResolvedValueOnce(informationalRun);

    const { rerenderWorkspace } = renderWorkspace();
    await userEvent.type(screen.getByLabelText(/US equity symbol/i), 'AAPL');
    await userEvent.click(screen.getByRole('button', { name: /Run research/i }));
    expect(await screen.findByText(informationalRun.summary!)).toBeVisible();

    authMock.user = { id: 'user-b', email: 'other@example.com' };
    rerenderWorkspace();

    await waitFor(() =>
      expect(screen.queryByText(informationalRun.summary!)).not.toBeInTheDocument()
    );
    expect(screen.getByText(/Enter a US equity symbol above/i)).toBeVisible();
  });

  it('drops the previous owner workspace state when the real provider switches owner', async () => {
    authMock.useRealProvider = true;
    authMock.session = { user: { id: 'user-a' } };
    vi.mocked(api.createResearchRun).mockResolvedValueOnce(informationalRun);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    renderWithRouter(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <Routes>
            <Route path="/app/research" element={<ResearchWorkspace />} />
            <Route path="/app/research/:runId" element={<ResearchWorkspace />} />
          </Routes>
        </AuthProvider>
      </QueryClientProvider>,
      { route: '/app/research' }
    );

    // The provider has hydrated once the owner-scoped history has resolved.
    expect(await screen.findByText(/no previous research runs/i)).toBeVisible();

    const input = screen.getByLabelText(/US equity symbol/i);
    await userEvent.type(input, 'AAPL');
    await userEvent.click(screen.getByRole('button', { name: /Run research/i }));
    expect(await screen.findByText(informationalRun.summary!)).toBeVisible();

    authMock.session = { user: { id: 'user-b' } };
    await act(async () => {
      authMock.listeners.forEach((listener) =>
        listener('SIGNED_IN', authMock.session)
      );
    });

    await waitFor(() =>
      expect(screen.queryByText(informationalRun.summary!)).not.toBeInTheDocument()
    );
    expect(screen.getByText(/Enter a US equity symbol above/i)).toBeVisible();
    expect(screen.getByLabelText(/US equity symbol/i)).toHaveValue('');
  });

  it('hydrates a run from the url', async () => {
    vi.mocked(api.getResearchRun).mockResolvedValue(informationalRun);

    renderWorkspace({
      route: `/app/research/${informationalRun.run_id}`,
      path: '/app/research/:runId',
    });

    expect(await screen.findByText(informationalRun.summary!)).toBeVisible();
    expect(api.getResearchRun).toHaveBeenCalledWith(informationalRun.run_id);
  });

  it('marks a url-loaded run as historical', async () => {
    vi.mocked(api.getResearchRun).mockResolvedValue(historicalRun);

    renderWorkspace({
      route: `/app/research/${historicalRun.run_id}`,
      path: '/app/research/:runId',
    });

    expect(await screen.findByText(/historical/i)).toBeVisible();
  });

  it('navigates to the run url after creating one', async () => {
    vi.mocked(api.createResearchRun).mockResolvedValue(informationalRun);

    renderWorkspace({
      route: '/app/research',
      path: '/app/research',
    });

    await userEvent.type(screen.getByLabelText(/US equity symbol/i), 'aapl');
    await userEvent.click(screen.getByRole('button', { name: /Run research/i }));

    await waitFor(() =>
      expect(mockNavigate).toHaveBeenCalledWith(
        `/app/research/${informationalRun.run_id}`,
        { replace: true }
      )
    );
  });
});
