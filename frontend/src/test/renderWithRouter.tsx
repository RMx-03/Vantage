import type { ReactElement, ReactNode } from 'react';
import { render, type RenderResult } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

export function renderWithRouter(
  ui: ReactElement,
  { route = '/', path }: { route?: string; path?: string } = {}
): RenderResult {
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={[route]}>
      {path ? (
        <Routes>
          <Route path={path} element={children} />
        </Routes>
      ) : (
        children
      )}
    </MemoryRouter>
  );

  return render(ui, { wrapper: Wrapper });
}
