import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MemoryRouter, Routes, Route, Navigate, useLocation, Outlet } from 'react-router-dom';

function LocationProbe() {
  return <span data-testid="pathname">{useLocation().pathname}</span>;
}

// Mirrors the /app subtree defined in App.tsx, without auth or data providers.
function AppRoutes() {
  return (
    <Routes>
      <Route path="/app" element={<><span>shell</span><LocationProbe /><Outlet /></>}>
        <Route index element={<Navigate to="research" replace />} />
        <Route path="research" element={<span>workspace</span>} />
        <Route path="research/:runId" element={<span>workspace</span>} />
        <Route path="settings" element={<Navigate to="profile" replace />} />
        <Route path="settings/:tab" element={<span>settings</span>} />
      </Route>
    </Routes>
  );
}

describe('app routes', () => {
  it('redirects /app to /app/research', async () => {
    render(<MemoryRouter initialEntries={['/app']}><AppRoutes /></MemoryRouter>);
    expect(await screen.findByTestId('pathname')).toHaveTextContent('/app/research');
  });

  it('redirects /app/settings to the profile tab', async () => {
    render(<MemoryRouter initialEntries={['/app/settings']}><AppRoutes /></MemoryRouter>);
    expect(await screen.findByTestId('pathname')).toHaveTextContent('/app/settings/profile');
  });
});
