import { StrictMode } from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';

import VerifyEmail from './VerifyEmail';
import * as authClient from '../lib/authClient';

const refreshUser = vi.fn().mockResolvedValue(undefined);

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ refreshUser, user: null, loading: false }),
}));

afterEach(() => vi.restoreAllMocks());

it('verifies a single-use token once, even when effects run twice', async () => {
  // main.tsx renders under <StrictMode>, which mounts effects twice in
  // development. The token is single-use, exactly as on the server: the first
  // request spends it and any second request is rejected. Sending it twice
  // made the page show "invalid or has expired" to a user who had just been
  // verified.
  let spent = false;
  const verify = vi.spyOn(authClient, 'verifyEmail').mockImplementation(async () => {
    if (spent) {
      throw Object.assign(new Error('This link is invalid or has expired.'), {
        code: 'AUTH_INVALID',
      });
    }
    spent = true;
  });

  render(
    <StrictMode>
      <MemoryRouter initialEntries={['/verify-email?token=single-use-token']}>
        <Routes>
          <Route path="/verify-email" element={<VerifyEmail />} />
        </Routes>
      </MemoryRouter>
    </StrictMode>
  );

  expect(await screen.findByText(/address is confirmed/i)).toBeInTheDocument();
  expect(screen.queryByText(/invalid or has expired/i)).not.toBeInTheDocument();
  expect(verify).toHaveBeenCalledTimes(1);
});
