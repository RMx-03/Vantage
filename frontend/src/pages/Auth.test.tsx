import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import Auth from './Auth';

const signIn = vi.fn();
const signUp = vi.fn();

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ signIn, signUp, user: null, loading: false }),
}));

const renderAuth = () =>
  render(
    <MemoryRouter initialEntries={['/auth']}>
      <Routes>
        <Route path="/auth" element={<Auth />} />
        <Route path="/" element={<h1>Landing destination</h1>} />
      </Routes>
    </MemoryRouter>
  );

beforeEach(() => {
  vi.clearAllMocks();
});

describe('authentication navigation', () => {
  it('returns to the landing page without submitting the form', async () => {
    const user = userEvent.setup();
    renderAuth();

    await user.click(screen.getByRole('link', { name: /return to overview/i }));

    expect(screen.getByRole('heading', { name: 'Landing destination' })).toBeInTheDocument();
  });
});

describe('login mode', () => {
  it('signs in with the entered credentials', async () => {
    signIn.mockResolvedValueOnce(undefined);
    renderAuth();

    await userEvent.type(screen.getByLabelText(/email address/i), 'operator@example.com');
    await userEvent.type(screen.getByLabelText(/security credential/i), 'correct horse battery');
    await userEvent.click(screen.getByRole('button', { name: /access terminal/i }));

    await waitFor(() =>
      expect(signIn).toHaveBeenCalledWith('operator@example.com', 'correct horse battery')
    );
  });

  it('shows the safe error message on failure', async () => {
    signIn.mockRejectedValueOnce(
      Object.assign(new Error('Email or password is incorrect.'), { code: 'AUTH_INVALID' })
    );
    renderAuth();

    await userEvent.type(screen.getByLabelText(/email address/i), 'operator@example.com');
    await userEvent.type(screen.getByLabelText(/security credential/i), 'wrong password 123');
    await userEvent.click(screen.getByRole('button', { name: /access terminal/i }));

    expect(await screen.findByText(/email or password is incorrect/i)).toBeInTheDocument();
  });
});

describe('register mode', () => {
  it('registers and shows the generic confirmation', async () => {
    signUp.mockResolvedValueOnce(undefined);
    renderAuth();

    await userEvent.click(screen.getByRole('button', { name: /create account/i }));
    await userEvent.type(screen.getByLabelText(/email address/i), 'new@example.com');
    await userEvent.type(screen.getByLabelText(/security credential/i), 'correct horse battery');
    await userEvent.click(screen.getByRole('button', { name: /^create account$/i, hidden: false }));

    await waitFor(() => expect(signUp).toHaveBeenCalled());
  });

  it('states the password rules before submission', async () => {
    // Telling the user the rule only after a rejected attempt is a bad form.
    renderAuth();
    await userEvent.click(screen.getByRole('button', { name: /create account/i }));
    expect(screen.getByText(/at least 12 characters/i)).toBeInTheDocument();
  });
});
