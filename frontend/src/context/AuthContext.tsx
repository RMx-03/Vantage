import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import * as authClient from '../lib/authClient';
import type { AuthUser } from '../types/auth';

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  signIn: async () => {},
  signUp: async () => {},
  signOut: async () => {},
  refreshUser: async () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const queryClient = useQueryClient();
  const ownerIdRef = useRef<string | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const applyUser = useCallback(
    (nextUser: AuthUser | null) => {
      if (!mountedRef.current) return;
      const nextOwnerId = nextUser?.id ?? null;

      if (nextOwnerId !== ownerIdRef.current) {
        // The signed-in owner changed (sign-in, sign-out, account switch).
        // Drop every owner-scoped research query before the next owner can
        // render, so cached rows never outlive the session that fetched them.
        //
        // INVARIANT: every owner-scoped query key root must be purged here.
        // If you add a query whose data belongs to one user, add its root to
        // this list — otherwise the next user signed into the same browser
        // can render the previous user's rows from the cache.
        for (const root of [['research-runs'], ['research-run']]) {
          void queryClient.cancelQueries({ queryKey: root });
          queryClient.removeQueries({ queryKey: root });
        }
        ownerIdRef.current = nextOwnerId;
      }

      setUser(nextUser);
    },
    [queryClient]
  );

  const hydrate = useCallback(async () => {
    try {
      const ok = await authClient.refresh();
      if (!mountedRef.current) return;
      applyUser(ok ? await authClient.fetchMe() : null);
    } catch {
      // Any failure means "not signed in". Leaving `loading` true would trap
      // the user on a spinner with no way forward.
      if (!mountedRef.current) return;
      applyUser(null);
    }
  }, [applyUser]);

  useEffect(() => {
    void hydrate().finally(() => {
      if (mountedRef.current) {
        setLoading(false);
      }
    });
  }, [hydrate]);

  // Proactively refresh shortly before expiry so an active user never sees a
  // request fail. The 401 path in researchRuns.ts remains the safety net.
  useEffect(() => {
    if (!user) return;
    const leadMs = 60_000;
    const delay = Math.max(authClient.accessTokenExpiresAt() - Date.now() - leadMs, 5_000);
    const timer = window.setTimeout(() => void hydrate(), delay);
    return () => window.clearTimeout(timer);
  }, [user, hydrate]);

  const signIn = useCallback(
    async (email: string, password: string) => {
      await authClient.login(email, password);
      applyUser(await authClient.fetchMe());
    },
    [applyUser]
  );

  const signUp = useCallback(async (email: string, password: string) => {
    await authClient.register(email, password);
  }, []);

  const signOut = useCallback(async () => {
    await authClient.logout();
    applyUser(null);
  }, [applyUser]);

  const refreshUser = useCallback(async () => {
    await hydrate();
  }, [hydrate]);

  return (
    <AuthContext.Provider value={{ user, loading, signIn, signUp, signOut, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

// Convenience hook — import this instead of useContext(AuthContext) directly.
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  return useContext(AuthContext);
}
