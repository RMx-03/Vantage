import { useEffect } from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider, useAuth } from './AuthContext';
import * as authClient from '../lib/authClient';
import type { AuthUser } from '../types/auth';

const ALICE: AuthUser = { id: 'user-a', email: 'alice@example.com', email_verified: true };

let handle: ReturnType<typeof useAuth> | null = null;

function Probe() {
  const auth = useAuth();
  // Exposed to the test after render, not during it.
  useEffect(() => {
    handle = auth;
  });
  if (auth.loading) return <p>loading</p>;
  return <p>{auth.user ? `signed-in:${auth.user.email}` : 'signed-out'}</p>;
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

function deferred<T>() {
  let resolve: (value: T) => void = () => {};
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

beforeEach(() => {
  handle = null;
  authClient.setAccessToken(null);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('stale hydration results are discarded', () => {
  it('does not sign the user back in after a sign-out that finished first', async () => {
    vi.spyOn(authClient, 'refreshSession').mockResolvedValue('refreshed');
    const me = deferred<AuthUser>();
    vi.spyOn(authClient, 'fetchMe')
      .mockResolvedValueOnce(ALICE) // mount hydration
      .mockReturnValueOnce(me.promise); // the later, slow hydration
    vi.spyOn(authClient, 'logout').mockResolvedValue();

    renderProbe();
    await waitFor(() => expect(screen.getByText('signed-in:alice@example.com')).toBeInTheDocument());

    // A proactive refresh starts, then the user signs out before it lands.
    let slow: Promise<void> = Promise.resolve();
    act(() => {
      slow = handle!.refreshUser();
    });
    await act(async () => {
      await handle!.signOut();
    });
    await act(async () => {
      me.resolve(ALICE);
      await slow;
    });

    expect(screen.getByText('signed-out')).toBeInTheDocument();
  });

  it('does not sign the user out when a stale mount refresh fails after a login', async () => {
    const mountRefresh = deferred<authClient.RefreshOutcome>();
    vi.spyOn(authClient, 'refreshSession').mockReturnValueOnce(mountRefresh.promise);
    vi.spyOn(authClient, 'login').mockResolvedValue();
    vi.spyOn(authClient, 'fetchMe').mockResolvedValue(ALICE);

    renderProbe();
    await act(async () => {
      await handle!.signIn('alice@example.com', 'correct horse battery');
    });
    await act(async () => {
      mountRefresh.resolve('unauthenticated');
      await mountRefresh.promise;
    });

    expect(screen.getByText('signed-in:alice@example.com')).toBeInTheDocument();
  });
});

describe('transient failures do not sign the user out', () => {
  it('keeps the user and their cache when the server is unavailable', async () => {
    const client = new QueryClient();
    const refresh = vi
      .spyOn(authClient, 'refreshSession')
      .mockResolvedValueOnce('refreshed')
      .mockResolvedValueOnce('unavailable');
    vi.spyOn(authClient, 'fetchMe').mockResolvedValue(ALICE);

    renderProbe(client);
    await waitFor(() => expect(screen.getByText('signed-in:alice@example.com')).toBeInTheDocument());
    client.setQueryData(['research-runs', ALICE.id], { pages: [] });

    await act(async () => {
      await handle!.refreshUser();
    });

    expect(refresh).toHaveBeenCalledTimes(2);
    expect(screen.getByText('signed-in:alice@example.com')).toBeInTheDocument();
    expect(client.getQueryData(['research-runs', ALICE.id])).toBeDefined();
  });

  it('still signs the user out when the session is genuinely gone', async () => {
    vi.spyOn(authClient, 'refreshSession')
      .mockResolvedValueOnce('refreshed')
      .mockResolvedValueOnce('unauthenticated');
    vi.spyOn(authClient, 'fetchMe').mockResolvedValue(ALICE);

    renderProbe();
    await waitFor(() => expect(screen.getByText('signed-in:alice@example.com')).toBeInTheDocument());

    await act(async () => {
      await handle!.refreshUser();
    });

    expect(screen.getByText('signed-out')).toBeInTheDocument();
  });
});
