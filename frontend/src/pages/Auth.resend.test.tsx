import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Auth from './Auth';
import * as authClient from '../lib/authClient';

const signIn = vi.fn();
const signUp = vi.fn().mockResolvedValue(undefined);

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ signIn, signUp, user: null, loading: false }),
}));

const renderAuth = () =>
  render(
    <MemoryRouter initialEntries={['/auth']}>
      <Routes>
        <Route path="/auth" element={<Auth />} />
      </Routes>
    </MemoryRouter>
  );

afterEach(() => vi.restoreAllMocks());

describe('resending the verification email from the sign-in page', () => {
  // The only resend control used to live inside the app, after signing in.
  // A user whose first email never arrived was on this page, found no way to
  // ask again, and registered a second time instead.

  it('offers a resend right after registering', async () => {
    const resend = vi.spyOn(authClient, 'resendVerification').mockResolvedValue();
    renderAuth();

    await userEvent.click(screen.getAllByRole('button', { name: /create account/i })[0]);
    await userEvent.type(screen.getByLabelText(/email address/i), 'new@example.com');
    await userEvent.type(
      screen.getByLabelText(/security credential/i),
      'correct horse battery{enter}'
    );
    await waitFor(() => expect(signUp).toHaveBeenCalled());

    await userEvent.click(await screen.findByRole('button', { name: /resend verification email/i }));

    await waitFor(() => expect(resend).toHaveBeenCalledWith('new@example.com'));
    expect(screen.getByText(/a message is on its way/i)).toBeInTheDocument();
  });

  it('offers a resend on the sign-in tab for the address entered', async () => {
    const resend = vi.spyOn(authClient, 'resendVerification').mockResolvedValue();
    renderAuth();

    await userEvent.type(screen.getByLabelText(/email address/i), 'pending@example.com');
    await userEvent.click(screen.getByRole('button', { name: /resend verification email/i }));

    await waitFor(() => expect(resend).toHaveBeenCalledWith('pending@example.com'));
    expect(screen.getByText(/a message is on its way/i)).toBeInTheDocument();
  });

  it('asks for the address instead of calling the API when it is empty', async () => {
    const resend = vi.spyOn(authClient, 'resendVerification').mockResolvedValue();
    renderAuth();

    await userEvent.click(screen.getByRole('button', { name: /resend verification email/i }));

    expect(resend).not.toHaveBeenCalled();
    expect(screen.getByText(/enter your email address/i)).toBeInTheDocument();
  });

  it('gives the same answer whether or not the request succeeded', async () => {
    // Enumeration resistance: the backend answers alike for every address,
    // and the page must not reveal more than the backend does.
    vi.spyOn(authClient, 'resendVerification').mockRejectedValue(new Error('boom'));
    renderAuth();

    await userEvent.type(screen.getByLabelText(/email address/i), 'anyone@example.com');
    await userEvent.click(screen.getByRole('button', { name: /resend verification email/i }));

    expect(await screen.findByText(/a message is on its way/i)).toBeInTheDocument();
  });
});
