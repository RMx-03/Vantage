import { screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderWithRouter } from '../test/renderWithRouter';
import Terminal from './Terminal';
import { informationalRun } from '../test/fixtures';

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'u1', email: 'a@b.c' }, signOut: vi.fn() }),
}));

describe('Terminal active model', () => {
  it('shows an em dash when no run is on screen', () => {
    renderWithRouter(
      <QueryClientProvider client={new QueryClient()}>
        <Terminal />
      </QueryClientProvider>,
      { route: '/app/research', path: '/app/research' }
    );
    expect(screen.getByText('—')).toBeVisible();
  });

  it('shows the model of the run named in the url', () => {
    const client = new QueryClient();
    client.setQueryData(
      ['research-run', 'u1', informationalRun.run_id],
      informationalRun
    );

    renderWithRouter(
      <QueryClientProvider client={client}>
        <Terminal />
      </QueryClientProvider>,
      { route: `/app/research/${informationalRun.run_id}`, path: '/app/research/:runId' }
    );

    expect(screen.getByText(informationalRun.model_info!.model)).toBeVisible();
  });
});
