import { vi } from 'vitest';
import * as authClient from '../lib/authClient';
import type { AuthUser } from '../types/auth';

export const TEST_USER: AuthUser = {
  id: '00000000-0000-4000-8000-000000000001',
  email: 'operator@example.com',
  email_verified: true,
};

/** Put the auth client into a signed-in state for component tests. */
export function mockSignedIn(user: AuthUser = TEST_USER): void {
  authClient.setAccessToken('test-access-token', 900);
  vi.spyOn(authClient, 'refresh').mockResolvedValue(true);
  vi.spyOn(authClient, 'refreshSession').mockResolvedValue('refreshed');
  vi.spyOn(authClient, 'fetchMe').mockResolvedValue(user);
}

/** Put the auth client into a signed-out state. */
export function mockSignedOut(): void {
  authClient.setAccessToken(null);
  vi.spyOn(authClient, 'refresh').mockResolvedValue(false);
  vi.spyOn(authClient, 'refreshSession').mockResolvedValue('unauthenticated');
}
