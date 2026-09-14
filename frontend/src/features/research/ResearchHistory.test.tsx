import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ResearchHistory from './ResearchHistory';
import * as api from '../../api/researchRuns';
import { historicalRun, informationalRun } from '../../test/fixtures';

import type { SafeError } from '../../types/research';

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

function renderWithQuery(ui: React.ReactElement) {
  const testQueryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={testQueryClient}>{ui}</QueryClientProvider>
  );
}

describe('ResearchHistory', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders history items with accessible names', async () => {
    vi.mocked(api.listResearchRuns).mockResolvedValueOnce({
      items: [historicalRun],
      next_cursor: null,
    });

    const onSelect = vi.fn();
    renderWithQuery(<ResearchHistory onSelectRun={onSelect} />);

    const runButton = await screen.findByRole('button', {
      name: /AAPL.*Jul 31, 2026/i,
    });
    expect(runButton).toBeVisible();

    await userEvent.click(runButton);
    expect(onSelect).toHaveBeenCalledWith(historicalRun);
  });

  it('renders empty message when no history exists', async () => {
    vi.mocked(api.listResearchRuns).mockResolvedValueOnce({
      items: [],
      next_cursor: null,
    });

    renderWithQuery(<ResearchHistory />);
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

    renderWithQuery(<ResearchHistory />);
    expect(await screen.findByText('AAPL')).toBeVisible();

    const loadMoreButton = await screen.findByRole('button', { name: /load more/i });
    expect(loadMoreButton).toBeVisible();

    await userEvent.click(loadMoreButton);
    expect(await screen.findByRole('button', { name: /AAPL.*Jul 31, 2026/i })).toBeVisible();
  });
});
