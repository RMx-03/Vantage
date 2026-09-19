import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';
import type { ReactNode } from 'react';
import type { Session, User } from '@supabase/supabase-js';
import { useQueryClient } from '@tanstack/react-query';
import { supabase } from '../lib/supabase';

interface AuthContextValue {
  session: Session | null;
  user: User | null;
  loading: boolean;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  session: null,
  user: null,
  loading: true,
  signOut: async () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const queryClient = useQueryClient();
  const ownerIdRef = useRef<string | null>(null);

  useEffect(() => {
    const applySession = (nextSession: Session | null) => {
      const nextOwnerId = nextSession?.user?.id ?? null;

      if (nextOwnerId !== ownerIdRef.current) {
        // The signed-in owner changed (sign-in, sign-out, account switch).
        // Drop every owner-scoped research query before the next owner can
        // render, so cached rows never outlive the session that fetched them.
        void queryClient.cancelQueries({ queryKey: ['research-runs'] });
        queryClient.removeQueries({ queryKey: ['research-runs'] });
        ownerIdRef.current = nextOwnerId;
      }

      setSession(nextSession);
      setUser(nextSession?.user ?? null);
    };

    // Hydrate from an existing persisted session on first mount.
    supabase.auth.getSession().then(({ data }) => {
      applySession(data.session);
      setLoading(false);
    });

    // Subscribe to future auth state changes (login, logout, token refresh).
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, newSession) => {
      applySession(newSession);
    });

    return () => subscription.unsubscribe();
  }, [queryClient]);

  const signOut = async () => {
    await supabase.auth.signOut();
  };

  return (
    <AuthContext.Provider value={{ session, user, loading, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

// Convenience hook — import this instead of useContext(AuthContext) directly.
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  return useContext(AuthContext);
}
