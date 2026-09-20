import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import Terminal from './Terminal';
import ResearchWorkspace from '../features/research/ResearchWorkspace';
import * as api from '../api/researchRuns';
import { informationalRun } from '../test/fixtures';

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'u1', email: 'a@b.c' }, signOut: vi.fn() }),
}));

vi.mock('../api/researchRuns', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/researchRuns')>();
  return {
    ...actual,
    createResearchRun: vi.fn(),
    getResearchRun: vi.fn(),
    listResearchRuns: vi.fn(),
  };
});

function renderTerminal(route: string, client: QueryClient) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/app" element={<Terminal />}>
            <Route path="research" element={<div>Research home</div>} />
            <Route
              path="research/:runId"
              element={<Link to="/app/research/run-2">Next run</Link>}
            />
            <Route path="settings/:tab" element={<div>Settings</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function renderTerminalWithWorkspace(route: string, client: QueryClient) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/app" element={<Terminal />}>
            <Route path="research/:runId" element={<ResearchWorkspace />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

describe('Terminal active model', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getResearchRun).mockResolvedValue(informationalRun);
    vi.mocked(api.listResearchRuns).mockResolvedValue({
      items: [],
      next_cursor: null,
    });
  });

  it('shows an em dash when no run is on screen', () => {
    renderTerminal('/app/research', new QueryClient());
    expect(screen.getByText('—')).toBeVisible();
  });

  it('shows the model of the run named in the url', () => {
    const client = new QueryClient();
    client.setQueryData(
      ['research-run', 'u1', informationalRun.run_id],
      informationalRun
    );

    renderTerminal(`/app/research/${informationalRun.run_id}`, client);

    expect(screen.getByText(informationalRun.model_info!.model)).toBeVisible();
  });

  it('updates the active model when the child run route changes', async () => {
    const client = new QueryClient();
    const first = {
      ...informationalRun,
      run_id: 'run-1',
      model_info: { ...informationalRun.model_info!, model: 'model-one' },
    };
    const second = {
      ...informationalRun,
      run_id: 'run-2',
      model_info: { ...informationalRun.model_info!, model: 'model-two' },
    };
    client.setQueryData(['research-run', 'u1', 'run-1'], first);
    client.setQueryData(['research-run', 'u1', 'run-2'], second);
    vi.mocked(api.getResearchRun).mockImplementation(async (runId) =>
      runId === 'run-2' ? second : first
    );

    renderTerminal('/app/research/run-1', client);
    expect(screen.getByText('model-one')).toBeVisible();

    await userEvent.click(screen.getByRole('link', { name: 'Next run' }));
    expect(screen.getByText('model-two')).toBeVisible();
  });

  it('updates the active model after a cold deep link finishes loading', async () => {
    const pendingRun = deferred<typeof informationalRun>();
    vi.mocked(api.getResearchRun).mockReturnValue(pendingRun.promise);
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    renderTerminalWithWorkspace(
      `/app/research/${informationalRun.run_id}`,
      client
    );

    const activeModel = screen.getByText('Active Model').parentElement!;
    expect(within(activeModel).getByText('—')).toBeVisible();

    await act(async () => {
      pendingRun.resolve(informationalRun);
    });

    expect(await screen.findByText(informationalRun.summary!)).toBeVisible();
    await waitFor(() =>
      expect(
        within(activeModel).getByText(informationalRun.model_info!.model)
      ).toBeVisible()
    );
  });
});
