import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ResearchWorkspace from './ResearchWorkspace';
import * as api from '../../api/researchRuns';
import { historicalRun, informationalRun } from '../../test/fixtures';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}));

const authMock = vi.hoisted(() => ({
  user: null as { id: string; email: string } | null,
  signOut: vi.fn(),
}));
vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({
    user: authMock.user,
    signOut: authMock.signOut,
  }),
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

function renderWorkspace() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const tree = () => (
    <QueryClientProvider client={queryClient}>
      <ResearchWorkspace />
    </QueryClientProvider>
  );
  const view = render(tree());
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
    vi.mocked(api.listResearchRuns).mockResolvedValue({
      items: [],
      next_cursor: null,
    });
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

    const historyBtn = await screen.findByRole('button', {
      name: /AAPL.*Jul 31, 2026/i,
    });
    expect(historyBtn).toBeVisible();

    await userEvent.click(historyBtn);

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
      await screen.findByRole('button', { name: /AAPL.*Jul 31, 2026/i })
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
});
