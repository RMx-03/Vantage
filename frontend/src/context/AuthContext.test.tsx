import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider, useAuth } from './AuthContext';
import * as authClient from '../lib/authClient';

function Probe() {
  const { user, loading } = useAuth();
  if (loading) return <p>loading</p>;
  return <p>{user ? `signed-in:${user.email}` : 'signed-out'}</p>;
}

function renderProbe(client = new QueryClient()) {
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  authClient.setAccessToken(null);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('hydration', () => {
  it('signs the user in when the refresh cookie is valid', async () => {
    vi.spyOn(authClient, 'refreshSession').mockResolvedValue('refreshed');
    vi.spyOn(authClient, 'fetchMe').mockResolvedValue({
      id: 'user-1',
      email: 'operator@example.com',
      email_verified: true,
    });

    renderProbe();
    await waitFor(() =>
      expect(screen.getByText('signed-in:operator@example.com')).toBeInTheDocument()
    );
  });

  it('settles signed-out when there is no valid cookie', async () => {
    vi.spyOn(authClient, 'refreshSession').mockResolvedValue('unauthenticated');
    renderProbe();
    await waitFor(() => expect(screen.getByText('signed-out')).toBeInTheDocument());
  });

  it('stops loading even when hydration throws', async () => {
    // A hung loading state locks the user out of the whole application.
    vi.spyOn(authClient, 'refreshSession').mockRejectedValue(new Error('network down'));
    renderProbe();
    await waitFor(() => expect(screen.getByText('signed-out')).toBeInTheDocument());
  });
});

describe('owner-change cache purge', () => {
  it('drops research queries when the signed-in owner changes', async () => {
    // Preserved invariant. Without it, the next user
    // signed into the same browser can render the previous user's rows.
    const client = new QueryClient();
    client.setQueryData(['research-runs', 'list'], [{ id: 'run-from-previous-user' }]);
    client.setQueryData(['research-run', 'user-1', 'run-1'], { id: 'detail' });
    const removeSpy = vi.spyOn(client, 'removeQueries');

    vi.spyOn(authClient, 'refreshSession').mockResolvedValue('refreshed');
    vi.spyOn(authClient, 'fetchMe').mockResolvedValue({
      id: 'user-2',
      email: 'second@example.com',
      email_verified: true,
    });

    renderProbe(client);
    await waitFor(() =>
      expect(screen.getByText('signed-in:second@example.com')).toBeInTheDocument()
    );
    expect(removeSpy).toHaveBeenCalledWith({ queryKey: ['research-runs'] });
    expect(removeSpy).toHaveBeenCalledWith({ queryKey: ['research-run'] });
  });
});
