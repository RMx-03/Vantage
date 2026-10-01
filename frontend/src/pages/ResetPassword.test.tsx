import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';

import ResetPassword from './ResetPassword';
import * as authClient from '../lib/authClient';

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/reset-password" element={<ResetPassword />} />
      </Routes>
    </MemoryRouter>
  );

afterEach(() => vi.restoreAllMocks());

it('reports a missing token without calling the API', async () => {
  const spy = vi.spyOn(authClient, 'resetPassword');
  renderAt('/reset-password');
  expect(await screen.findByText(/link is incomplete/i)).toBeInTheDocument();
  expect(spy).not.toHaveBeenCalled();
});

it('renders the password field with policy hint', () => {
  renderAt('/reset-password?token=valid-token');
  expect(screen.getByLabelText(/new security credential/i)).toBeInTheDocument();
  expect(screen.getByText(/at least 12 characters/i)).toBeInTheDocument();
});

it('submits a new password and directs to sign in', async () => {
  const user = userEvent.setup();
  vi.spyOn(authClient, 'resetPassword').mockResolvedValue(undefined);
  renderAt('/reset-password?token=valid-token');

  await user.type(
    screen.getByLabelText(/new security credential/i),
    'brand new strong passphrase'
  );
  await user.click(screen.getByRole('button', { name: /update credential/i }));

  expect(await screen.findByText(/password has been changed/i)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /sign in/i })).toBeInTheDocument();
});

it('displays an error if the reset fails', async () => {
  const user = userEvent.setup();
  vi.spyOn(authClient, 'resetPassword').mockRejectedValue(
    new Error('This link is invalid or has expired.')
  );
  renderAt('/reset-password?token=bad-token');

  await user.type(
    screen.getByLabelText(/new security credential/i),
    'brand new strong passphrase'
  );
  await user.click(screen.getByRole('button', { name: /update credential/i }));

  expect(await screen.findByText(/invalid or has expired/i)).toBeInTheDocument();
});
