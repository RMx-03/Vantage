import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { QueryProvider } from './providers/QueryProvider';
import ProtectedRoute from './components/ProtectedRoute';
import Landing from './pages/Landing';
import Terminal from './pages/Terminal';
import Auth from './pages/Auth';

import ResearchWorkspace from './features/research/ResearchWorkspace';
import UserSettingsPanel from './components/UserSettingsPanel';

export default function App() {
  return (
    <QueryProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/auth" element={<Auth />} />
            <Route
              path="/app"
              element={
                <ProtectedRoute>
                  <Terminal />
                </ProtectedRoute>
              }
            >
              <Route index element={<Navigate to="research" replace />} />
              <Route path="research" element={<ResearchWorkspace />} />
              <Route path="research/:runId" element={<ResearchWorkspace />} />
              <Route path="settings" element={<Navigate to="profile" replace />} />
              <Route path="settings/:tab" element={<UserSettingsPanel />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryProvider>
  );
}
