import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import Terminal from './Terminal';
import { informationalRun } from '../test/fixtures';

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'u1', email: 'a@b.c' }, signOut: vi.fn() }),
}));

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

describe('Terminal active model', () => {
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

    renderTerminal('/app/research/run-1', client);
    expect(screen.getByText('model-one')).toBeVisible();

    await userEvent.click(screen.getByRole('link', { name: 'Next run' }));
    expect(screen.getByText('model-two')).toBeVisible();
  });
});
