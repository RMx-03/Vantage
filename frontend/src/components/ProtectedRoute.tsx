import { Navigate } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useAuth } from '../context/AuthContext';

interface ProtectedRouteProps {
  children: ReactNode;
}

export default function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { user, loading } = useAuth();

  // Wait for the auth state to resolve before making a redirect decision.
  if (loading) return null;

  if (!user) {
    return <Navigate to="/auth" replace />;
  }

  return <>{children}</>;
}
