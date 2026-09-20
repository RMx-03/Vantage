import { screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderWithRouter } from '../test/renderWithRouter';
import UserSettingsPanel from './UserSettingsPanel';

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'user-1', email: 'operator@example.com' },
    signOut: vi.fn(),
  }),
}));

vi.mock('../features/research/ResearchHistory', () => ({
  default: () => <div>history stub</div>,
}));

const renderPanel = (route: string) =>
  renderWithRouter(
    <QueryClientProvider client={new QueryClient()}>
      <UserSettingsPanel />
    </QueryClientProvider>,
    { route, path: '/app/settings/:tab' }
  );

describe('UserSettingsPanel', () => {
  it('shows the profile tab at /app/settings/profile', () => {
    renderPanel('/app/settings/profile');
    expect(screen.getByText('operator@example.com')).toBeVisible();
  });

  it('shows the run log at /app/settings/runs', () => {
    renderPanel('/app/settings/runs');
    expect(screen.getByText('history stub')).toBeVisible();
  });

  it('renders tabs as links, not buttons', () => {
    renderPanel('/app/settings/profile');
    expect(screen.getByRole('link', { name: /User Profile/i })).toHaveAttribute(
      'href',
      '/app/settings/profile'
    );
    expect(screen.getByRole('link', { name: /Research Run Log/i })).toHaveAttribute(
      'href',
      '/app/settings/runs'
    );
  });
});
