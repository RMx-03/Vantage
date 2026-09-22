import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import Auth from './Auth';

describe('authentication navigation', () => {
  it('returns to the landing page without submitting the form', async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/auth']}>
        <Routes>
          <Route path="/auth" element={<Auth />} />
          <Route path="/" element={<h1>Landing destination</h1>} />
        </Routes>
      </MemoryRouter>,
    );

    await user.click(screen.getByRole('link', { name: /return to overview/i }));

    expect(screen.getByRole('heading', { name: 'Landing destination' })).toBeInTheDocument();
  });
});
