import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';

import VerifyEmail from './VerifyEmail';
import * as authClient from '../lib/authClient';

const refreshUser = vi.fn().mockResolvedValue(undefined);

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ refreshUser, user: null, loading: false }),
}));

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/verify-email" element={<VerifyEmail />} />
      </Routes>
    </MemoryRouter>
  );

afterEach(() => vi.restoreAllMocks());

it('confirms the address when the token is valid', async () => {
  vi.spyOn(authClient, 'verifyEmail').mockResolvedValue(undefined);
  renderAt('/verify-email?token=good-token');
  expect(await screen.findByText(/address is confirmed/i)).toBeInTheDocument();
});

it('refreshes the session so the new verified state takes effect', async () => {
  // The `ev` claim is baked into the access token. Without a refresh the user
  // stays gated for up to 15 minutes after verifying.
  vi.spyOn(authClient, 'verifyEmail').mockResolvedValue(undefined);
  renderAt('/verify-email?token=good-token');
  await waitFor(() => expect(refreshUser).toHaveBeenCalled());
});

it('explains an expired link and offers a resend', async () => {
  vi.spyOn(authClient, 'verifyEmail').mockRejectedValue(
    Object.assign(new Error('This link is invalid or has expired.'), { code: 'AUTH_INVALID' })
  );
  renderAt('/verify-email?token=stale');
  expect(await screen.findByText(/invalid or has expired/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /send a new link/i })).toBeInTheDocument();
});

it('reports a missing token without calling the API', async () => {
  const spy = vi.spyOn(authClient, 'verifyEmail');
  renderAt('/verify-email');
  expect(await screen.findByText(/link is incomplete/i)).toBeInTheDocument();
  expect(spy).not.toHaveBeenCalled();
});
