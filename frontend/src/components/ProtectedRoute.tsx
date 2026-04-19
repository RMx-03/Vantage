import { Navigate } from 'react-router-dom';
import { ReactNode } from 'react';
import { useAuth } from '../context/AuthContext';

interface ProtectedRouteProps {
  children: ReactNode;
}

export default function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { session, loading } = useAuth();

  // Wait for the auth state to resolve before making a redirect decision.
  if (loading) return null;

  if (!session) {
    return <Navigate to="/auth" replace />;
  }

  return <>{children}</>;
}
