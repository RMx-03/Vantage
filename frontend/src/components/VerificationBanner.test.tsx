import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';

import VerificationBanner from './VerificationBanner';
import * as authClient from '../lib/authClient';

let mockUser: { id: string; email: string; email_verified: boolean } | null = null;

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: mockUser }),
}));

afterEach(() => {
  vi.restoreAllMocks();
  mockUser = null;
});

it('does not render if no user is signed in', () => {
  mockUser = null;
  const { container } = render(<VerificationBanner />);
  expect(container.firstChild).toBeNull();
});

it('does not render if user is already verified', () => {
  mockUser = { id: 'u1', email: 'verified@example.com', email_verified: true };
  const { container } = render(<VerificationBanner />);
  expect(container.firstChild).toBeNull();
});

it('renders warning and resend button when user is unverified', () => {
  mockUser = { id: 'u1', email: 'unverified@example.com', email_verified: false };
  render(<VerificationBanner />);
  expect(screen.getByText(/confirm your email address/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /resend verification/i })).toBeInTheDocument();
});

it('calls resendVerification on button click and shows confirmation', async () => {
  const user = userEvent.setup();
  const spy = vi.spyOn(authClient, 'resendVerification').mockResolvedValue(undefined);
  mockUser = { id: 'u1', email: 'unverified@example.com', email_verified: false };
  render(<VerificationBanner />);

  await user.click(screen.getByRole('button', { name: /resend verification/i }));
  expect(spy).toHaveBeenCalledWith('unverified@example.com');
  expect(await screen.findByText(/verification email sent/i)).toBeInTheDocument();
});
