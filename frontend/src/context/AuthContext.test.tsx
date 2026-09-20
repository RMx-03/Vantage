import { act, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, useAuth } from './AuthContext';

type Listener = (event: string, session: unknown) => void;

const authMock = vi.hoisted(() => ({
  listeners: [] as Listener[],
  releaseGetSession: null as ((session: unknown) => void) | null,
}));

vi.mock('../lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: () =>
        new Promise((resolve) => {
          authMock.releaseGetSession = (session: unknown) =>
            resolve({ data: { session } });
        }),
      onAuthStateChange: (listener: Listener) => {
        authMock.listeners.push(listener);
        return { data: { subscription: { unsubscribe: vi.fn() } } };
      },
      signOut: () => Promise.resolve({ error: null }),
    },
  },
}));

const OWNER_A = { user: { id: 'owner-a' } };
const OWNER_B = { user: { id: 'owner-b' } };

function OwnerProbe() {
  const { user } = useAuth();
  return <span data-testid="owner">{user?.id ?? 'anonymous'}</span>;
}

function emit(session: unknown) {
  act(() => {
    authMock.listeners.forEach((listener) => listener('SIGNED_IN', session));
  });
}

async function releaseHydration(session: unknown) {
  await act(async () => {
    authMock.releaseGetSession?.(session);
  });
}

describe('AuthProvider hydration race', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    authMock.listeners = [];
    authMock.releaseGetSession = null;
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <OwnerProbe />
        </AuthProvider>
      </QueryClientProvider>
    );
  });

  it('keeps the newer owner when the initial session resolves late', async () => {
    await waitFor(() => expect(authMock.listeners.length).toBeGreaterThan(0));

    // A newer auth event lands while getSession() is still in flight.
    emit(OWNER_B);
    expect(screen.getByTestId('owner')).toHaveTextContent('owner-b');

    // The stale hydration for the previous owner must not win.
    await releaseHydration(OWNER_A);
    expect(screen.getByTestId('owner')).toHaveTextContent('owner-b');
  });

  it('does not purge the newer owner cache when the initial session resolves late', async () => {
    await waitFor(() => expect(authMock.listeners.length).toBeGreaterThan(0));

    emit(OWNER_B);
    queryClient.setQueryData(['research-runs', 'owner-b'], { items: ['kept'] });

    await releaseHydration(OWNER_A);

    expect(queryClient.getQueryData(['research-runs', 'owner-b'])).toEqual({
      items: ['kept'],
    });
  });

  it('still hydrates from the persisted session when no event precedes it', async () => {
    await waitFor(() => expect(authMock.listeners.length).toBeGreaterThan(0));

    await releaseHydration(OWNER_A);

    expect(screen.getByTestId('owner')).toHaveTextContent('owner-a');
  });

  it('purges cached list and detail queries when the signed-in owner changes', async () => {
    await waitFor(() => expect(authMock.listeners.length).toBeGreaterThan(0));

    emit(OWNER_A);
    queryClient.setQueryData(['research-run', 'owner-a', 'run-1'], {
      run_id: 'run-1',
    });
    queryClient.setQueryData(['research-runs', 'owner-a'], {
      pages: [],
    });

    emit(OWNER_B);

    await waitFor(() => {
      expect(
        queryClient.getQueryData(['research-run', 'owner-a', 'run-1'])
      ).toBeUndefined();
      expect(
        queryClient.getQueryData(['research-runs', 'owner-a'])
      ).toBeUndefined();
    });
  });
});
